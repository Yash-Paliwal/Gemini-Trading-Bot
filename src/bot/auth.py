import os
from src.upstox_client import upstox_client
from src.database import init_db

def authenticate_system():
    """
    Checks Upstox connection and initializes Database.
    Returns True if system is ready to trade.
    """
    print("🔌 Connecting to Upstox...", end=" ")
    
    # 1. Try Token from Env
    if os.getenv("UPSTOX_ACCESS_TOKEN"):
        upstox_client.set_access_token(os.getenv("UPSTOX_ACCESS_TOKEN"))
    
    # 2. Verify Connection
    if not upstox_client.check_connection():
        print("⚠️ Checking DB for Token...", end=" ")
        if upstox_client.fetch_token_from_db(): 
            print("✅ DB Token Loaded.")
        else: 
            print("❌ CRITICAL: No Token found.")
            return False
    else:
        print("✅ Env Token Active.")
    
    # 3. Initialize DB
    try: 
        init_db()
        print("✅ DB Online.")
        return True
    except Exception as e: 
        print(f"❌ DB Fail: {e}")
        return False