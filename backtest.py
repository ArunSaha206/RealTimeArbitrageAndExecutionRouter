import os
import math
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from webull.core.client import ApiClient
from webull.data.data_client import DataClient
from webull.data.common.category import Category
from webull.data.common.timespan import Timespan

# Import your active strategy module (e.g., breakout, rsi, etc.)
import breakout as strategy

# =====================================================================
# 1. BACKTEST CONFIGURATION
# =====================================================================
TARGET_SYMBOL = "NKE"
BAR_RESOLUTION = "M5"        # Options: "M1", "M5", "M15", "M30", "H1", "D1"
STARTING_CASH = 10000.00     # Initial virtual portfolio cash
DAYS_TO_TEST = 50            # Calendar days back to evaluate

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

# =====================================================================
# 3. BACKTEST ENGINE
# =====================================================================

def run_backtest():
    print(f"🚀 Initializing Backtest Engine for [{TARGET_SYMBOL}]...")
    print(f"⚙️ Config: Resolution={BAR_RESOLUTION} | Target Window={DAYS_TO_TEST} Days | Starting Capital=${STARTING_CASH:,.2f} | Strategy={strategy.__name__}\n")

    # Connect to Webull API
    api_client = ApiClient(APP_KEY, APP_SECRET, REGION)
    api_client.add_endpoint(REGION, "api.webull.com")
    data_client = DataClient(api_client)

    timespan = get_webull_timespan(BAR_RESOLUTION)
    
    # Request maximum historical bar window available from Webull endpoint
    res = data_client.market_data.get_history_bar(
        TARGET_SYMBOL, 
        Category.US_STOCK.name, 
        timespan.name, 
        count="1200"
    )

    if res.status_code != 200 or not res.json():
        raise RuntimeError(f"Failed to fetch market data from Webull API. Status: {res.status_code}")

    # Standardize & sort chronologically
    raw_bars = res.json()
    formatted_bars = [format_candle(b) for b in raw_bars]
    formatted_bars.sort(key=lambda x: x['datetime'])

    # Enforce calendar day cutoff if specified
    if DAYS_TO_TEST is not None:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_TEST)
        formatted_bars = [b for b in formatted_bars if b['datetime'] >= cutoff_date]

    lookback_window = STRATEGY_PARAMS.get("lookback", 20)
    if len(formatted_bars) <= lookback_window:
        raise ValueError(f"Insufficient historical data ({len(formatted_bars)} bars) for strategy lookback window ({lookback_window}).")

    # Tracking variables
    cash = STARTING_CASH
    position_qty = 0
    entry_price = 0.0
    entry_time = None
    entry_bar_index = 0

    trades = []             # Records completed trades
    equity_curve = []       # Portfolio balance tracking over time

    # Warm start rolling buffer with initial lookback bars
    rolling_buffer = formatted_bars[:lookback_window]
    simulation_bars = formatted_bars[lookback_window:]

    print(f"📈 Loaded {len(formatted_bars)} total candles across period: "
          f"{formatted_bars[0]['datetime'].strftime('%Y-%m-%d %H:%M')} to {formatted_bars[-1]['datetime'].strftime('%Y-%m-%d %H:%M')}")
    print(f"⏳ Running simulation across {len(simulation_bars)} active candles...\n")

    for idx, bar in enumerate(simulation_bars, start=lookback_window):
        current_price = bar['close']
        current_dt = bar['datetime']
        rolling_buffer.append(bar)

        # Current portfolio valuation
        portfolio_value = cash + (position_qty * current_price)
        equity_curve.append(portfolio_value)

        # Get signal from strategy module
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

    # Close open position at end of simulation for final tally
    if position_qty > 0:
        final_price = simulation_bars[-1]['close']
        final_dt = simulation_bars[-1]['datetime']
        pnl_dollars = (final_price - entry_price) * position_qty
        pnl_pct = ((final_price - entry_price) / entry_price) * 100
        cash += position_qty * final_price

        trades.append({
            "entry_time": entry_time,
            "exit_time": final_dt,
            "entry_price": entry_price,
            "exit_price": final_price,
            "quantity": position_qty,
            "pnl_dollars": pnl_dollars,
            "pnl_pct": pnl_pct,
            "bars_held": len(formatted_bars) - entry_bar_index
        })

    # =====================================================================
    # 4. PERFORMANCE ANALYTICS & BENCHMARK CALCULATION
    # =====================================================================
    final_balance = cash
    total_net_pnl = final_balance - STARTING_CASH
    total_net_pnl_pct = (total_net_pnl / STARTING_CASH) * 100

    # Stock Buy & Hold benchmark calculation over the exact backtest period
    start_stock_price = formatted_bars[lookback_window]['close']
    end_stock_price = formatted_bars[-1]['close']
    stock_pnl_dollars = end_stock_price - start_stock_price
    stock_pnl_pct = ((end_stock_price - start_stock_price) / start_stock_price) * 100
    alpha_pct = total_net_pnl_pct - stock_pnl_pct

    total_trades = len(trades)
    winning_trades = [t for t in trades if t["pnl_dollars"] > 0]
    losing_trades = [t for t in trades if t["pnl_dollars"] < 0]

    wins_count = len(winning_trades)
    losses_count = len(losing_trades)
    win_rate = (wins_count / total_trades * 100) if total_trades > 0 else 0.0

    gross_profit = sum(t["pnl_dollars"] for t in winning_trades)
    gross_loss = abs(sum(t["pnl_dollars"] for t in losing_trades))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)

    avg_win = (gross_profit / wins_count) if wins_count > 0 else 0.0
    avg_loss = (gross_loss / losses_count) if losses_count > 0 else 0.0
    risk_reward_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0

    # Maximum Drawdown Calculation
    peak_equity = STARTING_CASH
    max_drawdown_dollars = 0.0
    max_drawdown_pct = 0.0

    for eq in equity_curve:
        if eq > peak_equity:
            peak_equity = eq
        dd = peak_equity - eq
        dd_pct = (dd / peak_equity) * 100 if peak_equity > 0 else 0.0
        
        if dd > max_drawdown_dollars:
            max_drawdown_dollars = dd
        if dd_pct > max_drawdown_pct:
            max_drawdown_pct = dd_pct

    avg_bars_held = (sum(t["bars_held"] for t in trades) / total_trades) if total_trades > 0 else 0.0

    # =====================================================================
    # 5. DISPLAY DASHBOARD
    # =====================================================================
    print("=" * 65)
    print(f"               BACKTEST PERFORMANCE SUMMARY              ")
    print("=" * 65)
    print(f" Target Asset:             {TARGET_SYMBOL}")
    print(f" Candle Resolution:        {BAR_RESOLUTION}")
    print(f" Tested Data Range:        {formatted_bars[0]['datetime'].strftime('%Y-%m-%d')} to {formatted_bars[-1]['datetime'].strftime('%Y-%m-%d')}")
    print(f" Total Candles Evaluated:  {len(formatted_bars)} bars")
    print("-" * 65)
    print(f" Starting Capital:         ${STARTING_CASH:,.2f}")
    print(f" Ending Capital:           ${final_balance:,.2f}")
    print(f" Strategy Net Return:      ${total_net_pnl:+,.2f} ({total_net_pnl_pct:+.2f}%)")
    print(f" Stock Buy & Hold Return:  ${stock_pnl_dollars:+,.2f} ({stock_pnl_pct:+.2f}%)  [${start_stock_price:.2f} ➔ ${end_stock_price:.2f}]")
    print(f" Strategy Outperformance:  {alpha_pct:+.2f}% vs. Buy & Hold")
    print("-" * 65)
    print(f" Total Trades Executed:    {total_trades}")
    print(f" Winning Trades:           {wins_count} ({win_rate:.1f}%)")
    print(f" Losing Trades:            {losses_count} ({100 - win_rate:.1f}%)")
    print(f" Profit Factor:            {profit_factor:.2f}")
    print("-" * 65)
    print(f" Average Win:              ${avg_win:,.2f}")
    print(f" Average Loss:             ${avg_loss:,.2f}")
    print(f" Risk-to-Reward Ratio:     {risk_reward_ratio:.2f}")
    print(f" Max Portfolio Drawdown:   -${max_drawdown_dollars:,.2f} (-{max_drawdown_pct:.2f}%)")
    print(f" Avg Trade Duration:       {avg_bars_held:.1f} bars")
    print("=" * 65)

    if trades:
        print("\n📋 RECENT TRADES (Last 5):")
        for t in trades[-5:]:
            print(f" • Entry: {t['entry_time'].strftime('%m-%d %H:%M')} @ ${t['entry_price']:.2f} | "
                  f"Exit: {t['exit_time'].strftime('%m-%d %H:%M')} @ ${t['exit_price']:.2f} | "
                  f"P&L: ${t['pnl_dollars']:+,.2f} ({t['pnl_pct']:+.2f}%) | Duration: {t['bars_held']} bars")
        print()

if __name__ == "__main__":
    run_backtest()