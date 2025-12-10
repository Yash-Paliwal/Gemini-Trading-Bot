import os
import streamlit as st

def load_config():
    """
    Loads configuration from Streamlit Secrets or Env Vars.
    CRITICAL: Automatically injects them into os.environ so 
    other modules (like database.py) can find them.
    """
    config = {}
    
    # 1. DATABASE_URL
    if "DATABASE_URL" in st.secrets:
        config["DATABASE_URL"] = st.secrets["DATABASE_URL"]
    else:
        config["DATABASE_URL"] = os.getenv("DATABASE_URL")

    # 2. UPSTOX CREDENTIALS
    # Check secrets first, then env
    config["UPSTOX_API_KEY"] = st.secrets.get("UPSTOX_API_KEY", os.getenv("UPSTOX_API_KEY"))
    config["UPSTOX_API_SECRET"] = st.secrets.get("UPSTOX_API_SECRET", os.getenv("UPSTOX_API_SECRET"))
    
    # 3. REDIRECT URI
    # Default to localhost if missing (for local dev)
    default_uri = "http://localhost:8501"
    config["REDIRECT_URI"] = st.secrets.get("REDIRECT_URI", os.getenv("REDIRECT_URI", default_uri))

    # 4. INJECT INTO ENVIRONMENT (The Magic Step)
    # This ensures src.database and src.upstox_client work without changes
    if config["DATABASE_URL"]: os.environ["DATABASE_URL"] = config["DATABASE_URL"]
    if config["UPSTOX_API_KEY"]: os.environ["UPSTOX_API_KEY"] = config["UPSTOX_API_KEY"]
    if config["UPSTOX_API_SECRET"]: os.environ["UPSTOX_API_SECRET"] = config["UPSTOX_API_SECRET"]
    if config["REDIRECT_URI"]: os.environ["REDIRECT_URI"] = config["REDIRECT_URI"]

    return config