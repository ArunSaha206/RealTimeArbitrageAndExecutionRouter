# import os
# import time
# from datetime import datetime, timedelta
# from dotenv import load_dotenv
# from webull.core.client import ApiClient
# from webull.data.data_client import DataClient
# from webull.data.common.category import Category
# from webull.data.common.timespan import Timespan

# # Load keys from your hidden .env file
# load_dotenv()

# # =====================================================================
# # 1. PARAMETERS & USER OVERRIDES
# # =====================================================================
# EXECUTION_MODE = "PAPER"       # "PAPER" or "LIVE"
# TARGET_SYMBOL = "AAPL"         # Target ticker asset (e.g., NVDA, TSLA, MSFT)

# # Hierarchy Custom Inputs (Leave as None for automatic live / previous day defaults)
# SPECIFIED_DATE = None          # Format: "YYYY-MM-DD" (e.g., "2026-07-17")
# SPECIFIED_TIME = None          # Format: "HH:MM:SS"   (e.g., "10:15:00")

# # Local virtual wallet tracking (simulated paper profile)
# local_portfolio = {
#     "cash": 100000.00,  
#     "positions": {}     
# }

# APP_KEY = os.environ.get("WEBULL_APP_KEY")
# APP_SECRET = os.environ.get("WEBULL_APP_SECRET")
# REGION = os.environ.get("WEBULL_REGION_ID", "us")

# def parse_webull_time(time_value):
#     """
#     Safely converts Webull's time field into a Python datetime object,
#     handling both ISO strings and millisecond integer timestamps.
#     """
#     if isinstance(time_value, str):
#         # Handle formats like '2026-07-14T19:30:00.000+0000'
#         # Python's fromisoformat expects a colon in the timezone string (+00:00 instead of +0000)
#         if time_value.endswith("+0000"):
#             time_value = time_value[:-5] + "+00:00"
#         return datetime.fromisoformat(time_value)
#     else:
#         # Fallback for millisecond unix timestamps
#         return datetime.fromtimestamp(int(time_value) / 1000)

# def get_last_market_day():
#     """Calculates the date string of the most recent weekday."""
#     today = datetime.now()
#     if today.weekday() == 5:    # Saturday -> Friday
#         target = today - timedelta(days=1)
#     elif today.weekday() == 6:  # Sunday -> Friday
#         target = today - timedelta(days=2)
#     else:
#         target = today
#     return target.strftime("%Y-%m-%d")

# print(f"Initializing Webull Hierarchy Routing Engine... Mode: [{EXECUTION_MODE}]")

# try:
#     # 2. Build connection using live endpoints
#     api_client = ApiClient(APP_KEY, APP_SECRET, REGION)
#     api_client.add_endpoint(REGION, "api.webull.com")
#     data_client = DataClient(api_client)
#     print("Handshake successful! Market data channel linked.")

#     def fake_buy_order(symbol, qty, current_price, time_label):
#         """Simulates a buy order locally in memory."""
#         cost = qty * current_price
#         if local_portfolio["cash"] >= cost:
#             local_portfolio["cash"] -= cost
#             local_portfolio["positions"][symbol] = local_portfolio["positions"].get(symbol, 0) + qty
#             print(f"\n--- 📈 [PAPER TRADE EXECUTED AT {time_label}] ---")
#             print(f"Action: Bought {qty} shares of {symbol} at ${current_price:.2f}")
#             print(f"Total Cost: ${cost:.2f}")
#             print(f"Available Paper Cash: ${local_portfolio['cash']:.2f}")
#             print(f"Current Portfolio Positions: {local_portfolio['positions']}")
#             print(f"-----------------------------------------------------------\n")
#         else:
#             print(f"❌ Paper Trade Failed: Insufficient funds.")

#     # 3. Assess Hierarchy State Step-by-Step
#     print(f"Evaluating hierarchy rules for [{TARGET_SYMBOL}]...")
#     res = data_client.market_data.get_history_bar(TARGET_SYMBOL, Category.US_STOCK.name, Timespan.M1.name, count="1200")
    
#     if res.status_code != 200 or not res.json():
#         raise Exception(f"Failed to fetch baseline tracking bars. Status: {res.status_code}")
        
#     all_bars = res.json()
#     latest_candle = all_bars[-1]
    
#     # Parse the time using our safe helper
#     latest_candle_time_dt = parse_webull_time(latest_candle['time'])
    
#     # Check rule condition flags
#     # If the latest candle was generated within the last 15 minutes (900 seconds), market is live
#     is_market_currently_open = (datetime.now().timestamp() - latest_candle_time_dt.timestamp()) < 900
#     has_date_override = SPECIFIED_DATE is not None

