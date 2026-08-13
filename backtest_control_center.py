from strategies.FifteenMinute import M15EMAPullback, M15geminiV2, M15geminiVIX
from strategies.FiveMinute.Support import (
    M5supportR1,
    M5supportR2,
    M5supportR3,
    M5vixsupport,
)
from strategies.OneHour import H1gemini, H1geminiNARROW, H1geminiWIDE

# =====================================================================
# 1. STRATEGY & UNIVERSE SELECTION
# =====================================================================
ACTIVE_STRATEGIES = [M15EMAPullback]

# TOGGLE YOUR UNIVERSE LOGIC HERE:
# Options:
#   • "core_stratified"          -> 50 stocks (Macro GICS weighted across all 11 sectors)
#   • "top_dollar_volume_25"     -> 25 stocks (Deepest order books / highest turnover)
#   • "cross_sectional_spread"   -> 20 stocks (10 paired intra-sector assets for Stat-Arb)
#   • "high_beta_growth"         -> 20 stocks (High beta, growth, tech, and momentum)
#   • "defensive_value"          -> 20 stocks (Low beta, staples, healthcare, utilities)
#   • "cyclical_macro"           -> 20 stocks (Industrials, Energy, Autos, Semis, Materials)
#   • "tech_semiconductor_heavy" -> 20 stocks (Pure-play enterprise tech & semiconductors)
ACTIVE_UNIVERSE_LOGIC = "defensive_value"

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
ENABLE_TAXES = True               
ORDINARY_INCOME_TAX_RATE = 0.24   

# =====================================================================
# 5. EXECUTION FRICTION CONFIGURATION (MULTI-SWEEP)
# =====================================================================
SLIPPAGE_RATES_BPS = [2.0] 
COMMISSION_PER_ORDER = 0.00

# =====================================================================
# 6. DATASET PHASE CONTROLLER & TAG SELECTOR KNOB
# =====================================================================
DATASET_PHASE = "TRAINING_2"  
ACTIVE_ASSET_TYPE = "STOCKS"  

# FILTER STANDALONE BACKTESTS BY REGIME TAG
# Options: "ALL", "BULL", "BEAR", "CHOP" or combinations e.g. ["BEAR", "CHOP"]
TARGET_REGIME_TAGS = ["ALL"]

