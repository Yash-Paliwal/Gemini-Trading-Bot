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
    Calculates quantity based on Risk AND Max Allocation.
    """
    try:
        entry = float(entry)
        stop_loss = float(stop_loss)
        
        # 1. Risk-Based Sizing (The "Math" Limit)
        risk_per_share = abs(entry - stop_loss) # abs() handles Short trades too
        if risk_per_share == 0: return 0
        
        volatility_factor = get_market_volatility()
        risk_budget = ACCOUNT_SIZE * RISK_PER_TRADE * volatility_factor
        qty_by_risk = int(risk_budget / risk_per_share)
        
        # 2. Capital-Based Sizing (The "Wallet" Limit)
        # We never want to put more than 20% of the account in one stock
        max_capital_allowed = ACCOUNT_SIZE * MAX_POSITION_ALLOCATION
        qty_by_capital = int(max_capital_allowed / entry)
        
        # 3. The Final Decision (Take the smaller number)
        final_qty = min(qty_by_risk, qty_by_capital)
        
        # Debug Log
        if qty_by_risk > qty_by_capital:
            print(f"   🛡️ Capped by Max Allocation (Risk Qty: {qty_by_risk} -> Cap Qty: {qty_by_capital})")
            
        return final_qty
    except Exception as e:
        print(f"Risk Calc Error: {e}")
        return 0