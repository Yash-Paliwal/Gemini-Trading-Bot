import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
from .config import DATABASE_URL

Base = declarative_base()
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
    level = Column(String) # INFO, SIGNAL, ERROR
    message = Column(Text)

# --- FUNCTIONS ---
def init_db():
    try: Base.metadata.create_all(engine)
    except: pass
    
    # Init Portfolio if missing
    session = Session()
    if not session.query(Portfolio).first():
        session.add(Portfolio(id=1, balance=100000.0))
        session.commit()
    session.close()

class Portfolio(Base):
    __tablename__ = 'portfolio'
    id = Column(Integer, primary_key=True)
    balance = Column(Float, default=100000.0)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# --- CASH MANAGER ---
def get_current_balance():
    session = Session()
    try:
        p = session.query(Portfolio).first()
        return p.balance if p else 0.0
    finally: session.close()

def update_balance(amount):
    session = Session()
    try:
        p = session.query(Portfolio).first()
        p.balance += float(amount)
        session.commit()
        print(f"   💰 Wallet Updated: ₹{p.balance:,.2f}")
    except: session.rollback()
    finally: session.close()

# --- LOGGING (SEPARATED) ---
def log_trade(data, qty):
    """Saves ONLY actual trades."""
    session = Session()
    try:
        new_trade = Trade(
            ticker=str(data['ticker']),
            signal="BUY", # Only BUYs go here
            entry_price=float(data.get('entry_price', 0)),
            target_price=float(data.get('target_price', 0)),
            stop_loss=float(data.get('stop_loss', 0)),
            quantity=int(qty),
            reasoning=str(data.get('reasoning', '')),
            status="OPEN"
        )
        session.add(new_trade)
        session.commit()
        print(f"   💾 DB: Trade Opened ({data['ticker']})")
    except Exception as e: print(f"   ❌ DB Trade Error: {e}")
    finally: session.close()

def log_signal_audit(ticker, signal, reasoning):
    """Saves WAIT signals to app_logs, keeping trades table clean."""
    session = Session()
    try:
        log_entry = Log(
            level="SIGNAL",
            message=f"{ticker}: {signal} - {reasoning}"
        )
        session.add(log_entry)
        session.commit()
        print(f"   🗂️ Audit Log: {ticker} -> {signal}")
    except: pass
    finally: session.close()

# --- TRADE MANAGEMENT ---
def get_open_trades():
    session = Session()
    try: return session.query(Trade).filter(Trade.status == 'OPEN').all()
    finally: session.close()

def update_trade_status(trade_id, status, exit_price, pnl):
    session = Session()
    try:
        t = session.query(Trade).filter(Trade.id == trade_id).first()
        if t:
            t.status = status
            t.exit_time = datetime.now()
            t.pnl = pnl
            # We don't have an exit_price column, but PnL captures the math
            session.commit()
            print(f"   🔒 Trade Closed. PnL: {pnl}")
    except: session.rollback()
    finally: session.close()