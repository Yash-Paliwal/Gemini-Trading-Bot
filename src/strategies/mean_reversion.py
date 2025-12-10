import pandas_ta_classic as ta

def analyze(df):
    """
    STRATEGY: MEAN REVERSION
    Rule: Buy if RSI < 30 (Oversold bounce)
    """
    df['RSI'] = ta.rsi(df['Close'], length=14)
    latest = df.iloc[-1]
    
    # Catch the falling knife safely
    if latest['RSI'] < 30:
        return {
            "action": "BUY",
            "reason": f"Oversold Bounce (RSI {latest['RSI']:.0f} < 30)",
            "confidence": 90
        }
    return None