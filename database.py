import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# --- CONFIGURATION ---
# ⚠️ Load this from Environment Variables (GitHub Secrets)
DB_URL = os.getenv("DATABASE_URL") 

# --- SETUP ---
Base = declarative_base()
engine = create_engine(DB_URL, pool_pre_ping=True) # Auto-reconnect
Session = sessionmaker(bind=engine)

# --- MODELS (Mapping Python Classes to SQL Tables) ---
class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    ticker = Column(String)
    signal = Column(String)
    entry_price = Column(Float)
    target_price = Column(Float)
    stop_loss = Column(Float)
    quantity = Column(Integer)
    status = Column(String, default="OPEN")
    entry_time = Column(DateTime, default=datetime.now)
    exit_time = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    reasoning = Column(Text)

class Log(Base):
    __tablename__ = 'app_logs'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.now)
    level = Column(String)
    message = Column(Text)

# --- HELPER FUNCTIONS ---

def init_db():
    """Creates tables if they don't exist (Run once)."""
    Base.metadata.create_all(engine)

def log_trade(data, qty):
    """Saves a new BUY signal to the DB (With Type Safety)."""
    session = Session()
    try:
        new_trade = Trade(
            ticker=str(data['ticker']),
            signal=str(data['signal']),
            # 🛡️ SAFETY: Convert to float/int to prevent DB errors
            entry_price=float(data.get('entry_price', 0)),
            target_price=float(data.get('target_price', 0)),
            stop_loss=float(data.get('stop_loss', 0)),
            quantity=int(qty),
            reasoning=str(data.get('reasoning', '')),
            status="OPEN"
        )
        session.add(new_trade)
        session.commit()
        print(f"   💾 Database: Trade Saved ({data['ticker']})")
    except Exception as e:
        print(f"   ❌ Database Error: {e}")
        session.rollback()
    finally:
        session.close()

def get_open_trades():
    """Fetches all active trades for the Exit Manager."""
    session = Session()
    trades = session.query(Trade).filter(Trade.status == 'OPEN').all()
    session.close()
    return trades

def close_trade(trade_id, exit_price, status, pnl):
    """Updates a trade as CLOSED."""
    session = Session()
    try:
        trade = session.query(Trade).filter(Trade.id == trade_id).first()
        if trade:
            trade.status = status
            trade.exit_price = exit_price # Ensure you add this column if you want it
            trade.exit_time = datetime.now()
            trade.pnl = pnl
            session.commit()
            print(f"   🔒 Trade {trade_id} Closed.")
    except Exception as e:
        session.rollback()
        print(f"   ❌ DB Error Closing Trade: {e}")
    finally:
        session.close()
