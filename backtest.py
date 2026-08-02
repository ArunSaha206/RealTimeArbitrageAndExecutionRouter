import concurrent.futures
import hashlib
import importlib
import inspect
import json
import math
import os
import pickle
from datetime import datetime, timedelta, timezone

import databento as db
import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from tqdm import tqdm

# Control center owns: which strategy, which tickers, bar resolution, etc.
import BacktestControlCenter as control
import metrics

# Load API environment variables
load_dotenv()

# =====================================================================
# 1. HELPER & METRIC FUNCTIONS
# =====================================================================

BARS_PER_YEAR_BY_RESOLUTION = {
    "M1": 390 * 250,       
    "M5": 78 * 250,        
    "M15": 26 * 250,       
    "M30": 13 * 250,       
    "H1": 7 * 250,         
    "D1": 250,             
}

def get_periods_per_year(resolution_str, default=19500):
    return BARS_PER_YEAR_BY_RESOLUTION.get(str(resolution_str).upper(), default)

# =====================================================================
# 2. DEEP HISTORY DATA FETCHER (DATABENTO)
# =====================================================================

CACHE_DIR = "data_cache"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def fetch_deep_history(symbol, resolution, start_date_str, end_date_str, provider="DATABENTO"):
    formatted_bars = []
    
    if provider == "DATABENTO":
        cache_file = os.path.join(CACHE_DIR, f"{symbol}_{start_date_str}_{end_date_str}_1m.parquet")
        
        if os.path.exists(cache_file):
            df = pd.read_parquet(cache_file)
        else:
            db_key = os.environ.get("DATABENTO_API_KEY")
            if not db_key:
                return []
                
            try:
                client = db.Historical(db_key)
                
                raw_data = client.timeseries.get_range(
                    dataset="XNAS.ITCH",
                    schema="ohlcv-1m",
                    symbols=symbol,
                    start=start_date_str,
                    end=end_date_str,
                )
                
                df = raw_data.to_df()
                
                if df.empty:
                    return []
                    
                df.to_parquet(cache_file)
                
            except Exception as e:
                return []

        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')

        resample_map = {
            "M1": "1min",
            "M5": "5min",
            "M15": "15min",
            "M30": "30min",
            "H1": "1h",
            "D1": "1D"
        }
        pd_resolution = resample_map.get(resolution.upper(), "1min")
        
        resampled_df = df.resample(pd_resolution).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        for dt, row in resampled_df.iterrows():
            formatted_bars.append({
                "datetime": dt.to_pydatetime(),
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "volume": float(row['volume'])
            })
            
    return formatted_bars


# =====================================================================
# 3. SINGLE-TICKER BACKTEST ENGINE (WITH SMART CACHING)
# =====================================================================

RESULTS_CACHE_DIR = "results_cache"
if not os.path.exists(RESULTS_CACHE_DIR):
    os.makedirs(RESULTS_CACHE_DIR)

