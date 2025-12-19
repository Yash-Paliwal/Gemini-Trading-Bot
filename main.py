import time
import logging
from datetime import datetime

import pandas as pd

# --- IMPORTS ---
from src.dashboard_modules.env import load_config
from src.dashboard_modules.data import get_db_engine
from src.finder.strategy import run_screener
from src.tools import fetch_upstox_map, fetch_candles, get_live_price
from src.strategies import momentum as momentum_strategy
from src.strategies import mean_reversion as mean_rev_strategy
from src.strategies import ai_sniper as ai_sniper_strategy
from src.portfolio.manager import check_portfolio_health
from src.risk.calculator import (
    calculate_position_size,
    validate_trade_setup,
    get_market_volatility,
)
from src.db_helper import place_or_update_trade
from src.upstox_client import upstox_client

# --- SETUP LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
config = load_config()
DB_URL = config.get("DATABASE_URL")

if not DB_URL:
    logger.error("❌ Database URL is missing in .env")
    exit()

    # Connect to Database
engine = get_db_engine(DB_URL)


def _process_signal(strategy_name: str, ticker: str, entry_price: float, target: float, stop_loss: float):
    """
    Common execution path for all strategies (single pass):
    1) Portfolio-level checks
    2) Risk-based sizing
    3) DB-level validation (averaging / noise / allocation)
    4) Upsert into trades table
    """
    clean_ticker = ticker.replace(".NS", "")  # ensure DB uses plain symbol

    # 1. Portfolio health (per-strategy exposure rules)
    allowed_pf, reason_pf = check_portfolio_health(clean_ticker, strategy_name)
    if not allowed_pf:
        logger.info(f"✋ {strategy_name}: Portfolio Blocked for {clean_ticker} -> {reason_pf}")
        return

    # 2. Position sizing
    qty = calculate_position_size(entry=entry_price, stop_loss=stop_loss)
    if qty <= 0:
        logger.info(f"✋ {strategy_name}: Qty 0 for {clean_ticker} (Risk too high / SL too tight)")
        return

    # 3. DB-based validation (existing position, noise, allocation caps)
    allowed_db, final_qty, reason_db = validate_trade_setup(
        engine,
        strategy_name,
        clean_ticker,
        entry_price,
        qty,
    )

    if not allowed_db or final_qty <= 0:
        logger.info(f"✋ {strategy_name}: Risk Manager Blocked {clean_ticker} -> {reason_db}")
        return

    # 4. Execute & upsert trade
    place_or_update_trade(
        engine,
        strategy_name,
        clean_ticker,
        final_qty,
        entry_price,
        target,
        stop_loss,
    )
    logger.info(f"🚀 {strategy_name}: Executed {clean_ticker} | Qty: {final_qty} | Reason: {reason_db}")


def _market_regime_ok() -> bool:
    """
    Simple swing-trader style regime filter:
    - Index (NIFTY) above its 200-day EMA
    - Volatility (India VIX via get_market_volatility) not in 'dangerous' zone
    """
    try:
        import yfinance as yf

        # 1. Volatility filter (reuses your risk logic)
        vol_factor = get_market_volatility()  # 1.0 safe, 0.75 caution, 0.5 dangerous
        if vol_factor <= 0.5:
            logger.info("⚠️ Regime Filter: High volatility (VIX). Skipping new entries.")
            return False

        # 2. Index trend filter (NIFTY above 200 EMA)
        idx = yf.download("^NSEI", period="1y", progress=False)
        if idx.empty:
            logger.warning("⚠️ Regime Filter: Could not fetch NIFTY data. Allowing trades by default.")
            return True

        closes = idx["Close"]
        # yfinance can return DataFrame if multiple tickers; ensure Series
        if hasattr(closes, "columns"):
            closes = closes.iloc[:, 0]

        ema_200 = closes.ewm(span=200).mean()
        last_close = float(closes.iloc[-1])
        last_ema = float(ema_200.iloc[-1])

        if last_close <= last_ema:
            logger.info("⚠️ Regime Filter: NIFTY below 200 EMA. Skipping new entries.")
            return False

        return True
    except Exception as e:
        logger.warning(f"⚠️ Regime Filter Error: {e}. Allowing trades by default.")
        return True


