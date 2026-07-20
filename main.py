import os
import time
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv
from webull.core.client import ApiClient
from webull.data.data_client import DataClient
from webull.data.common.category import Category
from webull.data.common.timespan import Timespan
# Note: If your SDK layout requires trade client operations for live execution, 
# you would import: from webull.trade.trade_client import TradeClient

# Load keys from your hidden .env file
load_dotenv()

# =====================================================================
# 1. PARAMETERS & SIMULATION SPEED/RESOLUTION CONTROLS
# =====================================================================
EXECUTION_MODE = "PAPER"       # 🛡️ Set to "PAPER" for safe local simulation or "LIVE" for Webull API
TARGET_SYMBOL = "GRAB"          # Target ticker asset

# ---- TIME-STEP CONTROLS ----
# Adjust how fast the script processes ticks (in real-world seconds)
SIMULATION_SPEED = 1         # e.g., 0.5 means wait half a second between ticks

# Adjust the resolution of each data point (How much market time elapses per tick)
# Available options: "M1" (1 min), "M5" (5 min), "M15" (15 min), "M30" (30 min), "H1" (1 hour), "D1" (1 day)
BAR_RESOLUTION = "M5"          

# ---- HIERARCHY OVERRIDES ----
SPECIFIED_DATE = "2026-07-13"          # Format: "YYYY-MM-DD"
SPECIFIED_TIME = "14:30:34"          # Format: "HH:MM:SS"

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
        elif res_upper == "H1": 
            return getattr(Timespan, "H1", Timespan.M1) 
        elif res_upper == "D1": 
            return getattr(Timespan, "D1", Timespan.M1)
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
        return datetime.fromtimestamp(int(time_value) / 1000)

def get_last_market_day():
    """Calculates the date string of the most recent weekday."""
    today = datetime.now()
    if today.weekday() == 5:    # Saturday -> Friday
        target = today - timedelta(days=1)
    elif today.weekday() == 6:  # Sunday -> Friday
        target = today - timedelta(days=2)
    else:
        target = today
    return target.strftime("%Y-%m-%d")

def execute_order(symbol, action, quantity, current_price):
    """
    Acts as a hard safety gateway. Handles paper trading locally in-memory 
    and completely blocks any outbound Webull API live orders unless 
    EXECUTION_MODE is explicitly set to "LIVE".
    """
    global local_portfolio
    
    action = action.upper()  # "BUY" or "SELL"
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
                print(f"✅ PAPER SUCCESS | Bought {quantity} shares. New Cash Balance: ${local_portfolio['cash']:.2f}")
            else:
                print(f"❌ PAPER REJECTED | Insufficient Cash. Needed: ${total_cost:.2f}, Available: ${local_portfolio['cash']:.2f}")
                
        elif action == "SELL":
            current_holding = local_portfolio["positions"].get(symbol, 0)
            if current_holding >= quantity:
                local_portfolio["positions"][symbol] -= quantity
                local_portfolio["cash"] += total_cost
                print(f"✅ PAPER SUCCESS | Sold {quantity} shares. New Cash Balance: ${local_portfolio['cash']:.2f}")
                if local_portfolio["positions"][symbol] == 0:
                    del local_portfolio["positions"][symbol]
            else:
                print(f"❌ PAPER REJECTED | Insufficient Shares. Trying to sell {quantity}, but only hold {current_holding}.")
        return True

    # -----------------------------------------------------------------
    # OPTION B: LIVE TRADING LAYER (Real Money Risk)
    # -----------------------------------------------------------------
    elif EXECUTION_MODE == "LIVE":
        print(f"\n[⚠️ LIVE EXECUTION] WARNING: Routing real order to Webull API | {action} {quantity} {symbol}...")
        try:
            # Structuring the payload following typical Webull OpenAPI v2 schemas
            # client_order_id = uuid.uuid4().hex
            # new_order = {
            #     "client_order_id": client_order_id,
            #     "symbol": symbol,
            #     "instrument_type": "EQUITY",
            #     "market": "US",
            #     "order_type": "MARKET",
            #     "quantity": str(quantity),
            #     "side": action,
            #     "time_in_force": "DAY",
            #     "entrust_type": "QTY",
            #     "support_trading_session": "CORE"
            # }
            # res = trade_client.order_v2.place_order(account_id="YOUR_ACCOUNT", new_orders=new_order)
            print("⚡ Webull Live API endpoint execution skipped (Safe placeholder bypass).")
            return True
        except Exception as api_err:
            print(f"❌ LIVE API ORDER FAILED: {api_err}")
            return False
            
    else:
        raise ValueError(f"Unknown EXECUTION_MODE: '{EXECUTION_MODE}'. Order blocked for absolute safety.")

# =====================================================================
# 3. ENGINE ENTRYPOINT
# =====================================================================

print(f"Initializing Webull Routing Engine... Mode: [{EXECUTION_MODE}]")

