import os
import math
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from webull.core.client import ApiClient
from webull.data.data_client import DataClient
from webull.data.common.category import Category
from webull.data.common.timespan import Timespan

# Control center owns: which strategy, which tickers, bar resolution,
# starting cash, days to test, risk-free rate.
import BacktestControlCenter as control

# =====================================================================
# 1. BACKTEST CONFIGURATION
# =====================================================================
# Everything below is sourced from BacktestControlCenter.py. Nothing
# strategy-specific (bar resolution, sizing mode, fixed share qty,
# lookback windows) lives here anymore -- that's owned by
# control.ACTIVE_STRATEGY itself via its get_params() function.
STARTING_CASH_PER_TICKER = control.STARTING_CASH_PER_TICKER
DAYS_TO_TEST = control.DAYS_TO_TEST
RISK_FREE_RATE = control.RISK_FREE_RATE
ACTIVE_UNIVERSE = control.ACTIVE_UNIVERSE
strategy = control.ACTIVE_STRATEGY

# Load API environment variables
load_dotenv()
APP_KEY = os.environ.get("WEBULL_APP_KEY")
APP_SECRET = os.environ.get("WEBULL_APP_SECRET")
REGION = os.environ.get("WEBULL_REGION_ID", "us")

# =====================================================================
# 2. HELPER & DATA FORMATTING FUNCTIONS
# =====================================================================

def get_webull_timespan(resolution_str):
    """Maps resolution strings to Webull Timespan objects."""
    res_upper = resolution_str.upper()
    try:
        if res_upper == "M1": return Timespan.M1
        elif res_upper == "M5": return Timespan.M5
        elif res_upper == "M15": return Timespan.M15
        elif res_upper == "M30": return Timespan.M30
        elif res_upper == "H1": return getattr(Timespan, "H1", Timespan.M1)
        elif res_upper == "D1": return getattr(Timespan, "D1", Timespan.M1)
    except AttributeError:
        pass
    return Timespan.M1

def parse_webull_time(time_value):
    """Converts Webull timestamp to UTC-aware datetime."""
    if isinstance(time_value, str):
        if time_value.endswith("+0000"):
            time_value = time_value[:-5] + "+00:00"
        return datetime.fromisoformat(time_value)
    else:
        return datetime.fromtimestamp(int(time_value) / 1000, tz=timezone.utc)

def format_candle(raw_bar):
    """Standardizes raw candle data."""
    return {
        "datetime": parse_webull_time(raw_bar['time']),
        "open": float(raw_bar.get('open', raw_bar['close'])),
        "high": float(raw_bar.get('high', raw_bar['close'])),
        "low": float(raw_bar.get('low', raw_bar['close'])),
        "close": float(raw_bar['close']),
        "volume": float(raw_bar.get('volume', 0))
    }

def calculate_max_drawdown(equity_curve):
    """Calculates peak-to-trough max dollar and percentage drawdown."""
    peak = equity_curve[0] if len(equity_curve) > 0 else 0
    max_dd_dollars = 0.0
    max_dd_pct = 0.0

    for val in equity_curve:
        if val > peak:
            peak = val
        dd = peak - val
        dd_pct = (dd / peak * 100) if peak > 0 else 0.0

        if dd > max_dd_dollars:
            max_dd_dollars = dd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    return max_dd_dollars, max_dd_pct

def calculate_sharpe_ratio(equity_curve, periods_per_year=19500):
    """Calculates annualized Sharpe Ratio from intra-bar equity returns."""
    if len(equity_curve) < 2:
        return 0.0

    returns = np.diff(equity_curve) / equity_curve[:-1]
    returns = returns[~np.isnan(returns)]

    if len(returns) == 0 or np.std(returns) == 0:
        return 0.0

    rf_per_period = (1 + RISK_FREE_RATE)**(1 / periods_per_year) - 1
    excess_returns = returns - rf_per_period

    sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(periods_per_year)
    return float(sharpe)

