import time
import yfinance as yf
from src.tools import fetch_upstox_map, fetch_data
from src.finder.strategy import run_screener

# --- MODULAR IMPORTS ---
from src.strategies import momentum, mean_reversion, ai_sniper
from src.bot.auth import authenticate_system
from src.bot.telegram import send_telegram_alert
from src.bot.executor import execute_trade

# --- CONFIG ---
STRATEGIES = {
    "STRATEGY_MOMENTUM": momentum,
    "STRATEGY_MEAN_REVERSION": mean_reversion,
    "STRATEGY_AI_SNIPER": ai_sniper
}

def check_market_regime():
    """
    Returns False if Nifty 50 is in a downtrend.
    Acts as a 'Circuit Breaker' for the whole fund.
    """
    try:
        # Download Nifty 50 Data
        nifty = yf.download("^NSEI", period="1y", progress=False)
        
        if not nifty.empty:
            curr = float(nifty['Close'].iloc[-1])
            # Calculate 200 Day Moving Average
            ema200 = float(nifty['Close'].ewm(span=200).mean().iloc[-1])
            
            if curr < ema200:
                print(f"🔴 MARKET BEARISH (Nifty {curr:.0f} < 200EMA {ema200:.0f}). Halting Long Strategies.")
                return False
                
        return True
    except Exception as e:
        print(f"   ⚠️ Market Check Warning: {e}")
        return True # Default to True if check fails to avoid stalling

def run_bot():
    print(f"\n🏟️ OPENING THE ARENA")
    
    # 1. System Check (Auth + Market Health)
    if not authenticate_system(): return
    if not check_market_regime(): return

    # 2. Find Candidates (The 'Battlefield')
    candidates = run_screener(limit=10)
    master_map = fetch_upstox_map()
    
    print(f"\n⚔️ Analyzing {len(candidates)} Stocks across {len(STRATEGIES)} Strategies...")

    # 3. The Tournament Loop
    for ticker in candidates:
        print(f"\n🔍 {ticker}...")
        
        # Fetch Data Once (Efficiency)
        # Note: fetch_data handles the .NS suffix logic internally
        df_daily = fetch_data(ticker, period="1y", interval="1d")
        
        if df_daily is None or df_daily.empty: 
            continue

        for strat_name, gladiator in STRATEGIES.items():
            try:
                # A. Analysis Phase
                decision = None
                
                if strat_name == "STRATEGY_AI_SNIPER":
                    # AI needs the Map to check Upstox keys
                    decision = gladiator.analyze(ticker, master_map)
                else:
                    # Technical bots just need the dataframe
                    decision = gladiator.analyze(df_daily)

                # B. Execution Phase
                if decision and decision['action'] == "BUY":
                    # Smart Fallbacks: If strategy didn't specify price, use current Close
                    price = decision.get('price', df_daily['Close'].iloc[-1])
                    # If strategy didn't calc ATR, use 2% default
                    atr = decision.get('atr', price * 0.02) 
                    
                    # Delegate to Executor (Handles Risk & DB)
                    qty = execute_trade(
                        ticker=ticker,
                        strategy_name=strat_name,
                        signal="BUY",
                        price=price,
                        atr=atr,
                        decision_reason=decision['reason'],
                        confidence=decision['confidence']
                    )
                    
                    if qty > 0:
                        print(f"   🚀 {strat_name}: BUY {qty} shares")
                        # Send Alert
                        send_telegram_alert(ticker, strat_name, "BUY", qty, price, decision['reason'])
                    else:
                        print(f"   ⚠️ {strat_name}: Signal BUY, but Insufficient Funds or Risk Cap.")
            
            except Exception as e:
                print(f"   ❌ {strat_name} Error: {e}")

    print("\n🏁 TOURNAMENT ROUND COMPLETE.")

if __name__ == "__main__":
    run_bot()