import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
from .config import DATABASE_URL

# --- SETUP ---
Base = declarative_base()
# pool_pre_ping=True prevents connection drops
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

# --- MODELS ---
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

# --- FUNCTIONS ---

def init_db():
    """Creates tables if they don't exist."""
    try: Base.metadata.create_all(engine)
    except: pass

def log_trade(data, qty):
    """Saves a new trade to the DB."""
    session = Session()
    try:
        # Determine status: BUY -> OPEN, WAIT -> WATCH
        status = "OPEN" if data['signal'] == "BUY" else "WATCH"
        
        new_trade = Trade(
            ticker=str(data['ticker']),
            signal=str(data['signal']),
            entry_price=float(data.get('entry_price', 0)),
            target_price=float(data.get('target_price', 0)),
            stop_loss=float(data.get('stop_loss', 0)),
            quantity=int(qty),
            reasoning=str(data.get('reasoning', '')),
            status=status
        )
        session.add(new_trade)
        session.commit()
        print(f"   💾 DB: Saved {data['ticker']} ({status})")
    except Exception as e:
        print(f"   ❌ DB Error: {e}")
        session.rollback()
    finally:
        session.close()

# --- 👇 THE MISSING FUNCTIONS 👇 ---

def get_open_trades():
    """Fetches all active trades (Status = OPEN)."""
    session = Session()
    try:
        trades = session.query(Trade).filter(Trade.status == 'OPEN').all()
        return trades
    except Exception as e:
        print(f"   ❌ DB Read Error: {e}")
        return []
    finally:
        session.close()

def update_trade_status(trade_id, new_status, exit_price, pnl):
    """Closes a trade (Updates Status, Exit Price, and PnL)."""
    session = Session()
    try:
        trade = session.query(Trade).filter(Trade.id == trade_id).first()
        if trade:
            trade.status = new_status
            trade.exit_time = datetime.now()
            trade.pnl = pnl
            session.commit()
            print(f"   🔒 Trade {trade.ticker} Closed ({new_status}).")
    except Exception as e:
        print(f"   ❌ DB Update Failed: {e}")
        session.rollback()
    finally:
        session.close()