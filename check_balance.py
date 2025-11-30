import os
from src.database import Session, Portfolio, Trade, get_open_trades
from src.tools import get_live_price, fetch_upstox_map, upstox_client # Use tools for live data
from src.config import UPSTOX_ACCESS_TOKEN

def show_account_summary():
    print("\n💰 --- HEDGE FUND ACCOUNT SUMMARY ---")
    
    # 1. Get Cash
    session = Session()
    pf = session.query(Portfolio).first()
    cash_balance = pf.balance if pf else 0
    session.close()
    
    print(f"💵 Cash in Hand:    ₹{cash_balance:,.2f}")
    
    # 2. Calculate Holdings Value
    upstox_client.set_access_token(UPSTOX_ACCESS_TOKEN) # Auth for live prices
    open_trades = get_open_trades()
    master_map = fetch_upstox_map()
    
    holdings_value = 0
    unrealized_pnl = 0
    
    print("\n📋 Open Positions:")
    print(f"{'TICKER':<12} {'QTY':<6} {'ENTRY':<10} {'CURRENT':<10} {'P&L':<10}")
    print("-" * 50)
    
    for t in open_trades:
        key = master_map.get(t.ticker)
        # Fetch price (or fallback to entry if market closed/error)
        current_price = get_live_price(key, t.ticker) or t.entry_price
        
        value = current_price * t.quantity
        pnl = (current_price - t.entry_price) * t.quantity
        
        holdings_value += value
        unrealized_pnl += pnl
        
        print(f"{t.ticker:<12} {t.quantity:<6} {t.entry_price:<10.2f} {current_price:<10.2f} {pnl:+.2f}")
        
    # 3. Final Total
    total_equity = cash_balance + holdings_value
    
    print("-" * 50)
    print(f"📈 Stock Value:     ₹{holdings_value:,.2f}")
    print(f"📉 Unrealized P&L:  ₹{unrealized_pnl:,.2f}")
    print("=" * 50)
    print(f"🏛️ TOTAL EQUITY:    ₹{total_equity:,.2f}")
    print("=" * 50)

if __name__ == "__main__":
    show_account_summary()