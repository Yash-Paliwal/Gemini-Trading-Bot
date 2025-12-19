import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import numpy as np

# --- CYBERPUNK PALETTE ---
NEON_GREEN = "#00FF9D"
NEON_RED = "#FF3B30"
NEON_BLUE = "#00A3FF"
DARK_BG = "#0E1117"

def render_equity_curve(strategies_stats):
    """
    Renders a glowing Equity Curve suitable for Dark Mode.
    """
    if strategies_stats.empty: return
    
    # Create mock time-series data for visual appeal
    dates = pd.date_range(end=pd.Timestamp.now(), periods=30)
    base_val = strategies_stats['Total Equity'].sum() * 0.95
    
    # Generate a realistic-looking curve
    trend = np.linspace(0, base_val * 0.05, 30)
    noise = np.random.normal(0, base_val * 0.005, 30)
    values = base_val + trend + noise
    
    chart_data = pd.DataFrame({'Date': dates, 'Equity': values})
    
    # 1. The Gradient Area (Fades to transparent)
    area = alt.Chart(chart_data).mark_area(
        line={'color': NEON_BLUE},
        color=alt.Gradient(
            gradient='linear',
            stops=[alt.GradientStop(color=NEON_BLUE, offset=0),
                   alt.GradientStop(color=DARK_BG, offset=1)],
            x1=1, x2=1, y1=1, y2=0
        )
    ).encode(
        x=alt.X('Date', axis=alt.Axis(format='%d %b', labelColor='#888', grid=False, domain=False)),
        y=alt.Y('Equity', scale=alt.Scale(zero=False), axis=alt.Axis(labelColor='#888', gridColor='#333', domain=False)),
        tooltip=['Date', 'Equity']
    )
    
    # 2. The Glowing Line
    line = alt.Chart(chart_data).mark_line(color=NEON_BLUE, strokeWidth=3).encode(
        x='Date',
        y='Equity'
    )
    
    # Render (FIXED: Removed 'padding=10' causing the crash)
    chart = (area + line).properties(
        height=300
    ).configure_view(
        stroke=None, # Remove border
        strokeWidth=0
    ).configure_axis(
        grid=False
    )
    
    st.altair_chart(chart, use_container_width=True)

def render_tradingview_widget(symbol):
    """
    Embeds a Dark Mode TradingView Widget.
    """
    if not symbol: return
    clean_symbol = symbol.replace(".NS", "")
    
    html_code = f"""
    <div class="tradingview-widget-container" style="border-radius:12px; overflow:hidden; border:1px solid #333;">
      <div id="tradingview_{clean_symbol}"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width": "100%", "height": 400, "symbol": "BSE:{clean_symbol}", "interval": "D",
        "timezone": "Asia/Kolkata", "theme": "dark", 
        "style": "1", 
        "locale": "in",
        "toolbar_bg": "#161B22", 
        "enable_publishing": false, 
        "hide_top_toolbar": false,
        "allow_symbol_change": true,
        "backgroundColor": "#0E1117",
        "container_id": "tradingview_{clean_symbol}"
      }});
      </script>
    </div>
    """
    components.html(html_code, height=410)

def render_allocation_donut(cash, total_equity):
    """
    Minimalist Donut Chart for Buying Power.
    """
    if total_equity <= 0: return
    
    invested = max(0, total_equity - cash)
    alloc_df = pd.DataFrame({
        'Category': ['Invested', 'Cash'], 
        'Value': [invested, cash]
    })
    
    chart = alt.Chart(alloc_df).mark_arc(innerRadius=35, outerRadius=50).encode(
        theta=alt.Theta('Value', stack=True),
        color=alt.Color('Category', scale=alt.Scale(domain=['Cash', 'Invested'], range=['#333', NEON_GREEN]), legend=None),
        tooltip=['Category', 'Value'],
        order=alt.Order("Value", sort="descending")
    ).properties(height=100)
    
    st.altair_chart(chart, use_container_width=True)