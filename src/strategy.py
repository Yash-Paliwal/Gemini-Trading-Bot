import pandas as pd
import yfinance as yf

# --- 1. TECHNICAL MATH ENGINE ---
def get_technicals(candles):
    if not candles or len(candles) < 200: return None
    # Assuming 'c.model_dump()' works (Pydantic v2) or 'c.dict()' (v1)
    try:
        data = [c.model_dump() for c in candles]
    except:
        data = [c.dict() for c in candles]
        
    df = pd.DataFrame(data)
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float); df['low'] = df['low'].astype(float)
    
    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta>0, 0)).rolling(14).mean()
    loss = (-delta.where(delta<0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100/(1+(gain/loss)))
    
    # ATR
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['close'].shift())
    df['tr3'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    
    cur = df.iloc[-1]
    return {"rsi": round(cur['rsi'],2), "price": cur['close'], "atr": round(cur['atr'],2), "trend": "UP" if cur['close']>cur['ema_200'] else "DOWN"}

def calculate_weekly_trend(candles):
    if not candles or len(candles) < 40: return "UNKNOWN"
    try:
        data = [c.model_dump() for c in candles]
    except:
        data = [c.dict() for c in candles]
        
    df = pd.DataFrame(data)
    df['close'] = df['close'].astype(float)
    df['ema_40'] = df['close'].ewm(span=40).mean()
    return "UP" if df.iloc[-1]['close'] > df.iloc[-1]['ema_40'] else "DOWN"

# --- 2. MULTI-STRATEGY SCREENER ---
def run_screener(limit=5):
    print("\n🕵️ SCANNING SECTORS & VOLUME...")
    
    # 🚨 FIX: Correct Yahoo Tickers for Indices (Must have ^)
    sector_universe = {
        "^CNXAUTO": ["MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "HEROMOTOCO.NS", "EICHERMOT.NS", "BAJAJ-AUTO.NS", "TVSMOTOR.NS"],
        "^CNXIT": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "TECHM.NS", "WIPRO.NS", "LTIM.NS", "PERSISTENT.NS"],
        "^CNXMETAL": ["TATASTEEL.NS", "HINDALCO.NS", "JSWSTEEL.NS", "JINDALSTEL.NS", "VEDL.NS", "NMDC.NS"],
        "^CNXPHARMA": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "APOLLOHOSP.NS", "LUPIN.NS"],
        "^CNXFMCG": ["ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS", "VBL.NS"],
        "^NSEBANK": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS", "INDUSINDBK.NS", "BANKBARODA.NS"],
        # General list for fallback (No index here)
        "OTHERS": ["RELIANCE.NS", "BEL.NS", "HAL.NS", "TRENT.NS", "ETERNAL.NS", "DLF.NS", "VBL.NS", "ABB.NS", "INDIGO.NS"]
    }
    
    # Flatten list for broad scan
    all_stocks = [s for sublist in sector_universe.values() for s in sublist]
    
    # List of Indices to check (Only keys starting with ^)
    indices = [k for k in sector_universe.keys() if k.startswith("^")]

    try:
        # 1. Check Sectors
        # 🚨 FIX: Handle yfinance 0.2+ MultiIndex columns
        idx_data = yf.download(indices, period="2d", progress=False)
        
        # Extract 'Close' safely
        if 'Close' in idx_data.columns:
            closes = idx_data['Close']
        else:
            closes = idx_data # Fallback
            
        # Calculate % Change
        idx_pct = ((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2]) * 100
        top_sec = idx_pct.idxmax()
        top_gain = idx_pct.max()
        
        # Decide Scan List
        if top_gain > 0.8:
            scan_list = sector_universe.get(top_sec, all_stocks)
            print(f"   🎯 Target: {top_sec} (+{top_gain:.2f}%)")
        else:
            scan_list = all_stocks
            print(f"   ⚠️ Market Flat. Scanning Broad List ({len(scan_list)} stocks).")
        
        # 2. Check Volume & Momentum
        data = yf.download(scan_list, period="20d", progress=False)
        candidates = {}
        
        # Handle yfinance structure again
        vol_df = data['Volume'] if 'Volume' in data.columns else data
        close_df = data['Close'] if 'Close' in data.columns else data

        for s in scan_list:
            try:
                # Handle Single vs Multi Ticker response
                if len(scan_list) > 1:
                    vol = vol_df[s]
                    close = close_df[s]
                else:
                    vol = vol_df
                    close = close_df
                
                # Math
                shock = vol.iloc[-1] / vol.mean()
                change = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100
                
                # Logic: Volume > 1.5x AND Price Up > 0.2%
                if shock > 1.5 and change > 0.2: 
                    clean = s.replace(".NS","")
                    candidates[clean] = shock
            except: continue
            
        winners = sorted(candidates, key=candidates.get, reverse=True)[:limit]
        
        # Fallback if no volume shocks found
        if not winners:
            print("   ⚠️ No Volume Spikes. Using Top Price Gainers.")
            if len(scan_list) > 1: 
                # Calculate simple price % change
                gains = ((close_df.iloc[-1] - close_df.iloc[-2]) / close_df.iloc[-2] * 100)
                winners = [x.replace(".NS","") for x in gains.sort_values(ascending=False).head(limit).index]
        
        print(f"   🚀 Candidates: {winners}")
        return winners

    except Exception as e:
        print(f"   ⚠️ Screener Error: {e}")
        return ["RELIANCE", "TCS"] # Safe Fallback