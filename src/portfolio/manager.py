import yfinance as yf
from src.database import get_open_trades

# --- PORTFOLIO RULES ---
MAX_SECTOR_EXPOSURE = 2   # Max 2 stocks per sector (Per Strategy)
MAX_POSITIONS_PER_STRATEGY = 5  # Max 5 open trades per strategy (Total 15 for 3 strategies)

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

def check_portfolio_health(new_candidate, strategy_name):
    """
    Checks if THIS SPECIFIC STRATEGY is allowed to buy this stock.
    Returns: (Allowed: bool, Reason: str)
    """
    # 1. Get Open Trades for THIS Strategy Only
    # (We rely on the database function we updated earlier)
    open_trades = get_open_trades(strategy_name)
    
    # 2. Rule: Max Positions (Per Strategy)
    if len(open_trades) >= MAX_POSITIONS_PER_STRATEGY:
        return False, f"Strategy {strategy_name} is Full ({len(open_trades)}/{MAX_POSITIONS_PER_STRATEGY})"

    # 3. Rule: No Duplicates (Per Strategy)
    # (Strategy A can hold RELIANCE, even if Strategy B holds it. But A can't hold it twice.)
    for t in open_trades:
        # Dictionary access is safer as get_open_trades returns dicts
        if t['ticker'] == new_candidate:
            return False, f"{strategy_name} already holds {new_candidate}"

    # 4. Rule: Sector Exposure (Per Strategy)
    # Note: Frequent YFinance calls can be slow, but we keep your logic here.
    # We only check sector if we passed the previous checks.
    print(f"   🧩 {strategy_name}: Checking Sector for {new_candidate}...")
    
    candidate_sector = get_sector(new_candidate)
    
    if candidate_sector == 'Unknown':
        return True, "OK (Sector Unknown)"
        
    # Count existing stocks in this sector for THIS strategy
    same_sector_count = 0
    for t in open_trades:
        existing_sector = get_sector(t['ticker'])
        if existing_sector == candidate_sector:
            same_sector_count += 1
            
    if same_sector_count >= MAX_SECTOR_EXPOSURE:
        return False, f"Max {candidate_sector} exposure reached for {strategy_name}"
        
    # If all checks pass
    return True, "OK"