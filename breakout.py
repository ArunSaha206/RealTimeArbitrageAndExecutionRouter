def analyze(candle_history: list, lookback: int = 20, exit_lookback: int = 10, current_position: int = 0) -> dict:
    """
    Computes Donchian Channel breakout logic with volume confirmation and exit signals.
    
    :param candle_history: List of OHLCV candle dicts
    :param lookback: Bars to calculate Resistance (Entry)
    :param exit_lookback: Bars to calculate Support (Exit)
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