def get_beta_and_alpha(strategy_daily_returns, benchmark_symbol="SPY", risk_free_rate_annual=0.04):
    """Computes Beta (β) and Period Jensen's Alpha (α) against a target benchmark."""
    if strategy_daily_returns.empty or len(strategy_daily_returns) < 3:
        return None

    strat_returns = strategy_daily_returns.copy()
    strat_returns.index = pd.to_datetime(strat_returns.index).tz_localize(None).normalize()

    min_date = strat_returns.index.min()
    max_date = strat_returns.index.max()

    start_date = (min_date - timedelta(days=3)).strftime('%Y-%m-%d')
    end_date = (max_date + timedelta(days=3)).strftime('%Y-%m-%d')

    try:
        bench_data = yf.download(benchmark_symbol, start=start_date, end=end_date, progress=False)
    except Exception:
        return None

    if bench_data.empty:
        return None

    # Handle MultiIndex and single-level column structures from yfinance
    if isinstance(bench_data.columns, pd.MultiIndex):
        if 'Close' in bench_data.columns.get_level_values(0):
            bench_close = bench_data['Close']
            if isinstance(bench_close, pd.DataFrame):
                bench_close = bench_close.iloc[:, 0]
        else:
            bench_close = bench_data.iloc[:, 0]
    else:
        if 'Close' in bench_data.columns:
            bench_close = bench_data['Close']
            if isinstance(bench_close, pd.DataFrame):
                bench_close = bench_close.iloc[:, 0]
        else:
            bench_close = bench_data.iloc[:, 0]

    bench_close = bench_close.squeeze()
    if not isinstance(bench_close, pd.Series):
        return None

    bench_close.index = pd.to_datetime(bench_close.index).tz_localize(None).normalize()
    bench_returns = bench_close.pct_change().dropna()

    aligned = pd.concat([strat_returns, bench_returns], axis=1, join='inner').dropna()
    aligned.columns = ['strategy', 'benchmark']

    if len(aligned) < 3:
        return None

    cov_matrix = np.cov(aligned['strategy'], aligned['benchmark'])
    covariance = cov_matrix[0, 1]
    benchmark_variance = cov_matrix[1, 1]
    beta = covariance / benchmark_variance if benchmark_variance != 0 else 1.0

    strat_period_return = (1 + aligned['strategy']).prod() - 1
    bench_period_return = (1 + aligned['benchmark']).prod() - 1

    num_days = max((max_date - min_date).days, 1)
    risk_free_period = (1 + risk_free_rate_annual) ** (num_days / 365.0) - 1

    expected_return = risk_free_period + beta * (bench_period_return - risk_free_period)
    alpha = strat_period_return - expected_return

    return {
        "beta": float(beta),
        "alpha_pct": float(alpha * 100),
        "strat_return_pct": float(strat_period_return * 100),
        "bench_return_pct": float(bench_period_return * 100)
    }

def print_trade_log(trades, title="EXECUTED TRADES LOG"):
    """Formats and prints detailed individual trade information."""
    if not trades:
        print(f"\n--- {title} ---")
        print("No trades executed.")
        return

    print("\n" + "=" * 115)
    print(f"                                   {title.upper()}                                   ")
    print("=" * 115)
    print(f"{'#':<4} | {'Symbol':<7} | {'Entry Time (UTC)':<19} | {'Exit Time (UTC)':<19} | {'Qty':<5} | {'Entry ($)':<9} | {'Exit ($)':<9} | {'P&L ($)':<10} | {'P&L %':<8} | {'Bars':<5}")
    print("-" * 115)

    for i, t in enumerate(trades, start=1):
        entry_str = t['entry_time'].strftime('%Y-%m-%d %H:%M') if isinstance(t['entry_time'], datetime) else str(t['entry_time'])
        exit_str = t['exit_time'].strftime('%Y-%m-%d %H:%M') if isinstance(t['exit_time'], datetime) else str(t['exit_time'])

        print(f"{i:<4} | {t['symbol']:<7} | {entry_str:<19} | {exit_str:<19} | {t['quantity']:<5} | ${t['entry_price']:<8.2f} | ${t['exit_price']:<8.2f} | ${t['pnl_dollars']:>+8.2f} | {t['pnl_pct']:>+7.2f}% | {t['bars_held']:<5}")
    print("=" * 115)

