import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from webull.core.client import ApiClient
from webull.data.data_client import DataClient
from webull.data.common.category import Category
from webull.data.common.timespan import Timespan

# Import strategies
import strategies.M5breakout as M5breakout

# Active strategy selection & configuration
ACTIVE_STRATEGY = M5breakout.analyze
STRATEGY_PARAMS = {
    "lookback": 20,       # Bars for Resistance (Entry)
    "exit_lookback": 10   # Bars for Support (Exit)
}

# Load keys from hidden .env file
load_dotenv()

# =====================================================================
# 1. PARAMETERS & SIMULATION SPEED/RESOLUTION CONTROLS
# =====================================================================
EXECUTION_MODE = "PAPER"       # 🛡️ Set to "PAPER" for local simulation or "LIVE" for Webull API
TARGET_SYMBOL = "NVDA"         # Target ticker asset

# ---- TIME-STEP CONTROLS ----
SIMULATION_SPEED = 1           # Real-world delay (in seconds) between ticks
BAR_RESOLUTION = "M5"          # "M1", "M5", "M15", "M30", "H1", "D1"

# ---- HIERARCHY OVERRIDES ----
SPECIFIED_DATE = "2026-07-13"  # Format: "YYYY-MM-DD" or None
SPECIFIED_TIME = "14:30:34"    # Format: "HH:MM:SS" or None

# Local virtual wallet tracking for safe paper testing
local_portfolio = {
    "cash": 100000.00,  
    "positions": {}     
}

APP_KEY = os.environ.get("WEBULL_APP_KEY")
APP_SECRET = os.environ.get("WEBULL_APP_SECRET")
REGION = os.environ.get("WEBULL_REGION_ID", "us")

# =====================================================================
# 2. HELPER & CORE PROTECTION FUNCTIONS
# =====================================================================

def get_webull_timespan(resolution_str):
    """Maps custom text resolution inputs directly to Webull API Timespan objects."""
    res_upper = resolution_str.upper()
    try:
        if res_upper == "M1": return Timespan.M1
        elif res_upper == "M5": return Timespan.M5
        elif res_upper == "M15": return Timespan.M15
        elif res_upper == "M30": return Timespan.M30
        elif res_upper == "H1": return getattr(Timespan, "H1", Timespan.M1) 
        elif res_upper == "D1": return getattr(Timespan, "D1", Timespan.M1)
    except AttributeError:
        print(f"⚠️ Warning: Timespan configuration '{resolution_str}' not explicitly exposed by SDK. Falling back to M1.")
        
    return Timespan.M1

def parse_webull_time(time_value):
    """Safely converts Webull's time field into a Python datetime object."""
    if isinstance(time_value, str):
        if time_value.endswith("+0000"):
            time_value = time_value[:-5] + "+00:00"
        return datetime.fromisoformat(time_value)
    else:
        return datetime.fromtimestamp(int(time_value) / 1000, tz=timezone.utc)

def get_last_market_day():
    """Calculates the date string of the most recent weekday."""
    today = datetime.now(timezone.utc)
    if today.weekday() == 5:    # Saturday -> Friday
        target = today - timedelta(days=1)
    elif today.weekday() == 6:  # Sunday -> Friday
        target = today - timedelta(days=2)
    else:
        target = today
    return target.strftime("%Y-%m-%d")

def format_candle(raw_bar):
    """Standardizes raw Webull API responses into unified dictionary schema."""
    bar_dt = parse_webull_time(raw_bar['time'])
    return {
        "datetime": bar_dt,
        "open": float(raw_bar.get('open', raw_bar['close'])),
        "high": float(raw_bar.get('high', raw_bar['close'])),
        "low": float(raw_bar.get('low', raw_bar['close'])),
        "close": float(raw_bar['close']),
        "volume": float(raw_bar.get('volume', 0))
    }

