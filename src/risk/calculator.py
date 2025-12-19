import yfinance as yf
from sqlalchemy import text
from src.config import ACCOUNT_SIZE, RISK_PER_TRADE

# --- CONFIGURATION ---
MAX_POSITION_ALLOCATION = 0.2  # Max 20% of account in one stock
MIN_PRICE_DIFF_PERCENT = 0.5   # Only buy more if price moved 0.5% from last entry

def get_market_volatility():
    """
    Checks India VIX to determine market fear.
    Returns a 'Safety Factor' (0.5 to 1.0).
    """
    try:
        vix = yf.Ticker("^INDIAVIX").history(period="5d")
        if vix.empty: return 1.0
        current_vix = vix['Close'].iloc[-1]
        
        if current_vix < 15: return 1.0   # Safe
        elif current_vix < 20: return 0.75 # Caution
        else: return 0.5                   # Dangerous
    except:
        return 1.0

def calculate_position_size(entry, stop_loss, risk_per_trade=None):
    """
    Calculates initial quantity for a NEW trade based on Risk & Volatility.
    """
    try:
        entry = float(entry)
        stop_loss = float(stop_loss)
        final_risk_pct = risk_per_trade if risk_per_trade is not None else RISK_PER_TRADE

        risk_per_share = abs(entry - stop_loss) 
        if risk_per_share == 0: return 0
        
        volatility_factor = get_market_volatility()
        risk_budget = ACCOUNT_SIZE * final_risk_pct * volatility_factor
        
        # 1. Risk limit
        qty_by_risk = int(risk_budget / risk_per_share)
        
        # 2. Hard Capital Limit (Max 20% of account)
        max_capital_allowed = ACCOUNT_SIZE * MAX_POSITION_ALLOCATION
        qty_by_capital = int(max_capital_allowed / entry)
        
        return max(1, min(qty_by_risk, qty_by_capital))
    except Exception as e:
        print(f"⚠️ Risk Calc Error: {e}")
        return 0

def validate_trade_setup(engine, strategy, ticker, signal_price, signal_qty):
    """
    The 'Brain' of the operation.
    Checks DB for existing positions and decides if we should add more.
    
    Returns:
        (is_allowed, final_qty, message)
    """
    try:
        # Normalise incoming types to avoid float / Decimal clashes
        signal_price = float(signal_price)
        signal_qty = int(signal_qty)

        with engine.connect() as conn:
            # Check for existing OPEN position for this strategy & ticker
            query = text("""
                SELECT quantity, entry_price 
                FROM trades 
                WHERE ticker = :ticker 
                  AND strategy_name = :strat 
                  AND status = 'OPEN' 
                LIMIT 1
            """)
            existing = conn.execute(query, {"ticker": ticker, "strat": strategy}).fetchone()

        # --- CASE 1: FRESH ENTRY ---
        if not existing:
            return True, signal_qty, "✅ Fresh Entry"

        # --- CASE 2: EXISTING POSITION CHECKS ---
        # Database may return Decimal / other numeric types; cast for safe math
        current_qty = int(existing[0])
        last_entry = float(existing[1])
        
        # 1. Anti-Spam Check: Is price too close to last buy?
        price_diff_pct = abs((signal_price - last_entry) / last_entry) * 100
        if price_diff_pct < MIN_PRICE_DIFF_PERCENT:
            return False, 0, f"🚫 Price noise ({price_diff_pct:.2f}% < {MIN_PRICE_DIFF_PERCENT}%)"

        # 2. Max Exposure Check: Do we already own too much?
        current_invested = current_qty * last_entry
        new_invested = signal_qty * signal_price
        total_projected = current_invested + new_invested
        
        max_allowed_rupees = ACCOUNT_SIZE * MAX_POSITION_ALLOCATION
        
        if current_invested >= max_allowed_rupees:
            return False, 0, f"🚫 Max Allocation Reached (₹{current_invested:,.0f})"
            
        # 3. Partial Fill Logic (Optional)
        # If adding full signal_qty breaks the limit, allow a smaller partial add?
        if total_projected > max_allowed_rupees:
            remaining_budget = max_allowed_rupees - current_invested
            adjusted_qty = int(remaining_budget / signal_price)
            if adjusted_qty > 0:
                 return True, adjusted_qty, f"⚠️ Capped Quantity ({signal_qty} -> {adjusted_qty})"
            else:
                 return False, 0, "🚫 No Budget Left"

        return True, signal_qty, f"✅ Averaging/Pyramiding (Diff: {price_diff_pct:.2f}%)"

    except Exception as e:
        return False, 0, f"Error in validation: {str(e)}"