# ---------------------------------------------------------------------
# PHASE 1: STANDARD TRAINING DATA (2020-2024)
# ---------------------------------------------------------------------
REGIME_WINDOWS_TRAIN_1 = {
    "covid_crash_2020": {
        "tag": "BEAR",
        "start": "2020-02-19", 
        "end": "2020-03-23",
        "universes": {
            "core_stratified": [
                "AAPL", "MSFT", "INTC", "CSCO", "ADBE", "CRM", "ORCL", "IBM", "TXN", "QCOM", "AMAT", "MU", "NVDA",
                "JPM", "BAC", "WFC", "C", "GS", "MS", "V", "MA", "JNJ", "UNH", "PFE", "MRK", "ABT", "AMGN",
                "AMZN", "HD", "MCD", "NKE", "SBUX", "GOOGL", "FB", "NFLX", "DIS", "BA", "CAT", "HON", "UNP",
                "WMT", "PG", "KO", "XOM", "CVX", "COP", "NEE", "DUK", "AMT", "PLD", "LIN"
            ],
            "top_dollar_volume_25": [
                "AAPL", "MSFT", "AMZN", "FB", "GOOGL", "TSLA", "BA", "DIS", "NFLX", "AMD",
                "JPM", "BAC", "V", "MA", "INTC", "CSCO", "XOM", "CVX", "WMT", "PG",
                "HD", "UNH", "PFE", "JNJ", "VZ"
            ],
            "cross_sectional_spread": [
                "V", "MA", "INTC", "AMD", "KO", "PEP", "HD", "LOW", "XOM", "CVX",
                "JPM", "BAC", "MSFT", "GOOGL", "UNH", "ABT", "UPS", "FDX", "NEE", "DUK"
            ],
            "high_beta_growth": [
                "TSLA", "AMD", "NFLX", "PYPL", "SQ", "ZM", "PTON", "ROKU", "SHOP", "DOCU",
                "TWLO", "SPOT", "SNAP", "UBER", "LYFT", "OKTA", "CRWD", "DDOG", "NET", "NVDA"
            ],
            "defensive_value": [
                "JNJ", "PFE", "MRK", "PG", "KO", "PEP", "WMT", "COST", "NEE", "DUK",
                "SO", "VZ", "T", "ABT", "BMY", "CL", "KMB", "MCD", "WM", "RSG"
            ],
            "cyclical_macro": [
                "BA", "CAT", "DE", "UNP", "HON", "XOM", "CVX", "COP", "LIN", "FCX",
                "F", "GM", "DAL", "UAL", "JPM", "BAC", "INTC", "AMAT", "MU", "TXN"
            ],
            "tech_semiconductor_heavy": [
                "AAPL", "MSFT", "INTC", "AMD", "CSCO", "ORCL", "IBM", "TXN", "QCOM", "AMAT",
                "MU", "LRCX", "ADBE", "CRM", "NOW", "WDAY", "ADSK", "INTU", "NVDA", "AVGO"
            ]
        }
    },
    "bull_run_2021": {
        "tag": "BULL",
        "start": "2021-04-01", 
        "end": "2021-11-19",
        "universes": {
            "core_stratified": [
                "AAPL", "MSFT", "AMZN", "FB", "GOOGL", "TSLA", "NVDA", "JPM", "JNJ", "UNH", "HD", "PG", "BAC",
                "DIS", "ADBE", "NFLX", "CRM", "PFE", "MRNA", "ABBV", "NKE", "WMT", "KO", "PEP", "XOM",
                "CVX", "V", "MA", "PYPL", "INTC", "AMD", "CSCO", "QCOM", "TXN", "AVGO", "AMAT", "BA",
                "CAT", "UPS", "HON", "TGT", "COST", "NEE", "DUK", "SO", "PLD", "AMT", "FCX", "LIN", "MCD"
            ],
            "top_dollar_volume_25": [
                "TSLA", "AAPL", "AMZN", "MSFT", "FB", "GOOGL", "NVDA", "AMD", "MRNA", "BABA",
                "PYPL", "SQ", "DIS", "JPM", "BAC", "NFLX", "F", "NIO", "SHOP", "WMT",
                "COST", "COIN", "PLTR", "ROKU", "ZM"
            ],
            "cross_sectional_spread": [
                "NVDA", "AMD", "V", "MA", "GOOGL", "FB", "JPM", "BAC", "XOM", "CVX",
                "HD", "LOW", "KO", "PEP", "UNH", "JNJ", "CAT", "DE", "NEE", "SO"
            ],
            "high_beta_growth": [
                "TSLA", "MRNA", "SHOP", "SE", "SQ", "ROKU", "ZM", "PTON", "SNOW", "PLTR",
                "CRWD", "NET", "COIN", "HOOD", "UPST", "AFRM", "DKNG", "PENN", "RBLX", "U"
            ],
            "defensive_value": [
                "JNJ", "PFE", "ABBV", "PG", "KO", "PEP", "WMT", "COST", "TGT", "NEE",
                "DUK", "SO", "VZ", "T", "ABT", "BMY", "CL", "KMB", "WM", "RSG"
            ],
            "cyclical_macro": [
                "CAT", "DE", "FCX", "NUE", "XOM", "CVX", "EOG", "F", "GM", "AAL",
                "DAL", "UNP", "HON", "BA", "JPM", "MS", "AMAT", "LRCX", "MU", "LIN"
            ],
            "tech_semiconductor_heavy": [
                "AAPL", "MSFT", "NVDA", "AMD", "QCOM", "AVGO", "INTC", "AMAT", "LRCX", "MU",
                "TXN", "CRM", "ADBE", "NOW", "SNOW", "PLTR", "CRWD", "NET", "DDOG", "PANW"
            ]
        }
    },
    "bear_chop_2022": {
        "tag": "CHOP",
        "start": "2022-01-03", 
        "end": "2022-10-13",
        "universes": {
            "core_stratified": [
                "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "UNH", "JNJ", "XOM", "CVX", "JPM", "V", "PG", "HD",
                "CVX", "MA", "ABBV", "PFE", "LLY", "BAC", "KO", "PEP", "COST", "MRK", "TMO", "MCD",
                "WMT", "CSCO", "ACN", "DIS", "ADBE", "TXN", "VZ", "CRM", "AMD", "CMCSA", "NKE", "QCOM",
                "INTC", "COP", "OXY", "SLB", "CAT", "DE", "RTX", "LMT", "NEE", "DUK", "PLD", "AMT", "LIN"
            ],
            "top_dollar_volume_25": [
                "TSLA", "AAPL", "AMZN", "MSFT", "NVDA", "AMD", "GOOGL", "XOM", "CVX", "OXY",
                "JPM", "BAC", "BABA", "NFLX", "META", "ENPH", "UNH", "LLY", "PFE", "WMT",
                "COST", "HD", "DIS", "BA", "SQ"
            ],
            "cross_sectional_spread": [
                "XOM", "CVX", "OXY", "COP", "V", "MA", "MSFT", "GOOGL", "JPM", "BAC",
                "HD", "LOW", "KO", "PEP", "LLY", "UNH", "RTX", "LMT", "NEE", "DUK"
            ],
            "high_beta_growth": [
                "TSLA", "NVDA", "AMD", "SNOW", "CRWD", "DDOG", "NET", "PLTR", "RBLX", "SQ",
                "SHOP", "SE", "COIN", "META", "NFLX", "AMZN", "GOOGL", "PYPL", "ZM", "ROKU"
            ],
            "defensive_value": [
                "XOM", "CVX", "OXY", "COP", "LMT", "RTX", "NOC", "GD", "JNJ", "LLY",
                "MRK", "ABBV", "UNH", "PG", "KO", "PEP", "WMT", "COST", "NEE", "DUK"
            ],
            "cyclical_macro": [
                "XOM", "CVX", "OXY", "COP", "SLB", "HAL", "CAT", "DE", "LMT", "RTX",
                "NUE", "FCX", "LIN", "UNP", "JPM", "GS", "AMAT", "MU", "F", "GM"
            ],
            "tech_semiconductor_heavy": [
                "AAPL", "MSFT", "NVDA", "AMD", "INTC", "QCOM", "AVGO", "TXN", "AMAT", "LRCX",
                "MU", "CRM", "ADBE", "ORCL", "IBM", "CSCO", "NOW", "PANW", "SNPS", "CDNS"
            ]
        }
    },
    "correction_2023": {
        "tag": "CHOP",
        "start": "2023-07-31", 
        "end": "2023-10-27",
        "universes": {
            "core_stratified": [
                "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "LLY", "UNH", "JPM", "V", "JNJ",
                "XOM", "WMT", "PG", "MA", "AVGO", "HD", "CVX", "MRK", "ABBV", "COST", "PEP", "ADBE",
                "KO", "BAC", "CSCO", "CRM", "TMO", "MCD", "CMCSA", "AMD", "INTC", "QCOM", "TXN", "AMAT",
                "CAT", "GE", "UNP", "BA", "COP", "NEE", "CEG", "PLD", "AMT", "LIN", "ISRG", "NOW", "NFLX", "BKNG"
            ],
            "top_dollar_volume_25": [
                "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "AMD", "GOOGL", "AVGO", "PLTR",
                "NFLX", "LLY", "JPM", "BAC", "XOM", "CVX", "UNH", "WMT", "COST", "HD",
                "BA", "DIS", "COIN", "CRM", "SMCI"
            ],
            "cross_sectional_spread": [
                "NVDA", "AMD", "MSFT", "GOOGL", "V", "MA", "JPM", "BAC", "XOM", "CVX",
                "LLY", "UNH", "HD", "LOW", "KO", "PEP", "CAT", "GE", "NEE", "CEG"
            ],
            "high_beta_growth": [
                "NVDA", "AMD", "SMCI", "TSLA", "META", "AVGO", "PLTR", "CRWD", "PANW", "SNOW",
                "DDOG", "MDB", "CELH", "UBER", "ABNB", "SHOP", "COIN", "MARA", "RIOT", "CVNA"
            ],
            "defensive_value": [
                "LLY", "NVO", "JNJ", "MRK", "PFE", "UNH", "ELV", "PG", "KO", "PEP",
                "WMT", "COST", "NEE", "DUK", "SO", "CEG", "LMT", "RTX", "WM", "RSG"
            ],
            "cyclical_macro": [
                "CAT", "GE", "UNP", "BA", "HON", "ETN", "XOM", "CVX", "COP", "LIN",
                "FCX", "NUE", "JPM", "GS", "AMAT", "LRCX", "MU", "TSLA", "BKNG", "UBER"
            ],
            "tech_semiconductor_heavy": [
                "NVDA", "MSFT", "AAPL", "AMD", "AVGO", "QCOM", "AMAT", "LRCX", "INTC", "MU",
                "ADBE", "CRM", "NOW", "PANW", "SNPS", "CDNS", "ORCL", "CRWD", "SNOW", "PLTR"
            ]
        }
    },
    "ai_bull_2023_2024": {
        "tag": "BULL",
        "start": "2023-11-01", 
        "end": "2024-05-01",
        "universes": {
            "core_stratified": [
                "MSFT", "AAPL", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "LLY", "AVGO", "JPM", "UNH", "V",
                "XOM", "MA", "JNJ", "PG", "HD", "COST", "MRK", "ABBV", "CRM", "AMD", "CVX", "WMT",
                "BAC", "PEP", "KO", "LIN", "TMO", "MCD", "CSCO", "INTC", "QCOM", "AMAT", "LRCX", "MU",
                "DIS", "NFLX", "GE", "CAT", "ETN", "UBER", "COP", "VST", "CEG", "PLD", "AMT", "ISRG", "NOW", "CRWD"
            ],
            "top_dollar_volume_25": [
                "NVDA", "TSLA", "AMD", "AAPL", "MSFT", "AMZN", "META", "SMCI", "AVGO", "PLTR",
                "GOOGL", "ARM", "MU", "COIN", "MSTR", "MARA", "LLY", "JPM", "NFLX", "UBER",
                "WMT", "COST", "XOM", "CVX", "GE"
            ],
            "cross_sectional_spread": [
                "NVDA", "AMD", "MSFT", "GOOGL", "V", "MA", "JPM", "GS", "XOM", "CVX",
                "LLY", "UNH", "AMAT", "LRCX", "HD", "LOW", "KO", "PEP", "VST", "CEG"
            ],
            "high_beta_growth": [
                "NVDA", "AMD", "SMCI", "AVGO", "MU", "ARM", "PLTR", "CRWD", "META", "TSLA",
                "COIN", "MSTR", "MARA", "RIOT", "HOOD", "SOFI", "UBER", "CELH", "CVNA", "UPST"
            ],
            "defensive_value": [
                "LLY", "NVO", "UNH", "JNJ", "MRK", "ABBV", "PG", "KO", "PEP", "WMT",
                "COST", "TGT", "VST", "CEG", "NEE", "DUK", "SO", "GE", "ETN", "CAT"
            ],
            "cyclical_macro": [
                "GE", "CAT", "ETN", "UNP", "HON", "BA", "XOM", "CVX", "COP", "LIN",
                "FCX", "NUE", "JPM", "GS", "AXP", "AMAT", "LRCX", "MU", "UBER", "BKNG"
            ],
            "tech_semiconductor_heavy": [
                "NVDA", "MSFT", "AAPL", "AMD", "AVGO", "QCOM", "AMAT", "LRCX", "MU", "ARM",
                "SMCI", "PLTR", "CRM", "NOW", "CRWD", "PANW", "SNPS", "CDNS", "ORCL", "DELL"
            ]
        }
    }
}

