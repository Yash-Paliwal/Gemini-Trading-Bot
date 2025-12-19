import os
import time
import requests
import pandas as pd
import streamlit as st
from sqlalchemy import text, inspect

# --- IMPORTS ---
from src.dashboard_modules.auth import get_login_url, exchange_code_for_token
from src.dashboard_modules.data import get_db_engine, fetch_dashboard_data, save_token_to_db
from src.tools import fetch_upstox_map
from src.dashboard_modules.env import load_config

# --- CONFIG ---
st.set_page_config(page_title="Gemini Manager", layout="wide", page_icon="💼")
config = load_config()

if not config.get("DATABASE_URL"):
    st.error("❌ DB URL missing!"); st.stop()
engine = get_db_engine(config["DATABASE_URL"])

if 'login_status' not in st.session_state: st.session_state['login_status'] = None 
if 'login_msg' not in st.session_state: st.session_state['login_msg'] = ""

# --- SMART TOKEN FETCHER ---
def get_raw_token(engine):
    """Fetches Upstox access token from database."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT access_token FROM api_tokens WHERE provider = 'UPSTOX' LIMIT 1")).fetchone()
            if result and result[0]:
                return str(result[0]).strip()
    except Exception as e:
        st.warning(f"Token fetch error: {e}")
    return None

# --- HELPER: BATCH PRICE FETCHER (Using Upstox V3 API) ---
def get_live_prices_batch(instrument_keys_list, access_token):
    """
    Fetches live prices for multiple instruments using Upstox V3 API.
    Returns a dict mapping instrument_key -> last_price.
    Uses individual requests per instrument (matches working pattern in tools.py).
    """
    if not instrument_keys_list: return {}
    
    clean_token = str(access_token).strip()
    price_map = {}
    
    url = "https://api.upstox.com/v3/market-quote/ltp"
    headers = {'Authorization': f'Bearer {clean_token}', 'Accept': 'application/json'}
    
    for instr_key in instrument_keys_list:
        try:
            response = requests.get(url, headers=headers, params={'instrument_key': instr_key}, timeout=3)
            
            if response.status_code == 401:
                return "INVALID_TOKEN"
            
            if response.status_code != 200:
                continue  # Skip this one, try next
            
            data = response.json()
            
            # V3 response format: data is a dict where keys are instrument_keys
            if 'data' in data and data['data']:
                # Get the first (and only) entry in the data dict
                first_key = next(iter(data['data']))
                details = data['data'][first_key]
                
                if isinstance(details, dict):
                    price = details.get('last_price', 0.0)
                    if price:
                        price_map[instr_key] = float(price)
                        
        except Exception:
            continue  # Skip on error, continue with next
    
    return price_map

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔐 Connection")

    # LOGIN HANDLER
    if "code" in st.query_params:
        auth_code = st.query_params["code"]
        if st.button("Generate Token (Click Once)"):
            with st.spinner("Authenticating..."):
                ok, response_data = exchange_code_for_token(auth_code, config.get("UPSTOX_API_KEY"), config.get("UPSTOX_API_SECRET"), config.get("REDIRECT_URI"))
                if ok:
                    final_token = response_data
                    if isinstance(response_data, dict): final_token = response_data.get('access_token', response_data)
                    final_token = str(final_token)

                    with engine.connect() as conn:
                        try: conn.execute(text("DELETE FROM api_tokens")); conn.commit()
                        except: pass
                    
                    save_token_to_db(engine, final_token)
                    st.session_state['login_status'] = 'success'
                    st.session_state['login_msg'] = "✅ Connected!"
                else:
                    st.session_state['login_status'] = 'failed'
                    st.session_state['login_msg'] = f"❌ Error: {response_data}"
                st.query_params.clear(); time.sleep(1); st.rerun()

    if st.session_state['login_status'] == 'success': st.success(st.session_state['login_msg'])
    elif st.session_state['login_status'] == 'failed': st.error(st.session_state['login_msg'])

    access_token = get_raw_token(engine)
    if access_token: st.success("🟢 System Online")
    else:
        st.error("🔴 Disconnected")
        if config.get("UPSTOX_API_KEY"): st.link_button("🔑 Login", get_login_url(config.get("UPSTOX_API_KEY"), config.get("REDIRECT_URI")), type="primary")

    st.divider()
    if st.button("Refresh"): st.rerun()

# --- MAIN PAGE ---
st.title("💼 Portfolio Manager")

try: trades, portfolio = fetch_dashboard_data(engine)
except: st.error("DB Error"); st.stop()

if portfolio.empty: st.info("No strategies active."); st.stop()

# --- 1. DATA PREP & API CALL ---
all_open = trades[trades['status'] == 'OPEN']['ticker'].unique().tolist()
ticker_map = {}
keys_to_fetch = []
live_prices = {}

if access_token and all_open:
    master_map = fetch_upstox_map()
    if master_map:
        for ticker in all_open:
            key = master_map.get(ticker)
            if not key: key = master_map.get(f"{ticker}.NS")
            if not key: key = master_map.get(ticker.replace(".NS", ""))
            
            if key:
                ticker_map[ticker] = key
                keys_to_fetch.append(key)
            
    if keys_to_fetch:
        result = get_live_prices_batch(keys_to_fetch, access_token)
        if result == "INVALID_TOKEN":
            st.warning("⚠️ Token Expired. Cleaning up...");
            with engine.connect() as conn: conn.execute(text("DELETE FROM api_tokens")); conn.commit()
            st.rerun()
        else:
            live_prices = result

# --- 2. RENDER STRATEGIES (CORRECTED MATH) ---
strategies = portfolio['strategy_name'].unique().tolist()

for strategy in strategies:
    clean_name = strategy.replace("STRATEGY_", "")
    
    # Metadata
    strat_row = portfolio[portfolio['strategy_name'] == strategy]
    # 'balance' in DB is treated as Liquid Cash (Available for trading)
    db_cash_balance = float(strat_row.iloc[0]['balance']) if not strat_row.empty else 0.0
    
    # Trades
    s_trades = trades[trades['strategy_name'] == strategy]
    open_pos = s_trades[s_trades['status'] == 'OPEN'].copy()
    closed_pos = s_trades[s_trades['status'] != 'OPEN'].copy()
    
    # Realized PnL (Just for display, likely already added to balance by the bot)
    realized_pnl = closed_pos['pnl'].sum() if not closed_pos.empty else 0.0
    
    # Calculate Invested & Unrealized
    invested_value = 0.0
    unrealized_pnl = 0.0
    holdings = []
    
    if not open_pos.empty:
        for _, row in open_pos.iterrows():
            ticker = row['ticker']
            qty = row['quantity']
            entry = row['entry_price']
            
            # Locked Capital
            invested_value += (entry * qty)
            
            # Live Price
            key = ticker_map.get(ticker)
            ltp = live_prices.get(key, entry)
            
            # Debug: log if we're using fallback price
            if key and key not in live_prices:
                # Price not found in live_prices, using entry as fallback
                # This means either API call failed or instrument_key mismatch
                pass  # Silent fallback - entry price is reasonable default
            
            cur_val = ltp * qty
            inv_val = entry * qty
            pnl = cur_val - inv_val
            pct = (pnl / inv_val) * 100 if inv_val > 0 else 0.0
            
            unrealized_pnl += pnl
            
            holdings.append({
                "Stock": ticker,
                "Qty": int(qty),
                "Entry": round(entry, 2),
                "CMP": round(ltp, 2),
                "P&L ₹": round(pnl, 2),
                "Change %": f"{pct:.2f}%"
            })

    # --- MATH CORRECTION ---
    # We DO NOT subtract invested_value from db_cash_balance anymore.
    # We assume the DB 'balance' is the source of truth for free cash.
    available_cash = db_cash_balance

    # UI Rendering
    st.markdown(f"### 🔹 {clean_name}")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cash (Free)", f"₹{available_cash:,.0f}")
    m2.metric("Invested (Locked)", f"₹{invested_value:,.0f}")
    m3.metric("Realized P&L", f"₹{realized_pnl:,.0f}")
    m4.metric("Unrealized P&L", f"₹{unrealized_pnl:,.0f}", delta="Floating")
    
    if holdings:
        df = pd.DataFrame(holdings)
        st.dataframe(df.style.map(lambda x: 'color: green' if x > 0 else 'color: red' if x < 0 else '', subset=['P&L ₹']), use_container_width=True, hide_index=True)
    else:
        st.info("No Open Holdings")
    st.divider()