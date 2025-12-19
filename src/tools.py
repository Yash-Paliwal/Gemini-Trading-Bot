import requests
import json
import gzip
import io
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import unescape
import yfinance as yf  # <--- NEW IMPORT
import pandas as pd    # <--- NEW IMPORT

from .config import UPSTOX_ACCESS_TOKEN, INDIANAPI_KEY
from .models import PriceCandle, FundamentalSnapshot, NewsItem
from .upstox_client import upstox_client

# --- 1. UPSTOX MAPPER ---
def fetch_upstox_map():
    print("📥 Loading Instrument Map...")
    try:
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        response = requests.get(url)
        with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as f:
            data = json.load(f)
        m = {i['trading_symbol']: i['instrument_key'] for i in data if i.get('segment') == 'NSE_EQ'}
        aliases = {"TATAMOTORS": "TMPV", "M&M": "M&M", "BAJAJ-AUTO": "BAJAJ-AUTO", "LTIM": "LTIM"}
        for y, u in aliases.items(): 
            if u in m: m[y] = m[u]
        print(f"   ✅ Loaded {len(m)} Instruments.")
        return m
    except: return {}

# --- 2. LIVE PRICE (DEBUG MODE) ---
def get_live_price(instrument_key: str, symbol_fallback: str = None):
    session = upstox_client.get_session()
    # Force V3 as requested
    url = "https://api.upstox.com/v3/market-quote/ltp" 
    
    def try_key(k):
        try:
            res = session.get(url, params={"instrument_key": k})
            if res.status_code != 200:
                # Debug print only on failure to keep logs clean
                # print(f"      ❌ API FAIL ({k}): {res.status_code}")
                return None
                
            d = res.json()
            if 'data' in d and d['data']:
                first = next(iter(d['data']))
                return float(d['data'][first]['last_price'])
        except Exception as e: 
            return None
        return None

    # Attempt 1: Direct Key
    price = try_key(instrument_key)
    if price: return price
    
    # Attempt 2: Fallback
    if symbol_fallback:
        clean_sym = symbol_fallback.replace(".NS", "").upper()
        return try_key(f"NSE_EQ|{clean_sym}")
        
    return None

# --- 3. UPSTOX HISTORICAL DATA (For specialized needs) ---
def fetch_candles(key, days, interval="days"):
    """
    Wrapper around Upstox Historical Candle Data V3.
    Docs: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data

    URL pattern:
      /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}

    For daily data:
      unit = "days", interval = "1"
      to_date = today, from_date = today - days
    """
    session = upstox_client.get_session()

    # Upstox expects to_date first, then from_date (both YYYY-MM-DD)
    to_date = datetime.now().date()
    from_date = to_date - timedelta(days=days)

    unit = interval  # keep backwards compatibility with existing calls
    url = f"https://api.upstox.com/v3/historical-candle/{key}/{unit}/1/{to_date}/{from_date}"

    try:
        res = session.get(url)
        if res.status_code != 200:
            # Return empty on failure; caller will log/handle
            # print(f"⚠️ Upstox candle API error {res.status_code} for {key}: {res.text}")
            return []

        data = res.json()
        candles = data.get("data", {}).get("candles", [])
        if not candles:
            return []

        return sorted(
            [
                PriceCandle(
                    timestamp=datetime.fromisoformat(row[0].replace("Z", "+00:00")),
                    open=row[1],
                    high=row[2],
                    low=row[3],
                    close=row[4],
                    volume=row[5],
                    ticker=key,
                )
                for row in candles
            ],
            key=lambda x: x.timestamp,
        )
    except Exception:
        return []

# --- 4. FUNDAMENTALS ---
def fetch_funds(name):
    try:
        r = requests.get("https://stock.indianapi.in/stock", params={'name': name.replace("&","%26")}, headers={'x-api-key': INDIANAPI_KEY}).json()
        get_v = lambda c,k: next((float(str(i['value']).replace('%','').replace(',','')) for i in r.get('keyMetrics',{}).get(c,[]) if i.get('key')==k), None)
        get_h = lambda l: next((float(str(g['categories'][-1]['percentage']).replace('%','')) for g in r.get('shareholding',[]) if l.lower() in g.get('displayName','').lower()), None)
        return FundamentalSnapshot(ticker=name, market_cap=get_v('priceandVolume','marketCap'), pe_ratio=get_v('valuation','pPerEIncludingExtraordinaryItemsTTM'), promoter_holding=get_h('Promoter'), fii_holding=get_h('Foreign'), dii_holding=get_h('Domestic'))
    except: return FundamentalSnapshot(ticker=name)

# --- 5. NEWS ---
def fetch_news(name):
    try:
        url = f"https://news.google.com/rss/search?q={name}+stock+news+india&hl=en-IN&gl=IN&ceid=IN:en"
        root = ET.fromstring(requests.get(url).content)
        return [NewsItem(title=unescape(i.find('title').text), source=i.find('source').text) for i in root.findall('./channel/item')[:3]]
    except: return []

# --- 6. GENERIC DATA FETCH (For Strategies) ---
# 🚨 THIS WAS MISSING
def fetch_data(ticker, period="1y", interval="1d"):
    """
    Robust wrapper for yfinance to fetch OHLCV data.
    Automatically handles the '.NS' suffix for Indian stocks.
    """
    try:
        # Ensure ticker has .NS suffix for Yahoo Finance
        sym = ticker if ticker.endswith(".NS") else f"{ticker}.NS"
        
        # Download data
        df = yf.download(sym, period=period, interval=interval, progress=False)
        
        if df.empty:
            print(f"      ⚠️ No data found for {sym}")
            return None
            
        # Standardize Columns (Remove MultiIndex if present)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        return df
        
    except Exception as e:
        print(f"      ❌ Data Fetch Error ({ticker}): {e}")
        return None