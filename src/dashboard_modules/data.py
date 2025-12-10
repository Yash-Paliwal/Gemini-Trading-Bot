import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

@st.cache_resource
def get_db_engine(db_url):
    """Creates and caches the database connection."""
    if not db_url: return None
    
    # Fix for Streamlit/SQLAlchemy compatibility with Supabase
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    return create_engine(db_url, pool_pre_ping=True)

def fetch_dashboard_data(engine):
    """
    Runs SQL queries to get Trades and Portfolio.
    automatically converts UTC timestamps to Indian Standard Time (IST).
    """
    if not engine: return pd.DataFrame(), pd.DataFrame()
    
    try:
        with engine.connect() as conn:
            trades_df = pd.read_sql("SELECT * FROM trades ORDER BY entry_time DESC", conn)
            portfolio_df = pd.read_sql("SELECT * FROM portfolio", conn)
            
        # 🚨 TIMEZONE FIX: Convert UTC to IST 🚨
        if not trades_df.empty:
            # Columns that contain time data
            time_cols = ['entry_time', 'exit_time']
            
            for col in time_cols:
                if col in trades_df.columns:
                    # 1. Convert to datetime objects (handling errors)
                    trades_df[col] = pd.to_datetime(trades_df[col], errors='coerce')
                    
                    # 2. Localize to UTC if they don't have timezone info (Naive -> UTC)
                    # If they already have timezone info, convert to UTC first just to be safe
                    if trades_df[col].dt.tz is None:
                        trades_df[col] = trades_df[col].dt.tz_localize('UTC')
                    else:
                        trades_df[col] = trades_df[col].dt.tz_convert('UTC')
                    
                    # 3. Convert from UTC to IST (Asia/Kolkata)
                    trades_df[col] = trades_df[col].dt.tz_convert('Asia/Kolkata')
                    
                    # 4. Format nicely as a string (e.g., "2023-12-09 09:51:50")
                    trades_df[col] = trades_df[col].dt.strftime('%Y-%m-%d %H:%M:%S')

        return trades_df, portfolio_df
        
    except Exception as e:
        st.error(f"Database Read Error: {e}")
        return pd.DataFrame(), pd.DataFrame()

def save_token_to_db(engine, token):
    """
    Saves the Upstox Token to the DB.
    Called by dashboard.py after auth.py returns the token.
    """
    if not engine: return
    
    try:
        with engine.connect() as conn:
            # Ensure table exists
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS api_tokens (
                    provider TEXT PRIMARY KEY,
                    access_token TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            # Upsert Token (Insert or Update)
            conn.execute(text("""
                INSERT INTO api_tokens (provider, access_token, updated_at)
                VALUES ('UPSTOX', :t, NOW())
                ON CONFLICT (provider) DO UPDATE 
                SET access_token = EXCLUDED.access_token, updated_at = NOW()
            """), {"t": token})
            conn.commit()
            # We don't print here to keep UI clean, the UI shows the success message
    except Exception as e:
        st.error(f"Database Write Error: {e}")