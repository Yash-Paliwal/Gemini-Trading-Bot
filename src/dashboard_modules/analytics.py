import pandas as pd
from src.tools import get_live_price, fetch_upstox_map

def calculate_strategy_performance(trades, portfolio, is_live=False):
    """
    Takes raw trade history and portfolio balance.
    Groups them by 'strategy_name' to calculate detailed performance for each bot.
    
    Returns: 
    1. stats_df (DataFrame for Leaderboard)
    2. total_fund_equity (Float)
    3. total_fund_cash (Float)
    """
    if portfolio.empty or 'strategy_name' not in portfolio.columns:
        return pd.DataFrame(), 0.0, 0.0

    # 1. Prepare Data
    strategies = portfolio['strategy_name'].unique().tolist()
    master_map = fetch_upstox_map() if is_live else {}
    
    strategy_stats = []
    total_fund_equity = 0.0
    total_fund_cash = 0.0

    # 2. Iterate through each Strategy (Momentum, MeanRev, AI)
    for strat in strategies:
        # A. Get Cash for THIS Strategy
        strat_cash_row = portfolio[portfolio['strategy_name'] == strat]
        cash = float(strat_cash_row.iloc[0]['balance']) if not strat_cash_row.empty else 0.0
        
        # B. Get Trades for THIS Strategy
        strat_trades = trades[trades['strategy_name'] == strat].copy()
        
        # C. Calculate Open Position Value (Live)
        open_trades = strat_trades[strat_trades['status'] == 'OPEN'].copy()
        invested = 0.0
        unrealized_pnl = 0.0
        current_holdings_val = 0.0
        
        if not open_trades.empty:
            current_vals = []
            
            for _, t in open_trades.iterrows():
                entry = t['entry_price']
                qty = t['quantity']
                curr_price = entry # Default to entry
                
                # Fetch Real Market Price if Live
                if is_live:
                    # Clean ticker for Upstox Map (RELIANCE.NS -> RELIANCE)
                    clean_ticker = t['ticker'].replace(".NS", "")
                    key = master_map.get(clean_ticker)
                    
                    if key:
                        lp = get_live_price(key, t['ticker'])
                        if lp: curr_price = lp
                
                # Math
                val = curr_price * qty
                current_vals.append(val)
            
            # Aggregates for this strategy
            invested = (open_trades['entry_price'] * open_trades['quantity']).sum()
            current_holdings_val = sum(current_vals)
            unrealized_pnl = current_holdings_val - invested
        
        # D. Calculate Realized P&L (Closed Trades)
        # We look for trades that are NOT 'OPEN'
        closed_trades = strat_trades[strat_trades['status'] != 'OPEN']
        realized_pnl = closed_trades['pnl'].sum() if not closed_trades.empty else 0.0
        
        # E. Total Equity for this Strategy
        total_equity = cash + current_holdings_val
        
        # Add to Global Totals
        total_fund_equity += total_equity
        total_fund_cash += cash

        # F. Add to Stats List
        strategy_stats.append({
            "Strategy": strat.replace("STRATEGY_", ""), # Clean name
            "Cash": cash,
            "Invested": invested,
            "Unrealized P&L": unrealized_pnl,
            "Realized P&L": realized_pnl,
            "Total Equity": total_equity,
            "ROI %": 0.0 # Placeholder, calculated in UI if needed
        })
        
    return pd.DataFrame(strategy_stats), total_fund_equity, total_fund_cash