import requests
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ACCOUNT_SIZE, RISK_PER_TRADE

def send_alert(t, live_price, qty):
    emoji = "🟢" if t['signal'] == "BUY" else "⚪"
    msg = f"{emoji} *GEMINI*\n💎 {t['ticker']}\nEntry: {live_price}\nTgt: {t['target_price']} | Stop: {t['stop_loss']}\n📦 Qty: {qty}\n🧠 {t['reasoning'][:200]}"
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})