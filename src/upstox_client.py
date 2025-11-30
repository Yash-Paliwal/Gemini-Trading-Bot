import requests
import sys

class UpstoxConnection:
    _instance = None  # Singleton instance

    def __new__(cls, *args, **kwargs):
        """Ensures only ONE connection object exists in your entire app."""
        if not cls._instance:
            cls._instance = super(UpstoxConnection, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        # Prevent re-initialization if already created
        if hasattr(self, 'initialized'):
            return
        
        self.access_token = None
        self.base_url = "https://api.upstox.com/v2"
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        self.initialized = True

    def set_access_token(self, token):
        """Call this once at the start of your program."""
        self.access_token = token
        self.headers['Authorization'] = f'Bearer {token}'
        print("✅ Access Token set globally.")

    def check_connection(self):
        """
        Pings the Upstox User Profile endpoint to check if the token is alive.
        Returns: True if good, False if expired/bad.
        """
        if not self.access_token:
            print("❌ Connection Error: No Access Token provided.")
            return False

        endpoint = f"{self.base_url}/user/profile"
        
        try:
            response = requests.get(endpoint, headers=self.headers)
            
            # Case 1: Success
            if response.status_code == 200:
                user_data = response.json().get('data', {})
                user_id = user_data.get('user_id', 'Unknown')
                print(f"🟢 Upstox Connection is GOOD. Logged in as: {user_id}")
                return True
            
            # Case 2: Token Expired or Invalid
            error_data = response.json()
            errors = error_data.get('errors', [])
            
            # Check for specific Upstox error code for expired token
            for err in errors:
                if err.get('errorCode') == 'UDAPI100050':
                    print("🔴 Connection Failed: TOKEN EXPIRED. Please generate a new one.")
                    return False
            
            # Case 3: Other Errors
            print(f"⚠️ Connection Issue. Status: {response.status_code}")
            print(f"   Reason: {error_data}")
            return False

        except Exception as e:
            print(f"❌ Network Error: Could not reach Upstox. {e}")
            return False

    def get_session(self):
        """Returns a configured requests session for use in other files."""
        if not self.access_token:
            raise ValueError("Upstox Access Token not set! Call set_access_token() first.")
        
        session = requests.Session()
        session.headers.update(self.headers)
        return session

# Create a global instance
upstox_client = UpstoxConnection()