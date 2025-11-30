import time
import requests
import json
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, UPSTOX_ACCESS_TOKEN
from src.database import get_open_trades, update_trade_status
from src.tools import get_live_price, fetch_upstox_map
from src.upstox_client import upstox_client

def send_exit_alert(ticker, status, price, pnl, info=""):
    emoji = "💰" if pnl > 0 else "🛑"
    if status == "TRAILING_UPDATE": emoji = "🛡️"
    
    msg = (
        f"{emoji} *EXIT ALERT: {ticker}*\n"
        f"Status: {status}\n"
        f"Price: {price}\n"
        f"P&L: {'+' if pnl>0 else ''}₹{pnl:.2f}\n"
        f"{info}"
    )
    print(f"   📲 Sending Telegram: {status}")
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except: pass

def run_watchdog():
    print("\n👮 STARTING WATCHDOG...")
    
    # 1. AUTHENTICATE
    upstox_client.set_access_token(UPSTOX_ACCESS_TOKEN)
    if not upstox_client.check_connection():
        print("   ❌ Upstox Token Expired. Stopping Watchdog.")
        return

    # 2. GET DATA
    trades = get_open_trades()
    if not trades:
        print("   💤 No open trades to monitor.")
        return

    master_map = fetch_upstox_map()
    print(f"   🔍 Monitoring {len(trades)} Positions...")
    
    for t in trades:
        key = master_map.get(t.ticker)
        if not key: 
            print(f"   ⚠️ Key not found for {t.ticker}")
            continue
        
        # 3. GET LIVE PRICE
        current_price = get_live_price(key, symbol_fallback=t.ticker)
        if not current_price: 
            print(f"   ⚠️ Price unavailable for {t.ticker}")
            continue
            
        print(f"   👉 {t.ticker}: {current_price} (Target: {t.target_price} | Stop: {t.stop_loss})")
        
        # 4. CHECK CONDITIONS
        new_status = None
        info_msg = ""
        
        # A. Target Hit
        if current_price >= t.target_price:
            new_status = "TARGET_HIT"
        
        # B. Stop Loss Hit
        elif current_price <= t.stop_loss:
            new_status = "STOP_HIT"
            
        # C. Trailing Stop Logic (Alert Only)
        # If profit is > 50% of target distance, alert to move stop
        if not new_status:
            total_dist = t.target_price - t.entry_price
            curr_dist = current_price - t.entry_price
            if total_dist > 0 and (curr_dist / total_dist) > 0.5:
                # We don't close the trade, just warn user
                # Only alert if price is reasonably above entry
                if t.stop_loss < t.entry_price:
                    # This check prevents spamming if you already moved the stop
                    print(f"   🚀 {t.ticker}: 50% to Target. Suggest Trailing Stop.")
                    # Optional: Enable this to get alerts
                    # send_exit_alert(t.ticker, "TRAILING_UPDATE", current_price, curr_dist * t.quantity, "Suggestion: Move Stop to Breakeven")

        # D. Execute Exit
        if new_status:
            pnl = (current_price - t.entry_price) * t.quantity
            print(f"   ⚡ TRIGGER: {new_status} (PnL: {pnl})")
            update_trade_status(t.id, new_status, current_price, pnl)
            send_exit_alert(t.ticker, new_status, current_price, pnl)

    print("🏁 WATCHDOG SCAN COMPLETE.")

if __name__ == "__main__":
    run_watchdog()