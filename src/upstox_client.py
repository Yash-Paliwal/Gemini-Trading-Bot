import requests
import sys
from sqlalchemy import text

# 🚨 FIX: Import Session so we can talk to the database
from src.database import Session 

class UpstoxConnection:
    _instance = None  # Singleton instance

    def __new__(cls, *args, **kwargs):
        """Ensures only ONE connection object exists."""
        if not cls._instance:
            cls._instance = super(UpstoxConnection, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'): return
        
        self.access_token = None
        self.base_url = "https://api.upstox.com/v2"
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        self.initialized = True

    def set_access_token(self, token):
        self.access_token = token
        self.headers['Authorization'] = f'Bearer {token}'
        print("✅ Access Token set globally.")

    def check_connection(self):
        """Pings Upstox to check if token is valid."""
        if not self.access_token: return False

        try:
            url = f"{self.base_url}/user/profile"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                print(f"🟢 Upstox Connection is GOOD.")
                return True
            elif response.status_code == 401:
                print("🔴 Connection Failed: TOKEN EXPIRED.")
                return False
            else:
                print(f"⚠️ Connection Issue: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Network Error: {e}")
            return False

    def get_session(self):
        if not self.access_token:
            raise ValueError("Upstox Access Token not set! Call set_access_token() first.")
        
        session = requests.Session()
        session.headers.update(self.headers)
        return session

    def fetch_token_from_db(self):
        """Gets the latest token from Supabase (Fallback Method)."""
        # This line caused the error before because Session wasn't imported
        session = Session() 
        try:
            # Fetch token where provider is 'UPSTOX'
            result = session.execute(text("SELECT access_token FROM api_tokens WHERE provider = 'UPSTOX'"))
            row = result.fetchone()
            
            if row:
                self.set_access_token(row[0])
                print("✅ Loaded Access Token from Database.")
                return True
            
            print("   ⚠️ No token found in Database.")
            return False
            
        except Exception as e:
            print(f"❌ Failed to fetch token from DB: {e}")
            return False
        finally:
            session.close()

# Create global instance
upstox_client = UpstoxConnection()