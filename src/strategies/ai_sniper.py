from src.tools import fetch_candles, fetch_funds, fetch_news, get_live_price
from src.finder.strategy import get_technicals, calculate_weekly_trend
from src.finder.brain import analyze_stock_ai

def analyze(ticker, master_map):
    """
    STRATEGY: AI SNIPER (The Heavyweight)
    Uses Deep Learning (Gemini), Fundamentals, and News.
    """
    # 🚨 FIX: Normalize Ticker (Remove .NS for Upstox Lookup)
    # Yahoo gives 'RELIANCE.NS', but Upstox Map needs 'RELIANCE'
    clean_ticker = ticker.replace(".NS", "")
    
    key = master_map.get(clean_ticker)
    if not key: 
        # print(f"      ⚠️ AI Sniper: Key not found for {clean_ticker}") # Uncomment for debug
        return None

    # 1. Fetch Data (Upstox Historical)
    daily = fetch_candles(key, 400, "days")
    weekly = fetch_candles(key, 700, "weeks")
    
    if not daily or not weekly: return None

    # 2. Get Technicals
    d_tech = get_technicals(daily)
    w_trend = calculate_weekly_trend(weekly)
    
    # 3. Get Live Price
    live_price = get_live_price(key, ticker)
    if not live_price: return None
    d_tech['price'] = live_price

    # 4. Get External Data
    # Use clean_ticker to ensure Indian APIs find the stock
    fund = fetch_funds(clean_ticker)
    news = fetch_news(clean_ticker)

    # 5. Ask Gemini
    decision = analyze_stock_ai(clean_ticker, d_tech, w_trend, fund, news)
    
    if decision['signal'] == "BUY":
        return {
            "action": "BUY",
            "reason": f"AI High Conviction: {decision['reasoning'][:100]}...",
            "confidence": decision['confidence'],
            "price": live_price,
            "atr": d_tech['atr']
        }
    
    return None