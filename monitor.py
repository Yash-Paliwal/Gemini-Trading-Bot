import time
import requests
import json
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, UPSTOX_ACCESS_TOKEN
from src.database import get_open_trades, update_trade_status, update_balance, get_current_balance
from src.tools import get_live_price, fetch_upstox_map
from src.upstox_client import upstox_client

# --- NEW FUNCTION: CALCULATE TOTAL NET WORTH ---
def get_total_equity(master_map):
    """Calculates Cash + Value of all Open Trades."""
    cash = get_current_balance()
    holdings_value = 0
    
    trades = get_open_trades()
    for t in trades:
        key = master_map.get(t.ticker)
        if key:
            price = get_live_price(key, symbol_fallback=t.ticker)
            if price:
                holdings_value += (price * t.quantity)
            else:
                # Fallback to entry price if live fails (conservative)
                holdings_value += (t.entry_price * t.quantity)
                
    return cash + holdings_value

def send_exit_alert(ticker, status, price, pnl, balance, total_equity):
    emoji = "💰" if pnl > 0 else "🛑"
    
    # Calculate % Return on this specific trade
    # (Avoid division by zero)
    roi = 0
    if price > 0: 
        # Approximate entry from PnL logic
        # PnL = (Exit - Entry) * Qty
        # We can just use the pnl to show raw profit
        pass

    msg = (
        f"{emoji} *EXIT ALERT: {ticker}*\n"
        f"Status: {status}\n"
        f"Price: {price}\n"
        f"PnL: {'+' if pnl>0 else ''}₹{pnl:.2f}\n"
        f"-------------------\n"
        f"💵 Cash: ₹{balance:,.0f}\n"
        f"🏛️ *Net Worth: ₹{total_equity:,.0f}*" 
    )
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except: pass

def run_watchdog():
    print("\n👮 STARTING WATCHDOG...")
    
    upstox_client.set_access_token(UPSTOX_ACCESS_TOKEN)
    if not upstox_client.check_connection():
        print("   ❌ Upstox Token Expired. Stopping.")
        return

    trades = get_open_trades()
    if not trades:
        print("   💤 No open trades.")
        return

    master_map = fetch_upstox_map()
    print(f"   🔍 Monitoring {len(trades)} Positions...")
    
    for t in trades:
        key = master_map.get(t.ticker)
        if not key: print(f"   ⚠️ Key missing for {t.ticker}"); continue
        
        current_price = get_live_price(key, symbol_fallback=t.ticker)
        if not current_price: print(f"   ⚠️ Price unavailable for {t.ticker}"); continue
            
        print(f"   👉 {t.ticker}: {current_price} (Tgt: {t.target_price} | Stop: {t.stop_loss})")
        
        # CHECK CONDITIONS
        new_status = None
        if current_price >= t.target_price: new_status = "TARGET_HIT"
        elif current_price <= t.stop_loss: new_status = "STOP_HIT"
            
        # EXECUTE EXIT
        if new_status:
            pnl = (current_price - t.entry_price) * t.quantity
            cash_back = current_price * t.quantity
            
            print(f"   ⚡ TRIGGER: {new_status} (PnL: {pnl:.2f})")
            
            # 1. Refund Wallet
            update_balance(cash_back)
            
            # 2. Close Trade in DB
            update_trade_status(t.id, new_status, current_price, pnl)
            
            # 3. Calculate Total Equity (The New Feature)
            # We calculate this AFTER the refund so 'Cash' is updated
            total_equity = get_total_equity(master_map)
            
            # 4. Alert
            send_exit_alert(t.ticker, new_status, current_price, pnl, get_current_balance(), total_equity)

    print("🏁 WATCHDOG SCAN COMPLETE.")

if __name__ == "__main__":
    run_watchdog()