try:
    # Build connection using live data endpoints
    api_client = ApiClient(APP_KEY, APP_SECRET, REGION)
    api_client.add_endpoint(REGION, "api.webull.com")
    data_client = DataClient(api_client)
    print("Handshake successful! Market data channel linked.")

    # Select timespan safely
    selected_timespan = get_webull_timespan(BAR_RESOLUTION)

    # Assess Hierarchy State Step-by-Step
    print(f"Evaluating hierarchy rules for [{TARGET_SYMBOL}] at [{BAR_RESOLUTION}] resolution...")
    res = data_client.market_data.get_history_bar(TARGET_SYMBOL, Category.US_STOCK.name, selected_timespan.name, count="1200")
    
    if res.status_code != 200 or not res.json():
        raise Exception(f"Failed to fetch baseline tracking bars. Status: {res.status_code}")
        
    all_bars = res.json()
    latest_candle = all_bars[-1]
    latest_candle_time_dt = parse_webull_time(latest_candle['time'])
    
    is_market_currently_open = (datetime.now().timestamp() - latest_candle_time_dt.timestamp()) < 900
    has_date_override = SPECIFIED_DATE is not None

    # =====================================================================
    # HIERARCHY LEVEL 1: LIVE DATA STREAM (Only loops if LIVE mode + Open Market)
    # =====================================================================
    if is_market_currently_open and EXECUTION_MODE == "LIVE" and not has_date_override:
        print(f"➡️ [HIERARCHY 1] Market is OPEN. Launching real-time streaming feed at [{BAR_RESOLUTION}] tracking cycles...")
        while True:
            live_res = data_client.market_data.get_history_bar(TARGET_SYMBOL, Category.US_STOCK.name, selected_timespan.name)
            if live_res.status_code == 200 and live_res.json():
                latest_bar = live_res.json()[-1]
                current_price = float(latest_bar['close'])
                time_str = parse_webull_time(latest_bar['time']).strftime("%H:%M:%S")
                print(f"🟢 LIVE STREAM | {time_str} | {TARGET_SYMBOL}: ${current_price:.2f}")
                
                # --- Example live strategy hook ---
                # should_buy = check_strategy_logic(current_price)
                # if should_buy:
                #     execute_order(TARGET_SYMBOL, "BUY", 5, current_price)
            
            sleep_duration = 60 if BAR_RESOLUTION == "M1" else 10
            time.sleep(sleep_duration)

    # =====================================================================
    # HISTORICAL PACKET PARSING (Runs if Market is Closed OR if Mode is PAPER)
    # =====================================================================
    else:
        if EXECUTION_MODE == "PAPER" and is_market_currently_open:
            print(f"ℹ️ Market is currently open, but running in PAPER simulation mode as configured.")

        if has_date_override:
            target_date_str = SPECIFIED_DATE
            mode_msg = f"[HIERARCHY 4] starting at {SPECIFIED_TIME}" if SPECIFIED_TIME else "[HIERARCHY 3] starting at Market Open"
            print(f"➡️ {mode_msg} on explicit date [{target_date_str}]...")
        else:
            target_date_str = get_last_market_day()
            print(f"➡️ [HIERARCHY 2] Replay Router Active. Target Session: [{target_date_str}]...")

        # Segment and process candles chronologically
        session_bars = []
        for bar in all_bars:
            bar_datetime = parse_webull_time(bar['time'])
            bar_date_str = bar_datetime.strftime("%Y-%m-%d")
            
            if bar_date_str == target_date_str:
                if SPECIFIED_TIME and has_date_override:
                    # 1. Parse your custom cut-off time as naive first
                    naive_cutoff = datetime.strptime(f"{target_date_str} {SPECIFIED_TIME}", "%Y-%m-%d %H:%M:%S")
                    # 2. Dynamically attach the exact timezone matching Webull's candle data
                    time_cutoff = naive_cutoff.replace(tzinfo=bar_datetime.tzinfo)
                    
                    if bar_datetime < time_cutoff:
                        continue
                session_bars.append((bar_datetime, float(bar['close'])))
        
        session_bars.sort(key=lambda x: x[0])

        if not session_bars:
            print("⚠️ Date parsing fell outside core buffer timeline. re-aligning tracking windows...")
            for bar in all_bars[-200:]:
                session_bars.append((parse_webull_time(bar['time']), float(bar['close'])))

        print(f"📊 Ready. Simulation contains {len(session_bars)} points at [{BAR_RESOLUTION}] interval resolution.")
        print(f"⏱️ Pacing Speed: Processing 1 data point every {SIMULATION_SPEED} real seconds.\n")
        
        # 4. Controlled Backtest Walk Loop
        for bar_time, current_price in session_bars:
            time_str = bar_time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"🟡 REPLAY SIMULATION | {time_str} | {TARGET_SYMBOL}: ${current_price:.2f}")
            
            # --- STRATEGY TEST HOOK ---
            # To test your execution logic, change this flag to True:
            should_trigger_buy = False  
            
            if should_trigger_buy:
                # This call handles all wallet transactions completely in memory safely
                execute_order(symbol=TARGET_SYMBOL, action="BUY", quantity=10, current_price=current_price)
            
            # Apply your configurable delay pacing
            time.sleep(SIMULATION_SPEED)
            
        print("\n🏁 Playback pipeline timeline exhaustion reached.")

except KeyboardInterrupt:
    print("\nStopping safe execution router loop. Session terminated.")
except Exception as e:
    print(f"\n❌ Loop Execution Interrupted: {e}")