# ---------------------------------------------------------------------
# PHASE 2: SECONDARY TRAINING DATA (2024-2025)
# ---------------------------------------------------------------------
REGIME_WINDOWS_TRAIN_2 = {
    "pre_election_chop_2024": {
        "tag": "CHOP",
        "start": "2024-06-01",
        "end": "2024-11-04",
        "universes": {
            "core_stratified": [
                "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "LLY", "TSLA", "AVGO", "JPM", "UNH", "V",
                "XOM", "MA", "JNJ", "PG", "HD", "COST", "MRK", "ABBV", "CRM", "AMD", "CVX", "WMT",
                "BAC", "PEP", "KO", "LIN", "MCD", "ORCL", "PLTR", "QCOM", "MU", "AMAT", "NOW", "PANW",
                "NFLX", "SPOT", "GE", "CAT", "ETN", "UBER", "PM", "OXY", "VST", "CEG", "PLD", "EQIX", "ISRG", "TJX"
            ],
            "top_dollar_volume_25": [
                "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "AMD", "AVGO", "PLTR", "GOOGL",
                "SMCI", "ARM", "MU", "ORCL", "COIN", "MSTR", "HOOD", "LLY", "JPM", "NFLX",
                "UBER", "SPOT", "WMT", "COST", "XOM"
            ],
            "cross_sectional_spread": [
                "NVDA", "AVGO", "MSFT", "GOOGL", "V", "MA", "JPM", "GS", "XOM", "CVX",
                "LLY", "UNH", "AMAT", "LRCX", "HD", "LOW", "KO", "PEP", "VST", "CEG"
            ],
            "high_beta_growth": [
                "NVDA", "AAPL", "AVGO", "PLTR", "TSLA", "AMD", "ARM", "MU", "CRWD", "PANW",
                "COIN", "MSTR", "HOOD", "SOFI", "RIVN", "SMCI", "CELH", "SPOT", "UBER", "RDDT"
            ],
            "defensive_value": [
                "LLY", "NVO", "UNH", "JNJ", "MRK", "ABBV", "WMT", "COST", "PM", "PG",
                "KO", "PEP", "VST", "CEG", "NEE", "SO", "DUK", "GE", "ETN", "WM"
            ],
            "cyclical_macro": [
                "GE", "CAT", "ETN", "UNP", "HON", "BA", "XOM", "CVX", "OXY", "LIN",
                "FCX", "NUE", "JPM", "GS", "AXP", "AMAT", "MU", "UBER", "TJX", "BKNG"
            ],
            "tech_semiconductor_heavy": [
                "NVDA", "AAPL", "MSFT", "AVGO", "AMD", "QCOM", "ORCL", "PLTR", "CRM", "MU",
                "AMAT", "LRCX", "NOW", "PANW", "CRWD", "ARM", "DELL", "SNPS", "CDNS", "MRVL"
            ]
        }
    },
    "election_rally_2024_2025": {
        "tag": "BULL",
        "start": "2024-11-05",
        "end": "2025-02-18",
        "universes": {
            "core_stratified": [
                "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "LLY", "TSLA", "AVGO", "JPM", "UNH", "V",
                "XOM", "MA", "JNJ", "PG", "HD", "COST", "MRK", "ABBV", "CRM", "AMD", "CVX", "WMT",
                "BAC", "PEP", "KO", "LIN", "MCD", "ORCL", "PLTR", "QCOM", "MU", "AMAT", "NOW", "TXN",
                "NFLX", "DIS", "GE", "CAT", "ETN", "UBER", "PM", "EOG", "VST", "CEG", "PLD", "EQIX", "ISRG", "BSX"
            ],
            "top_dollar_volume_25": [
                "TSLA", "NVDA", "PLTR", "MSTR", "COIN", "AAPL", "AMZN", "MSFT", "META", "GOOGL",
                "AMD", "AVGO", "HOOD", "MARA", "RIOT", "JPM", "GS", "NFLX", "LLY", "UBER",
                "WMT", "COST", "XOM", "CVX", "GE"
            ],
            "cross_sectional_spread": [
                "NVDA", "AMD", "PLTR", "AVGO", "V", "MA", "JPM", "GS", "COIN", "HOOD",
                "MSFT", "GOOGL", "XOM", "CVX", "LLY", "UNH", "HD", "LOW", "VST", "CEG"
            ],
            "high_beta_growth": [
                "TSLA", "PLTR", "MSTR", "COIN", "HOOD", "MARA", "RIOT", "NVDA", "AVGO", "ARM",
                "APP", "CRWD", "SOFI", "UPST", "CVNA", "RDDT", "UBER", "SPOT", "SMCI", "CELH"
            ],
            "defensive_value": [
                "JPM", "GS", "MS", "BAC", "WFC", "C", "LLY", "UNH", "JNJ", "ABBV",
                "WMT", "COST", "PM", "PG", "KO", "VST", "CEG", "NEE", "GE", "ETN"
            ],
            "cyclical_macro": [
                "GE", "CAT", "ETN", "UNP", "HON", "BA", "XOM", "CVX", "EOG", "LIN",
                "FCX", "NUE", "JPM", "GS", "MS", "GM", "TSLA", "AMAT", "MU", "UBER"
            ],
            "tech_semiconductor_heavy": [
                "NVDA", "AAPL", "MSFT", "AVGO", "PLTR", "AMD", "TXN", "ORCL", "CRM", "NOW",
                "MU", "QCOM", "AMAT", "LRCX", "ARM", "APP", "CRWD", "PANW", "SNPS", "CDNS"
            ]
        }
    },
    "tariff_shock_correction_2025": {
        "tag": "BEAR",
        "start": "2025-02-19",
        "end": "2025-04-08",
        "universes": {
            "core_stratified": [
                "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "LLY", "TSLA", "AVGO", "JPM", "UNH", "V",
                "XOM", "MA", "JNJ", "PG", "HD", "COST", "MRK", "ABBV", "CRM", "AMD", "CVX", "WMT",
                "BAC", "PEP", "KO", "LIN", "MCD", "ORCL", "PLTR", "QCOM", "MU", "AMAT", "NOW", "TXN",
                "NFLX", "TMUS", "GE", "CAT", "RTX", "LMT", "PM", "COP", "NEE", "SO", "PLD", "AMT", "ISRG", "TJX"
            ],
            "top_dollar_volume_25": [
                "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "AMD", "AVGO", "PLTR", "GOOGL",
                "MSTR", "COIN", "APP", "NFLX", "JPM", "GS", "LLY", "UNH", "WMT", "COST",
                "XOM", "CVX", "GE", "CAT", "UBER"
            ],
            "cross_sectional_spread": [
                "NVDA", "AVGO", "MSFT", "GOOGL", "V", "MA", "JPM", "GS", "XOM", "CVX",
                "LLY", "UNH", "RTX", "LMT", "HD", "LOW", "KO", "PEP", "NEE", "SO"
            ],
            "high_beta_growth": [
                "NVDA", "AMD", "AVGO", "TSLA", "PLTR", "MSTR", "COIN", "APP", "CRWD", "ARM",
                "MU", "SMCI", "HOOD", "SOFI", "UBER", "SPOT", "RDDT", "CVNA", "UPST", "CELH"
            ],
            "defensive_value": [
                "LMT", "RTX", "NOC", "GD", "LLY", "UNH", "MRK", "JNJ", "ABBV", "WMT",
                "COST", "PG", "PM", "KO", "PEP", "NEE", "SO", "DUK", "WM", "RSG"
            ],
            "cyclical_macro": [
                "GE", "CAT", "RTX", "LMT", "UNP", "HON", "XOM", "CVX", "COP", "LIN",
                "NUE", "FCX", "JPM", "BAC", "GS", "AMAT", "MU", "TJX", "MCD", "HD"
            ],
            "tech_semiconductor_heavy": [
                "NVDA", "MSFT", "AAPL", "AVGO", "AMD", "QCOM", "CRM", "ORCL", "PLTR", "NOW",
                "TXN", "AMAT", "LRCX", "MU", "ARM", "APP", "CRWD", "PANW", "SNPS", "CDNS"
            ]
        }
    },
    "trump_put_recovery_2025": {
        "tag": "BULL",
        "start": "2025-04-09",
        "end": "2025-07-31",
        "universes": {
            "core_stratified": [
                "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "LLY", "TSLA", "AVGO", "JPM", "UNH", "V",
                "XOM", "MA", "JNJ", "PG", "HD", "COST", "MRK", "ABBV", "CRM", "AMD", "CVX", "WMT",
                "BAC", "PEP", "KO", "LIN", "MCD", "ORCL", "PLTR", "QCOM", "MU", "AMAT", "NOW", "LRCX",
                "NFLX", "DIS", "GE", "CAT", "ETN", "UNP", "PM", "EOG", "VST", "CEG", "PLD", "EQIX", "ISRG", "BSX"
            ],
            "top_dollar_volume_25": [
                "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "AVGO", "PLTR", "AMD", "GOOGL",
                "MSTR", "COIN", "APP", "ARM", "NFLX", "JPM", "GS", "LLY", "UBER", "SPOT",
                "WMT", "COST", "XOM", "GE", "ETN"
            ],
            "cross_sectional_spread": [
                "NVDA", "AVGO", "PLTR", "AMD", "MSFT", "GOOGL", "V", "MA", "JPM", "GS",
                "XOM", "CVX", "LLY", "UNH", "AMAT", "LRCX", "HD", "LOW", "VST", "CEG"
            ],
            "high_beta_growth": [
                "NVDA", "AVGO", "PLTR", "TSLA", "MSTR", "COIN", "APP", "ARM", "AMD", "CRWD",
                "HOOD", "UBER", "SPOT", "SOFI", "RDDT", "CVNA", "UPST", "MARA", "RIOT", "MU"
            ],
            "defensive_value": [
                "JPM", "GS", "MS", "BAC", "WFC", "LLY", "UNH", "ABBV", "JNJ", "BSX",
                "WMT", "COST", "PM", "PG", "KO", "VST", "CEG", "NEE", "GE", "ETN"
            ],
            "cyclical_macro": [
                "GE", "CAT", "ETN", "UNP", "HON", "BA", "XOM", "CVX", "EOG", "LIN",
                "FCX", "NUE", "JPM", "GS", "MS", "AMAT", "LRCX", "MU", "UBER", "BKNG"
            ],
            "tech_semiconductor_heavy": [
                "NVDA", "AAPL", "MSFT", "AVGO", "PLTR", "AMD", "QCOM", "ORCL", "CRM", "NOW",
                "AMAT", "LRCX", "MU", "ARM", "APP", "CRWD", "PANW", "SNPS", "CDNS", "MRVL"
            ]
        }
    }
}

