import google.generativeai as genai
import json
from .config import GEMINI_API_KEY

def analyze_stock_ai(name, d_tech, w_trend, fund, news):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('models/gemini-2.5-flash', generation_config={"temperature": 0.1})
    
    smart_money = (fund.promoter_holding or 0) + (fund.fii_holding or 0)
    
    prompt = f"""
    ACT AS: Hedge Fund Manager. ASSET: {name}
    [TECHNICALS] Weekly Trend: {w_trend}. Daily Trend: {d_tech['trend']}. RSI: {d_tech['rsi']}.
    [FUNDAMENTALS] PE: {fund.pe_ratio}. Smart Money: {smart_money:.2f}%
    [NEWS] {chr(10).join([n.title for n in news])}
    [RULES] BUY if Weekly UP + Daily UP + RSI 40-60.
    [OUTPUT JSON] {{ "signal": "BUY/WAIT", "confidence": 0-100, "reasoning": "Text" }}
    """
    try:
        return json.loads(model.generate_content(prompt).text.strip().replace("```json","").replace("```",""))
    except Exception as e:
        return {"signal": "WAIT", "confidence": 0, "reasoning": f"Error: {e}"}