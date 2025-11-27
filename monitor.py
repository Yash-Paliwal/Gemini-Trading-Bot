import time
import requests
import json
# Import from your modules
from src.database import get_open_trades, update_trade_status
from src.tools import get_live_price, fetch_upstox_map
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_exit_alert(ticker, status, price, pnl):
    print(f"   📡 Sending Alert for {ticker}...")
    
    # 1. Debug Keys
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("   ❌ FAIL: Telegram Keys are missing in .env file!")
        return

    emoji = "💰" if pnl > 0 else "🛑"
    
    # Simple Text (Markdown sometimes causes errors with special chars)
    msg = (
        f"{emoji} EXIT ALERT: {ticker}\n"
        f"Status: {status}\n"
        f"Price: {price}\n"
        f"P&L: Rs {pnl:.2f}"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    
    try:
        response = requests.post(url, json=payload)
        
        # 2. Print Response Status
        if response.status_code == 200:
            print("   ✅ Telegram Sent Successfully.")
        else:
            print(f"   ❌ Telegram Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"   ❌ Network Error: {e}")

def run_watchdog():
    print("\n👮 STARTING WATCHDOG (DEBUG MODE)...")
    
    # 1. Check Trades
    trades = get_open_trades()
    if not trades:
        print("   💤 No open trades found in Database.")
        # FOR TESTING: Let's pretend we found one so you can test the alert
        # Uncomment lines below to FORCE a test alert
        print("   🧪 FORCING TEST ALERT...")
        send_exit_alert("TEST-STOCK", "TARGET_HIT", 150.0, 500.0)
        return

    # 2. Load Map
    master_map = fetch_upstox_map()
    print(f"   🔍 Monitoring {len(trades)} Positions...")
    
    for t in trades:
        key = master_map.get(t.ticker)
        if not key: 
            print(f"   ⚠️ Key not found for {t.ticker}")
            continue
        
        # 3. Get Price
        current_price = get_live_price(key, symbol_fallback=t.ticker)
        if not current_price: 
            print(f"   ⚠️ Price unavailable for {t.ticker}")
            continue
            
        print(f"   👉 {t.ticker}: {current_price} (Target: {t.target_price} | Stop: {t.stop_loss})")
        
        # 4. Check Conditions
        new_status = None
        
        # LOGIC: Check boundaries
        if current_price >= t.target_price:
            new_status = "TARGET_HIT"
        elif current_price <= t.stop_loss:
            new_status = "STOP_HIT"
            
        if new_status:
            pnl = (current_price - t.entry_price) * t.quantity
            print(f"   ⚡ TRIGGER: {new_status} (PnL: {pnl})")
            
            # Update DB
            update_trade_status(t.id, new_status, current_price, pnl)
            
            # Send Alert
            send_exit_alert(t.ticker, new_status, current_price, pnl)

    print("🏁 WATCHDOG SCAN COMPLETE.")

if __name__ == "__main__":
    run_watchdog()