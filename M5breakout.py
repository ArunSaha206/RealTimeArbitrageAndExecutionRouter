# =====================================================================
# STRATEGY CONFIGURATION
# =====================================================================
# This strategy owns ALL of its own knobs. Nothing here should be
# duplicated or overridden from backtest.py, BacktestControlCenter.py,
# or main.py -- if you want to change how this strategy sizes positions
# or how far back it looks, change it here and only here.

BAR_RESOLUTION = "M5"     # "M1", "M5", "M15", "M30", "H1", "D1" -- this strategy is tuned to this timeframe
LOOKBACK = 20             # Bars for Resistance (Entry)
EXIT_LOOKBACK = 10        # Bars for Support (Exit)

POSITION_MODE = "ALL_IN"  # "ALL_IN" / "ALLIN" (max affordable shares) or "FIXED_SHARES"
FIXED_SHARE_QTY = 5       # Used if POSITION_MODE == "FIXED_SHARES"


def get_params() -> dict:
    """
    Single source of truth for this strategy's runtime configuration.
    Any engine (backtest.py, main.py, future live router, etc.) should
    call this instead of hardcoding bar resolution/lookback/sizing
    values themselves.
    """
    return {
        "bar_resolution": BAR_RESOLUTION,
        "lookback": LOOKBACK,
        "exit_lookback": EXIT_LOOKBACK,
        "position_mode": POSITION_MODE,
        "fixed_share_qty": FIXED_SHARE_QTY,
    }


# =====================================================================
# STRATEGY LOGIC
# =====================================================================

def analyze(candle_history: list, lookback: int = LOOKBACK, exit_lookback: int = EXIT_LOOKBACK, current_position: int = 0) -> dict:
    """
    Computes Donchian Channel breakout logic with volume confirmation and exit signals.

    :param candle_history: List of OHLCV candle dicts
    :param lookback: Bars to calculate Resistance (Entry) -- defaults to this module's LOOKBACK
    :param exit_lookback: Bars to calculate Support (Exit) -- defaults to this module's EXIT_LOOKBACK
    :param current_position: Number of shares currently held (passed from main engine)
    """
    # Need enough candles for lookback + volume average
    if len(candle_history) < lookback + 1:
        return {"signal": "HOLD", "reason": "Insufficient data buffer"}

    # Lookback window excluding the latest active bar
    window = candle_history[-(lookback + 1):-1]
    latest = candle_history[-1]

    # Calculate key levels
    resistance = max(bar['high'] for bar in window)
    support = min(bar['low'] for bar in window[-exit_lookback:])

    # Calculate average volume over the lookback period
    avg_volume = sum(bar['volume'] for bar in window) / len(window)
    has_volume_surge = latest['volume'] > (avg_volume * 1.2)  # 20% volume surge

    # -----------------------------------------------------------------
    # ENTRY LOGIC: Buy breakout if flat or short
    # -----------------------------------------------------------------
    if latest['close'] > resistance:
        if current_position > 0:
            return {"signal": "HOLD", "reason": "Already holding position"}

        if has_volume_surge:
            return {
                "signal": "BUY",
                "reason": f"Resistance Breakout above ${resistance:.2f} with Volume Surge",
                "confidence": 1.0
            }
        else:
            return {"signal": "HOLD", "reason": f"Breakout above ${resistance:.2f} rejected due to low volume"}

    # -----------------------------------------------------------------
    # EXIT LOGIC: Cut loss/Exit profit when dropping below exit support
    # -----------------------------------------------------------------
    elif latest['close'] < support and current_position > 0:
        return {
            "signal": "SELL",
            "reason": f"Support Breakdown below ${support:.2f} (Trailing Exit)",
            "confidence": 1.0
        }

    return {"signal": "HOLD", "reason": "Price within range"}