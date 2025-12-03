import os
import time
import requests
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
import socket
import altair as alt

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Gemini Hedge Fund", layout="wide", page_icon="📈")

# Load Secrets (Hybrid Method)
try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
    API_KEY = st.secrets.get("UPSTOX_API_KEY", "")
    API_SECRET = st.secrets.get("UPSTOX_API_SECRET", "")
except FileNotFoundError:
    from src.config import DATABASE_URL # Import from local config if secrets missing
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
    st.header("🔐 Fund Access")
    
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

# --- 4. MAIN DASHBOARD ---
st.title("🤖 Gemini AI Hedge Fund")
st.caption("Automated Swing Trading System • Multi-Strategy • Risk Managed")

try:
    trades, portfolio = get_data()
except:
    st.warning("Waiting for Database connection...")
    st.stop()

# METRICS
cash = float(portfolio.iloc[0]['balance']) if not portfolio.empty else 0.0
open_trades = trades[trades['status'] == 'OPEN'].copy()
invested = (open_trades['entry_price'] * open_trades['quantity']).sum() if not open_trades.empty else 0
net_worth = cash + invested

closed = trades[trades['status'].str.contains('CLOSED|HIT', na=False)]
realized_pnl = closed['pnl'].sum() if not closed.empty else 0
win_rate = (len(closed[closed['pnl'] > 0]) / len(closed) * 100) if not closed.empty else 0

# TOP METRICS ROW
m1, m2, m3, m4 = st.columns(4)
m1.metric("🏛️ AUM (Net Worth)", f"₹{net_worth:,.0f}", delta=f"₹{realized_pnl:,.0f}")
m2.metric("💵 Cash", f"₹{cash:,.0f}")
m3.metric("🛡️ Invested", f"₹{invested:,.0f}")
m4.metric("🎯 Win Rate", f"{win_rate:.0f}%", f"{len(closed)} Trades")

st.divider()

# ACTIVE POSITIONS
col_table, col_chart = st.columns([2, 1])

with col_table:
    st.subheader("🟢 Active Positions")
    if not open_trades.empty:
        view = open_trades[['ticker', 'entry_price', 'target_price', 'stop_loss', 'quantity', 'reasoning']]
        st.dataframe(view, use_container_width=True, hide_index=True)
    else:
        st.info("No active trades. Scanning market...")

with col_chart:
    st.subheader("📊 Capital Allocation")
    if invested > 0:
        # Simple Pie Chart of Allocation
        alloc_data = pd.DataFrame({
            'Asset': ['Cash', 'Stocks'],
            'Value': [cash, invested]
        })
        c = alt.Chart(alloc_data).mark_arc(innerRadius=50).encode(
            theta=alt.Theta("Value", stack=True),
            color=alt.Color("Asset"),
            tooltip=["Asset", "Value"]
        )
        st.altair_chart(c, use_container_width=True)
    else:
        st.caption("100% Cash")

# PERFORMANCE HISTORY
st.subheader("📜 Trade History")
if not trades.empty:
    st.dataframe(trades, use_container_width=True)