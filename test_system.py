import os
import sys
import pandas as pd
import yfinance as yf
from sqlalchemy import text  # <--- CRITICAL IMPORT
from src.database import init_db, Session
from src.tools import fetch_upstox_map, fetch_data, get_live_price
from src.upstox_client import upstox_client
from src.risk.calculator import calculate_position_size

def run_diagnostics():
    print("🏥 GEMINI BOT DIAGNOSTICS TOOL 🏥")
    print("====================================")

    # TEST 1: Database Structure
    print("\n[1/5] Checking Database Schema...")
    try:
        init_db()
        session = Session()
        
        # 1. Check Trades Table (Using text() wrapper)
        try:
            session.execute(text("SELECT strategy_name FROM trades LIMIT 1"))
            print("   ✅ 'trades' table has 'strategy_name' column.")
        except Exception as e:
            # If this actually fails, the column is genuinely missing
            print(f"   ❌ CRITICAL: 'trades' table check failed. Error: {e}")

        # 2. Check Wallets (Using text() wrapper)
        try:
            wallets = session.execute(text("SELECT strategy_name, balance FROM portfolio")).fetchall()
            if len(wallets) >= 3:
                print(f"   ✅ Found {len(wallets)} Strategy Wallets.")
                for w in wallets:
                    print(f"      - {w[0]}: ₹{w[1]:,.2f}")
            else:
                print(f"   ⚠️ Warning: Only found {len(wallets)} wallets. Expected 3 (Momentum, MeanRev, AI).")
        except Exception as e:
            print(f"   ❌ Wallet Check Failed: {e}")
            
        session.close()
    except Exception as e:
        print(f"   ❌ DB Connection Failed: {e}")

    # TEST 2: Ticker Mapping
    print("\n[2/5] Checking Ticker Mapping...")
    master_map = fetch_upstox_map()
    if master_map:
        test_ticker = "RELIANCE.NS"
        clean_ticker = test_ticker.replace(".NS", "")
        key = master_map.get(clean_ticker)
        
        if key:
            print(f"   ✅ Mapping Working: '{test_ticker}' -> Key Found ({key})")
        else:
            print(f"   ❌ Mapping Failed for '{clean_ticker}'.")
    else:
        print("   ❌ Instrument Map failed to load.")

    # TEST 3: Data Feed
    print("\n[3/5] Checking Data Feed (yfinance)...")
    try:
        df = fetch_data("RELIANCE.NS")
        if df is not None and not df.empty:
            print(f"   ✅ Data Received. Latest Close: {df['Close'].iloc[-1]:.2f}")
        else:
            print("   ❌ Fetch Data Failed.")
    except Exception as e:
        print(f"   ❌ YFinance Crash: {e}")

    # TEST 4: Live Price (With Robust Auth)
    print("\n[4/5] Checking Live Price API...")
    
    # 🚨 AUTH FIX: Force load from DB if env is empty
    if not upstox_client.check_connection():
        print("   ⚠️ Token not in RAM. Fetching from DB...")
        if upstox_client.fetch_token_from_db():
            print("   ✅ Authenticated via Database.")
        else:
            print("   ❌ Authentication FAILED. Please login via Dashboard first.")
            key = None

    if upstox_client.check_connection() and key:
        try:
            price = get_live_price(key, "RELIANCE.NS")
            if price:
                print(f"   ✅ Live Price Fetched: ₹{price}")
            else:
                print("   ⚠️ Price returned None. (API limit or Market Closed?)")
        except Exception as e:
            print(f"   ❌ Price Fetch Error: {e}")
    else:
        print("   ⏭️ Skipping Price Check (No Auth or Key).")

    # TEST 5: Risk Calculator
    print("\n[5/5] Checking Risk Logic...")
    try:
        qty = calculate_position_size(1000, 950, risk_per_trade=0.02)
        if qty > 0:
            print(f"   ✅ Calculator Working. Qty: {qty}")
        else:
            print("   ❌ Calculator returned 0.")
    except Exception as e:
        print(f"   ❌ Calculator Crash: {e}")

    print("\n====================================")
    print("🏁 DIAGNOSTICS COMPLETE")

if __name__ == "__main__":
    run_diagnostics()