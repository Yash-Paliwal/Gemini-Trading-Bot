import os
import time
import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
import altair as alt
from sqlalchemy import create_engine, text
import socket

# --- 1. CRITICAL SETUP: LOAD SECRETS BEFORE IMPORTS ---
st.set_page_config(page_title="Gemini Hedge Fund", layout="wide", page_icon="📈")

# Load Secrets into Environment
try:
    if "DATABASE_URL" in st.secrets:
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
    if "UPSTOX_API_KEY" in st.secrets:
        os.environ["UPSTOX_API_KEY"] = st.secrets["UPSTOX_API_KEY"]
    if "UPSTOX_API_SECRET" in st.secrets:
        os.environ["UPSTOX_API_SECRET"] = st.secrets["UPSTOX_API_SECRET"]
    if "REDIRECT_URI" in st.secrets:
        os.environ["REDIRECT_URI"] = st.secrets["REDIRECT_URI"]
except FileNotFoundError:
    pass

# --- 2. NOW IMPORT MODULES ---
from src.upstox_client import upstox_client
from src.tools import get_live_price, fetch_upstox_map
from src.dashboard_modules.auth import get_login_url, exchange_code_for_token
from src.dashboard_modules.data import get_db_engine, fetch_dashboard_data, save_token_to_db

