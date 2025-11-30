import os
import time
import json
import requests
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
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

# --- TOOL: EXECUTION ---
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

    # 3. CHECK EXISTING POSITIONS
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
            live_price = get_live_price(key, sym) or d_tech['price']

            # Construct the Prompt
            smart_money = (fund.promoter_holding or 0) + (fund.fii_holding or 0)
            prompt = f"""
            ACT AS: Hedge Fund Manager. ASSET: {sym}
            [TECHNICALS] Weekly Trend: {w_trend}. Daily Trend: {d_tech['trend']}. RSI: {d_tech['rsi']}. ATR: {d_tech['atr']}
            [FUNDAMENTALS] PE: {fund.pe_ratio}. Smart Money: {smart_money:.2f}%
            [NEWS] {chr(10).join([n.title for n in news])}
            [RULES] BUY if Weekly UP + Daily UP + RSI 40-60.
            [OUTPUT JSON] {{ "signal": "BUY/WAIT", "confidence": 0-100, "reasoning": "Text" }}
            """

            # 🔍 DEBUG: PRINT PROMPT TO CONSOLE 🔍
            print("\n" + "="*50)
            print(f"🤖 SENDING TO GEMINI ({sym}):")
            print("-" * 50)
            print(prompt)
            print("="*50 + "\n")

            # Call Gemini
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('models/gemini-2.5-flash', generation_config={"temperature": 0.1})
            res = json.loads(model.generate_content(prompt).text.strip().replace("```json","").replace("```",""))
            
            res['ticker'] = sym
            
            qty = 0
            if res['signal'] == "BUY":
                atr = d_tech['atr']
                entry = live_price
                stop = int(entry - (2 * atr))
                target = int(entry + (4 * atr))
                
                risk_per_share = entry - stop
                if risk_per_share > 0: 
                    qty = int((ACCOUNT_SIZE * RISK_PER_TRADE) / risk_per_share)
                
                res.update({'entry_price': entry, 'target_price': target, 'stop_loss': stop})
                
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
            log_trade(res, qty)
            
            time.sleep(1.5)
        except Exception as e: print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    run_bot()