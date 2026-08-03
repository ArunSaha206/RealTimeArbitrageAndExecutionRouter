from strategies.FiveMinute.Support import M5supportR3
from strategies.FiveMinute.Support import M5supportR2
from strategies.FiveMinute.Support import M5supportR1
from strategies.FiveMinute.Support import M5vixsupport


# =====================================================================
# 1. STRATEGY SELECTION
# =====================================================================
# The backtester will now run each of these in sequence and compare them at the end.
ACTIVE_STRATEGIES = [M5supportR1, M5supportR2, M5supportR3]  # List of strategies to run, buggy when optimizing with multiple active

# =====================================================================
# 2. BACKTEST ENGINE CONFIGURATION
# =====================================================================
STARTING_CASH_PER_TICKER = 3000.00     
RISK_FREE_RATE = 0.04                  

# ---------------------------------------------------------------------
# 3. DATA PROVIDER ROUTING
# ---------------------------------------------------------------------
HISTORICAL_PROVIDER = "DATABENTO" 

# =====================================================================
# 4. TAX CONFIGURATION
# =====================================================================
ENABLE_TAXES = True               # Toggle tax modeling on/off
ORDINARY_INCOME_TAX_RATE = 0.24   # 24% Federal

# =====================================================================
# 5. REGIME & UNIVERSE MAPPING
# =====================================================================
ACTIVE_ASSET_TYPE = "STOCKS"  # Toggle this between "STOCKS" or "ETFS"

REGIME_WINDOWS = {
    "covid_crash_2020": {
        "start": "2020-02-14", 
        "end": "2020-05-15",
        "stocks": ["AAPL", "MSFT", "AMZN", "TSLA", "FB", "GOOGL", "NVDA", "AMD", "INTC", "BA",
                  "DIS", "JPM", "BAC", "WFC", "C", "V", "MA", "PYPL", "CSCO", "PEP",
                  "KO", "CMCSA", "NFLX", "PFE", "MRK", "XOM", "CVX", "UNH", "HD", "PG",
                  "JNJ", "ABBV", "CRM", "AAL", "DAL", "UAL", "CCL", "RCL", "NCLH", "ZM",
                  "MRNA", "PTON", "DOCU", "WMT", "TGT", "COST", "T", "VZ", "UBER", "LYFT"],
        "etfs":   ["SPY", "QQQ", "IWM", "XLK", "XLY", "XLF", "XLE", "XLU", "GLD", "TLT"]
    },
    "bull_run_2021": {
        "start": "2021-01-01", 
        "end": "2021-12-31",
        "stocks": ["TSLA", "AAPL", "AMC", "GME", "BB", "NOK", "NVDA", "MSFT", "AMZN", "NIO",
                  "AMD", "PLTR", "FB", "BABA", "SQ", "ROKU", "ZM", "PTON", "DKNG", "COIN",
                  "HOOD", "NFLX", "F", "RIVN", "LCID", "SOFI", "JPM", "BAC", "WFC", "BA",
                  "DIS", "UBER", "LYFT", "ABNB", "DASH", "SNOW", "CRWD", "PYPL", "V", "MA",
                  "TGT", "WMT", "XOM", "CVX", "PFE", "MRNA", "JNJ", "INTC", "CSCO", "MU"],
        "etfs":   ["SPY", "QQQ", "IWM", "XLK", "XLY", "XLF", "XLE", "XLU", "GLD", "TLT"]
    },
    "bear_chop_2022": {
        "start": "2022-01-01", 
        "end": "2022-12-31",
        "stocks": ["TSLA", "AAPL", "AMZN", "NVDA", "AMD", "FB", "META", "MSFT", "GOOGL", "F", 
                  "BABA", "NIO", "BAC", "SNAP", "NFLX", "JPM", "WFC", "C", "XOM", "CVX", 
                  "OXY", "COP", "HAL", "SLB", "PFE", "MRNA", "UNH", "JNJ", "LLY", "ABBV", 
                  "MRK", "T", "VZ", "DIS", "BA", "UBER", "PYPL", "SQ", "COIN", "RBLX", 
                  "PLTR", "INTC", "MU", "QCOM", "TGT", "WMT", "COST", "HD", "LOW", "V"],
        "etfs":   ["SPY", "QQQ", "IWM", "XLK", "XLY", "XLF", "XLE", "XLU", "GLD", "TLT"]
    },
    "recent_2023_2024": {
        "start": "2023-01-01", 
        "end": "2024-05-01",
        "stocks": ["NVDA", "TSLA", "AAPL", "AMD", "MSFT", "AMZN", "META", "GOOGL", "SMCI", "PLTR",
                  "ARM", "INTC", "MU", "QCOM", "TSM", "AVGO", "MARA", "RIOT", "COIN", "CVNA",
                  "UPST", "RBLX", "UBER", "SOFI", "PLUG", "HOOD", "DIS", "BA", "JPM", "BAC",
                  "WFC", "C", "XOM", "CVX", "LLY", "NVO", "MRK", "PFE", "JNJ", "UNH",
                  "V", "MA", "NFLX", "CRM", "SNOW", "CRWD", "PANW", "WMT", "COST", "TGT"],
        "etfs":   ["SPY", "QQQ", "IWM", "XLK", "XLY", "XLF", "XLE", "XLU", "GLD", "TLT"]
    }
}