# """
# BacktestControlCenter.py

# Single source of truth for BACKTEST ENGINE configuration:
#   - which strategy module is active
#   - which tickers to test
#   - bar resolution
#   - starting cash per ticker
#   - days to test
#   - risk-free rate assumption

# Deliberately NOT controlled here (owned by the strategy module itself,
# e.g. M5breakout.py): bar resolution, position sizing mode, fixed share
# quantity, lookback / exit_lookback. Each strategy is self-contained and
# exposes its own get_params(), so swapping ACTIVE_STRATEGY below is
# enough to change strategy behavior end-to-end -- no other file needs
# editing.
# """

# import M5breakout

# # =====================================================================
# # 1. STRATEGY SELECTION
# # =====================================================================
# # Point this at any module that implements:
# #   - analyze(candle_history, lookback, exit_lookback, current_position) -> dict
# #   - get_params() -> dict {lookback, exit_lookback, position_mode, fixed_share_qty}
# ACTIVE_STRATEGY = M5breakout

# # =====================================================================
# # 2. BACKTEST ENGINE CONFIGURATION
# # =====================================================================
# STARTING_CASH_PER_TICKER = 3000.00     # Virtual starting cash allocated per asset
# DAYS_TO_TEST = 50                      # Calendar days back to evaluate
# RISK_FREE_RATE = 0.04                  # 4% annualized risk-free rate assumption for Sharpe Ratio

# # =====================================================================
# # 3. TICKER UNIVERSE
# # =====================================================================
# DEFAULT_UNIVERSE = ["QQQ", "NVDA", "PYPL", "CAVA", "GME", "SPCX", "ALAB"]
# QQQ = ["QQQ"]
# SPCX = ["SPCX"]
# CAVA = ["CAVA"]
# NVDA = ["NVDA"]

# # --- STRATEGY & SECTOR BUCKETS ---
# LEVERAGED_PAIRS = ["TQQQ", "SQQQ"]
# PAIRS = ["PSQ", "QQQM"]
# TECH_GIANTS = ["AAPL", "MSFT", "NVDA", "AMD", "GOOGL"]
# HIGH_BETA = ["TSLA", "NVDA", "AMZN", "META"]
# ETFS_ONLY = ["SPY", "QQQ", "IWM", "XLE", "XLF"]

# # --- ACTIVE BENCHMARK ---
# # Set ACTIVE_UNIVERSE to whichever list you want to run right now
# ACTIVE_UNIVERSE = DEFAULT_UNIVERSE

















import M5breakout

# =====================================================================
# 1. STRATEGY SELECTION
# =====================================================================
ACTIVE_STRATEGY = M5breakout

# =====================================================================
# 2. BACKTEST ENGINE CONFIGURATION
# =====================================================================
STARTING_CASH_PER_TICKER = 3000.00     
RISK_FREE_RATE = 0.04                  

# ---------------------------------------------------------------------
# NEW: DATA PROVIDER ROUTING
# ---------------------------------------------------------------------
HISTORICAL_PROVIDER = "DATABENTO" 

# =====================================================================
# 3. REGIME & UNIVERSE MAPPING
# =====================================================================
ACTIVE_ASSET_TYPE = "ETFS"  # Toggle this between "STOCKS" or "ETFS"

# By nesting the universe inside the regime, you guarantee the backtester 
# trades the right assets for the right era, avoiding survivorship bias.
REGIME_WINDOWS = {
    "covid_crash_2020": {
        "start": "2020-02-14", 
        "end": "2020-05-15",
        "stocks": ["AAPL", "MSFT", "AMZN", "TSLA", "FB", "GOOGL", "NVDA", "AMD", "INTC", "BA",
                  "DIS", "JPM", "BAC", "WFC", "C", "V", "MA", "PYPL", "CSCO", "PEP",
                  "KO", "CMCSA", "NFLX", "PFE", "MRK", "XOM", "CVX", "UNH", "HD", "PG",
                  "JNJ", "ABBV", "CRM", "AAL", "DAL", "UAL", "CCL", "RCL", "NCLH", "ZM",
                  "MRNA", "PTON", "DOCU", "WMT", "TGT", "COST", "T", "VZ", "UBER", "LYFT"],   # 2020 Volume Leaders
        "etfs":   ["SPY", "QQQ", "IWM", "XLK", "XLY", "XLF", "XLE", "XLU", "GLD", "TLT"]
    },
    "bull_run_2021": {
        "start": "2021-01-01", 
        "end": "2021-12-31",
        "stocks": ["TSLA", "AAPL", "AMC", "GME", "BB", "NOK", "NVDA", "MSFT", "AMZN", "NIO",
                  "AMD", "PLTR", "FB", "BABA", "SQ", "ROKU", "ZM", "PTON", "DKNG", "COIN",
                  "HOOD", "NFLX", "F", "RIVN", "LCID", "SOFI", "JPM", "BAC", "WFC", "BA",
                  "DIS", "UBER", "LYFT", "ABNB", "DASH", "SNOW", "CRWD", "PYPL", "V", "MA",
                  "TGT", "WMT", "XOM", "CVX", "PFE", "MRNA", "JNJ", "INTC", "CSCO", "MU"],   # 2021 Volume Leaders
        "etfs":   ["SPY", "QQQ", "IWM", "XLK", "XLY", "XLF", "XLE", "XLU", "GLD", "TLT"]
    },
    "bear_chop_2022": {
        "start": "2022-01-01", 
        "end": "2022-12-31",
        "stocks": ["TSLA", "AAPL", "AMZN", "NVDA", "AMD", "META", "MSFT", "GOOGL", "F", "BABA",
                  "NIO", "BAC", "SNAP", "NFLX", "JPM", "WFC", "C", "XOM", "CVX", "OXY",
                  "COP", "HAL", "SLB", "PFE", "MRNA", "UNH", "JNJ", "LLY", "ABBV", "MRK",
                  "T", "VZ", "DIS", "BA", "UBER", "PYPL", "SQ", "COIN", "RBLX", "PLTR",
                  "INTC", "MU", "QCOM", "TGT", "WMT", "COST", "HD", "LOW", "V", "MA"],   # 2022 Volume Leaders
        "etfs":   ["SPY", "QQQ", "IWM", "XLK", "XLY", "XLF", "XLE", "XLU", "GLD", "TLT"]
    },
    "recent_2023_2024": {
        "start": "2023-01-01", 
        "end": "2024-05-01",
        "stocks": ["NVDA", "TSLA", "AAPL", "AMD", "MSFT", "AMZN", "META", "GOOGL", "SMCI", "PLTR",
                  "ARM", "INTC", "MU", "QCOM", "TSM", "AVGO", "MARA", "RIOT", "COIN", "CVNA",
                  "UPST", "RBLX", "UBER", "SOFI", "PLUG", "HOOD", "DIS", "BA", "JPM", "BAC",
                  "WFC", "C", "XOM", "CVX", "LLY", "NVO", "MRK", "PFE", "JNJ", "UNH",
                  "V", "MA", "NFLX", "CRM", "SNOW", "CRWD", "PANW", "WMT", "COST", "TGT"],  # Modern Volume Leaders
        "etfs":   ["SPY", "QQQ", "IWM", "XLK", "XLY", "XLF", "XLE", "XLU", "GLD", "TLT"]
    }
}