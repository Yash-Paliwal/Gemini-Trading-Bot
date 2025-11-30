import google.generativeai as genai
import json
from src.config import GEMINI_API_KEY

def analyze_stock_ai(name, d_tech, w_trend, fund, news):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('models/gemini-2.5-flash', generation_config={"temperature": 0.1})
    
    fallback = {"signal": "WAIT", "confidence": 0, "reasoning": "Data Error", "entry_price": 0, "target_price": 0, "stop_loss": 0}
    
    if not d_tech: return fallback

    smart_money = (fund.promoter_holding or 0) + (fund.fii_holding or 0) + (fund.dii_holding or 0)
    news_t = "\n".join([f"- {n.title}" for n in news])
    
    # Determine MACD Status
    macd_status = "BULLISH" if d_tech['macd'] > d_tech['macd_signal'] else "BEARISH"
    adx_status = "STRONG TREND" if d_tech['adx'] > 20 else "WEAK/CHOPPY"
    
    prompt = f"""
    ACT AS: Senior Quantitative Fund Manager.
    ASSET: {name}
    
    [ADVANCED TECHNICALS]
    1. WEEKLY TREND (Long Term): {w_trend} (Price vs 40-Week EMA)
    2. DAILY TREND (Medium Term): {d_tech['trend']} (Price vs 200-Day EMA)
    3. MOMENTUM (MACD): {macd_status} (Value: {d_tech['macd']})
    4. TREND STRENGTH (ADX): {d_tech['adx']} ({adx_status})
    5. RSI (14): {d_tech['rsi']}
    
    [FUNDAMENTALS]
    PE Ratio: {fund.pe_ratio}
    Smart Money Holding: {smart_money:.2f}%
    
    [NEWS SENTIMENT]
    {news_t}
    
    [DECISION MATRIX]
    - SIGNAL: "BUY" ONLY if:
      1. Weekly Trend is UP.
      2. Daily Trend is UP (or Pullback to support).
      3. MACD is Bullish (Crossover).
      4. ADX > 20 (Avoid choppy markets).
      5. Fundamentals/News are safe.
    
    - SIGNAL: "WAIT" if trend is weak, MACD is bearish, or News is negative.
    
    [OUTPUT JSON]
    {{
      "signal": "BUY", "SELL", or "WAIT",
      "confidence": 0-100,
      "reasoning": "Explain using MACD/ADX why you chose this.",
      "entry_price": 0,
      "target_price": 0,
      "stop_loss": 0
    }}
    """
    
    try:
        return json.loads(model.generate_content(prompt).text.strip().replace("```json","").replace("```",""))
    except Exception as e:
        fallback['reasoning'] = f"AI Error: {e}"
        return fallback