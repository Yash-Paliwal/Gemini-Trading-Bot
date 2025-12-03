import os
import time
import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import altair as alt
from sqlalchemy import create_engine, text
import socket
import hmac

# --- IMPORTS ---
from src.upstox_client import upstox_client
from src.tools import get_live_price, fetch_upstox_map

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Gemini Hedge Fund", layout="wide", page_icon="📈")

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: bold; }
    .stDataFrame { border-radius: 10px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# --- 🔒 AUTHENTICATION SYSTEM ---
def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if hmac.compare_digest(st.session_state["password"], st.secrets["APP_PASSWORD"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store the password
        else:
            st.session_state["password_correct"] = False

    # 1. Check if password already verified
    if st.session_state.get("password_correct", False):
        return True

    # 2. Show Input Box
    st.title("🔐 Gemini Hedge Fund")
    st.text_input(
        "Enter Access PIN", type="password", on_change=password_entered, key="password"
    )
    
    # 3. Handle Errors
    if "password_correct" in st.session_state:
        st.error("❌ Access Denied")
    
    return False

# 🛑 STOP EVERYTHING IF PASSWORD FAILS
if not check_password():
    st.stop()

# Load Secrets
try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
    API_KEY = st.secrets.get("UPSTOX_API_KEY", "")
    API_SECRET = st.secrets.get("UPSTOX_API_SECRET", "")
    REDIRECT_URI = st.secrets.get("REDIRECT_URI", "")
except FileNotFoundError:
    DATABASE_URL = os.getenv("DATABASE_URL")
    API_KEY = os.getenv("UPSTOX_API_KEY")
    API_SECRET = os.getenv("UPSTOX_API_SECRET")
    REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8501")

if not DATABASE_URL:
    st.error("❌ Database URL missing!")
    st.stop()

# --- 2. DATABASE ---
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
        conn.execute(text("CREATE TABLE IF NOT EXISTS api_tokens (provider TEXT PRIMARY KEY, access_token TEXT, updated_at TIMESTAMP DEFAULT NOW())"))
        conn.execute(text("INSERT INTO api_tokens (provider, access_token, updated_at) VALUES ('UPSTOX', :t, NOW()) ON CONFLICT (provider) DO UPDATE SET access_token = EXCLUDED.access_token, updated_at = NOW()"), {"t": token})
        conn.commit()

# --- HELPER: TRADINGVIEW WIDGET (FIXED) ---
def render_tradingview_chart(symbol):
    # 1. Remove .NS extension
    clean_symbol = symbol.replace(".NS", "")
    
    # 2. 🚨 FIX: Use 'BSE' instead of 'NSE' to bypass embedding restriction
    # Most Indian stocks are listed on both. BSE charts work on embedded sites.
    tv_symbol = f"BSE:{clean_symbol}"
    
    html_code = f"""
    <div class="tradingview-widget-container">
      <div id="tradingview_{clean_symbol}"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "width": "100%",
        "height": 500,
        "symbol": "{tv_symbol}", 
        "interval": "D",
        "timezone": "Asia/Kolkata",
        "theme": "light",
        "style": "1",
        "locale": "in",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "allow_symbol_change": true,
        "container_id": "tradingview_{clean_symbol}"
      }}
      );
      </script>
    </div>
    """
    components.html(html_code, height=500)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🔐 Daily Login")
    
    # Determine Redirect URI
    if "localhost" in socket.gethostname() or "127.0.0.1" in socket.gethostbyname(socket.gethostname()):
        final_redirect_uri = "http://localhost:8501"
    else:
        final_redirect_uri = "https://gemini-trading-bot-yash.streamlit.app"
    
    if API_KEY and API_SECRET:
        auth_url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={API_KEY}&redirect_uri={final_redirect_uri}"
        st.link_button("1. Login to Upstox 🚀", auth_url, type="primary")
        
        auth_code = st.query_params.get("code")
        if auth_code:
            if st.button("2. Generate Token 🔑"):
                with st.spinner("Authenticating..."):
                    try:
                        url = 'https://api.upstox.com/v2/login/authorization/token'
                        headers = {'accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
                        data = {'code': auth_code, 'client_id': API_KEY, 'client_secret': API_SECRET, 'redirect_uri': final_redirect_uri, 'grant_type': 'authorization_code'}
                        resp = requests.post(url, headers=headers, data=data)
                        if resp.status_code == 200:
                            update_token_in_db(resp.json()['access_token'])
                            st.success("✅ System Armed.")
                            time.sleep(1); st.query_params.clear(); st.rerun()
                        else: st.error(f"Failed: {resp.text}")
                    except Exception as e: st.error(f"Error: {e}")
    st.divider()
    if st.button('🔄 Refresh Data'): st.rerun()

# --- 4. DASHBOARD LOGIC ---
st.title("🤖 Gemini AI Hedge Fund")

try: trades, portfolio = get_data()
except Exception as e: st.error(f"DB Error: {e}"); st.stop()

# -- METRICS PREP --
cash = float(portfolio.iloc[0]['balance']) if not portfolio.empty else 0.0
open_trades = trades[trades['status'] == 'OPEN'].copy()

# 🚨 FIX: PRE-INITIALIZE COLUMNS WITH DEFAULT VALUES 🚨
# This ensures columns exist even if API calls fail later
if not open_trades.empty:
    open_trades['Live Price'] = open_trades['entry_price']
    open_trades['PnL'] = 0.0
    open_trades['PnL %'] = 0.0
    open_trades['Current Value'] = open_trades['entry_price'] * open_trades['quantity']

# -- FETCH LIVE DATA --
is_live = upstox_client.fetch_token_from_db()

if is_live and not open_trades.empty:
    master_map = fetch_upstox_map()
    
    # Lists to hold updated values
    live_prices = []
    pnls = []
    current_values = []
    
    for index, row in open_trades.iterrows():
        key = master_map.get(row['ticker'])
        
        # Get Price (or fallback to entry)
        current_price = row['entry_price']
        if key:
            lp = get_live_price(key, row['ticker'])
            if lp: current_price = lp
        
        # Calc Stats
        val = current_price * row['quantity']
        pnl = val - (row['entry_price'] * row['quantity'])
        
        live_prices.append(current_price)
        pnls.append(pnl)
        current_values.append(val)
    
    # Assign lists back to DataFrame
    open_trades['Live Price'] = live_prices
    open_trades['PnL'] = pnls
    open_trades['Current Value'] = current_values
    open_trades['PnL %'] = ((open_trades['Live Price'] - open_trades['entry_price']) / open_trades['entry_price']) * 100

elif not is_live:
    st.warning("⚠️ Upstox Token Expired. Showing static data.")

# -- FINAL METRICS --
if not open_trades.empty:
    invested = open_trades['Current Value'].sum()
    total_unrealized_pnl = open_trades['PnL'].sum()
else:
    invested = 0
    total_unrealized_pnl = 0

closed = trades[trades['status'].str.contains('CLOSED|HIT', na=False)]
realized_pnl = closed['pnl'].sum() if not closed.empty else 0
total_pnl = realized_pnl + total_unrealized_pnl
closed_count = len(closed)
win_count = len(closed[closed['pnl'] > 0])
win_rate = (win_count / closed_count * 100) if closed_count > 0 else 0
net_worth = cash + invested

# DISPLAY
m1, m2, m3, m4 = st.columns(4)
m1.metric("🏛️ Net Worth", f"₹{net_worth:,.0f}", delta=f"{total_unrealized_pnl:+.0f} (Open)")
m2.metric("💵 Liquid Cash", f"₹{cash:,.0f}")
m3.metric("🛡️ Invested", f"₹{invested:,.0f}")
m4.metric("💰 Total P&L", f"₹{total_pnl:,.0f}", delta=f"Realized: {realized_pnl:.0f}")

# TABS
tab1, tab2, tab3 = st.tabs(["📊 Overview", "⚡ Active Trades", "📜 History"])

with tab1:
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Equity Curve")
        if not closed.empty:
            chart_data = closed.sort_values('exit_time').copy()
            chart_data['cumulative_pnl'] = chart_data['pnl'].cumsum()
            st.line_chart(chart_data, x='exit_time', y='cumulative_pnl', color="#00FF00")
        else: st.info("No closed trades yet.")
    with c2:
        st.subheader("Allocation")
        if net_worth > 0:
            alloc = pd.DataFrame({'Asset': ['Cash', 'Stocks'], 'Value': [cash, max(invested, 0)]})
            st.altair_chart(alt.Chart(alloc).mark_arc(innerRadius=50).encode(theta="Value", color="Asset", tooltip=["Asset", "Value"]), use_container_width=True)

with tab2:
    st.subheader("🟢 Live Positions")
    if not open_trades.empty:
        # Now this safe because columns are pre-initialized
        view = open_trades[['ticker', 'quantity', 'entry_price', 'Live Price', 'target_price', 'stop_loss', 'PnL', 'PnL %']].copy()
        st.dataframe(view.style.format({'entry_price': '₹{:.2f}', 'Live Price': '₹{:.2f}', 'target_price': '₹{:.2f}', 'stop_loss': '₹{:.2f}', 'PnL': '₹{:.2f}', 'PnL %': '{:.2f}%'}), use_container_width=True)
        
        st.divider()
        st.markdown("### 🕯️ Live Charts")
        tabs = st.tabs(open_trades['ticker'].tolist())
        for i, tab in enumerate(tabs):
            with tab:
                row = open_trades.iloc[i]
                c1, c2 = st.columns([3, 1])
                with c1: render_tradingview_chart(row['ticker'])
                with c2: 
                    st.info(f"**AI Logic:**\n\n{row['reasoning']}")
                    st.metric("Target", f"₹{row['target_price']}")
                    st.metric("Stop", f"₹{row['stop_loss']}")
    else: st.info("No active trades.")

with tab3:
    st.subheader("📜 Ledger")
    st.dataframe(trades, use_container_width=True)