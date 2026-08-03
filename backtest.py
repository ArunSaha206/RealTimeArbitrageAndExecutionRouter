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
import backtest_control_center as control
import metrics
import data_engine
import monte_carlo
import backtest_reporter as reporter
import portfolio  # <--- NEW: Import the centralized portfolio logic

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
# 2. SINGLE-TICKER BACKTEST ENGINE (WITH SMART CACHING)
# =====================================================================

RESULTS_CACHE_DIR = "results_cache"
if not os.path.exists(RESULTS_CACHE_DIR):
    os.makedirs(RESULTS_CACHE_DIR)

def backtest_single_symbol(symbol, start_date, end_date, strategy_config, strategy_name, regime_name):
    """Runs backtest logic on a single ticker for a specific historical window."""
    
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

    formatted_bars = data_engine.fetch_deep_history(
        symbol=symbol,
        resolution=strategy_config["bar_resolution"],
        start_date_str=start_date,
        end_date_str=end_date,
        provider=control.HISTORICAL_PROVIDER
    )

    # Fetch VIX data for this date window
    vix_map = data_engine.fetch_vix_series(start_date, end_date)

    # Inject VIX value into each bar so strategies can read it natively
    for bar in formatted_bars:
        bar_dt = bar['datetime']
        bar_date = bar_dt.date() if hasattr(bar_dt, 'date') else pd.to_datetime(bar_dt).date()
        # Assign matching VIX or look for the most recent available day's print
        bar['vix_open'] = vix_map.get(bar_date, 15.0) # Defaults to 15.0 baseline if missing

    if not formatted_bars:
        return None

    formatted_bars.sort(key=lambda x: x['datetime'])

    lookback_window = strategy_config["lookback"]
    if len(formatted_bars) <= lookback_window:
        return None

    # =================================================================
    # NEW: Initialize the centralized Portfolio object
    # =================================================================
    port = portfolio.Portfolio(control.STARTING_CASH_PER_TICKER)
    
    equity_curve = []
    timestamps = []

    rolling_buffer = formatted_bars[:lookback_window]
    simulation_bars = formatted_bars[lookback_window:]

    analyze_sig = inspect.signature(strategy_module.analyze)
    has_entry_price = 'entry_price' in analyze_sig.parameters
    # Some strategies (e.g. M5vixsupport) accept tunable divisor/exponent
    # params. These MUST be threaded through strategy_config (already passed
    # into this function as a plain argument, so it survives being pickled
    # to a ProcessPoolExecutor worker) rather than read off the strategy
    # module's own globals — mutating a module global in the parent process
    # (e.g. from an optimizer) does not propagate to separately-spawned
    # worker processes.
    has_vix_params = 'divisor' in analyze_sig.parameters and 'exponent' in analyze_sig.parameters

    for idx, bar in enumerate(simulation_bars, start=lookback_window):
        current_price = bar['close']
        current_dt = bar['datetime']
        rolling_buffer.append(bar)

        # Get current state from portfolio
        pos = port.get_position(symbol)
        position_qty = pos['qty']
        entry_price = pos['entry_price']

        # Log total equity
        equity_curve.append(port.get_equity(symbol, current_price))
        timestamps.append(current_dt)

        extra_kwargs = {}
        if has_vix_params:
            extra_kwargs['divisor'] = strategy_config.get('vix_divisor')
            extra_kwargs['exponent'] = strategy_config.get('vix_exponent')

        if has_entry_price:
            signal_result = strategy_module.analyze(
                rolling_buffer,
                lookback=strategy_config["lookback"],
                exit_lookback=strategy_config.get("exit_lookback", 10),
                current_position=position_qty,
                entry_price=entry_price,
                **extra_kwargs
            )
        else:
            signal_result = strategy_module.analyze(
                rolling_buffer,
                lookback=strategy_config["lookback"],
                exit_lookback=strategy_config.get("exit_lookback", 10),
                current_position=position_qty,
                **extra_kwargs
            )

        signal = signal_result.get("signal", "HOLD")

        if signal == "BUY" and position_qty == 0:
            mode = str(strategy_config["position_mode"]).upper().replace("_", "").strip()
            fixed_qty = strategy_config.get("fixed_share_qty", 0)
            
            # Delegate buy math to the class
            port.buy(symbol, current_price, current_dt, idx, strategy_module.__name__, mode, fixed_qty)

        elif signal == "SELL" and position_qty > 0:
            # Delegate sell math and logging to the class
            port.sell(symbol, current_price, current_dt, idx, strategy_module.__name__)


    # Force close any open positions at the end of the simulation
    if port.get_position(symbol)['qty'] > 0:
        final_price = simulation_bars[-1]['close']
        final_dt = simulation_bars[-1]['datetime']
        port.sell(symbol, final_price, final_dt, len(formatted_bars), strategy_module.__name__)

    # Extract final stats from the Portfolio object
    final_balance = port.cash
    total_net_pnl = final_balance - control.STARTING_CASH_PER_TICKER
    trades = port.trade_log

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
        "metrics": generated_metrics
    }
    
    try:
        with open(cache_filepath, 'wb') as f:
            pickle.dump(result_dict, f)
    except Exception:
        pass 
        
    return result_dict

# =====================================================================
# 3. MULTI-TICKER RUNNER & REGIME AGGREGATOR
# =====================================================================

