import concurrent.futures
import hashlib
import importlib
import inspect
import json
import os
import pickle
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

# Load API environment variables
load_dotenv() 

import backtest_control_center as control
import metrics
import data_engine
import monte_carlo
import backtest_reporter as reporter
import portfolio  

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
# 2. SINGLE-TICKER BACKTEST ENGINE (RESTORED SPEED)
# =====================================================================
RESULTS_CACHE_DIR = "results_cache"
if not os.path.exists(RESULTS_CACHE_DIR):
    os.makedirs(RESULTS_CACHE_DIR)

def backtest_single_symbol(symbol, start_date, end_date, strategy_config, strategy_name, regime_name, current_bps):
    strategy_module = importlib.import_module(strategy_name)
    try:
        source_code = inspect.getsource(strategy_module)
    except Exception:
        source_code = "unknown_source"
        
    config_str = json.dumps(strategy_config, sort_keys=True)
    # Cache is now securely partitioned by BPS rate
    unique_run_string = f"{symbol}_{regime_name}_{start_date}_{end_date}_{strategy_name}_{config_str}_{source_code}_{control.STARTING_CASH_PER_TICKER}_{current_bps}"
    
    cache_hash = hashlib.sha256(unique_run_string.encode('utf-8')).hexdigest()
    cache_filepath = os.path.join(RESULTS_CACHE_DIR, f"{cache_hash}.pkl")

    if os.path.exists(cache_filepath):
        try:
            with open(cache_filepath, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass

    formatted_bars = data_engine.fetch_deep_history(
        symbol=symbol, resolution=strategy_config["bar_resolution"],
        start_date_str=start_date, end_date_str=end_date, provider=control.HISTORICAL_PROVIDER
    )
    vix_map = data_engine.fetch_vix_series(start_date, end_date)

    if not formatted_bars: return None

    for bar in formatted_bars:
        bar_dt = bar['datetime']
        bar_date = bar_dt.date() if hasattr(bar_dt, 'date') else pd.to_datetime(bar_dt).date()
        bar['vix_open'] = vix_map.get(bar_date, 15.0) 

    formatted_bars.sort(key=lambda x: x['datetime'])

    lookback_window = strategy_config["lookback"]
    if len(formatted_bars) <= lookback_window: return None

    port = portfolio.Portfolio(control.STARTING_CASH_PER_TICKER)
    equity_curve, timestamps = [], []
    rolling_buffer = formatted_bars[:lookback_window]
    simulation_bars = formatted_bars[lookback_window:]

    analyze_sig = inspect.signature(strategy_module.analyze)
    has_entry_price = 'entry_price' in analyze_sig.parameters

    for idx, bar in enumerate(simulation_bars, start=lookback_window):
        current_price = bar['close']
        current_dt = bar['datetime']
        rolling_buffer.append(bar)

        pos = port.get_position(symbol)
        position_qty, entry_price = pos['qty'], pos['entry_price']

        equity_curve.append(port.get_equity(symbol, current_price))
        timestamps.append(current_dt)

        reserved_keys = ["bar_resolution", "lookback", "exit_lookback", "position_mode", "fixed_share_qty"]
        extra_kwargs = {k: v for k, v in strategy_config.items() if k not in reserved_keys}

        if has_entry_price:
            signal_result = strategy_module.analyze(
                rolling_buffer, lookback=strategy_config["lookback"],
                exit_lookback=strategy_config.get("exit_lookback", 10),
                current_position=position_qty, entry_price=entry_price, **extra_kwargs
            )
        else:
            signal_result = strategy_module.analyze(
                rolling_buffer, lookback=strategy_config["lookback"],
                exit_lookback=strategy_config.get("exit_lookback", 10),
                current_position=position_qty, **extra_kwargs
            )

        signal = signal_result.get("signal", "HOLD")

        if signal == "BUY" and position_qty == 0:
            mode = str(strategy_config["position_mode"]).upper().replace("_", "").strip()
            fixed_qty = strategy_config.get("fixed_share_qty", 0)
            slippage_pct = current_bps / 10000.0
            execution_price = current_price * (1.0 + slippage_pct)
            port.buy(symbol, execution_price, current_dt, idx, strategy_module.__name__, mode, fixed_qty)

        elif signal == "SELL" and position_qty > 0:
            slippage_pct = current_bps / 10000.0
            execution_price = current_price * (1.0 - slippage_pct)
            port.sell(symbol, execution_price, current_dt, idx, strategy_module.__name__)

    if port.get_position(symbol)['qty'] > 0:
        final_price = simulation_bars[-1]['close']
        final_dt = simulation_bars[-1]['datetime']
        slippage_pct = current_bps / 10000.0
        execution_price = final_price * (1.0 - slippage_pct)
        port.sell(symbol, execution_price, final_dt, len(formatted_bars), strategy_module.__name__)

    final_balance = port.cash
    total_net_pnl = final_balance - control.STARTING_CASH_PER_TICKER
    trades = port.trade_log
    
    start_stock_price = formatted_bars[lookback_window]['close']
    end_stock_price = formatted_bars[-1]['close']
    stock_pnl_pct = ((end_stock_price - start_stock_price) / start_stock_price) * 100

    periods_per_year = get_periods_per_year(strategy_config["bar_resolution"])
    generated_metrics = metrics.generate_all_metrics(
        equity_curve=equity_curve, timestamps=timestamps, trades=trades,
        periods_per_year=periods_per_year, starting_cash=control.STARTING_CASH_PER_TICKER, benchmark_symbol=symbol
    )

    result_dict = {
        "symbol": symbol, "regime_name": regime_name, "strategy_used": strategy_module.__name__,
        "final_balance": final_balance, "net_pnl": total_net_pnl, "buy_hold_pct": stock_pnl_pct, 
        "trades": trades, "equity_curve": equity_curve, "timestamps": timestamps,
        "bars_count": len(formatted_bars), "metrics": generated_metrics
    }
    
    try:
        with open(cache_filepath, 'wb') as f:
            pickle.dump(result_dict, f)
    except Exception:
        pass 
        
    return result_dict

# =====================================================================
# 2.5 OPTUNA ORCHESTRATOR HOOKS (ROBUSTNESS UPDATED)
# =====================================================================
REGIME_DATA_CACHE = {}

def preload_regime_data(regime_name, config):
    """
    Fetches and caches the combined universe data for the orchestrator.
    Minimizes redundant Databento queries during optimization.
    """
    if regime_name in REGIME_DATA_CACHE:
        return REGIME_DATA_CACHE[regime_name]
        
    unique_tickers = set()
    for universe_name, ticker_list in config.get("universes", {}).items():
        unique_tickers.update(ticker_list)
        
    unique_tickers = sorted(list(unique_tickers))
    if not unique_tickers:
        return pd.DataFrame()
        
    all_data = []
    strategy_module = control.ACTIVE_STRATEGIES[0]
    resolution = strategy_module.get_params().get("bar_resolution", "M15")
    
    for sym in unique_tickers:
        bars = data_engine.fetch_deep_history(
            symbol=sym, resolution=resolution,
            start_date_str=config['start'], end_date_str=config['end'],
            provider=control.HISTORICAL_PROVIDER
        )
        if bars:
            df = pd.DataFrame(bars)
            df['symbol'] = sym
            all_data.append(df)
            
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)
        REGIME_DATA_CACHE[regime_name] = combined_df
        return combined_df
        
    return pd.DataFrame()

