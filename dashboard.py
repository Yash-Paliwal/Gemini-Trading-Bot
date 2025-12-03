import os
import time
import requests
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
import socket

# --- NEW IMPORTS FOR LIVE DATA ---
from src.upstox_client import upstox_client
from src.tools import get_live_price, fetch_upstox_map

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Gemini Hedge Fund", layout="wide", page_icon="📈")

# Load Secrets
try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
    API_KEY = st.secrets.get("UPSTOX_API_KEY", "")
    API_SECRET = st.secrets.get("UPSTOX_API_SECRET", "")
except FileNotFoundError:
    # Fallback for local dev without secrets.toml
    DATABASE_URL = os.getenv("DATABASE_URL")
    API_KEY = os.getenv("UPSTOX_API_KEY")
    API_SECRET = os.getenv("UPSTOX_API_SECRET")

if not DATABASE_URL:
    st.error("❌ Database URL missing!")
    st.stop()

# --- 2. DATABASE CONNECTION ---
@st.cache_resource
def get_engine():
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True)

engine = get_engine()

def get_data():
    with engine.connect() as conn:
        trades_df = pd.read_sql("SELECT * FROM trades ORDER BY entry_time DESC", conn)
        portfolio_df = pd.read_sql("SELECT * FROM portfolio", conn)
    return trades_df, portfolio_df

def update_token_in_db(token):
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS api_tokens (
                provider TEXT PRIMARY KEY,
                access_token TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            INSERT INTO api_tokens (provider, access_token, updated_at)
            VALUES ('UPSTOX', :t, NOW())
            ON CONFLICT (provider) DO UPDATE 
            SET access_token = EXCLUDED.access_token, updated_at = NOW()
        """), {"t": token})
        conn.commit()

# --- 3. SIDEBAR: LOGIN ---
with st.sidebar:
    st.header("🔐 Daily Login")
    
    # Smart Redirect
    if "localhost" in socket.gethostname() or "127.0.0.1" in socket.gethostbyname(socket.gethostname()):
        redirect_uri = "http://localhost:8501"
    else:
        redirect_uri = "https://gemini-trading-bot-yash.streamlit.app"
        
    if API_KEY and API_SECRET:
        auth_url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={API_KEY}&redirect_uri={redirect_uri}"
        st.link_button("1. Login to Upstox 🚀", auth_url, type="primary")
        
        auth_code = st.query_params.get("code")
        if auth_code:
            if st.button("2. Generate Token 🔑"):
                with st.spinner("Authenticating..."):
                    try:
                        url = 'https://api.upstox.com/v2/login/authorization/token'
                        headers = {'accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
                        data = {'code': auth_code, 'client_id': API_KEY, 'client_secret': API_SECRET, 'redirect_uri': redirect_uri, 'grant_type': 'authorization_code'}
                        resp = requests.post(url, headers=headers, data=data)
                        if resp.status_code == 200:
                            update_token_in_db(resp.json()['access_token'])
                            st.success("✅ System Armed.")
                            time.sleep(1)
                            st.query_params.clear()
                            st.rerun()
                        else: st.error(f"Failed: {resp.text}")
                    except Exception as e: st.error(f"Error: {e}")

    st.divider()
    if st.button('🔄 Refresh Data'): st.rerun()

# --- 4. DASHBOARD LOGIC ---
st.title("🤖 Gemini AI Hedge Fund")
st.caption("Live P&L Monitor")

# A. Connect to DB
try:
    trades, portfolio = get_data()
except:
    st.warning("Waiting for Database connection...")
    st.stop()

# B. Authenticate Upstox (For Live Prices)
is_live = False
if upstox_client.fetch_token_from_db():
    is_live = True
else:
    st.warning("⚠️ Upstox Token Expired. Prices may be stale. Please Login in Sidebar.")

# C. Calculate Real-Time Metrics
cash = float(portfolio.iloc[0]['balance']) if not portfolio.empty else 0.0
open_trades = trades[trades['status'] == 'OPEN'].copy()

total_invested_cost = 0
current_holdings_value = 0
total_unrealized_pnl = 0

if not open_trades.empty:
    # Load Map for Live Prices
    master_map = fetch_upstox_map() if is_live else {}
    
    # Create columns for live data
    live_prices = []
    current_values = []
    pnls = []
    
    for index, row in open_trades.iterrows():
        entry = row['entry_price']
        qty = row['quantity']
        ticker = row['ticker']
        
        # Fetch Live Price
        current_price = entry # Default to entry if offline
        if is_live:
            key = master_map.get(ticker)
            if key:
                lp = get_live_price(key, ticker)
                if lp: current_price = lp
        
        # Math
        val = current_price * qty
        pnl = val - (entry * qty)
        
        live_prices.append(current_price)
        current_values.append(val)
        pnls.append(pnl)
        
    # Add to DataFrame
    open_trades['Live Price'] = live_prices
    open_trades['Current Value'] = current_values
    open_trades['P&L'] = pnls
    
    # Totals
    total_invested_cost = (open_trades['entry_price'] * open_trades['quantity']).sum()
    current_holdings_value = sum(current_values)
    total_unrealized_pnl = sum(pnls)

# D. Final Metrics
net_worth = cash + current_holdings_value
closed = trades[trades['status'].str.contains('CLOSED|HIT', na=False)]
realized_pnl = closed['pnl'].sum() if not closed.empty else 0
total_pnl = realized_pnl + total_unrealized_pnl

# --- 5. DISPLAY ---

# Top Row
m1, m2, m3, m4 = st.columns(4)
m1.metric("🏛️ Net Worth", f"₹{net_worth:,.0f}", delta=f"{total_unrealized_pnl:+.0f} (Today)")
m2.metric("💵 Liquid Cash", f"₹{cash:,.0f}")
m3.metric("🛡️ Invested", f"₹{current_holdings_value:,.0f}")
m4.metric("💰 Total Profit", f"₹{total_pnl:,.0f}", delta=f"Realized: {realized_pnl:.0f}")

st.divider()

# Active Positions Table
st.subheader("🟢 Active Positions")
if not open_trades.empty:
    # Format for display
    view = open_trades[['ticker', 'quantity', 'entry_price', 'Live Price', 'Current Value', 'P&L', 'stop_loss', 'target_price']].copy()
    
    # Add colors to P&L column logic would go here in advanced streamlit, 
    # for now standard dataframe is fine.
    st.dataframe(
        view.style.format({
            'entry_price': '₹{:.2f}',
            'Live Price': '₹{:.2f}',
            'Current Value': '₹{:.0f}',
            'P&L': '₹{:.2f}',
            'stop_loss': '₹{:.2f}',
            'target_price': '₹{:.2f}'
        }), 
        use_container_width=True
    )
else:
    st.info("No active trades.")

# Trade History
with st.expander("📜 Trade History"):
    st.dataframe(trades, use_container_width=True)