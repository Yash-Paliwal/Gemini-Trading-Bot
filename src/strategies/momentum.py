import pandas_ta_classic as ta

def analyze(df):
    """
    STRATEGY: MOMENTUM
    Rule: Buy if Price > 200 EMA and RSI > 50
    """
    df['EMA_200'] = ta.ema(df['Close'], length=200)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    
    latest = df.iloc[-1]
    
    if latest['Close'] > latest['EMA_200'] and latest['RSI'] > 55:
        return {
            "action": "BUY",
            "reason": f"Uptrend (Price {latest['Close']:.0f} > 200 EMA) + Momentum (RSI {latest['RSI']:.0f})",
            "confidence": 80
        }
    return None