# --- SINGLE-PASS MAIN BOT (for GitHub Actions / cron) ---
def run_bot():
    """
    Single-pass swing engine:
    - Meant to be invoked by a scheduler (GitHub Actions / cron / Streamlit button)
    - No internal while-loop or sleeps
    """
    logger.info("🤖 Gemini Swing Trading Bot Started (single pass)...")

    # --- Upstox Auth for AI Sniper / Live Prices ---
    ai_enabled = True
    try:
        if not upstox_client.check_connection():
            logger.info("⚠️ Upstox token not in memory. Attempting to load from DB...")
            if upstox_client.fetch_token_from_db():
                logger.info("✅ Upstox authenticated via database.")
            else:
                logger.warning("❌ No Upstox token found. Disabling AI Sniper for this run.")
                ai_enabled = False
    except Exception as e:
        logger.warning(f"❌ Upstox auth error: {e}. Disabling AI Sniper.")
        ai_enabled = False

    # Load Upstox instrument map once
    master_map = fetch_upstox_map()
    if not master_map:
        logger.error("❌ Failed to load Upstox instrument map. Exiting.")
        return

    # --- Market Regime Filter ---
    if not _market_regime_ok():
        logger.info("🧱 Regime Filter blocked new entries for this pass.")
        return

    try:
        logger.info(f"⏳ Scanning markets at {datetime.now().strftime('%H:%M:%S')}...")

        # 1) Build universe via multi-strategy screener (batch scan)
        candidates = run_screener(limit=5)  # returns plain tickers like 'RELIANCE'
        if not candidates:
            logger.info("😴 Screener returned no candidates.")
            return

        logger.info(f"🎯 Screener Candidates: {candidates}")

        # 2) Loop over each candidate and run strategies (all on Upstox data)
        for symbol in candidates:
            yahoo_sym = symbol if symbol.endswith(".NS") else f"{symbol}.NS"

            # Resolve Upstox instrument key
            clean = symbol.replace(".NS", "")
            key = master_map.get(clean) or master_map.get(symbol)
            if not key:
                logger.warning(f"⚠️ No Upstox key found for {symbol}")
                continue

            # 2A) MOMENTUM + MEAN REVERSION (daily OHLC via Upstox historical candles)
            # Ask Upstox for a long enough window so EMA200 / RSI have room to stabilize.
            candles = fetch_candles(key, days=800, interval="days")
            if not candles or len(candles) < 220:
                logger.warning(f"⚠️ Not enough candle history for {symbol} (got {len(candles) if candles else 0})")
                continue

            # Convert PriceCandle list -> DataFrame with 'Close' column for strategies
            try:
                try:
                    data = [c.model_dump() for c in candles]
                except Exception:
                    data = [c.dict() for c in candles]
                df = pd.DataFrame(data)
            except Exception as e:
                logger.warning(f"⚠️ Failed to build DataFrame for {symbol}: {e}")
                continue

            if "close" not in df.columns:
                logger.warning(f"⚠️ Candle data missing 'close' for {symbol}")
                continue

            df["Close"] = df["close"].astype(float)
            last_close = float(df["Close"].iloc[-1])

            # Prefer live LTP from Upstox when available
            ltp = get_live_price(key, yahoo_sym)
            entry_ref_price = float(ltp) if ltp else last_close

            # MOMENTUM (trend-following swing)
            try:
                mom_decision = momentum_strategy.analyze(df.copy())
            except Exception as e:
                logger.error(f"❌ Momentum strategy error for {symbol}: {e}")
                mom_decision = None

            if mom_decision and mom_decision.get("action") == "BUY":
                # Swing-style: modest SL/TP for strong trend
                sl = entry_ref_price * 0.95   # 5% SL
                tgt = entry_ref_price * 1.10  # 10% target
                logger.info(f"🔔 MOMENTUM BUY: {symbol} @ ~{entry_ref_price:.2f} | {mom_decision['reason']}")
                _process_signal(
                    strategy_name="STRATEGY_MOMENTUM",
                    ticker=symbol,
                    entry_price=entry_ref_price,
                    target=tgt,
                    stop_loss=sl,
                )

            # MEAN REVERSION (oversold bounce within uptrend)
            try:
                mr_decision = mean_rev_strategy.analyze(df.copy())
            except Exception as e:
                logger.error(f"❌ Mean Reversion strategy error for {symbol}: {e}")
                mr_decision = None

            if mr_decision and mr_decision.get("action") == "BUY":
                # Give more room & upside for bounces
                sl = entry_ref_price * 0.92   # 8% SL
                tgt = entry_ref_price * 1.18  # 18% target
                logger.info(f"🔔 MEAN REV BUY: {symbol} @ ~{entry_ref_price:.2f} | {mr_decision['reason']}")
                _process_signal(
                    strategy_name="STRATEGY_MEAN_REVERSION",
                    ticker=symbol,
                    entry_price=entry_ref_price,
                    target=tgt,
                    stop_loss=sl,
                )

            # 2B) AI SNIPER (heavyweight: Upstox candles + Gemini + fundamentals + news)
            if ai_enabled:
                try:
                    ai_decision = ai_sniper_strategy.analyze(yahoo_sym, master_map)
                except Exception as e:
                    logger.error(f"❌ AI Sniper error for {symbol}: {e}")
                    ai_decision = None

                if ai_decision and ai_decision.get("action") == "BUY":
                    price = float(ai_decision["price"])
                    atr = float(ai_decision["atr"])
                    # ATR-based swing levels (2 ATR stop, 4 ATR target)
                    sl = price - 2 * atr
                    tgt = price + 4 * atr
                    logger.info(f"🔔 AI SNIPER BUY: {symbol} @ {price:.2f} | {ai_decision['reason']}")
                    _process_signal(
                        strategy_name="STRATEGY_AI_SNIPER",
                        ticker=symbol,
                        entry_price=price,
                        target=tgt,
                        stop_loss=sl,
                    )

    except Exception as e:
        logger.error(f"❌ Critical Error in Single-Pass Bot: {e}")

if __name__ == "__main__":
    run_bot()