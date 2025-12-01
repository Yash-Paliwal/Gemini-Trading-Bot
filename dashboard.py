import time
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
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
        trades_df = pd.read_sql("SELECT * FROM trades ORDER BY entry_time DESC", conn)
        portfolio_df = pd.read_sql("SELECT * FROM portfolio", conn)
    return trades_df, portfolio_df

# --- DASHBOARD LOGIC ---
st.title("🤖 Gemini AI Hedge Fund")
st.markdown("### Live Performance Monitor")

# Auto-Refresh button
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
    cash_balance = portfolio.iloc[0]['balance']
else:
    cash_balance = 0

# Calculate Open Risk & Unrealized PnL (Simulated)
open_trades = trades[trades['status'] == 'OPEN']
invested_capital = (open_trades['entry_price'] * open_trades['quantity']).sum()
active_positions = len(open_trades)

# Calculate Win Rate (Closed Trades)
closed_trades = trades[trades['status'].str.contains('CLOSED')]
total_closed = len(closed_trades)
winning_trades = len(closed_trades[closed_trades['pnl'] > 0])
win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0
total_realized_pnl = closed_trades['pnl'].sum() if not closed_trades.empty else 0

# Net Worth (Approximate: Cash + Cost Basis of Open Trades)
# Note: For real-time Net Worth, you'd need live prices here. 
# For now, we use Cost Basis.
net_worth = cash_balance + invested_capital

# --- 3. DISPLAY METRICS (Top Row) ---
col1, col2, col3, col4 = st.columns(4)

col1.metric("🏛️ Net Worth", f"₹{net_worth:,.0f}", delta=f"₹{total_realized_pnl:,.0f}")
col2.metric("💵 Cash Available", f"₹{cash_balance:,.0f}")
col3.metric("📈 Win Rate", f"{win_rate:.1f}%", f"{total_closed} Trades")
col4.metric("🛡️ Active Risk", f"₹{invested_capital:,.0f}", f"{active_positions} Positions")

# --- 4. CHARTS & TABLES ---

# A. Active Positions (The Watchlist)
st.subheader("🟢 Active Positions")
if not open_trades.empty:
    # Clean up columns for display
    display_open = open_trades[['ticker', 'entry_price', 'target_price', 'stop_loss', 'quantity', 'entry_time', 'reasoning']]
    st.dataframe(display_open, use_container_width=True)
else:
    st.info("No open positions. Scanning market...")

# B. Performance Chart (Cumulative PnL)
st.subheader("💰 Equity Curve")
if not closed_trades.empty:
    # Sort by Exit Time for the chart
    chart_data = closed_trades.sort_values('exit_time')
    chart_data['cumulative_pnl'] = chart_data['pnl'].cumsum()
    st.line_chart(chart_data, x='exit_time', y='cumulative_pnl')
else:
    st.text("Waiting for first closed trade to plot chart...")

# C. Trade History (The Ledger)
with st.expander("📜 View Trade History (Audit Log)"):
    st.dataframe(trades, use_container_width=True)

# D. AI Reasoning Audit
st.subheader("🧠 AI Brain Logic (Latest Trade)")
if not trades.empty:
    latest = trades.iloc[0]
    st.markdown(f"**Ticker:** {latest['ticker']} | **Signal:** {latest['signal']}")
    st.info(latest['reasoning'])