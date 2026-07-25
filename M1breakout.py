"""
breakout_m1.py - M1 Strategy Module
Calibrated specifically for 1-minute candle breakout trading.
"""

def analyze(
    candle_history: list, 
    lookback: int = 100,         # 100 1-min bars = 100 minutes (matches M5 20-bar lookback)
    exit_lookback: int = 50,     # 50 1-min bars = 50 minutes (matches M5 10-bar exit)
    volume_surge_mult: float = 1.8, # 80% volume surge required (M1 volume is spike-prone)
    current_position: int = 0
) -> dict:
    """
    Computes Donchian Channel breakout logic for M1 data with strict 
    volume surge confirmation to filter out sub-minute noise.
    
    :param candle_history: List of OHLCV candle dicts
    :param lookback: Bars to calculate Resistance (Default: 100 for M1)
    :param exit_lookback: Bars to calculate Support (Default: 50 for M1)
    :param volume_surge_mult: Volume multiplier threshold (Default: 1.8 for M1)
    :param current_position: Number of shares currently held
    """
    # Ensure sufficient buffer for lookback calculation
    if len(candle_history) < lookback + 1:
        return {"signal": "HOLD", "reason": "Insufficient data buffer for M1 lookback"}

    # Historical window excluding the latest active candle
    window = candle_history[-(lookback + 1):-1]
    latest = candle_history[-1]

    # Calculate key resistance and support levels
    resistance = max(bar['high'] for bar in window)
    support = min(bar['low'] for bar in window[-exit_lookback:])
    
    # Calculate baseline average volume over the 100-minute window
    avg_volume = sum(bar['volume'] for bar in window) / len(window)
    
    # Require stronger volume surge on M1 to avoid whipsaws
    has_volume_surge = latest['volume'] > (avg_volume * volume_surge_mult)

    # -----------------------------------------------------------------
    # ENTRY LOGIC: Buy breakout above 100-minute resistance
    # -----------------------------------------------------------------
    if latest['close'] > resistance:
        if current_position > 0:
            return {"signal": "HOLD", "reason": "Already holding position"}
            
        if has_volume_surge:
            surge_pct = (volume_surge_mult - 1.0) * 100
            return {
                "signal": "BUY",
                "reason": f"M1 Breakout above ${resistance:.2f} with >{surge_pct:.0f}% Volume Surge",
                "confidence": 1.0
            }
        else:
            return {
                "signal": "HOLD", 
                "reason": f"M1 Breakout above ${resistance:.2f} rejected (Volume {latest['volume']:.0f} <= {avg_volume * volume_surge_mult:.0f} threshold)"
            }

    # -----------------------------------------------------------------
    # EXIT LOGIC: Trailing exit below 50-minute support
    # -----------------------------------------------------------------
    elif latest['close'] < support and current_position > 0:
        return {
            "signal": "SELL",
            "reason": f"M1 Support Breakdown below ${support:.2f} (Trailing Exit)",
            "confidence": 1.0
        }

    return {"signal": "HOLD", "reason": "Price within M1 range"}
