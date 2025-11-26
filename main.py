import os
import time
import json
import gzip
import io
import requests
import pandas as pd
import yfinance as yf
import google.generativeai as genai
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from html import unescape
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURATION ---
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
INDIANAPI_KEY       = os.getenv("INDIANAPI_KEY")
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID")
GDRIVE_JSON         = os.getenv("GDRIVE_CREDENTIALS")
SHEET_NAME          = "GeminiTrader_Logs"

ACCOUNT_SIZE = 100000
RISK_PER_TRADE = 0.02

# --- DATA MODELS ---
class PriceCandle(BaseModel):
    timestamp: datetime; open: float; high: float; low: float; close: float; volume: int; ticker: str

class FundamentalSnapshot(BaseModel):
    ticker: str; market_cap: Optional[float]=None; pe_ratio: Optional[float]=None; promoter_holding: Optional[float]=None; fii_holding: Optional[float]=None; dii_holding: Optional[float]=None

class NewsItem(BaseModel):
    title: str; source: str

# --- TOOL 1: MAPPER ---
def fetch_upstox_map():
    print("📥 Loading Instrument Map...")
    try:
        r = requests.get("https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz")
        with gzip.GzipFile(fileobj=io.BytesIO(r.content)) as f: data = json.load(f)
        m = {i['trading_symbol']: i['instrument_key'] for i in data if i.get('segment') == 'NSE_EQ'}
        aliases = {"TATAMOTORS": "TMPV", "M&M": "M&M", "BAJAJ-AUTO": "BAJAJ-AUTO", "LTIM": "LTIM"}
        for y, u in aliases.items(): 
            if u in m: m[y] = m[u]
        print(f"✅ Loaded {len(m)} Instruments.")
        return m
    except: return {}

MASTER_MAP = fetch_upstox_map()

# --- TOOL 2: DATA ---
def get_live_price(instrument_key, symbol_fallback=None):
    url = "https://api.upstox.com/v3/market-quote/ltp"
    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {UPSTOX_ACCESS_TOKEN}'}
    def try_key(k):
        try:
            res = requests.get(url, params={"instrument_key": k}, headers=headers)
            d = res.json()
            if 'data' in d and d['data']:
                first = next(iter(d['data']))
                return float(d['data'][first]['last_price'])
        except: return None
    price = try_key(instrument_key)
    if price: return price
    if symbol_fallback: return try_key(f"NSE_EQ|{symbol_fallback.replace('.NS','').upper()}")
    return None

def fetch_candles(key, days, interval="days"):
    start = datetime.now().date() - timedelta(days=days)
    url = f"https://api.upstox.com/v3/historical-candle/{key}/{interval}/1/{datetime.now().date()}/{start}"
    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {UPSTOX_ACCESS_TOKEN}'}
    try:
        res = requests.get(url, headers=headers).json()
        c = res.get('data', {}).get('candles', [])
        if not c: return []
        return sorted([PriceCandle(timestamp=datetime.fromisoformat(i[0].replace('Z','+00:00')), open=i[1], high=i[2], low=i[3], close=i[4], volume=i[5], ticker=key) for i in c], key=lambda x: x.timestamp)
    except: return []