def execute_order(symbol, action, quantity, current_price):
    """Acts as a safety gateway for Paper & Live executions."""
    global local_portfolio
    action = action.upper()
    total_cost = current_price * quantity
    
    # -----------------------------------------------------------------
    # OPTION A: PAPER TRADING LAYER (Zero Risk)
    # -----------------------------------------------------------------
    if EXECUTION_MODE == "PAPER":
        print(f"\n[🛡️ SAFE PAPER EXECUTION] Attempting to {action} {quantity} shares of {symbol} at ${current_price:.2f}...")
        
        if action == "BUY":
            if local_portfolio["cash"] >= total_cost:
                local_portfolio["cash"] -= total_cost
                local_portfolio["positions"][symbol] = local_portfolio["positions"].get(symbol, 0) + quantity
                print(f"✅ PAPER SUCCESS | Bought {quantity} shares. Cash: ${local_portfolio['cash']:.2f} | Holding: {local_portfolio['positions'][symbol]} shares")
            else:
                print(f"❌ PAPER REJECTED | Insufficient Cash. Needed: ${total_cost:.2f}, Available: ${local_portfolio['cash']:.2f}")
                
        elif action == "SELL":
            current_holding = local_portfolio["positions"].get(symbol, 0)
            if current_holding >= quantity and quantity > 0:
                local_portfolio["positions"][symbol] -= quantity
                local_portfolio["cash"] += total_cost
                print(f"✅ PAPER SUCCESS | Sold {quantity} shares. Cash: ${local_portfolio['cash']:.2f}")
                if local_portfolio["positions"][symbol] == 0:
                    del local_portfolio["positions"][symbol]
            else:
                print(f"❌ PAPER REJECTED | Insufficient Shares. Holding: {current_holding}, Requested: {quantity}")
        return True

    # -----------------------------------------------------------------
    # OPTION B: LIVE TRADING LAYER (Real Money Risk)
    # -----------------------------------------------------------------
    elif EXECUTION_MODE == "LIVE":
        print(f"\n[⚠️ LIVE EXECUTION] WARNING: Routing real order to Webull API | {action} {quantity} {symbol}...")
        try:
            print("⚡ Webull Live API endpoint execution skipped (Safe placeholder bypass).")
            return True
        except Exception as api_err:
            print(f"❌ LIVE API ORDER FAILED: {api_err}")
            return False
            
    else:
        raise ValueError(f"Unknown EXECUTION_MODE: '{EXECUTION_MODE}'. Order blocked for safety.")

# =====================================================================
# 3. ENGINE ENTRYPOINT
# =====================================================================

print(f"Initializing Webull Routing Engine... Mode: [{EXECUTION_MODE}]")

