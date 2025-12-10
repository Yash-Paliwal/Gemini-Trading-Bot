import os
import requests

# Load Config once
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
PAPER_MODE         = os.getenv("PAPER_MODE", "True").lower() == "true"

def send_telegram_alert(ticker, strategy, action, qty, price, reason):
    """Sends a formatted alert to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    mode = "📝 *PAPER*" if PAPER_MODE else "💸 *LIVE*"
    strategy_name = strategy.replace('STRATEGY_', '')
    
    msg = (
        f"{mode} *TOURNAMENT ALERT*\n"
        f"🤖 *Bot:* {strategy_name}\n"
        f"💎 *{ticker}* | {action}\n"
        f"⚡ Price: {price}\n"
        f"📦 Qty: {qty}\n"
        f"🧠 Reason: {reason}"
    )
    
    try:
        url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={TELEGRAM_BOT_TOKEN}&redirect_uri={TELEGRAM_CHAT_ID}" # Mock URL structure, replacing with real API call below
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        )
    except Exception as e:
        print(f"   ❌ Telegram Error: {e}")


def send_exit_alert(ticker, strategy, status, price, pnl, final_balance):
    """Sends a formatted EXIT alert."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return

    mode = "📝 *PAPER*" if PAPER_MODE else "💸 *LIVE*"
    emoji = "✅" if pnl > 0 else "🛑"
    
    msg = (
        f"{emoji} *EXIT ALERT: {strategy}*\n"
        f"💎 *{ticker}* | {mode}\n"
        f"⚡ Status: {status}\n"
        f"💵 Exit Price: {price}\n"
        f"💰 PnL: {'+' if pnl>0 else ''}₹{pnl:.2f}\n"
        f"🏦 Strategy Balance: ₹{final_balance:,.0f}"
    )
    
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        )
    except: pass