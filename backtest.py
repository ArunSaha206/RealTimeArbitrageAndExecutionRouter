import os
import math
import numpy as np
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from webull.core.client import ApiClient
from webull.data.data_client import DataClient
from webull.data.common.category import Category
from webull.data.common.timespan import Timespan

# Import strategy module and ticker selection universe
import breakout as strategy
from tickers import ACTIVE_UNIVERSE

# =====================================================================
# 1. BACKTEST CONFIGURATION
# =====================================================================
BAR_RESOLUTION = "M5"        # Options: "M1", "M5", "M15", "M30", "H1", "D1"
STARTING_CASH_PER_TICKER = 10000.00     # Virtual starting cash allocated per asset
DAYS_TO_TEST = 50            # Calendar days back to evaluate
RISK_FREE_RATE = 0.04        # 4% annualized risk-free rate assumption for Sharpe Ratio

# Position sizing mode: "ALL_IN" (max affordable shares) or "FIXED_SHARES"
POSITION_MODE = "ALL_IN"     
FIXED_SHARE_QTY = 10         # Used if POSITION_MODE == "FIXED_SHARES"

# Strategy parameters passed to strategy.analyze
STRATEGY_PARAMS = {
    "lookback": 20,          # Resistance entry lookback
    "exit_lookback": 10      # Support exit lookback
}

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
    """Calculates annualized Sharpe Ratio from intra-bar equity returns.
    Default periods_per_year ~ 19,500 for 5-minute bars (78 bars/day * 250 days).
    """
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

# =====================================================================
# 3. SINGLE-TICKER BACKTEST ENGINE
# =====================================================================