def simulate_strategy_on_universe(df_universe, **kwargs) -> dict:
    """
    Simulation engine for Optuna optimization.
    Returns raw statistical metrics for the fitness engine to evaluate.
    """
    import inspect
    import portfolio
    import monte_carlo
    import backtest_control_center as control

    if df_universe.empty: 
        return {"pf": 0.0, "p5": -999.0, "trades": 0}
    
    strategy_module = control.ACTIVE_STRATEGIES[0]
    base_config = dict(strategy_module.get_params())
    
    for k, v in kwargs.items():
        base_config[k] = v

    analyze_sig = inspect.signature(strategy_module.analyze)
    has_entry_price = 'entry_price' in analyze_sig.parameters
    reserved_keys = ["bar_resolution", "lookback", "exit_lookback", "position_mode", "fixed_share_qty"]
    extra_kwargs = {k: v for k, v in base_config.items() if k not in reserved_keys}

    all_trades = []
    total_trades_count = 0
    symbols = df_universe['symbol'].unique()
    
    for sym in symbols:
        sym_df = df_universe[df_universe['symbol'] == sym].copy()
        if sym_df.empty: continue
        
        formatted_bars = sym_df.to_dict('records')
        lookback_window = base_config.get("lookback", 35)
        
        if len(formatted_bars) <= lookback_window: continue
        
        port = portfolio.Portfolio(control.STARTING_CASH_PER_TICKER)
        rolling_buffer = formatted_bars[:lookback_window]
        simulation_bars = formatted_bars[lookback_window:]
        
        for idx, bar in enumerate(simulation_bars, start=lookback_window):
            current_price = bar['close']
            rolling_buffer.append(bar)
            
            pos = port.get_position(sym)
            
            if has_entry_price:
                signal_result = strategy_module.analyze(
                    rolling_buffer, lookback=base_config["lookback"],
                    exit_lookback=base_config.get("exit_lookback", 10),
                    current_position=pos['qty'], entry_price=pos['entry_price'],
                    **extra_kwargs
                )
            else:
                signal_result = strategy_module.analyze(
                    rolling_buffer, lookback=base_config["lookback"],
                    exit_lookback=base_config.get("exit_lookback", 10),
                    current_position=pos['qty'], **extra_kwargs
                )
            
            signal = signal_result.get("signal", "HOLD")
            
            if signal == "BUY" and pos['qty'] == 0:
                mode = str(base_config.get("position_mode", "ALL_IN")).upper().replace("_", "").strip()
                fixed_qty = base_config.get("fixed_share_qty", 0)
                success, _ = port.buy(sym, current_price, bar['datetime'], idx, strategy_module.__name__, mode, fixed_qty)
                if success: total_trades_count += 1
            elif signal == "SELL" and pos['qty'] > 0:
                port.sell(sym, current_price, bar['datetime'], idx, strategy_module.__name__)
                
        all_trades.extend(port.trade_log)
            
    if not all_trades or total_trades_count == 0: 
        return {"pf": 0.0, "p5": -999.0, "trades": 0}
    
    winning_trades = [t for t in all_trades if t["pnl_dollars"] > 0]
    losing_trades = [t for t in all_trades if t["pnl_dollars"] < 0]
    gross_profit = sum(t["pnl_dollars"] for t in winning_trades)
    gross_loss = abs(sum(t["pnl_dollars"] for t in losing_trades))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (100.0 if gross_profit > 0 else 0.0)

    starting_capital = len(symbols) * control.STARTING_CASH_PER_TICKER
    mc_result = monte_carlo.run_monte_carlo_simulation(
        all_trades=all_trades, starting_capital=starting_capital,
        avg_buy_hold_pct=0.0, num_simulations=1000, title="Optuna Fast MC"
    )
    
    if not mc_result:
        return {"pf": 0.0, "p5": -999.0, "trades": total_trades_count}
        
    p5_final = mc_result["percentiles"]["p5"]
    p5_return_pct = ((p5_final - starting_capital) / starting_capital) * 100
    
    return {"pf": profit_factor, "p5": p5_return_pct, "trades": total_trades_count}

