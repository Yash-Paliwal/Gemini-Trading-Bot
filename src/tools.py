import requests, gzip, io, json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import unescape
from .config import UPSTOX_ACCESS_TOKEN, INDIANAPI_KEY
from .models import PriceCandle, FundamentalSnapshot, NewsItem

def fetch_upstox_map():
    print("📥 Loading Map...")
    try:
        r = requests.get("https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz")
        with gzip.GzipFile(fileobj=io.BytesIO(r.content)) as f: data = json.load(f)
        m = {i['trading_symbol']: i['instrument_key'] for i in data if i.get('segment') == 'NSE_EQ'}
        # Alias Fixes
        aliases = {"TATAMOTORS": "TMPV", "M&M": "M&M", "BAJAJ-AUTO": "BAJAJ-AUTO", "LTIM": "LTIM"}
        for y, u in aliases.items(): 
            if u in m: m[y] = m[u]
        return m
    except: return {}

def get_live_price(key, symbol_fallback=None):
    url = "https://api.upstox.com/v3/market-quote/ltp"
    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {UPSTOX_ACCESS_TOKEN}'}
    def try_key(k):
        try:
            res = requests.get(url, params={"instrument_key": k}, headers=headers)
            d = res.json()
            if 'data' in d and d['data']: return float(d['data'][next(iter(d['data']))]['last_price'])
        except: return None
    p = try_key(key)
    if p: return p
    if symbol_fallback: return try_key(f"NSE_EQ|{symbol_fallback.replace('.NS','').upper()}")
    return None

def fetch_candles(key, days, interval="days"):
    start = datetime.now().date() - timedelta(days=days)
    url = f"https://api.upstox.com/v3/historical-candle/{key}/{interval}/1/{datetime.now().date()}/{start}"
    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {UPSTOX_ACCESS_TOKEN}'}
    try:
        res = requests.get(url, headers=headers).json()
        c = res.get('data', {}).get('candles', [])
        return sorted([PriceCandle(timestamp=datetime.fromisoformat(i[0].replace('Z','+00:00')), open=i[1], high=i[2], low=i[3], close=i[4], volume=i[5], ticker=key) for i in c], key=lambda x: x.timestamp) if c else []
    except: return []

def fetch_funds(name):
    try:
        r = requests.get("https://stock.indianapi.in/stock", params={'name': name.replace("&","%26")}, headers={'x-api-key': INDIANAPI_KEY}).json()
        get_v = lambda c,k: next((float(str(i['value']).replace('%','').replace(',','')) for i in r.get('keyMetrics',{}).get(c,[]) if i.get('key')==k), None)
        get_h = lambda l: next((float(str(g['categories'][-1]['percentage']).replace('%','')) for g in r.get('shareholding',[]) if l.lower() in g.get('displayName','').lower()), None)
        return FundamentalSnapshot(ticker=name, market_cap=get_v('priceandVolume','marketCap'), pe_ratio=get_v('valuation','pPerEIncludingExtraordinaryItemsTTM'), promoter_holding=get_h('Promoter'), fii_holding=get_h('Foreign'), dii_holding=get_h('Domestic'))
    except: return FundamentalSnapshot(ticker=name)

def fetch_news(name):
    try:
        root = ET.fromstring(requests.get(f"https://news.google.com/rss/search?q={name}+stock+news+india&hl=en-IN&gl=IN&ceid=IN:en").content)
        return [NewsItem(title=unescape(i.find('title').text), source=i.find('source').text) for i in root.findall('./channel/item')[:3]]
    except: return []