def backtest_single_symbol(symbol, start_date, end_date, strategy_config, strategy_name, regime_name):
    """Runs backtest logic on a single ticker for a specific historical window.

    regime_name is the REGIME_WINDOWS key this run belongs to (e.g.
    "covid_crash_2020"). It's stamped onto the result so downstream
    consumers (like Dashboard.py) never accidentally aggregate equity
    curves across non-overlapping date windows.
    """
    
    strategy_module = importlib.import_module(strategy_name)

    try:
        source_code = inspect.getsource(strategy_module)
    except Exception:
        source_code = "unknown_source"
        
    config_str = json.dumps(strategy_config, sort_keys=True)
    unique_run_string = f"{symbol}_{start_date}_{end_date}_{strategy_name}_{config_str}_{source_code}_{control.STARTING_CASH_PER_TICKER}"
    
    cache_hash = hashlib.sha256(unique_run_string.encode('utf-8')).hexdigest()
    cache_filepath = os.path.join(RESULTS_CACHE_DIR, f"{cache_hash}.pkl")

    if os.path.exists(cache_filepath):
        try:
            with open(cache_filepath, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass

    formatted_bars = fetch_deep_history(
        symbol=symbol,
        resolution=strategy_config["bar_resolution"],
        start_date_str=start_date,
        end_date_str=end_date,
        provider=control.HISTORICAL_PROVIDER
    )

    if not formatted_bars:
        return None

    formatted_bars.sort(key=lambda x: x['datetime'])

    lookback_window = strategy_config["lookback"]
    if len(formatted_bars) <= lookback_window:
        return None

    cash = control.STARTING_CASH_PER_TICKER
    position_qty = 0
    entry_price = 0.0
    entry_time = None
    entry_bar_index = 0

    trades = []
    equity_curve = []
    timestamps = []

    rolling_buffer = formatted_bars[:lookback_window]
    simulation_bars = formatted_bars[lookback_window:]

    analyze_sig = inspect.signature(strategy_module.analyze)
    has_entry_price = 'entry_price' in analyze_sig.parameters

    for idx, bar in enumerate(simulation_bars, start=lookback_window):
        current_price = bar['close']
        current_dt = bar['datetime']
        rolling_buffer.append(bar)

        portfolio_value = cash + (position_qty * current_price)
        equity_curve.append(portfolio_value)
        timestamps.append(current_dt)

        if has_entry_price:
            signal_result = strategy_module.analyze(
                rolling_buffer,
                lookback=strategy_config["lookback"],
                exit_lookback=strategy_config.get("exit_lookback", 10),
                current_position=position_qty,
                entry_price=entry_price
            )
        else:
            signal_result = strategy_module.analyze(
                rolling_buffer,
                lookback=strategy_config["lookback"],
                exit_lookback=strategy_config.get("exit_lookback", 10),
                current_position=position_qty
            )

        signal = signal_result.get("signal", "HOLD")

        if signal == "BUY" and position_qty == 0:
            mode = str(strategy_config["position_mode"]).upper().replace("_", "").strip()
            if mode == "ALLIN":
                shares_to_buy = int(cash // current_price) if current_price > 0 else 0
            else:
                shares_to_buy = strategy_config["fixed_share_qty"]

            if shares_to_buy > 0 and (shares_to_buy * current_price) <= cash:
                position_qty = shares_to_buy
                cost = position_qty * current_price
                cash -= cost
                entry_price = current_price
                entry_time = current_dt
                entry_bar_index = idx

        elif signal == "SELL" and position_qty > 0:
            sale_revenue = position_qty * current_price
            cash += sale_revenue

            pnl_dollars = (current_price - entry_price) * position_qty
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            bars_held = idx - entry_bar_index

            trades.append({
                "symbol": symbol,
                "strategy_used": strategy_module.__name__,
                "entry_time": entry_time,
                "exit_time": current_dt,
                "entry_price": entry_price,
                "exit_price": current_price,
                "quantity": position_qty,
                "pnl_dollars": pnl_dollars,
                "pnl_pct": pnl_pct,
                "bars_held": bars_held
            })

            position_qty = 0
            entry_price = 0.0

    if position_qty > 0:
        final_price = simulation_bars[-1]['close']
        final_dt = simulation_bars[-1]['datetime']
        pnl_dollars = (final_price - entry_price) * position_qty
        pnl_pct = ((final_price - entry_price) / entry_price) * 100
        cash += position_qty * final_price

        trades.append({
            "symbol": symbol,
            "strategy_used": strategy_module.__name__,
            "entry_time": entry_time,
            "exit_time": final_dt,
            "entry_price": entry_price,
            "exit_price": final_price,
            "quantity": position_qty,
            "pnl_dollars": pnl_dollars,
            "pnl_pct": pnl_pct,
            "bars_held": len(formatted_bars) - entry_bar_index
        })

    final_balance = cash
    total_net_pnl = final_balance - control.STARTING_CASH_PER_TICKER

    # Keep B&H pct for the multi-ticker aggregator
    start_stock_price = formatted_bars[lookback_window]['close']
    end_stock_price = formatted_bars[-1]['close']
    stock_pnl_pct = ((end_stock_price - start_stock_price) / start_stock_price) * 100

    # =====================================================================
    # NEW: DELEGATED METRICS ENGINE
    # =====================================================================
    periods_per_year = get_periods_per_year(strategy_config["bar_resolution"])
    
    generated_metrics = metrics.generate_all_metrics(
        equity_curve=equity_curve,
        timestamps=timestamps,
        trades=trades,
        periods_per_year=periods_per_year,
        starting_cash=control.STARTING_CASH_PER_TICKER,
        benchmark_symbol=symbol
    )

    result_dict = {
        "symbol": symbol,
        "regime_name": regime_name,
        "strategy_used": strategy_module.__name__,
        "final_balance": final_balance,
        "net_pnl": total_net_pnl,
        "buy_hold_pct": stock_pnl_pct, 
        "trades": trades,
        "equity_curve": equity_curve,
        "timestamps": timestamps,
        "bars_count": len(formatted_bars),
        "metrics": generated_metrics  # Attach the dynamic dictionary here
    }
    
    try:
        with open(cache_filepath, 'wb') as f:
            pickle.dump(result_dict, f)
    except Exception:
        pass 
        
    return result_dict


# =====================================================================
# 4. MONTE CARLO SIMULATION (Fast Vectorized Implementation)
# =====================================================================

def run_monte_carlo_simulation(all_trades, starting_capital, avg_buy_hold_pct=0.0, spy_return_pct=None, num_simulations=1000, ruin_threshold_pct=20.0, title="ADVANCED MONTE CARLO STRESS TEST"):
    """
    Runs the vectorized Monte Carlo stress test AND returns its computed
    stats as a dict, so callers (like the dashboard report) can persist
    the results instead of them only living in the terminal print-out.
    """
    if not all_trades:
        print("⚠️ No trades available for Monte Carlo simulation.")
        return None

    trade_pnl_dollars = np.array([t["pnl_dollars"] for t in all_trades])
    num_trades = len(trade_pnl_dollars)

    simulated_pnl = np.random.choice(trade_pnl_dollars, size=(num_simulations, num_trades), replace=True)
    equity_curves = starting_capital + np.cumsum(simulated_pnl, axis=1)
    
    final_balances = equity_curves[:, -1]
    running_max = np.maximum.accumulate(equity_curves, axis=1)
    running_max = np.maximum(starting_capital, running_max)
    
    drawdowns = (running_max - equity_curves) / running_max * 100
    max_drawdowns_pct = np.max(drawdowns, axis=1)
    
    hit_ruin = max_drawdowns_pct >= ruin_threshold_pct
    ruin_count = np.sum(hit_ruin)
    
    sim_return_pct = ((final_balances - starting_capital) / starting_capital) * 100
    
    beat_bh_count = np.sum(sim_return_pct > avg_buy_hold_pct)
    beat_spy_count = np.sum(sim_return_pct > spy_return_pct) if spy_return_pct is not None else None
    
    is_loss = simulated_pnl < 0
    max_streaks = np.zeros(num_simulations, dtype=int)
    for i in range(num_simulations):
        streak = 0
        max_s = 0
        for val in is_loss[i]:
            if val:
                streak += 1
                if streak > max_s:
                    max_s = streak
            else:
                streak = 0
        max_streaks[i] = max_s

    pnl_array = final_balances - starting_capital
    prob_profitable = (np.sum(pnl_array > 0) / num_simulations) * 100
    prob_beat_bh = (beat_bh_count / num_simulations) * 100
    prob_beat_spy = (beat_spy_count / num_simulations) * 100 if beat_spy_count is not None else None
    risk_of_ruin = (ruin_count / num_simulations) * 100

    p5_final = np.percentile(final_balances, 5)
    p25_final = np.percentile(final_balances, 25)
    p50_final = np.percentile(final_balances, 50)
    p75_final = np.percentile(final_balances, 75)
    p95_final = np.percentile(final_balances, 95)
    p50_dd = np.percentile(max_drawdowns_pct, 50)
    p95_dd = np.percentile(max_drawdowns_pct, 95)
    p50_streak = int(np.percentile(max_streaks, 50))
    p95_streak = int(np.percentile(max_streaks, 95))

    print("\n" + "=" * 115)
    print(f"                            {title} ({num_simulations:,} Iterations)           ")
    print("=" * 115)
    print(f" 🎯 Overall Win Probability:     {prob_profitable:.1f}% of outcomes ended in net profit")
    print(f" 📈 Prob. of Beating Tickers B&H: {prob_beat_bh:.1f}% (vs Avg B&H: {avg_buy_hold_pct:+.2f}%)")
    if prob_beat_spy is not None:
        print(f" 🏆 Prob. of Beating SPY:         {prob_beat_spy:.1f}% (vs SPY: {spy_return_pct:+.2f}%)")
    else:
        print(f" 🏆 Prob. of Beating SPY:         N/A (SPY data unavailable)")
    print(f" ⚠️ Risk of Ruin (≥{ruin_threshold_pct:.0f}% Drawdown): {risk_of_ruin:.1f}% chance of hitting account distress")
    print("-" * 115)
    print(" 📊 EXPECTED RETURN DISTRIBUTION (Pre-Tax basis for probabilistic modeling):")
    print(f"    • 95th Percentile (Optimistic): ${p95_final:,.2f}  (+{(p95_final-starting_capital)/starting_capital*100:+.2f}%)")
    print(f"    • 75th Percentile:              ${p75_final:,.2f}  (+{(p75_final-starting_capital)/starting_capital*100:+.2f}%)")
    print(f"    • 50th Percentile (Median):     ${p50_final:,.2f}  (+{(p50_final-starting_capital)/starting_capital*100:+.2f}%)")
    print(f"    • 25th Percentile:              ${p25_final:,.2f}  (+{(p25_final-starting_capital)/starting_capital*100:+.2f}%)")
    print(f"    • 5th Percentile  (Pessimistic): ${p5_final:,.2f}  (+{(p5_final-starting_capital)/starting_capital*100:+.2f}%)")
    print("-" * 115)
    print(" 📉 RISK & STREAK METRICS:")
    print(f"    • Median Drawdown vs. 95% Worst Case:   -{p50_dd:.2f}%  |  95th %ile: -{p95_dd:.2f}%")
    print(f"    • Median Loss Streak vs. 95% Worst Case: {p50_streak} losses in a row  |  95th %ile: {p95_streak} in a row")
    print("=" * 115 + "\n")

    return {
        "title": title,
        "num_simulations": num_simulations,
        "prob_profitable": float(prob_profitable),
        "prob_beat_bh": float(prob_beat_bh),
        "avg_buy_hold_pct": float(avg_buy_hold_pct),
        "prob_beat_spy": float(prob_beat_spy) if prob_beat_spy is not None else None,
        "spy_return_pct": float(spy_return_pct) if spy_return_pct is not None else None,
        "risk_of_ruin": float(risk_of_ruin),
        "ruin_threshold_pct": float(ruin_threshold_pct),
        "starting_capital": float(starting_capital),
        "percentiles": {
            "p5": float(p5_final), "p25": float(p25_final), "p50": float(p50_final),
            "p75": float(p75_final), "p95": float(p95_final),
        },
        "drawdown_percentiles": {"p50": float(p50_dd), "p95": float(p95_dd)},
        "streak_percentiles": {"p50": p50_streak, "p95": p95_streak},
    }

# =====================================================================
# 5. MULTI-TICKER RUNNER & REGIME AGGREGATOR
# =====================================================================

def run_backtest():
    
    strategies_to_test = getattr(control, "ACTIVE_STRATEGIES", [])
    if not strategies_to_test:
        if hasattr(control, "ACTIVE_STRATEGY"):
            strategies_to_test = [control.ACTIVE_STRATEGY]
        else:
            print("❌ ERROR: No active strategy found in BacktestControlCenter.py")
            return

    enable_taxes = getattr(control, "ENABLE_TAXES", False)
    if enable_taxes:
        tax_rate = getattr(control, "ORDINARY_INCOME_TAX_RATE", 0.24) 
    else:
        tax_rate = 0.0

    print(f"🚀 Initializing Multi-Strategy Backtest Engine (SMART CACHING ENABLED)...")
    print(f"⚙️ Cash/Ticker: ${control.STARTING_CASH_PER_TICKER:,.2f} | Provider: {control.HISTORICAL_PROVIDER}")
    print(f"💻 Cores Available: {os.cpu_count()}")
    
    if enable_taxes:
        print(f"🏛️ Tax System (MTM): ENABLED ({int(tax_rate * 100)}% Federal Ordinary Income)")
    else:
        print(f"🏛️ Tax System (MTM): DISABLED")
        
    print(f"📋 Active Asset Class: {control.ACTIVE_ASSET_TYPE}\n")

    regimes = control.REGIME_WINDOWS
    if not regimes:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=control.DAYS_TO_TEST)
        regimes = {
            "recent_days": {
                "start": start_date.strftime("%Y-%m-%d"),
                "end": end_date.strftime("%Y-%m-%d"),
                control.ACTIVE_ASSET_TYPE.lower(): control.ACTIVE_UNIVERSE
            }
        }

    multi_strategy_results = []
    master_trade_log = []

    # =====================================================================
    # MASTER STRATEGY LOOP
    # =====================================================================
    for current_strategy in strategies_to_test:
        
        strategy_config = current_strategy.get_params()
        bar_resolution = strategy_config["bar_resolution"]
        
        print("\n" + "█" * 175)
        print(f" 🚀 NOW RUNNING STRATEGY: {current_strategy.__name__} | Res={bar_resolution} | Lookback={strategy_config['lookback']} | Sizing={strategy_config['position_mode']} ".center(175))
        print("█" * 175 + "\n")

        global_summary = {
            "total_symbols_evaluated": 0,
            "total_initial_capital": 0.0,
            "total_ending_capital_pre_tax": 0.0,
            "total_ending_capital_post_tax": 0.0,
            "total_tax_impact": 0.0,
            "total_trades": 0,
            "total_wins": 0,
            "total_losses": 0,
            "total_gross_profit": 0.0,
            "total_gross_loss": 0.0,
            "bh_returns": [],
            "regime_summaries": [] 
        }
        
        mc_tasks = []

        for regime_name, config in regimes.items():
            print("=" * 115)
            print(f" 📅 EXECUTING REGIME: {regime_name.upper()} ({config['start']} to {config['end']})")
            print("=" * 115)

            all_results = []
            all_trades = []
            
            target_universe = config.get(control.ACTIVE_ASSET_TYPE.lower(), [])

            if not target_universe:
                print(f"⚠️ No symbols found for '{control.ACTIVE_ASSET_TYPE}' in regime '{regime_name}'. Skipping.\n")
                continue

            futures = []
            with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
                for symbol in target_universe:
                    future = executor.submit(
                        backtest_single_symbol, 
                        symbol, 
                        config['start'], 
                        config['end'], 
                        strategy_config, 
                        current_strategy.__name__,
                        regime_name
                    )
                    futures.append(future)
                
                for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc=f"Analyzing {len(target_universe)} Tickers"):
                    res = future.result()
                    if res:
                        all_results.append(res)
                        all_trades.extend(res["trades"])

            if not all_results:
                print(f"❌ No valid ticker data evaluated for {regime_name.upper()}. Moving to next regime.\n")
                continue
            
            master_trade_log.extend(all_trades)

            # =====================================================================
            # REGIME DASHBOARD & SUMMARY (WITH TAX LOGIC AND TIME ALIGNMENT)
            # =====================================================================
            sorted_all_trades = sorted(all_trades, key=lambda x: x["entry_time"])
            total_initial_capital = len(all_results) * control.STARTING_CASH_PER_TICKER
            total_ending_capital_pre_tax = sum(r["final_balance"] for r in all_results)
            
            gross_pnl = total_ending_capital_pre_tax - total_initial_capital
            
            if total_initial_capital > 0:
                gross_pnl_pct = (gross_pnl / total_initial_capital) * 100 
            else:
                gross_pnl_pct = 0.0

            if enable_taxes:
                if gross_pnl > 0:
                    tax_impact = -(gross_pnl * tax_rate)
                    tax_label = "Tax Owed (Federal Ordinary Income)"
                else:
                    tax_impact = abs(gross_pnl) * tax_rate
                    tax_label = "Tax Credit (Business Loss Write-off)"
            else:
                tax_impact = 0.0
                tax_label = "Taxes"

            net_ending_capital = total_ending_capital_pre_tax + tax_impact
            aggregate_pnl = net_ending_capital - total_initial_capital
            
            if total_initial_capital > 0:
                aggregate_pnl_pct = (aggregate_pnl / total_initial_capital) * 100 
            else:
                aggregate_pnl_pct = 0.0

            avg_buy_hold_pct = sum(r["buy_hold_pct"] for r in all_results) / len(all_results)
            
            daily_equity_series = []
            for r in all_results:
                temp_df = pd.DataFrame({
                    "datetime": r["timestamps"], 
                    "equity": r["equity_curve"]
                })
                temp_df['date'] = pd.to_datetime(temp_df['datetime']).dt.date
                daily_close_eq = temp_df.groupby('date')['equity'].last()
                daily_equity_series.append(daily_close_eq)

            portfolio_daily_df = pd.concat(daily_equity_series, axis=1)
            portfolio_daily_df = portfolio_daily_df.ffill().fillna(control.STARTING_CASH_PER_TICKER)
            
            daily_portfolio_equity = portfolio_daily_df.sum(axis=1)
            portfolio_daily_returns = daily_portfolio_equity.pct_change().dropna()

            spy_metrics = metrics.get_beta_and_alpha(
                portfolio_daily_returns,
                benchmark_symbol="SPY",
                risk_free_rate_annual=control.RISK_FREE_RATE
            )

            portfolio_max_dd_dollars, portfolio_max_dd_pct = metrics.calculate_max_drawdown(daily_portfolio_equity.values)
            portfolio_sharpe = metrics.calculate_sharpe_ratio(daily_portfolio_equity.values, periods_per_year=250)

            winning_trades = [t for t in sorted_all_trades if t["pnl_dollars"] > 0]
            losing_trades = [t for t in sorted_all_trades if t["pnl_dollars"] < 0]

            total_trade_count = len(sorted_all_trades)
            wins_count = len(winning_trades)
            losses_count = len(losing_trades)
            
            if total_trade_count > 0:
                win_rate = (wins_count / total_trade_count * 100) 
            else:
                win_rate = 0.0

            gross_profit = sum(t["pnl_dollars"] for t in winning_trades)
            gross_loss = abs(sum(t["pnl_dollars"] for t in losing_trades))
            
            if gross_loss > 0:
                profit_factor = (gross_profit / gross_loss)
            elif gross_profit > 0:
                profit_factor = float('inf')
            else:
                profit_factor = 0.0

            global_summary["total_symbols_evaluated"] += len(all_results)
            global_summary["total_initial_capital"] += total_initial_capital
            global_summary["total_ending_capital_pre_tax"] += total_ending_capital_pre_tax
            global_summary["total_ending_capital_post_tax"] += net_ending_capital
            global_summary["total_tax_impact"] += tax_impact
            global_summary["total_trades"] += total_trade_count
            global_summary["total_wins"] += wins_count
            global_summary["total_losses"] += losses_count
            global_summary["total_gross_profit"] += gross_profit
            global_summary["total_gross_loss"] += gross_loss
            global_summary["bh_returns"].append(avg_buy_hold_pct)

            global_summary["regime_summaries"].append({
                "name": regime_name.upper(),
                "pre_tax_pnl": gross_pnl,
                "pre_tax_pnl_pct": gross_pnl_pct,
                "post_tax_pnl": aggregate_pnl,
                "post_tax_pnl_pct": aggregate_pnl_pct,
                "tax_impact": tax_impact,
                "bh_pct": avg_buy_hold_pct,
                "trades": total_trade_count,
                "win_rate": win_rate,
                "pf": profit_factor,
                "sharpe": portfolio_sharpe,
                "max_dd_pct": portfolio_max_dd_pct,
                "beta": spy_metrics['beta'] if spy_metrics else None,
                "alpha": spy_metrics['alpha_pct'] if spy_metrics else None,
                "monte_carlo": None,  # filled in below once MC has run
            })

            if total_trade_count > 0:
                mc_tasks.append({
                    "title": f"MC STRESS TEST: {regime_name.upper()} ({current_strategy.__name__})",
                    "regime_name": regime_name,
                    "all_trades": sorted_all_trades,
                    "starting_capital": total_initial_capital,
                    "avg_buy_hold_pct": avg_buy_hold_pct,
                    "spy_return_pct": spy_metrics["bench_return_pct"] if spy_metrics else None
                })

            print("\n" + "=" * 115)
            print(f"                     REGIME PORTFOLIO SUMMARY: {regime_name.upper()}                                 ")
            print("=" * 115)
            print(f" Total Symbols Evaluated:     {len(all_results)} / {len(target_universe)}")
            print(f" Pre-Tax Gross P&L:           ${gross_pnl:+,.2f} ({gross_pnl_pct:+.2f}%)")
            
            if enable_taxes:
                print(f" {tax_label}: {('+$' if tax_impact > 0 else '-$')}{abs(tax_impact):,.2f}")
                
            print(f" Post-Tax Net P&L:            ${aggregate_pnl:+,.2f} ({aggregate_pnl_pct:+.2f}%)")
            print(f" Benchmark Average Return:    {avg_buy_hold_pct:+.2f}%")
            print("-" * 115)
            
            if spy_metrics:
                print(f" Broad Market Beta (β vs SPY): {spy_metrics['beta']:.2f}")
                print(f" Jensen's Alpha (α vs SPY):    {spy_metrics['alpha_pct']:+.2f}%")
                print(f" SPY Benchmark Return:        {spy_metrics['bench_return_pct']:+.2f}%")
            else:
                print(f" Broad Market Beta (β vs SPY): N/A (Insufficient daily benchmark alignment)")
                
            print("-" * 115)
            print(f" Total Trades Executed:       {total_trade_count}")
            
            if total_trade_count < 100:
                print(f" ⚠️ WARNING: Low sample size ({total_trade_count} trades). Sharpe may be statistically unreliable.")
                
            print(f" Win Rate:                    {win_rate:.1f}% ({wins_count} W / {losses_count} L)")
            print(f" Profit Factor:               {profit_factor:.2f} (Gross Profit: ${gross_profit:,.2f} / Gross Loss: ${gross_loss:,.2f})")
            print(f" Max Portfolio Drawdown:      -${portfolio_max_dd_dollars:,.2f} (-{portfolio_max_dd_pct:.2f}%)")
            print(f" Portfolio Sharpe Ratio:      {portfolio_sharpe:.2f}")
            print("=" * 115 + "\n")

        # =====================================================================
        # MASTER GLOBAL SUMMARY ACROSS ALL REGIMES FOR THIS STRATEGY
        # =====================================================================
        if global_summary["total_symbols_evaluated"] > 0:
            g_pnl_pre_tax = global_summary["total_ending_capital_pre_tax"] - global_summary["total_initial_capital"]
            
            if global_summary["total_initial_capital"] > 0:
                g_pnl_pct_pre_tax = (g_pnl_pre_tax / global_summary["total_initial_capital"]) * 100 
            else:
                g_pnl_pct_pre_tax = 0.0
            
            g_pnl_post_tax = global_summary["total_ending_capital_post_tax"] - global_summary["total_initial_capital"]
            
            if global_summary["total_initial_capital"] > 0:
                g_pnl_pct_post_tax = (g_pnl_post_tax / global_summary["total_initial_capital"]) * 100 
            else:
                g_pnl_pct_post_tax = 0.0

            if global_summary["total_trades"] > 0:
                global_win_rate = (global_summary["total_wins"] / global_summary["total_trades"] * 100) 
            else:
                global_win_rate = 0.0
                
            if global_summary["total_gross_loss"] > 0:
                global_pf = (global_summary["total_gross_profit"] / global_summary["total_gross_loss"]) 
            else:
                global_pf = 0.0
                
            if global_summary["bh_returns"]:
                avg_global_bh = np.mean(global_summary["bh_returns"]) 
            else:
                avg_global_bh = 0.0

            print("\n" + "★" * 175)
            print(f"{'🌟 MULTI-REGIME SUMMARY FOR: ' + current_strategy.__name__ + ' (PRE-TAX VS. POST-TAX) 🌟':^175}")
            print("★" * 175)

            print(f"{'REGIME':<18} | {'PRE-TAX P&L ($)':>15} | {'PRE-TAX (%)':>11} | {'TAX IMPACT ($)':>14} | {'POST-TAX P&L ($)':>16} | {'POST-TAX (%)':>12} | {'B&H (%)':>8} | {'TRADES':>6} | {'WIN %':>6} | {'PF':>5} | {'SHARPE':>6} | {'MAX DD':>8} | {'BETA':>5} | {'ALPHA (%)':>9}")
            print("-" * 175)
            for rs in global_summary["regime_summaries"]:
                r_name = rs['name'][:18]
                
                if rs['beta'] is not None:
                    beta_str = f"{rs['beta']:>5.2f}"
                else:
                    beta_str = " N/A "
                    
                if rs['alpha'] is not None:
                    alpha_str = f"{rs['alpha']:>8.2f}%"
                else:
                    alpha_str = "  N/A   "
                    
                t_imp = rs['tax_impact']
                if enable_taxes:
                    tax_str = f"{'+$' if t_imp > 0 else '-$'}{abs(t_imp):>9,.2f}"
                else:
                    tax_str = "$0.00"
                
                print(f"{r_name:<18} | ${rs['pre_tax_pnl']:>14,.2f} | {rs['pre_tax_pnl_pct']:>10.2f}% | {tax_str:>14} | ${rs['post_tax_pnl']:>15,.2f} | {rs['post_tax_pnl_pct']:>11.2f}% | {rs['bh_pct']:>7.2f}% | {rs['trades']:>6} | {rs['win_rate']:>5.1f}% | {rs['pf']:>4.2f} | {rs['sharpe']:>6.2f} | -{rs['max_dd_pct']:>6.2f}% | {beta_str} | {alpha_str}")
            print("-" * 175)

            print(f" Total Regimes Tested:        {len(regimes)}")
            print(f" Total Symbols Evaluated:     {global_summary['total_symbols_evaluated']}")
            print(f" Total Cumulative Capital:    ${global_summary['total_initial_capital']:,.2f}")
            print("-" * 175)
            print(f" Global Gross P&L (PRE-TAX):  ${g_pnl_pre_tax:+,.2f} ({g_pnl_pct_pre_tax:+.2f}%)")
            
            if enable_taxes:
                net_tax = global_summary['total_tax_impact']
                print(f" Global Net Tax Impact:       {('+$' if net_tax > 0 else '-$')}{abs(net_tax):,.2f} {( '(Net Credit)' if net_tax > 0 else '(Net Paid)' )}")
                
            print(f" Global Net P&L (POST-TAX):   ${g_pnl_post_tax:+,.2f} ({g_pnl_pct_post_tax:+.2f}%)")
            print(f" Global Average B&H Return:   {avg_global_bh:+.2f}%")
            print("-" * 175)
            print(f" Total Trades Executed:       {global_summary['total_trades']}")
            print(f" Global Win Rate:             {global_win_rate:.1f}% ({global_summary['total_wins']} W / {global_summary['total_losses']} L)")
            print(f" Global Profit Factor:        {global_pf:.2f}")
            print("★" * 175 + "\n")

            if mc_tasks:
                print(f"🎲 Running Vectorized Monte Carlo Simulations for {len(mc_tasks)} Regimes on {current_strategy.__name__}...")
                for task in mc_tasks:
                    mc_result = run_monte_carlo_simulation(
                        all_trades=task["all_trades"],
                        starting_capital=task["starting_capital"],
                        avg_buy_hold_pct=task["avg_buy_hold_pct"],
                        spy_return_pct=task["spy_return_pct"],
                        num_simulations=1000,
                        title=task["title"]
                    )
                    # Attach the MC result back onto its matching regime summary
                    # so the full report has it alongside the rest of that regime's stats.
                    for rs in global_summary["regime_summaries"]:
                        if rs["name"] == task["regime_name"].upper():
                            rs["monte_carlo"] = mc_result
                            break
        
        multi_strategy_results.append({
            "name": current_strategy.__name__,
            "global_summary": global_summary
        })

    # =====================================================================
    # 💥 ULTIMATE STRATEGY COMPARISON MATRIX (WITH DYNAMIC REGIME WIN %) 💥
    # =====================================================================
    export_summary_rows = []

    if len(multi_strategy_results) > 1:
        all_regime_names = []
        for res in multi_strategy_results:
            for rs in res["global_summary"]["regime_summaries"]:
                if rs["name"] not in all_regime_names:
                    all_regime_names.append(rs["name"])

        regime_headers_str = " | ".join([f"{(r[:10] + ' W%'):>14}" for r in all_regime_names])

        print("\n" + "🏆" * 95)
        print(f"{'ULTIMATE STRATEGY COMPARISON MATRIX':^190}")
        print("🏆" * 95)
        print(f"{'STRATEGY':<18} | {'PRE-TAX ($)':>12} | {'PRE-TAX (%)':>11} | {'POST-TAX ($)':>13} | {'POST-TAX (%)':>12} | {'OVERALL W%':>10} | {regime_headers_str} | {'PF':>5} | {'AVG SHARPE':>10} | {'AVG MAX DD':>10} | {'AVG BETA':>8}")
        print("-" * 190)

        for res in multi_strategy_results:
            name = res["name"][:18]
            g_sum = res["global_summary"]
            
            if g_sum["total_symbols_evaluated"] == 0:
                continue
                
            if g_sum["regime_summaries"]:
                avg_sharpe = np.mean([r["sharpe"] for r in g_sum["regime_summaries"]])
                avg_dd = np.mean([r["max_dd_pct"] for r in g_sum["regime_summaries"]])
                
                valid_betas = [r["beta"] for r in g_sum["regime_summaries"] if r["beta"] is not None]
                avg_beta = np.mean(valid_betas) if valid_betas else 0.0
            else:
                avg_sharpe, avg_dd, avg_beta = 0.0, 0.0, 0.0
            
            g_pnl_pre = g_sum["total_ending_capital_pre_tax"] - g_sum["total_initial_capital"]
            g_pnl_post = g_sum["total_ending_capital_post_tax"] - g_sum["total_initial_capital"]
            
            g_pnl_pct_pre = (g_pnl_pre / g_sum["total_initial_capital"]) * 100 if g_sum["total_initial_capital"] > 0 else 0.0
            g_pnl_pct_post = (g_pnl_post / g_sum["total_initial_capital"]) * 100 if g_sum["total_initial_capital"] > 0 else 0.0
            
            overall_win_rate = (g_sum["total_wins"] / g_sum["total_trades"] * 100) if g_sum["total_trades"] > 0 else 0.0
            pf = (g_sum["total_gross_profit"] / g_sum["total_gross_loss"]) if g_sum["total_gross_loss"] > 0 else 0.0
            
            regime_win_map = {rs["name"]: rs["win_rate"] for rs in g_sum["regime_summaries"]}
            
            regime_win_cells = []
            row_export_dict = {
                "Strategy": res["name"],
                "Pre-Tax PnL ($)": round(g_pnl_pre, 2),
                "Pre-Tax PnL (%)": round(g_pnl_pct_pre, 2),
                "Post-Tax PnL ($)": round(g_pnl_post, 2),
                "Post-Tax PnL (%)": round(g_pnl_pct_post, 2),
                "Overall Win Rate (%)": round(overall_win_rate, 2),
            }

            for r_name in all_regime_names:
                if r_name in regime_win_map:
                    w_val = regime_win_map[r_name]
                    regime_win_cells.append(f"{w_val:>13.1f}%")
                    row_export_dict[f"{r_name} Win %"] = round(w_val, 2)
                else:
                    regime_win_cells.append("          N/A ")
                    row_export_dict[f"{r_name} Win %"] = "N/A"

            row_export_dict.update({
                "Profit Factor": round(pf, 2),
                "Avg Sharpe": round(avg_sharpe, 2),
                "Avg Max Drawdown (%)": round(avg_dd, 2),
                "Avg Beta": round(avg_beta, 2),
                "Total Trades Executed": g_sum["total_trades"]
            })
            export_summary_rows.append(row_export_dict)

            regime_win_row_str = " | ".join(regime_win_cells)

            print(f"{name:<18} | ${g_pnl_pre:>11,.2f} | {g_pnl_pct_pre:>10.2f}% | ${g_pnl_post:>12,.2f} | {g_pnl_pct_post:>11.2f}% | {overall_win_rate:>9.1f}% | {regime_win_row_str} | {pf:>4.2f} | {avg_sharpe:>10.2f} | -{avg_dd:>9.2f}% | {avg_beta:>8.2f}")
            
        print("-" * 190 + "\n")

    # =====================================================================
    # 📝 SAVE CONSOLIDATED REPORT FOR THE DASHBOARD
    # =====================================================================
    # Unlike results_cache/<hash>.pkl (per-symbol, content-addressed, never
    # overwritten), this is a "latest run" report at a fixed path — it's
    # meant to always reflect the most recent full run, so Dashboard.py can
    # show the regime tables, tax breakdown, and Monte Carlo stress tests
    # that previously only existed as terminal print() output.
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "enable_taxes": enable_taxes,
        "tax_rate": tax_rate,
        "starting_cash_per_ticker": control.STARTING_CASH_PER_TICKER,
        "strategies": multi_strategy_results,
        "comparison_matrix": export_summary_rows,
    }
    report_path = os.path.join(RESULTS_CACHE_DIR, "summary_report.pkl")
    try:
        with open(report_path, "wb") as f:
            pickle.dump(report, f)
        print(f"📝 Full report saved for dashboard access: {report_path}")
    except Exception as e:
        print(f"⚠️ Failed to save summary report: {e}")

    # =====================================================================
    # 💾 DATA EXPORT LOGIC
    # =====================================================================
    if master_trade_log:
        print(f"💾 EXPORTING DATA TO CSV...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = f"backtest_results_{timestamp}"
        os.makedirs(out_dir, exist_ok=True)

        if len(multi_strategy_results) > 1 and export_summary_rows:
            summary_df = pd.DataFrame(export_summary_rows)
            summary_path = os.path.join(out_dir, "strategy_comparison.csv")
            summary_df.to_csv(summary_path, index=False)

        trades_df = pd.DataFrame(master_trade_log)
        trades_path = os.path.join(out_dir, "all_trades_log.csv")
        
        for col in ['entry_time', 'exit_time']:
            if col in trades_df.columns:
                trades_df[col] = trades_df[col].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if isinstance(x, datetime) else x)
        
        trades_df.to_csv(trades_path, index=False)
        
        print(f"✅ Success! Your backtest results and raw trade logs have been saved to the folder: {out_dir}/")

if __name__ == "__main__":
    run_backtest()