import yfinance as yf
from src.database import get_open_trades

# SETTINGS
MAX_SECTOR_EXPOSURE = 2  # Max 2 stocks per sector
MAX_TOTAL_POSITIONS = 10 # Max 10 open trades allowed

def get_sector(ticker):
    """Fetches the Sector of a stock from Yahoo Finance."""
    try:
        sym = ticker if ".NS" in ticker else f"{ticker}.NS"
        info = yf.Ticker(sym).info
        return info.get('sector', 'Unknown')
    except: return 'Unknown'

def check_portfolio_health(new_candidate):
    """
    Checks if we are allowed to add this new trade.
    Returns: (Allowed: bool, Reason: str)
    """
    open_trades = get_open_trades()
    
    # 1. Check Total Capacity
    if len(open_trades) >= MAX_TOTAL_POSITIONS:
        return False, "Max Portfolio Capacity Reached"

    # 2. Check Duplicates
    for t in open_trades:
        if t.ticker == new_candidate:
            return False, f"Position already OPEN for {new_candidate}"

    # 3. Check Sector Exposure
    print(f"   🧩 Checking Sector Exposure for {new_candidate}...")
    candidate_sector = get_sector(new_candidate)
    
    if candidate_sector == 'Unknown':
        return True, "Sector Unknown (Allowed)"
        
    same_sector_count = 0
    for t in open_trades:
        existing_sector = get_sector(t.ticker)
        if existing_sector == candidate_sector:
            same_sector_count += 1
            
    if same_sector_count >= MAX_SECTOR_EXPOSURE:
        return False, f"Max limit reached for sector: {candidate_sector}"
        
    return True, "OK"