import time
import argparse
import sys
import yfinance as yf
from datetime import datetime

# --- IMPORT MODULES ---
from src.config import ACCOUNT_SIZE, RISK_PER_TRADE
from src.database import init_db, log_trade
from src.tools import (
    fetch_upstox_map, 
    get_live_price, 
    fetch_candles, 
    fetch_funds, 
    fetch_news
)
from src.strategy import (
    run_screener, 
    get_technicals, 
    calculate_weekly_trend
)
from src.brain import analyze_stock_ai
from src.notifier import send_alert

# --- CLI ARGUMENTS ---
parser = argparse.ArgumentParser(description="Gemini Swing Trading Bot")
parser.add_argument("--dry-run", action="store_true", help="Run analysis without sending alerts or logging DB")
args = parser.parse_args()

def check_market_status():
    """Checks NIFTY 50 trend to decide if we trade."""
    print("🚦 Checking Market Regime...", end=" ")
    try:
        # Download Nifty 50 Data
        mkt = yf.download("^NSEI", period="1y", progress=False)
        
        # 🚨 FIX: Handle yfinance MultiIndex issue
        if 'Close' in mkt.columns:
            closes = mkt['Close']
            # If it's a DataFrame (multiple columns), squeeze it to Series
            if hasattr(closes, "shape") and len(closes.shape) > 1:
                closes = closes.iloc[:, 0]
        else:
            print("⚠️ Data Error. Assuming CAUTION.")
            return "CAUTION"

        # Calculate Indicators
        ema200 = closes.ewm(span=200).mean().iloc[-1]
        current = closes.iloc[-1]
        
        # 🚨 FIX: Force conversion to standard Python float
        current_val = float(current)
        ema_val = float(ema200)
        
        if current_val < ema_val:
            print(f"🔴 BEARISH (Price {current_val:.0f} < 200EMA {ema_val:.0f})")
            return "STOP"
        print(f"🟢 BULLISH (Price {current_val:.0f} > 200EMA {ema_val:.0f})")
        return "GO"
        
    except Exception as e:
        print(f"⚠️ Error ({e}). Assuming CAUTION.")
        return "CAUTION"

def run_bot():
    print(f"\n🤖 STARTING ENGINE at {datetime.now().strftime('%H:%M:%S')}...")
    if args.dry_run:
        print("🧪 MODE: DRY RUN (No DB writes, No Telegram)")

    # 1. Initialize DB
    if not args.dry_run:
        init_db()

    # 2. Market Filter
    market_status = check_market_status()
    if market_status == "STOP":
        print("🛑 HALTING: Market is in Downtrend.")
        return

    # 3. Run Screener
    winners = run_screener(limit=5)
    print(f"\n🧠 Analyzing {len(winners)} Candidates...")
    
    master_map = fetch_upstox_map()

    for sym in winners:
        clean_sym = sym.replace(".NS", "")
        key = master_map.get(clean_sym)
        
        if not key:
            print(f"❌ Key Not Found: {clean_sym}")
            continue
            
        print(f"\n🔍 Checking {clean_sym}...")
        
        try:
            # A. Fetch Data
            daily = fetch_candles(key, 400, "days")
            weekly = fetch_candles(key, 700, "weeks")
            
            if not daily or not weekly:
                print("   ⚠️ Insufficient Candle Data")
                continue

            # B. Technical Analysis
            d_tech = get_technicals(daily)
            w_trend = calculate_weekly_trend(weekly)
            
            # C. Fundamental & News
            fund = fetch_funds(clean_sym)
            news = fetch_news(clean_sym)
            
            # D. LIVE PRICE & SLIPPAGE CHECK
            live_price = get_live_price(key, clean_sym) or d_tech['price']
            
            # Slippage Logic
            chart_price = d_tech['price']
            gap = abs((live_price - chart_price) / chart_price) * 100
            
            if gap > 2.0:
                print(f"   ⚠️ SLIPPAGE WARNING: Live {live_price} vs Chart {chart_price} (Gap: {gap:.1f}%)")
            
            # E. AI Analysis
            res = analyze_stock_ai(clean_sym, d_tech, w_trend, fund, news)
            res['ticker'] = clean_sym
            
            # F. Execution Logic
            qty = 0
            if res['signal'] == "BUY":
                atr = d_tech['atr']
                
                # Dynamic Targets based on Volatility (ATR)
                res['entry_price'] = live_price
                res['stop_loss'] = int(live_price - (2 * atr))
                res['target_price'] = int(live_price + (4 * atr))
                
                # Position Sizing
                risk_per_share = res['entry_price'] - res['stop_loss']
                if risk_per_share > 0:
                    qty = int((ACCOUNT_SIZE * RISK_PER_TRADE) / risk_per_share)
                
                # Alerts
                print(f"   🟢 SIGNAL: BUY {qty} Shares")
                if not args.dry_run:
                    send_alert(res, live_price, qty)
            else:
                # Ensure fields exist for logging
                res.update({'entry_price': 0, 'target_price': 0, 'stop_loss': 0})
                print(f"   ⚪ SIGNAL: {res['signal']}")

            # G. Logging
            if not args.dry_run:
                log_trade(res, qty)
            
            time.sleep(1.5)

        except KeyboardInterrupt:
            print("\n🛑 MANUAL STOP")
            sys.exit()
        except Exception as e:
            print(f"   ❌ ERROR: {e}")

    print("\n🏁 SCAN COMPLETE.")

if __name__ == "__main__":
    run_bot()