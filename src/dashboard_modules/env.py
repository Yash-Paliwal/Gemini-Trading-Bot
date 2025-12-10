import os
import streamlit as st

def load_config():
    """
    Loads configuration from Streamlit Secrets (Cloud) or Env Vars (Local).
    Returns a dictionary of settings.
    """
    config = {}
    
    try:
        # 1. Try Loading from Streamlit Secrets (Cloud / .streamlit/secrets.toml)
        config["DATABASE_URL"] = st.secrets["DATABASE_URL"]
        config["API_KEY"] = st.secrets.get("UPSTOX_API_KEY", "")
        config["API_SECRET"] = st.secrets.get("UPSTOX_API_SECRET", "")
        
        # 🚨 STRICT SOURCE OF TRUTH
        # If REDIRECT_URI is not in secrets, default to the Cloud App URL
        config["REDIRECT_URI"] = st.secrets.get("REDIRECT_URI", "https://gemini-trading-bot-yash.streamlit.app")
        
    except FileNotFoundError:
        # 2. Fallback for Local Dev without secrets.toml (Environment Variables)
        config["DATABASE_URL"] = os.getenv("DATABASE_URL")
        config["API_KEY"] = os.getenv("UPSTOX_API_KEY")
        config["API_SECRET"] = os.getenv("UPSTOX_API_SECRET")
        
        # Default to Localhost if running raw python
        # Note: You can change this default to your Cloud URL if you prefer
        config["REDIRECT_URI"] = os.getenv("REDIRECT_URI", "http://localhost:8501")

    return config