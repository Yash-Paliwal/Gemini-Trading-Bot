import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# --- CONSTANTS ---
COLOR_GREEN = "#00C805" # Robinhood Green
COLOR_RED = "#FF5000"   # Robinhood Red
COLOR_GRAY = "#30363A"  # Dark Slate for placeholders

def render_portfolio_growth_chart(strategies_stats):
    """
    Renders a sleek Gradient Area Chart for Strategy Equity.
    """
    if strategies_stats.empty: return
    
    # Add a dummy 'baseline' for the area chart to look grounded
    chart_data = strategies_stats.copy()
    
    # Create the Chart Base
    base = alt.Chart(chart_data).encode(
        x=alt.X('Strategy', axis=None), # Hide X Axis Labels for clean look
        tooltip=['Strategy', 'Total Equity', 'Cash', 'Realized P&L']
    )

    # 1. The Area with Gradient
    area = base.mark_area(
        opacity=0.3, 
        line={'color': COLOR_GREEN},
        color=alt.Gradient(
            gradient='linear',
            stops=[alt.GradientStop(color=COLOR_GREEN, offset=0),
                   alt.GradientStop(color='white', offset=1)],
            x1=1, x2=1, y1=1, y2=0
        )
    ).encode(
        y=alt.Y('Total Equity', axis=None, scale=alt.Scale(zero=False)) # Dynamic scale
    )
    
    # 2. The Line on top
    line = base.mark_line(color=COLOR_GREEN, strokeWidth=3).encode(
        y=alt.Y('Total Equity', axis=None)
    )
    
    # 3. Points for interaction (FIXED: Removed faulty opacity condition)
    points = base.mark_circle(size=60, color=COLOR_GREEN).encode(
        y='Total Equity',
        opacity=alt.value(1)  # Simply make them visible
    )

    # Combine
    final_chart = (area + line + points).properties(
        height=250,
        title=alt.TitleParams("Equity Curve (Projected)", color="gray", anchor="start", fontSize=12)
    ).configure_view(
        stroke=None # Remove border
    ).configure_axis(
        grid=False,
        domain=False
    )
    
    st.altair_chart(final_chart, use_container_width=True)

def render_allocation_donut(cash, total_equity):
    """
    Minimalist 'Ring' Chart for Buying Power.
    """
    if total_equity <= 0: return
    
    invested = max(0, total_equity - cash)
    
    # Create Data for the Ring
    alloc_df = pd.DataFrame({
        'Category': ['Invested', 'Cash'], 
        'Value': [invested, cash]
    })
    
    # Donut Chart
    chart = alt.Chart(alloc_df).mark_arc(innerRadius=40, outerRadius=55).encode(
        theta=alt.Theta('Value', stack=True),
        color=alt.Color('Category', scale=alt.Scale(domain=['Cash', 'Invested'], range=[COLOR_GRAY, COLOR_GREEN]), legend=None),
        tooltip=['Category', 'Value'],
        order=alt.Order("Value", sort="descending")
    ).properties(height=120)
    
    st.altair_chart(chart, use_container_width=True)

def render_tradingview_widget(symbol):
    """
    Embeds a TradingView Widget in 'Area' mode (Style=3) for a cleaner look.
    """
    clean_symbol = symbol.replace(".NS", "")
    
    # Style "3" = Area Chart (Mountain look), much cleaner than Candles for dashboards
    # Hide top toolbar = True for "App" feel
    html_code = f"""
    <div class="tradingview-widget-container" style="border-radius:12px; overflow:hidden; border:1px solid #333;">
      <div id="tradingview_{clean_symbol}"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width": "100%", "height": 400, "symbol": "BSE:{clean_symbol}", "interval": "D",
        "timezone": "Asia/Kolkata", "theme": "dark", 
        "style": "3", 
        "locale": "in",
        "toolbar_bg": "#f1f3f6", "enable_publishing": false, 
        "hide_top_toolbar": false,
        "allow_symbol_change": true,
        "container_id": "tradingview_{clean_symbol}"
      }});
      </script>
    </div>
    """
    components.html(html_code, height=410)