import yfinance as yf
from src.database import get_open_trades

# --- PORTFOLIO RULES ---
MAX_SECTOR_EXPOSURE = 2   # Max 2 stocks per sector (e.g., Only 2 Banks)
MAX_TOTAL_POSITIONS = 10  # Max 10 open trades at a time

def get_sector(ticker):
    """
    Fetches the Sector of a stock from Yahoo Finance.
    Example: 'TCS' -> 'Technology'
    """
    try:
        # Yahoo Finance requires .NS for Indian stocks
        sym = ticker if ".NS" in ticker else f"{ticker}.NS"
        info = yf.Ticker(sym).info
        return info.get('sector', 'Unknown')
    except Exception as e:
        print(f"      ⚠️ Sector fetch failed for {ticker}: {e}")
        return 'Unknown'

def check_portfolio_health(new_candidate):
    """
    Checks if adding this stock violates any portfolio rules.
    Returns: (Allowed: bool, Reason: str)
    """
    # 1. Get Current Portfolio
    open_trades = get_open_trades()
    
    # 2. Rule: Max Total Positions
    if len(open_trades) >= MAX_TOTAL_POSITIONS:
        return False, f"Portfolio Full ({len(open_trades)}/{MAX_TOTAL_POSITIONS} positions)"

    # 3. Rule: No Duplicates
    for t in open_trades:
        if t.ticker == new_candidate:
            return False, f"Position already OPEN for {new_candidate}"

    # 4. Rule: Sector Exposure
    print(f"   🧩 Checking Sector Exposure for {new_candidate}...")
    
    candidate_sector = get_sector(new_candidate)
    
    if candidate_sector == 'Unknown':
        # If we can't find the sector, we usually allow it but warn
        print(f"      ⚠️ Sector Unknown for {new_candidate}. Proceeding with caution.")
        return True, "OK (Sector Unknown)"
        
    # Count how many stocks we already have in this sector
    same_sector_count = 0
    for t in open_trades:
        existing_sector = get_sector(t.ticker)
        if existing_sector == candidate_sector:
            same_sector_count += 1
            
    print(f"      Sector: {candidate_sector} | Current Holdings: {same_sector_count}")
    
    if same_sector_count >= MAX_SECTOR_EXPOSURE:
        return False, f"Max exposure reached for {candidate_sector} ({same_sector_count} stocks)"
        
    # If all checks pass
    return True, "OK"