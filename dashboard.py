import os
import time
import requests
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Gemini Hedge Fund", layout="wide", page_icon="📈")

# Load Secrets
try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
    API_KEY = st.secrets.get("UPSTOX_API_KEY", "")
    API_SECRET = st.secrets.get("UPSTOX_API_SECRET", "")
    # 🚨 NEW: Load Redirect URI from Secrets
    REDIRECT_URI = st.secrets.get("REDIRECT_URI", "http://localhost:8501") 
except FileNotFoundError:
    st.error("❌ Secrets not found! Please create .streamlit/secrets.toml")
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
    """Fetches Trades and Portfolio data."""
    with engine.connect() as conn:
        trades_df = pd.read_sql("SELECT * FROM trades ORDER BY entry_time DESC", conn)
        portfolio_df = pd.read_sql("SELECT * FROM portfolio", conn)
    return trades_df, portfolio_df

def update_token_in_db(token):
    """Saves the fresh Upstox Token to the database."""
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

# --- 3. SIDEBAR: DAILY LOGIN ---
with st.sidebar:
    st.header("🔐 Daily Login")
    
    # Debug Info (Optional - helpful to verify which URI is loaded)
    # st.caption(f"Redirecting to: {REDIRECT_URI}")
    
    if API_KEY and API_SECRET:
        # 1. Login Button
        auth_url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={API_KEY}&redirect_uri={REDIRECT_URI}"
        st.link_button("1. Login to Upstox 🚀", auth_url, type="primary")
        
        # 2. Handle Redirect Code
        auth_code = st.query_params.get("code")
        
        if auth_code:
            st.success("Code Received!")
            if st.button("2. Generate Token 🔑"):
                with st.spinner("Exchanging code..."):
                    try:
                        url = 'https://api.upstox.com/v2/login/authorization/token'
                        headers = {'accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
                        data = {
                            'code': auth_code,
                            'client_id': API_KEY,
                            'client_secret': API_SECRET,
                            'redirect_uri': REDIRECT_URI,
                            'grant_type': 'authorization_code',
                        }
                        resp = requests.post(url, headers=headers, data=data)
                        if resp.status_code == 200:
                            new_token = resp.json()['access_token']
                            update_token_in_db(new_token)
                            st.success("✅ Token Saved! Bot is armed.")
                            time.sleep(2)
                            st.query_params.clear()
                            st.rerun()
                        else:
                            st.error(f"Login Failed: {resp.text}")
                            st.caption(f"Check Upstox App Settings. URI must match: {REDIRECT_URI}")
                    except Exception as e:
                        st.error(f"Error: {e}")
    else:
        st.warning("⚠️ API Credentials missing in Secrets.")

    st.divider()
    if st.button('🔄 Refresh Data'):
        st.rerun()

# --- 4. DASHBOARD UI ---
st.title("🤖 Gemini AI Hedge Fund")

try:
    trades, portfolio = get_data()
except Exception as e:
    st.error(f"Database Connection Error: {e}")
    st.stop()

# Metrics
if not portfolio.empty:
    cash_balance = float(portfolio.iloc[0]['balance'])
else:
    cash_balance = 0.0

open_trades = trades[trades['status'] == 'OPEN'].copy()
invested_capital = 0
if not open_trades.empty:
    invested_capital = (open_trades['entry_price'] * open_trades['quantity']).sum()

active_positions = len(open_trades)
closed_trades = trades[trades['status'].str.contains('CLOSED', na=False) | trades['status'].str.contains('HIT', na=False)]
total_closed = len(closed_trades)
winning_trades = len(closed_trades[closed_trades['pnl'] > 0])
win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0
total_realized_pnl = closed_trades['pnl'].sum() if not closed_trades.empty else 0
net_worth = cash_balance + invested_capital

# Display Metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("🏛️ Net Worth", f"₹{net_worth:,.0f}", delta=f"₹{total_realized_pnl:,.0f}")
col2.metric("💵 Cash Available", f"₹{cash_balance:,.0f}")
col3.metric("📈 Win Rate", f"{win_rate:.1f}%", f"{total_closed} Trades")
col4.metric("🛡️ Active Risk", f"₹{invested_capital:,.0f}", f"{active_positions} Positions")

st.divider()

# Active Positions
st.subheader("🟢 Active Positions")
if not open_trades.empty:
    display_open = open_trades[['ticker', 'entry_price', 'target_price', 'stop_loss', 'quantity', 'entry_time', 'reasoning']]
    st.dataframe(display_open, use_container_width=True)
else:
    st.info("No open positions.")

# Equity Curve
st.subheader("💰 Equity Curve")
if not closed_trades.empty:
    chart_data = closed_trades.sort_values('exit_time').copy()
    chart_data['cumulative_pnl'] = chart_data['pnl'].cumsum()
    st.line_chart(chart_data, x='exit_time', y='cumulative_pnl')
else:
    st.caption("No closed trades yet.")

# Audit Log
with st.expander("📜 View Trade Audit Log"):
    st.dataframe(trades, use_container_width=True)