def get_technicals(candles):
    if not candles or len(candles) < 200: return None
    df = pd.DataFrame([c.model_dump() for c in candles])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float); df['low'] = df['low'].astype(float)
    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta>0, 0)).rolling(14).mean()
    loss = (-delta.where(delta<0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100/(1+(gain/loss)))
    
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['close'].shift())
    df['tr3'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    
    cur = df.iloc[-1]
    return {"rsi": round(cur['rsi'],2), "price": cur['close'], "atr": round(cur['atr'],2), "trend": "UP" if cur['close']>cur['ema_200'] else "DOWN"}

def calculate_weekly_trend(candles):
    if not candles or len(candles) < 40: return "UNKNOWN"
    df = pd.DataFrame([c.model_dump() for c in candles])
    df['close'] = df['close'].astype(float)
    df['ema_40'] = df['close'].ewm(span=40).mean()
    return "UP" if df.iloc[-1]['close'] > df.iloc[-1]['ema_40'] else "DOWN"

def fetch_funds(name):
    try:
        r = requests.get("https://stock.indianapi.in/stock", params={'name': name.replace("&","%26")}, headers={'x-api-key': INDIANAPI_KEY}).json()
        get_v = lambda c,k: next((float(str(i['value']).replace('%','').replace(',','')) for i in r.get('keyMetrics',{}).get(c,[]) if i.get('key')==k), None)
        get_h = lambda l: next((float(str(g['categories'][-1]['percentage']).replace('%','')) for g in r.get('shareholding',[]) if l.lower() in g.get('displayName','').lower()), None)
        return FundamentalSnapshot(ticker=name, market_cap=get_v('priceandVolume','marketCap'), pe_ratio=get_v('valuation','pPerEIncludingExtraordinaryItemsTTM'), promoter_holding=get_h('Promoter'), fii_holding=get_h('Foreign'), dii_holding=get_h('Domestic'))
    except: return FundamentalSnapshot(ticker=name)

def fetch_news(name):
    try:
        url = f"https://news.google.com/rss/search?q={name}+stock+news+india&hl=en-IN&gl=IN&ceid=IN:en"
        root = ET.fromstring(requests.get(url).content)
        return [NewsItem(title=unescape(i.find('title').text), source=i.find('source').text) for i in root.findall('./channel/item')[:3]]
    except: return []

# --- TOOL 3: SCREENER ---
def run_screener(limit=5):
    print("\n🕵️ SCANNING SECTORS & VOLUME...")
    sector_universe = {
        "^CNXAUTO": ["MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "HEROMOTOCO.NS", "EICHERMOT.NS"],
        "^CNXIT": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "TECHM.NS", "WIPRO.NS"],
        "^CNXMETAL": ["TATASTEEL.NS", "HINDALCO.NS", "JSWSTEEL.NS", "VEDL.NS"],
        "^CNXPHARMA": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS"],
        "^CNXFMCG": ["ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "TATACONSUM.NS"],
        "^NSEBANK": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"]
    }
    all_stocks = [s for sublist in sector_universe.values() for s in sublist]
    
    try:
        idx_data = yf.download(list(sector_universe.keys()), period="2d", progress=False)['Close']
        idx_pct = ((idx_data.iloc[-1] - idx_data.iloc[-2]) / idx_data.iloc[-2]) * 100
        top_sec = idx_pct.idxmax()
        
        scan_list = sector_universe[top_sec.replace("^CNX","")] if idx_pct.max() > 0.8 and top_sec.replace("^CNX","") in sector_universe else all_stocks
        print(f"   🎯 Target: {top_sec} (+{idx_pct.max():.2f}%)" if idx_pct.max() > 0.8 else "   ⚠️ Market Flat. Scanning Broad.")
        
        data = yf.download(scan_list, period="20d", progress=False)
        candidates = {}
        for s in scan_list:
            try:
                vol = data['Volume'][s] if len(scan_list)>1 else data['Volume']
                close = data['Close'][s] if len(scan_list)>1 else data['Close']
                shock = vol.iloc[-1] / vol.mean()
                change = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100
                if shock > 1.5 and change > 0.2: candidates[s.replace(".NS","")] = shock
            except: continue
            
        winners = sorted(candidates, key=candidates.get, reverse=True)[:limit]
        if not winners and len(scan_list)>1: 
            gains = ((data['Close'].iloc[-1]-data['Close'].iloc[-2])/data['Close'].iloc[-2]*100).sort_values(ascending=False).head(limit)
            winners = [x.replace(".NS","") for x in gains.index]
        print(f"   🚀 Candidates: {winners}")
        return winners
    except: return ["RELIANCE", "TCS"]

# --- TOOL 4: LOGGING & EXECUTION (BUG FIXED) ---
def log_to_sheet(data, qty):
    if not GDRIVE_JSON: 
        print("   ⚠️ Google Sheets: No Credentials Found.")
        return
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(json.loads(GDRIVE_JSON), scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open(SHEET_NAME).sheet1
        
        if not sh.get_all_values(): 
            sh.append_row(["Date", "Ticker", "Signal", "Entry", "Target", "Stop", "Qty", "Reasoning", "Status"])
        
        status = "OPEN" if data['signal'] == "BUY" else "WATCH"
        row = [str(datetime.now().date()), data['ticker'], data['signal'], data.get('entry_price', 0), data.get('target_price', 0), data.get('stop_loss', 0), qty, data['reasoning'], status]
        
        sh.append_row(row)
        print(f"   📝 Sheet Update: SUCCESS ({data['ticker']} -> {data['signal']})")
        
    except Exception as e: 
        print(f"   ❌ Sheet Update: FAILED ({e})")

def run_bot():
    print("\n🤖 STARTING CLOUD AGENT...")
    
    try:
        mkt = yf.download("^NSEI", period="1y", progress=False)
        if mkt['Close'].iloc[-1] < mkt['Close'].ewm(span=200).mean().iloc[-1]:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": "🔴 *MARKET DOWNTREND* - HALTED", "parse_mode": "Markdown"})
            return
    except: pass

    winners = run_screener(limit=5)
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('models/gemini-2.5-flash', generation_config={"temperature": 0.1})

    print(f"\n🧠 Analyzing {len(winners)} Stocks...")
    for sym in winners:
        key = MASTER_MAP.get(sym)
        if not key: continue
        print(f"\n🔍 Checking {sym}...")
        try:
            daily = fetch_candles(key, 400, interval="days")
            weekly = fetch_candles(key, 700, interval="weeks")
            if not daily or not weekly: continue

            d_tech = get_technicals(daily)
            w_trend = calculate_weekly_trend(weekly)
            fund = fetch_funds(sym)
            news = fetch_news(sym)
            live_price = get_live_price(key, sym) or d_tech['price']

            prompt = f"""
            ACT AS: Hedge Fund Manager. ASSET: {sym}
            [TECHNICALS] Weekly Trend: {w_trend}. Daily Trend: {d_tech['trend']}. RSI: {d_tech['rsi']}. ATR: {d_tech['atr']}
            [FUNDAMENTALS] PE: {fund.pe_ratio}. Smart Money: {(fund.promoter_holding or 0)+(fund.fii_holding or 0)}%
            [NEWS] {chr(10).join([n.title for n in news])}
            [RULES] BUY if Weekly UP + Daily UP + RSI 40-60.
            [OUTPUT JSON] {{ "signal": "BUY/WAIT", "confidence": 0-100, "reasoning": "Text" }}
            """
            res = json.loads(model.generate_content(prompt).text.strip().replace("```json","").replace("```",""))
            
            # 🚨 FIX: Set Ticker HERE so it exists for both BUY and WAIT
            res['ticker'] = sym 
            
            qty = 0
            if res['signal'] == "BUY":
                atr = d_tech['atr']
                entry = live_price
                stop = int(entry - (2 * atr))
                target = int(entry + (4 * atr))
                risk_per_share = entry - stop
                if risk_per_share > 0: qty = int((ACCOUNT_SIZE * RISK_PER_TRADE) / risk_per_share)
                
                res.update({'entry_price': entry, 'target_price': target, 'stop_loss': stop})
                
                msg = f"🟢 *GEMINI BUY*\n💎 {sym}\nEntry: {entry}\nTgt: {target} | Stop: {stop}\n📦 *Qty: {qty}*\n🧠 {res['reasoning'][:200]}"
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
            else:
                # Ensure keys exist for logging
                res.update({'entry_price': 0, 'target_price': 0, 'stop_loss': 0})

            print(f"   ✅ Decision: {res['signal']}")
            
            # Log Everything
            log_to_sheet(res, qty)
            
            time.sleep(1.5)
        except Exception as e: print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    run_bot()
