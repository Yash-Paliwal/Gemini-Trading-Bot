import pandas as pd
import yfinance as yf
import numpy as np

# --- 1. SUPER TECHNICAL ENGINE (MACD + ADX + BOL) ---
def get_technicals(candles):
    if not candles or len(candles) < 200: return None
    
    # Standard Data Prep
    try: data = [c.model_dump() for c in candles]
    except: data = [c.dict() for c in candles]
    df = pd.DataFrame(data)
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    
    # 1. EMAs
    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()
    
    # 2. RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta>0, 0)).rolling(14).mean()
    loss = (-delta.where(delta<0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100/(1+(gain/loss)))
    
    # 3. MACD (12, 26, 9) - MOMENTUM
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['signal']
    
    # 4. ADX (14) - TREND STRENGTH
    # (Simplified True Range calculation for speed)
    df['tr'] = df[['high', 'low', 'close']].apply(
        lambda x: max(x['high']-x['low'], abs(x['high']-x['close']), abs(x['low']-x['close'])), axis=1
    )
    df['atr'] = df['tr'].rolling(14).mean()
    
    # Directional Movement
    df['up_move'] = df['high'] - df['high'].shift(1)
    df['down_move'] = df['low'].shift(1) - df['low']
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
    
    df['plus_di'] = 100 * (df['plus_dm'].rolling(14).mean() / df['atr'])
    df['minus_di'] = 100 * (df['minus_dm'].rolling(14).mean() / df['atr'])
    df['dx'] = 100 * abs((df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di']))
    df['adx'] = df['dx'].rolling(14).mean()

    cur = df.iloc[-1]
    
    return {
        "price": round(cur['close'], 2),
        "rsi": round(cur['rsi'], 2),
        "atr": round(cur['atr'], 2),
        "ema_50": round(cur['ema_50'], 2),
        "ema_200": round(cur['ema_200'], 2),
        "macd": round(cur['macd'], 2),
        "macd_signal": round(cur['signal'], 2),
        "adx": round(cur['adx'], 2),
        "trend": "UP" if cur['close'] > cur['ema_200'] else "DOWN"
    }

def calculate_weekly_trend(candles):
    if not candles or len(candles) < 40: return "UNKNOWN"
    try: data = [c.model_dump() for c in candles]
    except: data = [c.dict() for c in candles]
    df = pd.DataFrame(data)
    df['close'] = df['close'].astype(float)
    df['ema_40'] = df['close'].ewm(span=40).mean()
    return "UP" if df.iloc[-1]['close'] > df.iloc[-1]['ema_40'] else "DOWN"

# --- 2. MULTI-STRATEGY SCREENER ---
def run_screener(limit=3):
    print(f"\n🕵️ STARTING MULTI-STRATEGY SCAN (Universe: ~80 Stocks)...")
    
    sector_universe = {
        "AUTO": ["MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "HEROMOTOCO.NS", "EICHERMOT.NS", "BAJAJ-AUTO.NS", "TVSMOTOR.NS"],
        "IT": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "TECHM.NS", "WIPRO.NS", "LTIM.NS"],
        "METAL": ["TATASTEEL.NS", "HINDALCO.NS", "JSWSTEEL.NS", "JINDALSTEL.NS", "VEDL.NS", "NMDC.NS"],
        "PHARMA": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "APOLLOHOSP.NS"],
        "FMCG": ["ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS", "VBL.NS"],
        "BANKS": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS", "INDUSINDBK.NS"],
        # 🚨 FIX: Updated ZOMATO -> ETERNAL and VARUN -> VBL
        "OTHERS": ["RELIANCE.NS", "BEL.NS", "HAL.NS", "TRENT.NS", "ETERNAL.NS", "DLF.NS", "VBL.NS", "ABB.NS", "INDIGO.NS"]
    }
    all_stocks = [s for sublist in sector_universe.values() for s in sublist]

    try:
        print("   📊 Downloading Batch Data (1 Year)...")
        data = yf.download(all_stocks, period="1y", progress=False)
        
        # Handle yfinance MultiIndex
        closes = data['Close']
        volumes = data['Volume']
        highs = data['High']

        # --- STRATEGY A: MOMENTUM ---
        today_change = ((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2]) * 100
        mom_winners = today_change.sort_values(ascending=False).head(limit)
        
        print(f"\n   🚀 [MOMENTUM] Top Gainers:")
        for sym in mom_winners.index:
            print(f"      -> {sym.replace('.NS','')} (+{mom_winners[sym]:.2f}%)")

        # --- STRATEGY B: VOLUME SHOCKERS ---
        avg_vol = volumes.iloc[-20:].mean()
        today_vol = volumes.iloc[-1]
        vol_ratio = today_vol / avg_vol
        
        # Filter: Volume > 2x AND Price Green
        shockers = vol_ratio[(vol_ratio > 2.0) & (today_change > 0)].sort_values(ascending=False).head(limit)
        
        print(f"\n   ⚡ [VOLUME] Hidden Buying:")
        if not shockers.empty:
            for sym in shockers.index:
                print(f"      -> {sym.replace('.NS','')} (Vol {shockers[sym]:.1f}x)")
        else: print("      (None found)")

        # --- STRATEGY C: BREAKOUTS ---
        year_highs = highs.iloc[-252:].max()
        current = closes.iloc[-1]
        near_high = (current >= year_highs * 0.98)
        breakouts = near_high[near_high].index.tolist()[:limit]
        
        print(f"\n   🌟 [BREAKOUT] 52-Week Highs:")
        if breakouts:
            for sym in breakouts: print(f"      -> {sym.replace('.NS','')}")
        else: print("      (None found)")

        # --- CONSOLIDATE ---
        final_list = list(set(mom_winners.index.tolist() + shockers.index.tolist() + breakouts))
        clean_list = [x.replace(".NS", "") for x in final_list]
        
        print(f"\n   🔥 FINAL WATCHLIST: {clean_list}")
        return clean_list

    except Exception as e:
        print(f"   ⚠️ Screener Error: {e}")
        return ["RELIANCE", "TCS"] # Fallback