import yfinance as yf
from src.config import ACCOUNT_SIZE, RISK_PER_TRADE

def get_market_volatility():
    """
    Checks India VIX to determine market fear.
    Returns a 'Safety Factor' (0.5 to 1.0).
    """
    try:
        vix = yf.Ticker("^INDIAVIX").history(period="5d")
        if vix.empty: return 1.0
        
        current_vix = vix['Close'].iloc[-1]
        print(f"   📉 India VIX: {current_vix:.2f}")
        
        if current_vix < 15: return 1.0   # Safe (Full Size)
        elif current_vix < 20: return 0.75 # Caution (75% Size)
        else: return 0.5                   # Dangerous (Half Size)
    except:
        return 1.0

def calculate_position_size(entry, stop_loss):
    """
    Calculates quantity based on VIX-adjusted risk.
    """
    try:
        # 1. Adjust Risk based on Market Mood
        volatility_factor = get_market_volatility()
        adjusted_risk_money = ACCOUNT_SIZE * RISK_PER_TRADE * volatility_factor
        
        # 2. Calculate Risk per Share
        entry = float(entry)
        stop_loss = float(stop_loss)
        risk_per_share = entry - stop_loss
        
        if risk_per_share <= 0: return 0
        
        # 3. Final Quantity
        qty = int(adjusted_risk_money / risk_per_share)
        
        if volatility_factor < 1.0:
            print(f"   🛡️ Risk reduced by {(1-volatility_factor)*100}% (High VIX).")
            
        return qty
    except: return 0