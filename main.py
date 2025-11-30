import time
import requests
import yfinance as yf
from datetime import datetime

# --- 1. CONFIGURATION & CLIENTS ---
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ACCOUNT_SIZE, RISK_PER_TRADE, PAPER_MODE
from src.upstox_client import upstox_client

# --- 2. CORE INFRASTRUCTURE ---
from src.database import init_db, log_trade, Session
from src.tools import fetch_upstox_map, get_live_price, fetch_candles, fetch_funds, fetch_news

# --- 3. MODULES (THE NEW LOGIC) ---
# FINDER: Locates trades and analyzes charts
from src.finder.strategy import run_screener, get_technicals, calculate_weekly_trend
from src.finder.brain import analyze_stock_ai

# PORTFOLIO: Checks rules before entering
from src.portfolio.manager import check_portfolio_health

# RISK: Calculates exact size based on VIX
from src.risk.calculator import calculate_position_size

# --- HELPER: TELEGRAM SENDER ---
def send_telegram_alert(t, qty, live_price):
    emoji = "⚠️" if t['signal'] == "WAIT" else ("🟢" if t['signal']=="BUY" else "🔴")
    mode_tag = "📝 *PAPER*" if PAPER_MODE else "💸 *LIVE*"
    
    qty_text = ""
    if t['signal'] == "BUY":
        risk_amt = ACCOUNT_SIZE * RISK_PER_TRADE
        qty_text = f"\n📦 *SIZE: {qty} Shares* (Risk: ₹{risk_amt:.0f})"

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
    except Exception as e:
        print(f"   ❌ Telegram Error: {e}")

# --- MAIN EXECUTION ENGINE ---
def run_bot():
    mode_label = "📝 PAPER MODE" if PAPER_MODE else "💸 REAL MONEY MODE"
    print(f"\n🤖 STARTING HEDGE FUND ENGINE ({mode_label})...")
    print(f"   🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ---------------------------------------------------------
    # STEP 1: SYSTEM HEALTH CHECK
    # ---------------------------------------------------------
    
    # A. Upstox Login
    print("🔌 Connecting to Upstox...", end=" ")
    from src.config import UPSTOX_ACCESS_TOKEN # Import locally to ensure freshness
    upstox_client.set_access_token(UPSTOX_ACCESS_TOKEN)
    
    if upstox_client.check_connection():
        print("✅ Connection Good.")
    else:
        print("❌ Upstox Connection Failed. STOPPING.")
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": "🔴 *CRITICAL FAIL*: Upstox Token Expired!", "parse_mode": "Markdown"})
        return

    # B. Database Check
    print("🔌 Testing Database...", end=" ")
    try:
        init_db() # Create tables if missing
        print("✅ Online.")
    except Exception as e:
        print(f"❌ DATABASE FAILED: {e}")
        return

    # ---------------------------------------------------------
    # STEP 2: MACRO FILTER (The "Traffic Light")
    # ---------------------------------------------------------
    try:
        print("🚦 Checking Market Regime...", end=" ")
        mkt = yf.download("^NSEI", period="1y", progress=False)
        # Check if DataFrame is valid
        if not mkt.empty and 'Close' in mkt.columns:
            current_nifty = float(mkt['Close'].iloc[-1])
            ema200_nifty = float(mkt['Close'].ewm(span=200).mean().iloc[-1])
            
            if current_nifty < ema200_nifty:
                msg = f"🔴 *MARKET DOWNTREND* - {mode_label} HALTED (Nifty < 200 EMA)"
                print(f"BEARISH ({current_nifty:.0f} < {ema200_nifty:.0f})")
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
                return
            print(f"BULLISH ({current_nifty:.0f} > {ema200_nifty:.0f})")
    except Exception as e: 
        print(f"⚠️ Market Check Error: {e} (Proceeding with Caution)")

    # ---------------------------------------------------------
    # STEP 3: FINDING & FILTERING
    # ---------------------------------------------------------
    winners = run_screener(limit=5)
    master_map = fetch_upstox_map()

    print(f"\n🧠 Analyzing {len(winners)} Candidates...")
    
    for sym in winners:
        # A. PORTFOLIO GATEKEEPER
        # Before we fetch data, check if we are allowed to buy this
        allowed, reason = check_portfolio_health(sym)
        if not allowed:
            print(f"   ⛔ SKIPPING {sym}: {reason}")
            continue

        key = master_map.get(sym)
        if not key: 
            print(f"   ⚠️ No Key for {sym}")
            continue
            
        print(f"\n🔍 Checking {sym}...")
        
        try:
            # B. DATA GATHERING
            daily = fetch_candles(key, 400, "days")
            weekly = fetch_candles(key, 700, "weeks")
            if not daily or not weekly: 
                print("   ⚠️ Insufficient Data"); continue

            d_tech = get_technicals(daily)
            w_trend = calculate_weekly_trend(weekly)
            fund = fetch_funds(sym)
            news = fetch_news(sym)
            
            # Get Live Price (Crucial for Execution)
            live_price = get_live_price(key, sym) or d_tech['price']

            # C. AI ANALYSIS (The Brain)
            res = analyze_stock_ai(sym, d_tech, w_trend, fund, news)
            res['ticker'] = sym
            
            # D. EXECUTION LOGIC
            qty = 0
            if res['signal'] == "BUY":
                atr = d_tech['atr']
                
                # Dynamic ATR-Based Stops
                entry = live_price
                stop = int(entry - (2 * atr))
                target = int(entry + (4 * atr))
                
                # RISK MANAGER (Position Sizing)
                qty = calculate_position_size(entry, stop)
                
                # Update Result Object
                res.update({'entry_price': entry, 'target_price': target, 'stop_loss': stop})
                
                # Alert
                send_telegram_alert(res, qty, live_price)
                
            else:
                # Zero out for logs
                res.update({'entry_price': 0, 'target_price': 0, 'stop_loss': 0})

            print(f"   ✅ Decision: {res['signal']}")
            
            # E. LOGGING (Audit Trail)
            log_trade(res, qty)
            
            time.sleep(1.5) # Rate limit protection

        except Exception as e: 
            print(f"   ❌ Error analyzing {sym}: {e}")

    print("\n🏁 SESSION COMPLETE.")

if __name__ == "__main__":
    run_bot()