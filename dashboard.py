import os
import time
import streamlit as st
import pandas as pd
import altair as alt

# --- IMPORTS ---
from src.upstox_client import upstox_client
from src.dashboard_modules.auth import get_login_url, exchange_code_for_token
from src.dashboard_modules.data import get_db_engine, fetch_dashboard_data, save_token_to_db
from src.dashboard_modules.analytics import calculate_strategy_performance
from src.dashboard_modules.charts import render_allocation_donut, render_portfolio_growth_chart, render_tradingview_widget
from src.dashboard_modules.env import load_config

# --- CONFIG & STYLING ---
st.set_page_config(page_title="Gemini Fund", layout="wide", page_icon="🏛️")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    /* Global Text Colors for Dark Mode */
    h1, h2, h3, h4, h5, p, span, div { color: #E0E0E0; }
    
    /* Metrics Box - Dark Theme Friendly */
    [data-testid="stMetric"] {
        background-color: #1E1E1E; /* Dark Gray */
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #333;
    }
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #FFFFFF !important; }
    [data-testid="stMetricLabel"] { color: #888888 !important; }
    
    /* Custom Classes */
    .profit-pos { color: #00C805; font-weight: 700; }
    .profit-neg { color: #FF5000; font-weight: 700; }
    
    .strat-card {
        background-color: #1E1E1E;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #333;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Setup
config = load_config()
if not config.get("DATABASE_URL"): st.error("❌ DB URL missing!"); st.stop()
engine = get_db_engine(config["DATABASE_URL"])

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### ⚡ Gemini Fund Admin")
    is_live = upstox_client.fetch_token_from_db()
    
    if is_live: st.success("🟢 System Online")
    else: st.error("🔴 System Offline")

    if config.get("UPSTOX_API_KEY") and not is_live:
        st.link_button("Login to Upstox", get_login_url(config.get("UPSTOX_API_KEY"), config.get("REDIRECT_URI")), type="primary")

    if "code" in st.query_params:
        if st.button("Complete Auth"):
            ok, msg = exchange_code_for_token(st.query_params["code"], config.get("UPSTOX_API_KEY"), config.get("UPSTOX_API_SECRET"), config.get("REDIRECT_URI"))
            if ok: save_token_to_db(engine, msg); st.rerun()
            else: st.error(msg)
            
    if st.button("↻ Refresh Data"): st.rerun()

# --- MAIN LOGIC ---
st.title("🏛️ Gemini AI Hedge Fund")

# 1. Fetch & Calculate
trades, portfolio = fetch_dashboard_data(engine)
df_stats, total_equity, total_cash = calculate_strategy_performance(trades, portfolio, is_live)

# 2. Global Fund Header
total_pnl = df_stats['Realized P&L'].sum() + df_stats['Unrealized P&L'].sum() if not df_stats.empty else 0
pnl_color = "profit-pos" if total_pnl >= 0 else "profit-neg"
pnl_sign = "+" if total_pnl >= 0 else ""

c1, c2, c3 = st.columns(3)
c1.metric("🏦 Fund AUM", f"₹{total_equity:,.0f}")
c2.metric("💵 Total Cash", f"₹{total_cash:,.0f}")
c3.markdown(f"""
<div style="background-color:#1E1E1E; padding:15px; border-radius:10px; border:1px solid #333;">
    <span style="font-size:0.9rem; color:#888;">Net P&L</span><br>
    <span style="font-size:1.8rem; color:#FFF; font-weight:700;">₹{total_pnl:,.0f}</span><br>
    <span class="{pnl_color}">{pnl_sign}{(total_pnl/100000)*100:.2f}% All Time</span>
</div>
""", unsafe_allow_html=True)

st.divider()

if df_stats.empty:
    st.info("No strategy data found. Waiting for first trade.")
    st.stop()

# 3. STRATEGY TABS (Master / Detail View)
tab_names = ["🏆 Overview"] + df_stats['Strategy'].tolist()
tabs = st.tabs(tab_names)

# --- TAB 1: OVERVIEW LEADERBOARD ---
with tabs[0]:
    st.markdown("#### Strategy Performance")
    
    # 3-Column Grid for Strategies
    cols = st.columns(3)
    for i, row in df_stats.iterrows():
        col_idx = i % 3
        with cols[col_idx]:
            # Strategy Card
            with st.container():
                st.markdown(f"""
                <div class="strat-card">
                    <div style="font-size:1.1rem; font-weight:700; margin-bottom:5px;">{row['Strategy']}</div>
                    <div style="color:#888; font-size:0.85rem;">Equity: <span style="color:#FFF;">₹{row['Total Equity']:,.0f}</span></div>
                    <div style="color:#888; font-size:0.85rem;">Cash: <span style="color:#FFF;">₹{row['Cash']:,.0f}</span></div>
                </div>
                """, unsafe_allow_html=True)
                
                # Visuals below card
                c_chart, c_pnl = st.columns([1, 1])
                with c_chart: render_allocation_donut(row['Cash'], row['Total Equity'])
                with c_pnl: 
                    s_pnl = row['Realized P&L'] + row['Unrealized P&L']
                    s_col = "profit-pos" if s_pnl >= 0 else "profit-neg"
                    st.markdown(f"<div style='text-align:center; padding-top:30px;'><span class='{s_col}' style='font-size:1.4rem;'>{'+' if s_pnl>=0 else ''}₹{s_pnl:,.0f}</span><br><span style='color:#666;'>Net P&L</span></div>", unsafe_allow_html=True)
    
    st.markdown("#### 📈 Portfolio Growth")
    render_portfolio_growth_chart(df_stats)


# --- TABS 2...N: DEEP DIVE ---
for i, strat_name in enumerate(df_stats['Strategy']):
    with tabs[i + 1]:
        strat_row = df_stats[df_stats['Strategy'] == strat_name].iloc[0]
        strat_db_name = f"STRATEGY_{strat_name}"
        strat_trades = trades[trades['strategy_name'] == strat_db_name]
        strat_open = strat_trades[strat_trades['status'] == 'OPEN'].copy()

        # Header Stats
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Buying Power", f"₹{strat_row['Cash']:,.0f}")
        k2.metric("Invested", f"₹{strat_row['Invested']:,.0f}")
        k3.metric("Realized P&L", f"₹{strat_row['Realized P&L']:,.0f}")
        k4.metric("Unrealized P&L", f"₹{strat_row['Unrealized P&L']:,.0f}")
        
        st.divider()

        col_holdings, col_charts = st.columns([1.5, 2.5])
        
        with col_holdings:
            st.markdown("#### 📦 Current Holdings")
            if not strat_open.empty:
                display_df = strat_open[['ticker', 'quantity', 'entry_price']].copy()
                st.dataframe(
                    display_df,
                    column_config={
                        "ticker": "Symbol",
                        "quantity": "Qty",
                        "entry_price": st.column_config.NumberColumn("Avg Cost", format="₹%.2f"),
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No open positions. Strategy is hunting...")
                
            st.markdown("#### 📜 Recent Trades")
            history = strat_trades[strat_trades['status'] != 'OPEN'].sort_values('entry_time', ascending=False).head(10)
            if not history.empty:
                st.dataframe(history[['ticker', 'signal', 'pnl']], use_container_width=True, hide_index=True)
            else:
                st.caption("No trade history yet.")

        with col_charts:
            st.markdown("#### 📉 Market Vision")
            
            # Smart Select Logic
            chart_ticker = None
            if not strat_open.empty:
                chart_ticker = strat_open.iloc[0]['ticker']
                
            # Dropdown Override
            all_tickers = list(set(strat_open['ticker'].tolist() + history['ticker'].tolist())) if not history.empty else strat_open['ticker'].tolist()
            
            if all_tickers:
                selected_ticker = st.selectbox(f"Analyze Stock ({strat_name})", all_tickers, index=0 if chart_ticker else 0)
                render_tradingview_widget(selected_ticker)
                
                # Show AI Reasoning if available
                if not strat_open.empty and selected_ticker in strat_open['ticker'].values:
                     details = strat_open[strat_open['ticker'] == selected_ticker].iloc[0]
                     with st.expander("🤖 AI Logic Analysis", expanded=True):
                         st.write(details.get('reasoning', 'No deep analysis logged.'))
            else:
                st.info("Waiting for data to generate charts...")