def run_backtest(regime_evaluator=None, target_strategy_name=None):
    """
    target_strategy_name: if provided (a strategy module's __name__, e.g.
    M5vixsupport.__name__), restricts this run to ONLY that strategy —
    other entries in control.ACTIVE_STRATEGIES are skipped entirely rather
    than being backtested and discarded. This matters for two reasons:
      1. Performance: a caller like optimize_vix.py that's tuning one
         strategy shouldn't pay the cost of fully backtesting every other
         strategy in ACTIVE_STRATEGIES on every trial.
      2. Correctness: the return-value section below used to always grab
         multi_strategy_results[0], which only happened to be right because
         the tuned strategy was first in the list — reordering
         ACTIVE_STRATEGIES, or a strategy silently producing zero results,
         would have silently scored the WRONG strategy. Passing
         target_strategy_name makes the match explicit instead of
         positional.
    Leave it as None for the normal multi-strategy comparison CLI run
    (`python backtest.py`) — behavior there is unchanged.
    """
    strategies_to_test = getattr(control, "ACTIVE_STRATEGIES", [])
    if not strategies_to_test:
        if hasattr(control, "ACTIVE_STRATEGY"):
            strategies_to_test = [control.ACTIVE_STRATEGY]
        else:
            print("❌ ERROR: No active strategy found in backtest_control_center.py")
            return {"total_trades": 0, "win_rate": 0.0, "error": "no_active_strategy"}

    if target_strategy_name is not None:
        strategies_to_test = [s for s in strategies_to_test if s.__name__ == target_strategy_name]
        if not strategies_to_test:
            print(f"❌ ERROR: target_strategy_name='{target_strategy_name}' not found in ACTIVE_STRATEGIES.")
            return {"total_trades": 0, "win_rate": 0.0, "error": "target_strategy_not_found"}

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
        
        reporter.print_strategy_header(
            current_strategy.__name__, 
            bar_resolution, 
            strategy_config['lookback'], 
            strategy_config['position_mode']
        )

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
                    tax_label = "Tax Owed"
                else:
                    tax_impact = abs(gross_pnl) * tax_rate
                    tax_label = "Tax Credit (Loss Write-off)"
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

            # =====================================================================
            # 🛑 EARLY STOPPING HOOK (Zero-Coupling)
            # =====================================================================
            if regime_evaluator:
                regime_evaluator(regime_name, total_trade_count, aggregate_pnl)
            # =====================================================================

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

            reporter.print_regime_summary(
                current_strategy.__name__, regime_name, len(target_universe), len(all_results), gross_pnl, gross_pnl_pct, 
                enable_taxes, tax_label, tax_impact, aggregate_pnl, aggregate_pnl_pct, 
                avg_buy_hold_pct, spy_metrics, total_trade_count, win_rate, wins_count, 
                losses_count, profit_factor, gross_profit, gross_loss, 
                portfolio_max_dd_dollars, portfolio_max_dd_pct, portfolio_sharpe
            )

        # =====================================================================
        # MASTER GLOBAL SUMMARY ACROSS ALL REGIMES FOR THIS STRATEGY
        # =====================================================================
        if global_summary["total_symbols_evaluated"] > 0:
            reporter.print_global_summary(
                current_strategy.__name__, 
                global_summary, 
                enable_taxes, 
                len(regimes)
            )
            
            if mc_tasks:
                print(f"🎲 Running Vectorized Monte Carlo Simulations for {len(mc_tasks)} Regimes on {current_strategy.__name__}...")
                for task in mc_tasks:
                    mc_result = monte_carlo.run_monte_carlo_simulation(
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
    # 💥 ULTIMATE STRATEGY COMPARISON MATRIX & DATA EXPORTS 💥
    # =====================================================================
    export_summary_rows = reporter.generate_comparison_matrix(multi_strategy_results)

    reporter.save_and_export_data(
        enable_taxes=enable_taxes,
        tax_rate=tax_rate,
        starting_cash=control.STARTING_CASH_PER_TICKER,
        multi_strategy_results=multi_strategy_results,
        export_summary_rows=export_summary_rows,
        master_trade_log=master_trade_log,
        cache_dir=RESULTS_CACHE_DIR
    )

    # =====================================================================
    # 🔁 RETURN VALUE FOR PROGRAMMATIC CALLERS (e.g. optimize_vix.py)
    # =====================================================================
    if multi_strategy_results:
        if target_strategy_name is not None:
            matches = [r for r in multi_strategy_results if r["name"] == target_strategy_name]
            if not matches:
                return {"total_trades": 0, "win_rate": 0.0, "error": "target_strategy_produced_no_results"}
            primary_summary = matches[0]["global_summary"]
        else:
            if len(multi_strategy_results) > 1:
                print(
                    f"⚠️ WARNING: run_backtest() was called without target_strategy_name but "
                    f"{len(multi_strategy_results)} strategies were tested. Returning results for "
                    f"'{multi_strategy_results[0]['name']}' (first in ACTIVE_STRATEGIES) — pass "
                    f"target_strategy_name explicitly if this isn't the one you meant."
                )
            primary_summary = multi_strategy_results[0]["global_summary"]

        total_trades = primary_summary.get("total_trades", 0)
        total_wins = primary_summary.get("total_wins", 0)
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0

        return {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "global_summary": primary_summary,
            "multi_strategy_results": multi_strategy_results,
            "comparison_matrix": export_summary_rows,
        }

    return {"total_trades": 0, "win_rate": 0.0, "error": "no_results_evaluated"}

if __name__ == "__main__":
    run_backtest()