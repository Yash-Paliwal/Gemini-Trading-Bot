import os
import time
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# --- 1. CLOUD SECRET BRIDGE (CRITICAL FOR DEPLOYMENT) ---
# This allows the app to read keys from Streamlit Secrets
try:
    if "DATABASE_URL" in st.secrets:
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
except FileNotFoundError:
    pass # Running locally, uses .env

# --- NOW IMPORT CONFIG ---
from src.config import DATABASE_URL

# --- CONFIGURATION ---
st.set_page_config(page_title="Gemini Hedge Fund", layout="wide")

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True)

engine = get_engine()

def get_data():
    """Fetches Trades and Portfolio data."""
    with engine.connect() as conn:
        # Fetch Trades
        trades_df = pd.read_sql("SELECT * FROM trades ORDER BY entry_time DESC", conn)
        # Fetch Portfolio Balance
        portfolio_df = pd.read_sql("SELECT * FROM portfolio", conn)
    return trades_df, portfolio_df

# --- DASHBOARD LOGIC ---
st.title("🤖 Gemini AI Hedge Fund")
st.markdown("### Live Performance Monitor")

if st.button('🔄 Refresh Data'):
    st.rerun()

# 1. FETCH DATA
try:
    trades, portfolio = get_data()
except Exception as e:
    st.error(f"Database Error: {e}")
    st.stop()

# 2. CALCULATE METRICS
if not portfolio.empty:
    cash_balance = float(portfolio.iloc[0]['balance'])
else:
    cash_balance = 0.0

# Open Trades Analysis
open_trades = trades[trades['status'] == 'OPEN'].copy()
invested_capital = 0
if not open_trades.empty:
    invested_capital = (open_trades['entry_price'] * open_trades['quantity']).sum()

active_positions = len(open_trades)

# Closed Trades Analysis
closed_trades = trades[trades['status'].str.contains('CLOSED', na=False) | trades['status'].str.contains('HIT', na=False)]
total_closed = len(closed_trades)
winning_trades = len(closed_trades[closed_trades['pnl'] > 0])
win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0
total_realized_pnl = closed_trades['pnl'].sum() if not closed_trades.empty else 0

# Approximate Net Worth (Cash + Cost of Open Positions)
# Note: For true Net Worth, we would need live prices of open positions.
net_worth = cash_balance + invested_capital

# --- 3. DISPLAY METRICS ---
col1, col2, col3, col4 = st.columns(4)

col1.metric("🏛️ Net Worth", f"₹{net_worth:,.0f}", delta=f"₹{total_realized_pnl:,.0f}")
col2.metric("💵 Cash Available", f"₹{cash_balance:,.0f}")
col3.metric("📈 Win Rate", f"{win_rate:.1f}%", f"{total_closed} Trades")
col4.metric("🛡️ Active Risk", f"₹{invested_capital:,.0f}", f"{active_positions} Positions")

# --- 4. CHARTS & TABLES ---
st.divider()

# A. Active Positions
st.subheader("🟢 Active Positions")
if not open_trades.empty:
    # Clean columns
    display_open = open_trades[['ticker', 'entry_price', 'target_price', 'stop_loss', 'quantity', 'entry_time', 'reasoning']]
    st.dataframe(display_open, use_container_width=True)
else:
    st.info("No open positions. Scanning market...")

# B. Equity Curve
st.subheader("💰 Equity Curve")
if not closed_trades.empty:
    chart_data = closed_trades.sort_values('exit_time')
    # Calculate running total of PnL
    chart_data['cumulative_pnl'] = chart_data['pnl'].cumsum()
    st.line_chart(chart_data, x='exit_time', y='cumulative_pnl')
else:
    st.text("Waiting for first closed trade to plot chart...")

# C. Detailed Ledger
with st.expander("📜 View Trade History (Audit Log)"):
    st.dataframe(trades, use_container_width=True)