try:
    # Initialize connection using Webull endpoints
    api_client = ApiClient(APP_KEY, APP_SECRET, REGION)
    api_client.add_endpoint(REGION, "api.webull.com")
    data_client = DataClient(api_client)
    print("Handshake successful! Market data channel linked.")

    selected_timespan = get_webull_timespan(BAR_RESOLUTION)

    print(f"Evaluating hierarchy rules for [{TARGET_SYMBOL}] at [{BAR_RESOLUTION}] resolution...")
    res = data_client.market_data.get_history_bar(TARGET_SYMBOL, Category.US_STOCK.name, selected_timespan.name, count="1200")
    
    if res.status_code != 200 or not res.json():
        raise Exception(f"Failed to fetch baseline tracking bars. Status: {res.status_code}")
        
    all_raw_bars = res.json()
    
    # Standardize candles and sort chronologically (oldest -> newest)
    formatted_bars = [format_candle(b) for b in all_raw_bars]
    formatted_bars.sort(key=lambda x: x['datetime'])
    
    latest_candle_time_dt = formatted_bars[-1]["datetime"]
    
    # Timezone-safe timestamp comparison (UTC vs UTC)
    now_utc_ts = datetime.now(timezone.utc).timestamp()
    is_market_currently_open = (now_utc_ts - latest_candle_time_dt.timestamp()) < 900
    has_date_override = SPECIFIED_DATE is not None

    # =====================================================================
    # HIERARCHY LEVEL 1: LIVE DATA STREAM
    # =====================================================================
    if is_market_currently_open and EXECUTION_MODE == "LIVE" and not has_date_override:
        print(f"➡️ [HIERARCHY 1] Market OPEN. Launching real-time streaming feed...")
        
        # Pre-seed buffer with last 50 historical bars before going live
        rolling_live_buffer = formatted_bars[-50:]
        
        while True:
            live_res = data_client.market_data.get_history_bar(TARGET_SYMBOL, Category.US_STOCK.name, selected_timespan.name)
            if live_res.status_code == 200 and live_res.json():
                latest_bar = format_candle(live_res.json()[-1])
                
                rolling_live_buffer.append(latest_bar)
                current_price = latest_bar['close']
                time_str = latest_bar['datetime'].strftime("%H:%M:%S")
                
                # Fetch position state
                current_shares = local_portfolio["positions"].get(TARGET_SYMBOL, 0)
                
                # Delegate to strategy
                signal_result = ACTIVE_STRATEGY(
                    rolling_live_buffer, 
                    **STRATEGY_PARAMS, 
                    current_position=current_shares
                )
                action_signal = signal_result.get("signal", "HOLD")
                reason = signal_result.get("reason", "")

                print(f"🟢 LIVE STREAM | {time_str} | {TARGET_SYMBOL}: ${current_price:.2f} | Position: {current_shares} | Signal: {action_signal} ({reason})")
                
                # Execute orders
                if action_signal == "BUY":
                    execute_order(TARGET_SYMBOL, "BUY", 10, current_price)
                elif action_signal == "SELL" and current_shares > 0:
                    execute_order(TARGET_SYMBOL, "SELL", current_shares, current_price)
            
            sleep_duration = 60 if BAR_RESOLUTION == "M1" else 10
            time.sleep(sleep_duration)

    # =====================================================================
    # HISTORICAL REPLAY / BACKTEST ENGINE
    # =====================================================================
    else:
        if EXECUTION_MODE == "PAPER" and is_market_currently_open:
            print(f"ℹ️ Market is open, running local PAPER simulation mode.")

        target_date_str = SPECIFIED_DATE if has_date_override else get_last_market_day()
        print(f"➡️ Replay Router Active. Target Session: [{target_date_str}]...")

        # Locate cutoff index for session walk
        start_index = None
        if SPECIFIED_TIME and has_date_override:
            time_cutoff = datetime.strptime(f"{target_date_str} {SPECIFIED_TIME}", "%Y-%m-%d %H:%M:%S")
            for idx, bar in enumerate(formatted_bars):
                bar_dt_naive = bar['datetime'].replace(tzinfo=None)
                if bar_dt_naive >= time_cutoff:
                    start_index = idx
                    break
        else:
            for idx, bar in enumerate(formatted_bars):
                if bar['datetime'].strftime("%Y-%m-%d") == target_date_str:
                    start_index = idx
                    break

        # Fallback if specific date/time was not found in returned history
        if start_index is None:
            print("⚠️ Selected target window was not found in buffer. Falling back to last 200 bars...")
            start_index = max(0, len(formatted_bars) - 200)

        # Extract pre-seeded historical bars (up to 50 preceding bars)
        seed_start = max(0, start_index - 50)
        rolling_candle_buffer = formatted_bars[seed_start:start_index]

        # Extract simulation loop bars
        session_bars = formatted_bars[start_index:]

        print(f"📊 Ready. Seeded buffer with {len(rolling_candle_buffer)} bars. Simulation contains {len(session_bars)} points.")
        print(f"⏱️ Pacing Speed: Processing 1 point every {SIMULATION_SPEED} real seconds.\n")

        for bar_data in session_bars:
            current_price = bar_data['close']
            time_str = bar_data['datetime'].strftime("%Y-%m-%d %H:%M:%S")

            # Push active bar into rolling buffer
            rolling_candle_buffer.append(bar_data)
            
            # Fetch position state from portfolio
            current_shares = local_portfolio["positions"].get(TARGET_SYMBOL, 0)
            
            # Compute strategy signal
            signal_result = ACTIVE_STRATEGY(
                rolling_candle_buffer, 
                **STRATEGY_PARAMS, 
                current_position=current_shares
            )
            action_signal = signal_result.get("signal", "HOLD")
            reason = signal_result.get("reason", "")

            print(f"🟡 REPLAY SIMULATION | {time_str} | {TARGET_SYMBOL}: ${current_price:.2f} | Position: {current_shares} | Signal: {action_signal} ({reason})")
            
            # Execute trade actions
            if action_signal == "BUY":
                execute_order(symbol=TARGET_SYMBOL, action="BUY", quantity=10, current_price=current_price)
            elif action_signal == "SELL" and current_shares > 0:
                execute_order(symbol=TARGET_SYMBOL, action="SELL", quantity=current_shares, current_price=current_price)
            
            time.sleep(SIMULATION_SPEED)
            
        print("\n🏁 Playback timeline completed.")

except KeyboardInterrupt:
    print("\nStopping safe execution router loop. Session terminated.")
except Exception as e:
    print(f"\n❌ Loop Execution Interrupted: {e}")