def backtest_single_symbol(symbol, data_client, timespan):
    """Runs backtest logic on a single ticker and returns individual results."""
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

    lookback_window = STRATEGY_PARAMS.get("lookback", 20)
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

    rolling_buffer = formatted_bars[:lookback_window]
    simulation_bars = formatted_bars[lookback_window:]

    for idx, bar in enumerate(simulation_bars, start=lookback_window):
        current_price = bar['close']
        current_dt = bar['datetime']
        rolling_buffer.append(bar)

        portfolio_value = cash + (position_qty * current_price)
        equity_curve.append(portfolio_value)

        signal_result = strategy.analyze(
            rolling_buffer, 
            **STRATEGY_PARAMS, 
            current_position=position_qty
        )
        signal = signal_result.get("signal", "HOLD")

        # --- EXECUTE BUY SIGNAL ---
        if signal == "BUY" and position_qty == 0:
            if POSITION_MODE == "ALL_IN":
                position_qty = int(cash // current_price)
            else:
                position_qty = FIXED_SHARE_QTY

            if position_qty > 0:
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

    # Metric calculations
    final_balance = cash
    total_net_pnl = final_balance - STARTING_CASH_PER_TICKER
    total_net_pnl_pct = (total_net_pnl / STARTING_CASH_PER_TICKER) * 100

    start_stock_price = formatted_bars[lookback_window]['close']
    end_stock_price = formatted_bars[-1]['close']
    stock_pnl_pct = ((end_stock_price - start_stock_price) / start_stock_price) * 100
    alpha_pct = total_net_pnl_pct - stock_pnl_pct

    max_dd_dollars, max_dd_pct = calculate_max_drawdown(equity_curve)
    sharpe = calculate_sharpe_ratio(equity_curve)

    return {
        "symbol": symbol,
        "final_balance": final_balance,
        "net_pnl": total_net_pnl,
        "net_pnl_pct": total_net_pnl_pct,
        "buy_hold_pct": stock_pnl_pct,
        "alpha_pct": alpha_pct,
        "max_dd_dollars": max_dd_dollars,
        "max_dd_pct": max_dd_pct,
        "sharpe_ratio": sharpe,
        "trades": trades,
        "equity_curve": equity_curve,
        "bars_count": len(formatted_bars)
    }

# =====================================================================
# 4. MULTI-TICKER RUNNER & AGGREGATOR
# =====================================================================

def run_monte_carlo_simulation(all_trades, starting_capital, num_simulations=1000):
    """
    Runs a Monte Carlo simulation by randomly resampling trade outcomes
    to stress-test drawdown limits and probability distributions.
    """
    if not all_trades:
        print("⚠️ No trades available for Monte Carlo simulation.")
        return

    trade_pnl_dollars = [t["pnl_dollars"] for t in all_trades]
    num_trades = len(trade_pnl_dollars)

    final_balances = []
    max_drawdowns_pct = []

    for _ in range(num_simulations):
        # Randomly shuffle trade order with replacement (Bootstrapping)
        simulated_pnl_sequence = np.random.choice(trade_pnl_dollars, size=num_trades, replace=True)
        
        # Track portfolio curve for this simulation run
        equity_curve = [starting_capital]
        current_balance = starting_capital
        peak = starting_capital
        max_dd_pct = 0.0

        for pnl in simulated_pnl_sequence:
            current_balance += pnl
            equity_curve.append(current_balance)

            if current_balance > peak:
                peak = current_balance
            
            dd = (peak - current_balance) / peak * 100 if peak > 0 else 0.0
            if dd > max_dd_pct:
                max_dd_pct = dd

        final_balances.append(current_balance)
        max_drawdowns_pct.append(max_dd_pct)

    # Statistical percentiles across all 1,000 simulations
    median_final_cash = np.percentile(final_balances, 50)
    p5_final_cash = np.percentile(final_balances, 5)   # 5th percentile (pessimistic)
    p95_final_cash = np.percentile(final_balances, 95) # 95th percentile (optimistic)

    median_dd = np.percentile(max_drawdowns_pct, 50)
    p95_dd = np.percentile(max_drawdowns_pct, 95)       # 95% worst-case drawdown

    print("\n" + "=" * 88)
    print(f"            MONTE CARLO SIMULATION RESULTS ({num_simulations:,} Iterations)            ")
    print("=" * 88)
    print(f" Starting Portfolio Capital:     ${starting_capital:,.2f}")
    print(f" Median Expected Ending Cash:    ${median_final_cash:,.2f} (P&L: ${median_final_cash - starting_capital:+,.2f})")
    print(f" 90% Confidence Return Window:   ${p5_final_cash:,.2f}  to  ${p95_final_cash:,.2f}")
    print("-" * 88)
    print(f" Median Max Drawdown:            -{median_dd:.2f}%")
    print(f" 95th Percentile Max Drawdown:   -{p95_dd:.2f}%  (Worst 5% of alternate realities)")
    print("=" * 88 + "\n")

def run_backtest():
    print(f"🚀 Initializing Multi-Ticker Backtest Engine...")
    print(f"⚙️ Config: Resolution={BAR_RESOLUTION} | Lookback Window={DAYS_TO_TEST} Days | Cash/Ticker=${STARTING_CASH_PER_TICKER:,.2f} | Strategy={strategy.__name__}")
    print(f"📋 Target Universe ({len(ACTIVE_UNIVERSE)} symbols): {', '.join(ACTIVE_UNIVERSE)}\n")

    api_client = ApiClient(APP_KEY, APP_SECRET, REGION)
    api_client.add_endpoint(REGION, "api.webull.com")
    data_client = DataClient(api_client)

    timespan = get_webull_timespan(BAR_RESOLUTION)

    all_results = []
    all_trades = []

    for idx, symbol in enumerate(ACTIVE_UNIVERSE, start=1):
        print(f"[{idx}/{len(ACTIVE_UNIVERSE)}] Backtesting {symbol}...", end=" ", flush=True)
        res = backtest_single_symbol(symbol, data_client, timespan)
        if res:
            all_results.append(res)
            all_trades.extend(res["trades"])
            print(f"Done. Net P&L: ${res['net_pnl']:+,.2f} ({res['net_pnl_pct']:+.2f}%) | Alpha: {res['alpha_pct']:+.2f}% | Trades: {len(res['trades'])}")

    if not all_results:
        print("❌ No valid ticker data evaluated. Exiting backtest.")
        return

    # =====================================================================
    # 5. DASHBOARD & AGGREGATE SUMMARY
    # =====================================================================
    total_initial_capital = len(all_results) * STARTING_CASH_PER_TICKER
    total_ending_capital = sum(r["final_balance"] for r in all_results)
    aggregate_pnl = total_ending_capital - total_initial_capital
    aggregate_pnl_pct = (aggregate_pnl / total_initial_capital) * 100

    avg_buy_hold_pct = sum(r["buy_hold_pct"] for r in all_results) / len(all_results)
    overall_alpha_pct = aggregate_pnl_pct - avg_buy_hold_pct

    # Portfolio combined equity curve
    min_length = min(len(r["equity_curve"]) for r in all_results)
    combined_equity = np.zeros(min_length)
    for r in all_results:
        combined_equity += np.array(r["equity_curve"][:min_length])

    portfolio_max_dd_dollars, portfolio_max_dd_pct = calculate_max_drawdown(combined_equity)
    portfolio_sharpe = calculate_sharpe_ratio(combined_equity)

    winning_trades = [t for t in all_trades if t["pnl_dollars"] > 0]
    losing_trades = [t for t in all_trades if t["pnl_dollars"] < 0]

    total_trade_count = len(all_trades)
    wins_count = len(winning_trades)
    losses_count = len(losing_trades)
    win_rate = (wins_count / total_trade_count * 100) if total_trade_count > 0 else 0.0

    gross_profit = sum(t["pnl_dollars"] for t in winning_trades)
    gross_loss = abs(sum(t["pnl_dollars"] for t in losing_trades))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)

    print("\n" + "=" * 88)
    print(f"                       PER-TICKER BREAKDOWN SUMMARY                         ")
    print("=" * 88)
    print(f"{'Ticker':<8} | {'Trades':<7} | {'Net P&L ($)':<12} | {'Strategy %':<10} | {'B&H %':<9} | {'Alpha %':<9} | {'Max DD %':<8} | {'Sharpe':<6}")
    print("-" * 88)
    for r in all_results:
        print(f"{r['symbol']:<8} | {len(r['trades']):<7} | ${r['net_pnl']:>+10,.2f} | {r['net_pnl_pct']:>+9.2f}% | {r['buy_hold_pct']:>+8.2f}% | {r['alpha_pct']:>+8.2f}% | -{r['max_dd_pct']:>6.2f}% | {r['sharpe_ratio']:>6.2f}")
    print("=" * 88)

    print("\n" + "=" * 88)
    print(f"                     COMBINED PORTFOLIO PERFORMANCE                         ")
    print("=" * 88)
    print(f" Total Symbols Evaluated:  {len(all_results)} / {len(ACTIVE_UNIVERSE)}")
    print(f" Combined Starting Cash:   ${total_initial_capital:,.2f}")
    print(f" Combined Ending Cash:     ${total_ending_capital:,.2f}")
    print(f" Aggregate Net P&L:        ${aggregate_pnl:+,.2f} ({aggregate_pnl_pct:+.2f}%)")
    print(f" Benchmark Average Return: {avg_buy_hold_pct:+.2f}%")
    print(f" Overall Alpha Generated:  {overall_alpha_pct:+.2f}% vs. Buy & Hold")
    print("-" * 88)
    print(f" Total Trades Executed:    {total_trade_count}")
    print(f" Win Rate:                 {win_rate:.1f}% ({wins_count} W / {losses_count} L)")
    print(f" Profit Factor:            {profit_factor:.2f} (Gross Profit: ${gross_profit:,.2f} / Gross Loss: ${gross_loss:,.2f})")
    print(f" Max Portfolio Drawdown:   -${portfolio_max_dd_dollars:,.2f} (-{portfolio_max_dd_pct:.2f}%)")
    print(f" Portfolio Sharpe Ratio:   {portfolio_sharpe:.2f}")
    print("=" * 88 + "\n")

    run_monte_carlo_simulation(
        all_trades=all_trades, 
        starting_capital=total_initial_capital, 
        num_simulations=1000
    )

if __name__ == "__main__":
    run_backtest()