#     # =====================================================================
#     # HIERARCHY LEVEL 1: LIVE DATA STREAM (Market open & no override set)
#     # =====================================================================
#     if is_market_currently_open and not has_date_override:
#         print(f"➡️ [HIERARCHY 1] Market is OPEN. Launching real-time streaming feed...")
#         while True:
#             live_res = data_client.market_data.get_history_bar(TARGET_SYMBOL, Category.US_STOCK.name, Timespan.M1.name)
#             if live_res.status_code == 200 and live_res.json():
#                 latest_bar = live_res.json()[-1]
#                 current_price = float(latest_bar['close'])
#                 time_str = parse_webull_time(latest_bar['time']).strftime("%H:%M:%S")
                
#                 print(f"🟢 LIVE STREAM | {time_str} | {TARGET_SYMBOL}: ${current_price:.2f}")
                
#                 # --- STRATEGY LOGIC ---
#                 should_trigger_buy = False 
#                 if should_trigger_buy:
#                     fake_buy_order(TARGET_SYMBOL, 10, current_price, f"{time_str} LIVE")
            
#             time.sleep(10)

#     # =====================================================================
#     # HISTORICAL PACKET PARSING (Handles Levels 2, 3, and 4)
#     # =====================================================================
#     else:
#         # Determine target replay date based on Priority hierarchy
#         if has_date_override:
#             target_date_str = SPECIFIED_DATE
#             if SPECIFIED_TIME:
#                 print(f"➡️ [HIERARCHY 4] Replaying historical date [{target_date_str}] starting at time [{SPECIFIED_TIME}]...")
#             else:
#                 print(f"➡️ [HIERARCHY 3] Replaying historical date [{target_date_str}] starting at Market Open...")
#         else:
#             target_date_str = get_last_market_day()
#             print(f"➡️ [HIERARCHY 2] Market is CLOSED. Defaulting to previous open day session: [{target_date_str}] starting at Market Open...")

#         # Segment and process candles chronologically
#         session_bars = []
#         for bar in all_bars:
#             bar_datetime = parse_webull_time(bar['time'])
#             bar_date_str = bar_datetime.strftime("%Y-%m-%d")
            
#             if bar_date_str == target_date_str:
#                 # If a starting time override is set, cut out candles before it
#                 if SPECIFIED_TIME and has_date_override:
#                     time_cutoff = datetime.strptime(f"{target_date_str} {SPECIFIED_TIME}", "%Y-%m-%d %H:%M:%S")
#                     if bar_datetime < time_cutoff:
#                         continue
#                 session_bars.append((bar_datetime, float(bar['close'])))
        
#         session_bars.sort(key=lambda x: x[0])

#         if not session_bars:
#             print(f"⚠️ API data payload did not contain explicit date [{target_date_str}] matching bounds.")
#             print("Extracting last available 390 bars from the buffer loop instead...")
#             for bar in all_bars[-390:]:
#                 session_bars.append((parse_webull_time(bar['time']), float(bar['close'])))

#         print(f"📊 Ready. Simulation size: {len(session_bars)} elements.")
        
#         # 4. Step-by-Step Backtest Walk Loop
#         for bar_time, current_price in session_bars:
#             time_str = bar_time.strftime("%H:%M:%S")
#             print(f"🟡 REPLAY SIMULATION | {target_date_str} {time_str} | {TARGET_SYMBOL}: ${current_price:.2f}")
            
#             # --- STRATEGY LOGIC ---
#             should_trigger_buy = False  
#             if should_trigger_buy:
#                 fake_buy_order(TARGET_SYMBOL, 10, current_price, time_str)
                
#             time.sleep(1) # Replay pacing speed (1 second = 1 historical bar minute)
            
#         print("\n🏁 Playback pipeline timeline exhaustion reached.")

# except KeyboardInterrupt:
#     print("\nStopping safe execution router loop. Session terminated.")
# except Exception as e:
#     print(f"\n❌ Loop Execution Interrupted: {e}")

import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from webull.core.client import ApiClient
from webull.data.data_client import DataClient
from webull.data.common.category import Category
from webull.data.common.timespan import Timespan

# Load keys from your hidden .env file
load_dotenv()

# =====================================================================
# 1. PARAMETERS & SIMULATION SPEED/RESOLUTION CONTROLS
# =====================================================================
EXECUTION_MODE = "PAPER"       # "PAPER" or "LIVE"
TARGET_SYMBOL = "AAPL"         # Target ticker asset

# ---- TIME-STEP CONTROLS ----
# Adjust how fast the script processes ticks (in real-world seconds)
SIMULATION_SPEED = 0.5         # 👈 e.g., 0.5 means wait half a second between ticks