# Custom CSS
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: bold; }
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    .positive { color: #4CAF50; font-weight: bold; }
    .negative { color: #FF5252; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Check Config
if not os.getenv("DATABASE_URL"):
    st.error("❌ Database URL missing! Check your .env or Secrets.")
    st.stop()

engine = get_db_engine(os.getenv("DATABASE_URL"))

# --- 3. HELPER: CHARTS ---
def render_tradingview_chart(symbol):
    clean_symbol = symbol.replace(".NS", "")
    tv_symbol = f"BSE:{clean_symbol}"
    html_code = f"""
    <div class="tradingview-widget-container">
      <div id="tradingview_{clean_symbol}"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width": "100%", "height": 400, "symbol": "{tv_symbol}", "interval": "D",
        "timezone": "Asia/Kolkata", "theme": "light", "style": "1", "locale": "in",
        "toolbar_bg": "#f1f3f6", "enable_publishing": false, "allow_symbol_change": true,
        "container_id": "tradingview_{clean_symbol}"
      }});
      </script>
    </div>
    """
    components.html(html_code, height=400)

# --- 4. SIDEBAR: LOGIN ---
with st.sidebar:
    st.header("🔐 Daily Login")
    
    # Check Live Status
    is_live = upstox_client.fetch_token_from_db()
    if is_live:
        st.success("🟢 Live Data: Connected")
    else:
        st.error("🔴 Live Data: Disconnected")

    # Smart Redirect Logic
    configured_uri = os.getenv("REDIRECT_URI", "")
    if "localhost" in socket.gethostname() or "127.0.0.1" in socket.gethostbyname(socket.gethostname()):
        final_redirect_uri = "http://localhost:8501"
    else:
        final_redirect_uri = configured_uri or "https://gemini-trading-bot-yash.streamlit.app"
    
    st.caption(f"Redirect: `{final_redirect_uri}`")
    
    api_key = os.getenv("UPSTOX_API_KEY")
    api_secret = os.getenv("UPSTOX_API_SECRET")
    
    if api_key and api_secret:
        st.link_button("Login to Upstox 🚀", get_login_url(api_key, final_redirect_uri), type="primary")
        
        if auth_code := st.query_params.get("code"):
            if st.button("Generate Token 🔑"):
                with st.spinner("Authorizing..."):
                    # 🚨 FIX: Call with 4 args, then save token manually
                    success, msg_or_token = exchange_code_for_token(auth_code, api_key, api_secret, final_redirect_uri)
                    
                    if success:
                        # Success = msg_or_token is the actual token string
                        save_token_to_db(engine, msg_or_token)
                        st.success("✅ System Armed.")
                        time.sleep(1)
                        st.query_params.clear()
                        st.rerun()
                    else:
                        # Failure = msg_or_token is the error message
                        st.error(f"❌ {msg_or_token}")
    
    st.divider()
    if st.button('🔄 Refresh Dashboard'): st.rerun()
    st.caption(f"Last Update: {time.strftime('%H:%M:%S')}")

# --- 5. MAIN LOGIC ---
st.title("🤖 Gemini AI Hedge Fund")

try: trades, portfolio = fetch_dashboard_data(engine)
except Exception as e: st.error(f"DB Error: {e}"); st.stop()

# Sum all strategy balances to get Total Fund Cash
cash = portfolio['balance'].sum() if not portfolio.empty else 0.0
open_trades = trades[trades['status'] == 'OPEN'].copy()

# Initialize Defaults
total_invested = 0
total_unrealized_pnl = 0
current_holdings_value = 0

if not open_trades.empty:
    open_trades['Live Price'] = open_trades['entry_price']
    open_trades['PnL'] = 0.0
    open_trades['PnL %'] = 0.0
    
    # Re-Check Token for Main Logic
    is_live = upstox_client.fetch_token_from_db()
    
    if is_live:
        master_map = fetch_upstox_map()
        live_prices, pnls, vals = [], [], []
        
        for _, row in open_trades.iterrows():
            curr = row['entry_price']
            key = master_map.get(row['ticker'])
            if key:
                lp = get_live_price(key, row['ticker'])
                if lp: curr = lp
            
            val = curr * row['quantity']
            pnl = val - (row['entry_price'] * row['quantity'])
            
            live_prices.append(curr)
            vals.append(val)
            pnls.append(pnl)
        
        open_trades['Live Price'] = live_prices
        open_trades['Current Value'] = vals
        open_trades['PnL'] = pnls
        open_trades['PnL %'] = ((open_trades['Live Price'] - open_trades['entry_price']) / open_trades['entry_price']) * 100
        
        total_invested = (open_trades['entry_price'] * open_trades['quantity']).sum()
        current_holdings_value = sum(vals)
        total_unrealized_pnl = sum(pnls)
    else:
        st.warning("⚠️ Showing cached data. Please Login in Sidebar to see Live P&L.")
        total_invested = (open_trades['entry_price'] * open_trades['quantity']).sum()
        current_holdings_value = total_invested

# Metrics
net_worth = cash + current_holdings_value
closed = trades[trades['status'].str.contains('CLOSED|HIT', na=False)]
realized_pnl = closed['pnl'].sum() if not closed.empty else 0
total_pnl = realized_pnl + total_unrealized_pnl

# Display Top Row
m1, m2, m3, m4 = st.columns(4)
m1.metric("🏛️ Net Worth", f"₹{net_worth:,.0f}", delta=f"{total_unrealized_pnl:+.0f} (Open)")
m2.metric("💵 Liquid Cash", f"₹{cash:,.0f}")
m3.metric("🛡️ Invested", f"₹{current_holdings_value:,.0f}")
m4.metric("💰 Total Lifetime Profit", f"₹{total_pnl:,.0f}", delta=f"Realized: {realized_pnl:.0f}")

# Tabs
t1, t2, t3 = st.tabs(["⚡ Active Trades", "📊 Analytics", "📜 Ledger"])

with t1:
    st.subheader("🟢 Live Positions")
    if not open_trades.empty:
        def color_pnl(val):
            color = '#d4edda' if val > 0 else '#f8d7da' if val < 0 else ''
            text_color = 'green' if val > 0 else 'red' if val < 0 else 'black'
            return f'background-color: {color}; color: {text_color}'

        styled_df = open_trades[['ticker', 'quantity', 'entry_price', 'Live Price', 'target_price', 'stop_loss', 'PnL', 'PnL %']].style\
            .format({'entry_price': '₹{:.2f}', 'Live Price': '₹{:.2f}', 'target_price': '₹{:.2f}', 'stop_loss': '₹{:.2f}', 'PnL': '₹{:.2f}', 'PnL %': '{:.2f}%'})\
            .map(color_pnl, subset=['PnL', 'PnL %'])

        st.dataframe(styled_df, use_container_width=True)
        
        st.divider()
        st.caption("Click tabs below to view charts")
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

with t2:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Performance Curve")
        if not closed.empty:
            chart = closed.sort_values('exit_time').copy()
            chart['cum_pnl'] = chart['pnl'].cumsum()
            st.line_chart(chart, x='exit_time', y='cum_pnl')
        else: st.caption("No closed trades yet.")
    with c2:
        st.subheader("Asset Allocation")
        if net_worth > 0:
            df = pd.DataFrame({'Asset': ['Cash', 'Stocks'], 'Value': [cash, max(current_holdings_value, 0)]})
            st.altair_chart(alt.Chart(df).mark_arc(innerRadius=50).encode(theta="Value", color="Asset"), use_container_width=True)

with t3:
    st.subheader("📜 Trade History")
    st.dataframe(trades, use_container_width=True)