import pandas as pd
import streamlit as st
from src.upstox_client import upstox_client
from src.tools import get_live_price, fetch_upstox_map

def calculate_live_metrics(trades_df):
    """
    Takes raw trade history, fetches live prices for OPEN trades,
    and returns enriched data + summary metrics.
    """
    # 1. Filter Open Trades
    open_trades = trades_df[trades_df['status'] == 'OPEN'].copy()
    
    # Initialize Defaults
    total_invested = 0.0
    total_unrealized_pnl = 0.0
    current_holdings_value = 0.0
    
    if open_trades.empty:
        return open_trades, 0, 0, 0, False

    # 2. Initialize Columns
    open_trades['Live Price'] = open_trades['entry_price']
    open_trades['PnL'] = 0.0
    open_trades['PnL %'] = 0.0
    open_trades['Current Value'] = 0.0

    # 3. Fetch Live Data
    is_live = upstox_client.fetch_token_from_db()
    
    if is_live:
        master_map = fetch_upstox_map()
        
        # Iterate and Update
        # (Using apply/lambda would be faster for huge datasets, but loop is safer for API calls)
        for idx, row in open_trades.iterrows():
            key = master_map.get(row['ticker'])
            live_price = row['entry_price'] # Default
            
            if key:
                lp = get_live_price(key, row['ticker'])
                if lp: live_price = lp
            
            # Math
            qty = row['quantity']
            entry = row['entry_price']
            val = live_price * qty
            pnl = val - (entry * qty)
            pnl_pct = ((live_price - entry) / entry) * 100
            
            # Assign
            open_trades.at[idx, 'Live Price'] = live_price
            open_trades.at[idx, 'Current Value'] = val
            open_trades.at[idx, 'PnL'] = pnl
            open_trades.at[idx, 'PnL %'] = pnl_pct

    # 4. Calculate Totals
    total_invested = (open_trades['entry_price'] * open_trades['quantity']).sum()
    current_holdings_value = open_trades['Current Value'].sum()
    total_unrealized_pnl = open_trades['PnL'].sum()
    
    return open_trades, total_invested, current_holdings_value, total_unrealized_pnl, is_live