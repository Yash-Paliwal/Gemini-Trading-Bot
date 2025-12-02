import os
import time
import json
import requests
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta
from html import unescape
from sqlalchemy import text

# --- IMPORTS ---
from src.database import log_trade, log_signal_audit, init_db, Session, get_open_trades, get_current_balance, update_balance
from src.tools import fetch_upstox_map, get_live_price, fetch_candles, fetch_funds, fetch_news
from src.finder.strategy import run_screener, get_technicals, calculate_weekly_trend
from src.finder.brain import analyze_stock_ai
from src.upstox_client import upstox_client
from src.portfolio.manager import check_portfolio_health
from src.risk.calculator import calculate_position_size

# --- CONFIGURATION ---
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
INDIANAPI_KEY       = os.getenv("INDIANAPI_KEY")
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID")
PAPER_MODE          = os.getenv("PAPER_MODE", "True").lower() == "true"

ACCOUNT_SIZE = 100000
RISK_PER_TRADE = 0.02

# --- HELPER: TELEGRAM ---
def send_telegram_alert(t, qty, live_price, wallet_bal):
    emoji = "⚠️" if t['signal'] == "WAIT" else ("🟢" if t['signal']=="BUY" else "🔴")
    mode_tag = "📝 *PAPER*" if PAPER_MODE else "💸 *LIVE*"
    
    qty_text = ""
    if t['signal'] == "BUY":
        cost = qty * live_price
        qty_text = f"\n📦 *SIZE: {qty} Shares* (₹{cost:,.0f})\n💰 *Wallet:* ₹{wallet_bal:,.0f}"

    msg = (
        f"{emoji} *GEMINI ALERT* ({mode_tag})\n"
        f"💎 *{t.get('ticker')}*\n"
        f"🚀 *{t['signal']}* (Conf: {t['confidence']}%)\n"
        f"⚡ Entry: {live_price}\n"
        f"🎯 Tgt: {t['target_price']} | 🛑 Stop: {t['stop_loss']}"
        f"{qty_text}\n\n"
        f"🧠 {t['reasoning'][:200]}"
    )
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except Exception as e: print(f"   ❌ Telegram Error: {e}")

# --- MAIN ENGINE ---
def run_bot():
    mode_label = "📝 PAPER MODE" if PAPER_MODE else "💸 REAL MONEY MODE"
    print(f"\n🤖 STARTING HEDGE FUND ENGINE ({mode_label})...")
    
    # 1. SMART AUTHENTICATION (The Final Link)
    print("🔌 Connecting to Upstox...", end=" ")
    
    # A. Try GitHub Secret First
    if UPSTOX_ACCESS_TOKEN:
        upstox_client.set_access_token(UPSTOX_ACCESS_TOKEN)
    
    # B. If Secret is missing or expired, Try Database
    if not upstox_client.check_connection():
        print("   ⚠️ Secret Token Invalid. Checking Database...")
        if upstox_client.fetch_token_from_db():
            print("   ✅ Loaded Fresh Token from Database!")
        else:
            print("   ❌ Database Token Missing/Expired.")
            
    # Final Check
    if not upstox_client.check_connection():
        print("❌ CRITICAL FAIL: No valid token found anywhere. STOPPING.")
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": "🔴 *AUTH FAILED*: Please Login via Dashboard!", "parse_mode": "Markdown"})
        return

    print("🔌 Testing Database...", end=" ")
    try: init_db(); print("✅ Online.")
    except Exception as e: print(f"❌ DB FAIL: {e}"); return

    # 2. MACRO FILTER
    try:
        print("🚦 Checking Market Regime...", end=" ")
        mkt = yf.download("^NSEI", period="1y", progress=False)
        if not mkt.empty:
            curr = float(mkt['Close'].iloc[-1])
            ema200 = float(mkt['Close'].ewm(span=200).mean().iloc[-1])
            if curr < ema200:
                print(f"🔴 BEARISH ({curr:.0f} < {ema200:.0f}). HALTING.")
                return
            print(f"🟢 BULLISH ({curr:.0f} > {ema200:.0f})")
    except: print("⚠️ Market Check Error. Proceeding cautiously.")

    # 3. SCREENER
    winners = run_screener(limit=5)
    master_map = fetch_upstox_map()

    print(f"\n🧠 Analyzing {len(winners)} Candidates...")
    for sym in winners:
        # A. PORTFOLIO CHECK
        allowed, reason = check_portfolio_health(sym)
        if not allowed:
            print(f"   ⛔ SKIPPING {sym}: {reason}")
            continue

        key = master_map.get(sym)
        if not key: print(f"   ⚠️ No Key for {sym}"); continue
            
        print(f"\n🔍 Checking {sym}...")
        try:
            # B. DATA
            daily = fetch_candles(key, 400, "days")
            weekly = fetch_candles(key, 700, "weeks")
            if not daily or not weekly: print("   ⚠️ Insufficient Data"); continue

            d_tech = get_technicals(daily)
            w_trend = calculate_weekly_trend(weekly)
            fund = fetch_funds(sym)
            news = fetch_news(sym)
            
            # C. LIVE PRICE CHECK
            live_price = get_live_price(key, sym)
            if not live_price:
                print(f"   ❌ ABORTING {sym}: Could not fetch Live Price.")
                continue
            
            # Inject Reality
            d_tech['price'] = live_price

            # D. AI BRAIN
            res = analyze_stock_ai(sym, d_tech, w_trend, fund, news)
            res['ticker'] = sym
            
            qty = 0
            if res['signal'] == "BUY":
                atr = d_tech['atr']
                
                # E. EXECUTION MATH
                slippage_buffer = atr * 0.10
                execution_price = round(live_price + slippage_buffer, 2)
                
                stop = int(execution_price - (2 * atr))
                target = int(execution_price + (4 * atr))
                
                qty = calculate_position_size(execution_price, stop)
                
                # F. WALLET CHECK
                cost = qty * execution_price
                balance = get_current_balance()
                
                if cost > balance:
                    if balance > 0:
                        safe_balance = balance * 0.99 
                        qty = int(safe_balance / execution_price)
                        print(f"   📉 Resized Qty to {qty} (Funds Limit)")
                        cost = qty * execution_price
                    else: qty = 0
                
                if qty > 0:
                    res.update({'entry_price': execution_price, 'target_price': target, 'stop_loss': stop})
                    
                    # Execute
                    update_balance(-cost)
                    log_trade(res, qty)
                    send_telegram_alert(res, qty, execution_price, get_current_balance())
                    print(f"   ✅ BUY EXECUTED: {qty} Shares")
                else:
                    print("   ⚠️ Signal BUY, but Qty is 0.")
            
            else:
                # Log Audit Trail for WAIT signals
                log_signal_audit(sym, res['signal'], res.get('reasoning', ''))
                print(f"   ⚪ Decision: {res['signal']}")

            time.sleep(1.5)

        except Exception as e: print(f"   ❌ Error analyzing {sym}: {e}")

    print("\n🏁 SESSION COMPLETE.")

if __name__ == "__main__":
    run_bot()