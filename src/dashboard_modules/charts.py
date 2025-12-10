import streamlit.components.v1 as components

def render_tradingview_chart(symbol):
    """Renders the TradingView Widget."""
    clean_symbol = symbol.replace(".NS", "")
    tv_symbol = f"BSE:{clean_symbol}"
    
    html_code = f"""
    <div class="tradingview-widget-container">
      <div id="tradingview_{clean_symbol}"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width": "100%", "height": 500, "symbol": "{tv_symbol}", "interval": "D",
        "timezone": "Asia/Kolkata", "theme": "light", "style": "1", "locale": "in",
        "toolbar_bg": "#f1f3f6", "enable_publishing": false, "allow_symbol_change": true,
        "container_id": "tradingview_{clean_symbol}"
      }});
      </script>
    </div>
    """
    components.html(html_code, height=500)