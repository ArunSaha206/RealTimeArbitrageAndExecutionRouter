"""
BacktestControlCenter.py

Single source of truth for BACKTEST ENGINE configuration:
  - which strategy module is active
  - which tickers to test
  - bar resolution
  - starting cash per ticker
  - days to test
  - risk-free rate assumption

Deliberately NOT controlled here (owned by the strategy module itself,
e.g. M5breakout.py): bar resolution, position sizing mode, fixed share
quantity, lookback / exit_lookback. Each strategy is self-contained and
exposes its own get_params(), so swapping ACTIVE_STRATEGY below is
enough to change strategy behavior end-to-end -- no other file needs
editing.
"""

import M5breakout

# =====================================================================
# 1. STRATEGY SELECTION
# =====================================================================
# Point this at any module that implements:
#   - analyze(candle_history, lookback, exit_lookback, current_position) -> dict
#   - get_params() -> dict {lookback, exit_lookback, position_mode, fixed_share_qty}
ACTIVE_STRATEGY = M5breakout

# =====================================================================
# 2. BACKTEST ENGINE CONFIGURATION
# =====================================================================
STARTING_CASH_PER_TICKER = 3000.00     # Virtual starting cash allocated per asset
DAYS_TO_TEST = 50                      # Calendar days back to evaluate
RISK_FREE_RATE = 0.04                  # 4% annualized risk-free rate assumption for Sharpe Ratio

# =====================================================================
# 3. TICKER UNIVERSE
# =====================================================================
DEFAULT_UNIVERSE = ["QQQ", "NVDA", "PYPL", "CAVA", "GME", "SPCX", "ALAB"]
QQQ = ["QQQ"]
SPCX = ["SPCX"]
CAVA = ["CAVA"]
NVDA = ["NVDA"]

# --- STRATEGY & SECTOR BUCKETS ---
LEVERAGED_PAIRS = ["TQQQ", "SQQQ"]
PAIRS = ["PSQ", "QQQM"]
TECH_GIANTS = ["AAPL", "MSFT", "NVDA", "AMD", "GOOGL"]
HIGH_BETA = ["TSLA", "NVDA", "AMZN", "META"]
ETFS_ONLY = ["SPY", "QQQ", "IWM", "XLE", "XLF"]

# --- ACTIVE BENCHMARK ---
# Set ACTIVE_UNIVERSE to whichever list you want to run right now
ACTIVE_UNIVERSE = NVDA