import time
import requests
import json
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, UPSTOX_ACCESS_TOKEN
from src.database import get_open_trades, update_trade_status, update_balance, get_current_balance
from src.tools import get_live_price, fetch_upstox_map
from src.upstox_client import upstox_client

def send_exit_alert(ticker, status, price, pnl, balance):
    emoji = "💰" if pnl > 0 else "🛑"
    msg = (
        f"{emoji} *EXIT ALERT: {ticker}*\n"
        f"Status: {status}\n"
        f"Price: {price}\n"
        f"P&L: {'+' if pnl>0 else ''}₹{pnl:.2f}\n"
        f"🏦 Wallet: ₹{balance:,.0f}"
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
        
        # CHECK EXIT
        new_status = None
        if current_price >= t.target_price: new_status = "TARGET_HIT"
        elif current_price <= t.stop_loss: new_status = "STOP_HIT"
            
        # CHECK TRAILING (Alert Only)
        dist = t.target_price - t.entry_price
        if dist > 0 and (current_price - t.entry_price)/dist > 0.5 and t.stop_loss < t.entry_price:
             print(f"   🚀 {t.ticker} >50% to Target. Move Stop to Breakeven?")

        # EXECUTE EXIT
        if new_status:
            # Calculate PnL
            pnl = (current_price - t.entry_price) * t.quantity
            
            # Calculate Refund (Entry Cost + Profit)
            # Note: We deducted (Entry * Qty) initially.
            # Now we add back (Exit * Qty).
            cash_back = current_price * t.quantity
            
            print(f"   ⚡ TRIGGER: {new_status} (PnL: {pnl:.2f})")
            
            # 1. Update Wallet
            update_balance(cash_back)
            
            # 2. Close Trade in DB
            update_trade_status(t.id, new_status, current_price, pnl)
            
            # 3. Alert
            send_exit_alert(t.ticker, new_status, current_price, pnl, get_current_balance())

    print("🏁 WATCHDOG SCAN COMPLETE.")

if __name__ == "__main__":
    run_watchdog()