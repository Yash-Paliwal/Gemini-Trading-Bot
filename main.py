import os
import time
import json
import requests
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta
from html import unescape
from sqlalchemy import text

# --- IMPORTS FROM SRC ---
from src.database import log_trade, init_db, Session, get_open_trades
from src.tools import fetch_upstox_map, get_live_price, fetch_candles, fetch_funds, fetch_news
from src.strategy import run_screener, get_technicals, calculate_weekly_trend
from src.brain import analyze_stock_ai
from src.upstox_client import upstox_client

# --- CONFIGURATION ---
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
INDIANAPI_KEY       = os.getenv("INDIANAPI_KEY")
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID")

# 🚨 PAPER TRADING SWITCH
PAPER_MODE = os.getenv("PAPER_MODE", "True").lower() == "true"

ACCOUNT_SIZE = 100000
RISK_PER_TRADE = 0.02

# --- EXECUTION ---
def run_bot():
    mode_label = "📝 PAPER MODE" if PAPER_MODE else "💸 REAL MONEY MODE"
    print(f"\n🤖 STARTING CLOUD AGENT ({mode_label})...")
    
    # 1. INITIALIZE UPSTOX GATEKEEPER
    print("🔌 Connecting to Upstox...", end=" ")
    upstox_client.set_access_token(UPSTOX_ACCESS_TOKEN)
    
    if upstox_client.check_connection():
        print("✅ Connection Good.")
    else:
        print("❌ Upstox Connection Failed. STOPPING.")
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": "🔴 *CRITICAL FAIL*: Upstox Token Expired!", "parse_mode": "Markdown"})
        return

    # 2. DB CHECK
    print("🔌 Testing Database...", end=" ")
    try:
        session = Session()
        session.execute(text("SELECT 1"))
        session.close()
        print("✅ ONLINE!")
    except Exception as e:
        print(f"❌ DATABASE FAILED: {e}")
        return

    try: init_db()
    except: pass

    # 3. CHECK EXISTING POSITIONS (Prevent Duplicates)
    open_trades = get_open_trades()
    open_tickers = [t.ticker for t in open_trades]
    print(f"   📋 Portfolio Positions: {open_tickers}")

    # 4. MARKET CHECK
    try:
        mkt = yf.download("^NSEI", period="1y", progress=False)
        if mkt['Close'].iloc[-1] < mkt['Close'].ewm(span=200).mean().iloc[-1]:
            msg = f"🔴 *MARKET DOWNTREND* - {mode_label} HALTED"
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
            return
    except: pass

    # 5. SCAN & ANALYZE
    winners = run_screener(limit=5)
    master_map = fetch_upstox_map()

    print(f"\n🧠 Analyzing {len(winners)} Stocks...")
    for sym in winners:
        # SKIP DUPLICATES
        if sym in open_tickers:
            print(f"   ⚠️ Skipping {sym}: Position already OPEN.")
            continue

        key = master_map.get(sym)
        if not key: continue
        print(f"\n🔍 Checking {sym}...")
        try:
            daily = fetch_candles(key, 400, "days")
            weekly = fetch_candles(key, 700, "weeks")
            if not daily or not weekly: continue

            d_tech = get_technicals(daily)
            w_trend = calculate_weekly_trend(weekly)
            fund = fetch_funds(sym)
            news = fetch_news(sym)
            
            # Get Live Price via Client
            live_price = get_live_price(key, sym) or d_tech['price']

            # AI Analysis
            res = analyze_stock_ai(sym, d_tech, w_trend, fund, news)
            res['ticker'] = sym
            
            qty = 0
            if res['signal'] == "BUY":
                atr = d_tech['atr']
                entry = live_price
                stop = int(entry - (2 * atr))
                target = int(entry + (4 * atr))
                
                # Position Sizing
                risk_per_share = entry - stop
                if risk_per_share > 0: 
                    qty = int((ACCOUNT_SIZE * RISK_PER_TRADE) / risk_per_share)
                
                res.update({'entry_price': entry, 'target_price': target, 'stop_loss': stop})
                
                # --- TELEGRAM ALERT ---
                title = "📝 *PAPER TRADE*" if PAPER_MODE else "🟢 *LIVE TRADE*"
                msg = (
                    f"{title}\n"
                    f"💎 *{sym}*\n"
                    f"Entry: {entry}\n"
                    f"Tgt: {target} | Stop: {stop}\n"
                    f"📦 Qty: {qty} (Risk: ₹{ACCOUNT_SIZE*RISK_PER_TRADE:.0f})\n"
                    f"🧠 {res['reasoning'][:200]}"
                )
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
                
            else:
                res.update({'entry_price': 0, 'target_price': 0, 'stop_loss': 0})

            print(f"   ✅ Decision: {res['signal']}")
            
            # Log Everything (Status is handled inside log_trade)
            log_trade(res, qty)
            
            time.sleep(1.5)
        except Exception as e: print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    run_bot()