# =====================================================================
# 3. MULTI-TICKER RUNNER & REGIME AGGREGATOR
# =====================================================================
def run_backtest(regime_evaluator=None, target_strategy_name=None):
    strategies_to_test = getattr(control, "ACTIVE_STRATEGIES", [])
    if not strategies_to_test:
        return {"total_trades": 0, "win_rate": 0.0, "error": "no_active_strategy"}

    if target_strategy_name is not None:
        strategies_to_test = [s for s in strategies_to_test if s.__name__ == target_strategy_name]

    enable_taxes = getattr(control, "ENABLE_TAXES", False)
    tax_rate = getattr(control, "ORDINARY_INCOME_TAX_RATE", 0.24) if enable_taxes else 0.0
    slippage_rates = getattr(control, "SLIPPAGE_RATES_BPS", [2.0])
    is_final_test = getattr(control, "DATASET_PHASE", "") == "FINAL_TESTING"

    print(f"🚀 Initializing Fast Multi-BPS Backtest Engine (PHASE: {getattr(control, 'DATASET_PHASE', 'UNKNOWN')})")
    print(f"⚙️ Cash/Ticker: ${control.STARTING_CASH_PER_TICKER:,.2f} | Provider: {control.HISTORICAL_PROVIDER}")
    if is_final_test: print(f"🔒 FINAL TESTING MODE DETECTED: Monte Carlo strictly disabled.")

    regimes = control.REGIME_WINDOWS
    multi_strategy_results = []
    master_trade_log = []

    # =====================================================================
    # TOP-LEVEL SWEEP: Keeps the workers isolated and fast
    # =====================================================================
    for current_bps in slippage_rates:
        for current_strategy in strategies_to_test:
            
            control.SLIPPAGE_BPS = current_bps 
            run_identifier = f"{current_strategy.__name__} ({current_bps} BPS)"
            
            strategy_config = current_strategy.get_params()
            bar_resolution = strategy_config["bar_resolution"]
            reporter.print_strategy_header(run_identifier, bar_resolution, strategy_config['lookback'], strategy_config['position_mode'])

            global_summary = {
                "total_symbols_evaluated": 0, "total_initial_capital": 0.0, "total_ending_capital_pre_tax": 0.0,
                "total_ending_capital_post_tax": 0.0, "total_tax_impact": 0.0, "total_trades": 0, "total_wins": 0,
                "total_losses": 0, "total_gross_profit": 0.0, "total_gross_loss": 0.0,
                "bh_returns": [], "regime_summaries": [] 
            }
            
            mc_tasks = []
            all_regime_daily_equities = []

            for regime_name, config in regimes.items():
                reporter.print_regime_header(regime_name, config['start'], config['end'])
                all_results, all_trades = [], []

                #target_universe = config.get(control.ACTIVE_ASSET_TYPE.lower(), [])

                universe_logic = getattr(control, "ACTIVE_UNIVERSE_LOGIC", "core_stratified")
                target_universe = config.get("universes", {}).get(universe_logic, [])
                if not target_universe:
                    target_universe = config.get(control.ACTIVE_ASSET_TYPE.lower(), [])

                if not target_universe: continue

                data_engine.fetch_vix_series(config['start'], config['end'])

                futures = []
                with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
                    for symbol in target_universe:
                        future = executor.submit(
                            backtest_single_symbol, symbol, config['start'], config['end'], 
                            strategy_config, current_strategy.__name__, regime_name, current_bps
                        )
                        futures.append(future)
                        
                    for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc=f"Analyzing {len(target_universe)} Tickers"):
                        res = future.result()
                        if res:
                            all_results.append(res)
                            all_trades.extend(res["trades"])

                if not all_results: continue
                master_trade_log.extend(all_trades)

                sorted_all_trades = sorted(all_trades, key=lambda x: x["entry_time"])
                total_initial_capital = len(all_results) * control.STARTING_CASH_PER_TICKER
                total_ending_capital_pre_tax = sum(r["final_balance"] for r in all_results)
                
                gross_pnl = total_ending_capital_pre_tax - total_initial_capital
                gross_pnl_pct = (gross_pnl / total_initial_capital) * 100 if total_initial_capital > 0 else 0.0

                if enable_taxes:
                    tax_impact = -(gross_pnl * tax_rate) if gross_pnl > 0 else abs(gross_pnl) * tax_rate
                    tax_label = "Tax Owed" if gross_pnl > 0 else "Tax Credit"
                else:
                    tax_impact, tax_label = 0.0, "Taxes"

                net_ending_capital = total_ending_capital_pre_tax + tax_impact
                aggregate_pnl = net_ending_capital - total_initial_capital
                aggregate_pnl_pct = (aggregate_pnl / total_initial_capital) * 100 if total_initial_capital > 0 else 0.0

                avg_buy_hold_pct = sum(r["buy_hold_pct"] for r in all_results) / len(all_results)
                
                daily_equity_series = []
                for r in all_results:
                    temp_df = pd.DataFrame({"datetime": r["timestamps"], "equity": r["equity_curve"]})
                    temp_df['date'] = pd.to_datetime(temp_df['datetime']).dt.date
                    daily_close_eq = temp_df.groupby('date')['equity'].last()
                    daily_equity_series.append(daily_close_eq)

                portfolio_daily_df = pd.concat(daily_equity_series, axis=1).ffill().fillna(control.STARTING_CASH_PER_TICKER)
                daily_portfolio_equity = portfolio_daily_df.sum(axis=1)
                all_regime_daily_equities.append(daily_portfolio_equity)
                
                portfolio_daily_returns = daily_portfolio_equity.pct_change().dropna()
                spy_metrics = metrics.get_beta_and_alpha(portfolio_daily_returns, benchmark_symbol="SPY", risk_free_rate_annual=control.RISK_FREE_RATE)
                portfolio_max_dd_dollars, portfolio_max_dd_pct = metrics.calculate_max_drawdown(daily_portfolio_equity.values)
                portfolio_sharpe = metrics.calculate_sharpe_ratio(daily_portfolio_equity.values, periods_per_year=250)
                portfolio_sortino = metrics.calculate_sortino_ratio(daily_portfolio_equity.values, periods_per_year=250)

                winning_trades = [t for t in sorted_all_trades if t["pnl_dollars"] > 0]
                losing_trades = [t for t in sorted_all_trades if t["pnl_dollars"] < 0]
                total_trade_count, wins_count, losses_count = len(sorted_all_trades), len(winning_trades), len(losing_trades)
                win_rate = (wins_count / total_trade_count * 100) if total_trade_count > 0 else 0.0
                gross_profit = sum(t["pnl_dollars"] for t in winning_trades)
                gross_loss = abs(sum(t["pnl_dollars"] for t in losing_trades))
                profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)

                if regime_evaluator: regime_evaluator(regime_name, total_trade_count, aggregate_pnl)

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
                    "name": regime_name.upper(), "pre_tax_pnl": gross_pnl, "pre_tax_pnl_pct": gross_pnl_pct,
                    "post_tax_pnl": aggregate_pnl, "post_tax_pnl_pct": aggregate_pnl_pct, "tax_impact": tax_impact,
                    "bh_pct": avg_buy_hold_pct, "trades": total_trade_count, "win_rate": win_rate,
                    "pf": profit_factor, "sharpe": portfolio_sharpe, "sortino": portfolio_sortino, "max_dd_pct": portfolio_max_dd_pct,
                    "beta": spy_metrics['beta'] if spy_metrics else None, "alpha": spy_metrics['alpha_pct'] if spy_metrics else None,
                    "monte_carlo": None, 
                })

                if total_trade_count > 0:
                    mc_tasks.append({
                        "title": f"MC STRESS TEST: {regime_name.upper()} ({run_identifier})",
                        "regime_name": regime_name, "all_trades": sorted_all_trades, "starting_capital": total_initial_capital,
                        "avg_buy_hold_pct": avg_buy_hold_pct, "spy_return_pct": spy_metrics["bench_return_pct"] if spy_metrics else None
                    })

                reporter.print_regime_summary(
                    run_identifier, regime_name, len(target_universe), len(all_results), gross_pnl, gross_pnl_pct, 
                    enable_taxes, tax_label, tax_impact, aggregate_pnl, aggregate_pnl_pct, 
                    avg_buy_hold_pct, spy_metrics, total_trade_count, win_rate, wins_count, 
                    losses_count, profit_factor, gross_profit, gross_loss, 
                    portfolio_max_dd_dollars, portfolio_max_dd_pct, portfolio_sharpe
                )

            # True Global Stitching Math
            if all_regime_daily_equities:
                global_daily_equity = pd.concat(all_regime_daily_equities).sort_index()
                global_daily_equity = global_daily_equity[~global_daily_equity.index.duplicated(keep='last')]
                global_max_dd_dollars, global_max_dd_pct = metrics.calculate_max_drawdown(global_daily_equity.values)
                global_sharpe = metrics.calculate_sharpe_ratio(global_daily_equity.values, periods_per_year=250)
                global_sortino = metrics.calculate_sortino_ratio(global_daily_equity.values, periods_per_year=250)
                global_summary["true_global_sharpe"] = global_sharpe
                global_summary["true_global_sortino"] = global_sortino
                global_summary["true_global_max_dd_pct"] = global_max_dd_pct
            else:
                global_summary["true_global_sharpe"], global_summary["true_global_max_dd_pct"] = 0.0, 0.0
                global_summary["true_global_sortino"] = 0.0

            if not is_final_test and mc_tasks:
                reporter.print_monte_carlo_header(run_identifier, len(regimes))
                for task in mc_tasks:
                    mc_result = monte_carlo.run_monte_carlo_simulation(
                        all_trades=task["all_trades"], starting_capital=task["starting_capital"],
                        avg_buy_hold_pct=task["avg_buy_hold_pct"], spy_return_pct=task["spy_return_pct"],
                        num_simulations=1000, title=task["title"]
                    )
                    for rs in global_summary["regime_summaries"]:
                        if rs["name"] == task["regime_name"].upper():
                            rs["monte_carlo"] = mc_result
                            break
            
            mc_ruins, mc_p5s, mc_p95s = [], [], []
            for rs in global_summary["regime_summaries"]:
                if rs.get("monte_carlo"):
                    mc = rs["monte_carlo"]
                    cap = mc["starting_capital"]
                    mc_ruins.append(mc["risk_of_ruin"])
                    mc_p5s.append(((mc["percentiles"]["p5"] - cap) / cap) * 100)
                    mc_p95s.append(((mc["percentiles"]["p95"] - cap) / cap) * 100)
            
            global_summary["worst_mc_ruin"] = max(mc_ruins) if mc_ruins else 0.0
            global_summary["worst_mc_p5_pct"] = min(mc_p5s) if mc_p5s else 0.0
            global_summary["avg_mc_p95_pct"] = (sum(mc_p95s) / len(mc_p95s)) if mc_p95s else 0.0

            if global_summary["total_symbols_evaluated"] > 0:
                reporter.print_global_summary(run_identifier, global_summary, enable_taxes, len(regimes))
            
            multi_strategy_results.append({
                "name": run_identifier,
                "global_summary": global_summary
            })

    export_summary_rows = reporter.generate_comparison_matrix(multi_strategy_results)
    reporter.save_and_export_data(
        enable_taxes=enable_taxes, tax_rate=tax_rate, starting_cash=control.STARTING_CASH_PER_TICKER,
        multi_strategy_results=multi_strategy_results, export_summary_rows=export_summary_rows,
        master_trade_log=master_trade_log, cache_dir=RESULTS_CACHE_DIR
    )

    if multi_strategy_results:
        return {
            "total_trades": multi_strategy_results[0]["global_summary"].get("total_trades", 0),
            "win_rate": (multi_strategy_results[0]["global_summary"].get("total_wins", 0) / max(1, multi_strategy_results[0]["global_summary"].get("total_trades", 1))) * 100,
            "global_summary": multi_strategy_results[0]["global_summary"],
            "multi_strategy_results": multi_strategy_results,
            "comparison_matrix": export_summary_rows,
        }

    return {"total_trades": 0, "win_rate": 0.0, "error": "no_results_evaluated"}

if __name__ == "__main__":
    run_backtest()