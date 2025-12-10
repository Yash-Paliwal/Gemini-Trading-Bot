import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
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
    # 🆕 NEW COLUMN
    strategy_name = Column(String, default="MASTER")
    confidence = Column(Integer, default=0)

class Log(Base):
    __tablename__ = 'app_logs'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.now)
    level = Column(String)
    message = Column(Text)

class Portfolio(Base):
    __tablename__ = 'portfolio'
    # 🆕 Composite Primary Key (id + strategy_name) to allow multiple wallets
    id = Column(Integer, primary_key=True, autoincrement=True) 
    strategy_name = Column(String, default="MASTER")
    balance = Column(Float, default=100000.0)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# --- INITIALIZATION ---
def init_db():
    try: Base.metadata.create_all(engine)
    except: pass
    
    # 🆕 Seed the 3 Strategy Wallets if empty
    session = Session()
    strategies = ["STRATEGY_MOMENTUM", "STRATEGY_MEAN_REVERSION", "STRATEGY_AI_SNIPER"]
    
    for strat in strategies:
        exists = session.query(Portfolio).filter_by(strategy_name=strat).first()
        if not exists:
            # Create wallet with ₹1 Lakh each
            session.add(Portfolio(strategy_name=strat, balance=100000.0))
            print(f"   💰 Created Wallet for {strat}")
    
    session.commit()
    session.close()

# --- CASH MANAGER ---
def get_current_balance(strategy_name="MASTER"):
    session = Session()
    try:
        # 🆕 Query by Strategy Name
        p = session.query(Portfolio).filter_by(strategy_name=strategy_name).first()
        return p.balance if p else 0.0
    finally: session.close()

def update_balance(amount, strategy_name="MASTER"):
    session = Session()
    try:
        # 🆕 Update specific strategy wallet
        p = session.query(Portfolio).filter_by(strategy_name=strategy_name).first()
        if p:
            p.balance += float(amount)
            session.commit()
            print(f"   💰 {strategy_name} Wallet Updated: ₹{p.balance:,.2f}")
    except: session.rollback()
    finally: session.close()

# --- LOGGING ---
def log_trade(data, qty):
    """Saves trades with strategy tags."""
    session = Session()
    try:
        new_trade = Trade(
            ticker=str(data['ticker']),
            signal=str(data['signal']),
            entry_price=float(data.get('entry_price', 0)),
            target_price=float(data.get('target_price', 0)),
            stop_loss=float(data.get('stop_loss', 0)),
            quantity=int(qty),
            reasoning=str(data.get('reasoning', '')),
            status="OPEN",
            # 🆕 Save Strategy info
            strategy_name=str(data.get('strategy_name', 'MASTER')),
            confidence=int(data.get('confidence', 0))
        )
        session.add(new_trade)
        session.commit()
        print(f"   💾 DB: Trade Opened for {data.get('strategy_name', 'MASTER')}")
    except Exception as e: print(f"   ❌ DB Trade Error: {e}")
    finally: session.close()

def log_signal_audit(ticker, signal, reasoning):
    session = Session()
    try:
        log_entry = Log(level="SIGNAL", message=f"{ticker}: {signal} - {reasoning}")
        session.add(log_entry)
        session.commit()
    except: pass
    finally: session.close()

# --- TRADE MANAGEMENT ---
def get_open_trades(strategy_name=None):
    """
    Fetches open trades.
    If strategy_name is provided, filters for that strategy.
    If None, returns ALL open trades (useful for dashboard).
    """
    session = Session()
    try: 
        query = session.query(Trade).filter(Trade.status == 'OPEN')
        if strategy_name:
            query = query.filter(Trade.strategy_name == strategy_name)
        return query.all()
    finally: session.close()

def update_trade_status(trade_id, status, exit_price, pnl):
    session = Session()
    try:
        t = session.query(Trade).filter(Trade.id == trade_id).first()
        if t:
            t.status = status
            t.exit_time = datetime.now()
            t.pnl = pnl
            session.commit()
            print(f"   🔒 Trade Closed. PnL: {pnl}")
    except: session.rollback()
    finally: session.close()