# =====================================================================
# 3. SINGLE-TICKER BACKTEST ENGINE
# =====================================================================

def backtest_single_symbol(symbol, data_client, timespan, strategy_config):
    """Runs backtest logic on a single ticker and captures detailed trade records.

    strategy_config is whatever strategy.get_params() returned -- this
    function never hardcodes lookback/sizing values itself.
    """
    res = data_client.market_data.get_history_bar(
        symbol,
        Category.US_STOCK.name,
        timespan.name,
        count="1200"
    )

    if res.status_code != 200 or not res.json():
        print(f"⚠️ Warning: Failed to fetch market data for [{symbol}]. Skipping.")
        return None

    raw_bars = res.json()
    formatted_bars = [format_candle(b) for b in raw_bars]
    formatted_bars.sort(key=lambda x: x['datetime'])

    if DAYS_TO_TEST is not None:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_TEST)
        formatted_bars = [b for b in formatted_bars if b['datetime'] >= cutoff_date]

    lookback_window = strategy_config["lookback"]
    if len(formatted_bars) <= lookback_window:
        print(f"⚠️ Warning: Insufficient data for [{symbol}] ({len(formatted_bars)} bars). Skipping.")
        return None

    cash = STARTING_CASH_PER_TICKER
    position_qty = 0
    entry_price = 0.0
    entry_time = None
    entry_bar_index = 0

    trades = []
    equity_curve = []
    timestamps = []

    rolling_buffer = formatted_bars[:lookback_window]
    simulation_bars = formatted_bars[lookback_window:]

    for idx, bar in enumerate(simulation_bars, start=lookback_window):
        current_price = bar['close']
        current_dt = bar['datetime']
        rolling_buffer.append(bar)

        portfolio_value = cash + (position_qty * current_price)
        equity_curve.append(portfolio_value)
        timestamps.append(current_dt)

        signal_result = strategy.analyze(
            rolling_buffer,
            lookback=strategy_config["lookback"],
            exit_lookback=strategy_config["exit_lookback"],
            current_position=position_qty
        )
        signal = signal_result.get("signal", "HOLD")

        # --- EXECUTE BUY SIGNAL ---
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

        # --- EXECUTE SELL SIGNAL ---
        elif signal == "SELL" and position_qty > 0:
            sale_revenue = position_qty * current_price
            cash += sale_revenue

            pnl_dollars = (current_price - entry_price) * position_qty
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            bars_held = idx - entry_bar_index

            trades.append({
                "symbol": symbol,
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

    # Close open position at simulation end
    if position_qty > 0:
        final_price = simulation_bars[-1]['close']
        final_dt = simulation_bars[-1]['datetime']
        pnl_dollars = (final_price - entry_price) * position_qty
        pnl_pct = ((final_price - entry_price) / entry_price) * 100
        cash += position_qty * final_price

        trades.append({
            "symbol": symbol,
            "entry_time": entry_time,
            "exit_time": final_dt,
            "entry_price": entry_price,
            "exit_price": final_price,
            "quantity": position_qty,
            "pnl_dollars": pnl_dollars,
            "pnl_pct": pnl_pct,
            "bars_held": len(formatted_bars) - entry_bar_index
        })

    # Performance metric evaluations
    final_balance = cash
    total_net_pnl = final_balance - STARTING_CASH_PER_TICKER
    total_net_pnl_pct = (total_net_pnl / STARTING_CASH_PER_TICKER) * 100

    start_stock_price = formatted_bars[lookback_window]['close']
    end_stock_price = formatted_bars[-1]['close']
    stock_pnl_pct = ((end_stock_price - start_stock_price) / start_stock_price) * 100

    max_dd_dollars, max_dd_pct = calculate_max_drawdown(equity_curve)
    sharpe = calculate_sharpe_ratio(equity_curve)

    single_equity_df = pd.DataFrame({"datetime": timestamps, "equity": equity_curve})
    single_equity_df['date'] = pd.to_datetime(single_equity_df['datetime']).dt.date
    daily_single_equity = single_equity_df.groupby('date')['equity'].last()
    single_daily_returns = daily_single_equity.pct_change().dropna()

    single_beta_metrics = get_beta_and_alpha(
        single_daily_returns,
        benchmark_symbol=symbol,
        risk_free_rate_annual=RISK_FREE_RATE
    )

    return {
        "symbol": symbol,
        "final_balance": final_balance,
        "net_pnl": total_net_pnl,
        "net_pnl_pct": total_net_pnl_pct,
        "buy_hold_pct": stock_pnl_pct,
        "alpha_pct": single_beta_metrics["alpha_pct"] if single_beta_metrics else (total_net_pnl_pct - stock_pnl_pct),
        "beta": single_beta_metrics["beta"] if single_beta_metrics else 1.0,
        "max_dd_dollars": max_dd_dollars,
        "max_dd_pct": max_dd_pct,
        "sharpe_ratio": sharpe,
        "trades": trades,
        "equity_curve": equity_curve,
        "timestamps": timestamps,
        "bars_count": len(formatted_bars)
    }

# =====================================================================
# 4. MONTE CARLO SIMULATION
# =====================================================================

def run_monte_carlo_simulation(all_trades, starting_capital, avg_buy_hold_pct=0.0, spy_return_pct=None, num_simulations=1000, ruin_threshold_pct=20.0):
    """Runs Monte Carlo risk, streak, and benchmark outperformance simulations."""
    if not all_trades:
        print("⚠️ No trades available for Monte Carlo simulation.")
        return

    trade_pnl_dollars = [t["pnl_dollars"] for t in all_trades]
    num_trades = len(trade_pnl_dollars)

    final_balances = []
    max_drawdowns_pct = []
    max_consecutive_losses_list = []
    ruin_count = 0

    beat_bh_count = 0
    beat_spy_count = 0

    for _ in range(num_simulations):
        simulated_pnl = np.random.choice(trade_pnl_dollars, size=num_trades, replace=True)

        current_balance = starting_capital
        peak = starting_capital
        max_dd_pct = 0.0

        current_streak = 0
        max_streak = 0
        hit_ruin = False

        for pnl in simulated_pnl:
            current_balance += pnl

            if current_balance > peak:
                peak = current_balance
            dd = (peak - current_balance) / peak * 100 if peak > 0 else 0.0
            if dd > max_dd_pct:
                max_dd_pct = dd

            if dd >= ruin_threshold_pct:
                hit_ruin = True

            if pnl < 0:
                current_streak += 1
                if current_streak > max_streak:
                    max_streak = current_streak
            else:
                current_streak = 0

        if hit_ruin:
            ruin_count += 1

        sim_return_pct = ((current_balance - starting_capital) / starting_capital) * 100

        if sim_return_pct > avg_buy_hold_pct:
            beat_bh_count += 1

        if spy_return_pct is not None and sim_return_pct > spy_return_pct:
            beat_spy_count += 1

        final_balances.append(current_balance)
        max_drawdowns_pct.append(max_dd_pct)
        max_consecutive_losses_list.append(max_streak)

    pnl_array = np.array(final_balances) - starting_capital
    prob_profitable = (np.sum(pnl_array > 0) / num_simulations) * 100
    prob_beat_bh = (beat_bh_count / num_simulations) * 100
    prob_beat_spy = (beat_spy_count / num_simulations) * 100 if spy_return_pct is not None else None
    risk_of_ruin = (ruin_count / num_simulations) * 100

    p5_final = np.percentile(final_balances, 5)
    p25_final = np.percentile(final_balances, 25)
    p50_final = np.percentile(final_balances, 50)
    p75_final = np.percentile(final_balances, 75)
    p95_final = np.percentile(final_balances, 95)

    p50_dd = np.percentile(max_drawdowns_pct, 50)
    p95_dd = np.percentile(max_drawdowns_pct, 95)

    p50_streak = int(np.percentile(max_consecutive_losses_list, 50))
    p95_streak = int(np.percentile(max_consecutive_losses_list, 95))

    print("\n" + "=" * 115)
    print(f"                            ADVANCED MONTE CARLO STRESS TEST ({num_simulations:,} Iterations)           ")
    print("=" * 115)
    print(f" 🎯 Overall Win Probability:     {prob_profitable:.1f}% of outcomes ended in net profit")
    print(f" 📈 Prob. of Beating Tickers B&H: {prob_beat_bh:.1f}% (vs Avg B&H: {avg_buy_hold_pct:+.2f}%)")
    if prob_beat_spy is not None:
        print(f" 🏆 Prob. of Beating SPY:         {prob_beat_spy:.1f}% (vs SPY: {spy_return_pct:+.2f}%)")
    else:
        print(f" 🏆 Prob. of Beating SPY:         N/A (SPY data unavailable)")
    print(f" ⚠️ Risk of Ruin (≥{ruin_threshold_pct:.0f}% Drawdown): {risk_of_ruin:.1f}% chance of hitting account distress")
    print("-" * 115)
    print(" 📊 EXPECTED RETURN DISTRIBUTION:")
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

# =====================================================================
# 5. MULTI-TICKER RUNNER & AGGREGATOR
# =====================================================================

def run_backtest():
    strategy_config = strategy.get_params()
    bar_resolution = strategy_config["bar_resolution"]

    print(f"🚀 Initializing Multi-Ticker Backtest Engine...")
    print(f"⚙️ Engine Config: Days Back={DAYS_TO_TEST} | Cash/Ticker=${STARTING_CASH_PER_TICKER:,.2f}")
    print(f"🧠 Strategy: {strategy.__name__} | Resolution={bar_resolution} | Lookback={strategy_config['lookback']} | Exit Lookback={strategy_config['exit_lookback']} | Sizing={strategy_config['position_mode']}")
    print(f"📋 Target Universe ({len(ACTIVE_UNIVERSE)} symbols): {', '.join(ACTIVE_UNIVERSE)}\n")

    api_client = ApiClient(APP_KEY, APP_SECRET, REGION)
    api_client.add_endpoint(REGION, "api.webull.com")
    data_client = DataClient(api_client)

    timespan = get_webull_timespan(bar_resolution)

    all_results = []
    all_trades = []

    for idx, symbol in enumerate(ACTIVE_UNIVERSE, start=1):
        print(f"[{idx}/{len(ACTIVE_UNIVERSE)}] Backtesting {symbol}...", end=" ", flush=True)
        res = backtest_single_symbol(symbol, data_client, timespan, strategy_config)
        if res:
            all_results.append(res)
            all_trades.extend(res["trades"])
            print(f"Done. Net P&L: ${res['net_pnl']:+,.2f} ({res['net_pnl_pct']:+.2f}%) | Beta: {res['beta']:.2f} | Alpha: {res['alpha_pct']:+.2f}% | Trades: {len(res['trades'])}")

    if not all_results:
        print("❌ No valid ticker data evaluated. Exiting backtest.")
        return

    # =====================================================================
    # 6. DETAILED TRADE LOG PRINTING
    # =====================================================================
    for r in all_results:
        print_trade_log(r["trades"], title=f"Trade Log for [{r['symbol']}]")

    sorted_all_trades = sorted(all_trades, key=lambda x: x["entry_time"])
    print_trade_log(sorted_all_trades, title="Master Portfolio Consolidated Trade Log")

    # =====================================================================
    # 7. DASHBOARD & AGGREGATE SUMMARY
    # =====================================================================
    total_initial_capital = len(all_results) * STARTING_CASH_PER_TICKER
    total_ending_capital = sum(r["final_balance"] for r in all_results)
    aggregate_pnl = total_ending_capital - total_initial_capital
    aggregate_pnl_pct = (aggregate_pnl / total_initial_capital) * 100

    avg_buy_hold_pct = sum(r["buy_hold_pct"] for r in all_results) / len(all_results)

    min_length = min(len(r["equity_curve"]) for r in all_results)
    combined_equity = np.zeros(min_length)
    for r in all_results:
        combined_equity += np.array(r["equity_curve"][:min_length])

    combined_timestamps = all_results[0]["timestamps"][:min_length]

    portfolio_df = pd.DataFrame({"datetime": combined_timestamps, "equity": combined_equity})
    portfolio_df['date'] = pd.to_datetime(portfolio_df['datetime']).dt.date
    daily_portfolio_equity = portfolio_df.groupby('date')['equity'].last()
    portfolio_daily_returns = daily_portfolio_equity.pct_change().dropna()

    spy_metrics = get_beta_and_alpha(
        portfolio_daily_returns,
        benchmark_symbol="SPY",
        risk_free_rate_annual=RISK_FREE_RATE
    )

    portfolio_max_dd_dollars, portfolio_max_dd_pct = calculate_max_drawdown(combined_equity)
    portfolio_sharpe = calculate_sharpe_ratio(combined_equity)

    winning_trades = [t for t in sorted_all_trades if t["pnl_dollars"] > 0]
    losing_trades = [t for t in sorted_all_trades if t["pnl_dollars"] < 0]

    total_trade_count = len(sorted_all_trades)
    wins_count = len(winning_trades)
    losses_count = len(losing_trades)
    win_rate = (wins_count / total_trade_count * 100) if total_trade_count > 0 else 0.0

    gross_profit = sum(t["pnl_dollars"] for t in winning_trades)
    gross_loss = abs(sum(t["pnl_dollars"] for t in losing_trades))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)

    print("\n" + "=" * 115)
    print(f"                                   PER-TICKER BREAKDOWN SUMMARY                                     ")
    print("=" * 115)
    print(f"{'Ticker':<8} | {'Trades':<6} | {'Net P&L ($)':<11} | {'Strategy %':<10} | {'B&H %':<8} | {'Beta (β)':<8} | {'Alpha %':<8} | {'Max DD %':<8}")
    print("-" * 115)
    for r in all_results:
        print(f"{r['symbol']:<8} | {len(r['trades']):<6} | ${r['net_pnl']:>+9,.2f} | {r['net_pnl_pct']:>+9.2f}% | {r['buy_hold_pct']:>+7.2f}% | {r['beta']:>8.2f} | {r['alpha_pct']:>+7.2f}% | -{r['max_dd_pct']:>6.2f}%")
    print("=" * 115)

    print("\n" + "=" * 115)
    print(f"                                 COMBINED PORTFOLIO PERFORMANCE                                     ")
    print("=" * 115)
    print(f" Total Symbols Evaluated:     {len(all_results)} / {len(ACTIVE_UNIVERSE)}")
    print(f" Combined Starting Cash:      ${total_initial_capital:,.2f}")
    print(f" Combined Ending Cash:        ${total_ending_capital:,.2f}")
    print(f" Aggregate Net P&L:           ${aggregate_pnl:+,.2f} ({aggregate_pnl_pct:+.2f}%)")
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
    print(f" Win Rate:                    {win_rate:.1f}% ({wins_count} W / {losses_count} L)")
    print(f" Profit Factor:               {profit_factor:.2f} (Gross Profit: ${gross_profit:,.2f} / Gross Loss: ${gross_loss:,.2f})")
    print(f" Max Portfolio Drawdown:      -${portfolio_max_dd_dollars:,.2f} (-{portfolio_max_dd_pct:.2f}%)")
    print(f" Portfolio Sharpe Ratio:      {portfolio_sharpe:.2f}")
    print("=" * 115 + "\n")

    run_monte_carlo_simulation(
        all_trades=sorted_all_trades,
        starting_capital=total_initial_capital,
        avg_buy_hold_pct=avg_buy_hold_pct,
        spy_return_pct=spy_metrics["bench_return_pct"] if spy_metrics else None,
        num_simulations=1000
    )

if __name__ == "__main__":
    run_backtest()