# Adjust the resolution of each data point (How much market time elapses per tick)
# Available options: "M1" (1 min), "M5" (5 min), "M15" (15 min), "M30" (30 min), "H1" (1 hour), "D1" (1 day)
BAR_RESOLUTION = "M5"          # 👈 Change this to shift your analysis timeframe

# ---- HIERARCHY OVERRIDES ----
SPECIFIED_DATE = None          # Format: "YYYY-MM-DD"
SPECIFIED_TIME = None          # Format: "HH:MM:SS"

# Local virtual wallet tracking
local_portfolio = {
    "cash": 100000.00,  
    "positions": {}     
}

APP_KEY = os.environ.get("WEBULL_APP_KEY")
APP_SECRET = os.environ.get("WEBULL_APP_SECRET")
REGION = os.environ.get("WEBULL_REGION_ID", "us")

def get_webull_timespan(resolution_str):
    """Maps custom text resolution inputs directly to Webull API Timespan objects."""
    # Webull's python SDK typically maps hourly as Timespan.H1 or uses specific string literals
    # Let's cleanly protect this lookup by falling back gracefully if an attribute is missing.
    res_upper = resolution_str.upper()
    
    try:
        if res_upper == "M1": return Timespan.M1
        elif res_upper == "M5": return Timespan.M5
        elif res_upper == "M15": return Timespan.M15
        elif res_upper == "M30": return Timespan.M30
        elif res_upper == "H1": 
            # If the library uses a different hourly name, handle it here
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

print(f"Initializing Webull Routing Engine... Mode: [{EXECUTION_MODE}]")

try:
    # 2. Build connection using live endpoints
    api_client = ApiClient(APP_KEY, APP_SECRET, REGION)
    api_client.add_endpoint(REGION, "api.webull.com")
    data_client = DataClient(api_client)
    print("Handshake successful! Market data channel linked.")

    # Select timespan based on user configuration
    selected_timespan = get_webull_timespan(BAR_RESOLUTION)

    # 3. Assess Hierarchy State Step-by-Step
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
    # HIERARCHY LEVEL 1: LIVE DATA STREAM
    # =====================================================================
    if is_market_currently_open and not has_date_override:
        print(f"➡️ [HIERARCHY 1] Market is OPEN. Launching real-time streaming feed at [{BAR_RESOLUTION}] tracking cycles...")
        while True:
            live_res = data_client.market_data.get_history_bar(TARGET_SYMBOL, Category.US_STOCK.name, selected_timespan.name)
            if live_res.status_code == 200 and live_res.json():
                latest_bar = live_res.json()[-1]
                current_price = float(latest_bar['close'])
                time_str = parse_webull_time(latest_bar['time']).strftime("%H:%M:%S")
                print(f"🟢 LIVE STREAM | {time_str} | {TARGET_SYMBOL}: ${current_price:.2f}")
            
            # Match live data updates to resolution frame pacing (minimum 10s fallback)
            sleep_duration = 60 if BAR_RESOLUTION == "M1" else 10
            time.sleep(sleep_duration)

    # =====================================================================
    # HISTORICAL PACKET PARSING (Handles Levels 2, 3, and 4)
    # =====================================================================
    else:
        if has_date_override:
            target_date_str = SPECIFIED_DATE
            mode_msg = f"[HIERARCHY 4] starting at {SPECIFIED_TIME}" if SPECIFIED_TIME else "[HIERARCHY 3] starting at Market Open"
            print(f"➡️ {mode_msg} on explicit date [{target_date_str}]...")
        else:
            target_date_str = get_last_market_day()
            print(f"➡️ [HIERARCHY 2] Market Closed. Defaulting to last active day: [{target_date_str}]...")

        # Segment and process candles chronologically
        session_bars = []
        for bar in all_bars:
            bar_datetime = parse_webull_time(bar['time'])
            bar_date_str = bar_datetime.strftime("%Y-%m-%d")
            
            if bar_date_str == target_date_str:
                if SPECIFIED_TIME and has_date_override:
                    time_cutoff = datetime.strptime(f"{target_date_str} {SPECIFIED_TIME}", "%Y-%m-%d %H:%M:%S")
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
            
            # Your strategy calculations run here...
            should_trigger_buy = False  
            
            # Apply your configurable delay pacing
            time.sleep(SIMULATION_SPEED)
            
        print("\n🏁 Playback pipeline timeline exhaustion reached.")

except KeyboardInterrupt:
    print("\nStopping safe execution router loop. Session terminated.")
except Exception as e:
    print(f"\n❌ Loop Execution Interrupted: {e}")