# ---------------------------------------------------------------------
# PHASE 3: FINAL OUT-OF-SAMPLE TESTING (Strictly unseen data)
# ---------------------------------------------------------------------
REGIME_WINDOWS_FINAL_TEST = {
    "latest_2025_2026": {
        "tag": "ALL",
        "start": "2025-08-01", 
        "end": "2026-08-01",
        "universes": {
            "core_stratified": [
                "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "LLY", "TSLA", "AVGO", "JPM", "UNH", "V",
                "XOM", "MA", "JNJ", "PG", "HD", "COST", "MRK", "ABBV", "CRM", "AMD", "CVX", "WMT",
                "BAC", "PEP", "KO", "LIN", "MCD", "ORCL", "PLTR", "QCOM", "MU", "AMAT", "NOW", "PANW",
                "NFLX", "DIS", "GE", "CAT", "ETN", "UBER", "PM", "COP", "VST", "CEG", "PLD", "EQIX", "ISRG", "BSX"
            ],
            "top_dollar_volume_25": [
                "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "AVGO", "PLTR", "AMD", "GOOGL",
                "MSTR", "COIN", "APP", "ARM", "NFLX", "JPM", "GS", "LLY", "UBER", "SPOT",
                "WMT", "COST", "XOM", "GE", "ETN"
            ],
            "cross_sectional_spread": [
                "NVDA", "AVGO", "MSFT", "GOOGL", "V", "MA", "JPM", "GS", "XOM", "CVX",
                "LLY", "UNH", "AMAT", "LRCX", "HD", "LOW", "KO", "PEP", "VST", "CEG"
            ],
            "high_beta_growth": [
                "NVDA", "AVGO", "PLTR", "TSLA", "MSTR", "COIN", "APP", "ARM", "AMD", "CRWD",
                "HOOD", "UBER", "SPOT", "SOFI", "RDDT", "CVNA", "UPST", "MARA", "RIOT", "MU"
            ],
            "defensive_value": [
                "LLY", "UNH", "JNJ", "ABBV", "MRK", "WMT", "COST", "PM", "PG", "KO",
                "PEP", "VST", "CEG", "NEE", "SO", "DUK", "JPM", "GS", "GE", "ETN"
            ],
            "cyclical_macro": [
                "GE", "CAT", "ETN", "UNP", "HON", "BA", "XOM", "CVX", "COP", "LIN",
                "FCX", "NUE", "JPM", "GS", "MS", "AMAT", "MU", "UBER", "TJX", "BKNG"
            ],
            "tech_semiconductor_heavy": [
                "NVDA", "AAPL", "MSFT", "AVGO", "PLTR", "AMD", "ORCL", "CRM", "NOW", "QCOM",
                "AMAT", "LRCX", "MU", "PANW", "CRWD", "ARM", "APP", "SNPS", "CDNS", "MRVL"
            ]
        }
    }
}

# ---------------------------------------------------------------------
# APPLY DATASET ROUTING & TAG FILTERING
# ---------------------------------------------------------------------
if DATASET_PHASE == "TRAINING_1":
    RAW_REGIME_WINDOWS = REGIME_WINDOWS_TRAIN_1
elif DATASET_PHASE == "TRAINING_2":
    RAW_REGIME_WINDOWS = REGIME_WINDOWS_TRAIN_2
elif DATASET_PHASE == "FINAL_TESTING":
    RAW_REGIME_WINDOWS = REGIME_WINDOWS_FINAL_TEST
else:
    RAW_REGIME_WINDOWS = REGIME_WINDOWS_TRAIN_1

if "ALL" in [t.upper() for t in TARGET_REGIME_TAGS]:
    REGIME_WINDOWS = RAW_REGIME_WINDOWS
else:
    REGIME_WINDOWS = {
        k: v for k, v in RAW_REGIME_WINDOWS.items()
        if v.get("tag", "").upper() in [t.upper() for t in TARGET_REGIME_TAGS]
    }