import sys
from src.database import get_open_trades
from src.tools import get_live_price, fetch_upstox_map
from src.upstox_client import upstox_client

# --- MODULAR IMPORTS ---
from src.bot.executor import execute_exit
from src.bot.telegram import send_exit_alert

def get_val(obj, key):
    """Helper to safely get value from either a Dict or an Object."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

def run_watchdog():
    print("\n👮 STARTING MULTI-STRATEGY WATCHDOG (Single Scan)...")
    
    # 1. Auth Check
    if not upstox_client.check_connection():
        # Try loading from DB if Env var is missing
        if upstox_client.fetch_token_from_db(): 
            print("   ✅ Token Loaded from DB.")
        else: 
            print("   ❌ No Token. Exiting.")
            return

    # 2. Get Data
    trades = get_open_trades(strategy_name=None)
    if not trades:
        print("   💤 No active trades to monitor.")
        return

    master_map = fetch_upstox_map()
    print(f"   🔍 Monitoring {len(trades)} Positions...")
    
    for t in trades:
        ticker = get_val(t, 'ticker')
        strategy = get_val(t, 'strategy_name') or 'MASTER'
        trade_id = get_val(t, 'id')
        stop_loss = get_val(t, 'stop_loss')
        target_price = get_val(t, 'target_price')
        quantity = get_val(t, 'quantity')
        entry_price = get_val(t, 'entry_price')
        
        # 3. Get Price
        key = master_map.get(ticker)
        if not key: continue
        
        current_price = get_live_price(key, ticker)
        if not current_price: continue
            
        # 4. Check Rules
        new_status = None
        if current_price <= stop_loss: new_status = "STOP_HIT"
        elif current_price >= target_price: new_status = "TARGET_HIT"

        # 5. Delegate Execution
        if new_status:
            pnl, new_bal = execute_exit(
                trade_id=trade_id,
                ticker=ticker,
                strategy_name=strategy,
                quantity=quantity,
                entry_price=entry_price,
                exit_price=current_price,
                status=new_status
            )
            send_exit_alert(ticker, strategy, new_status, current_price, pnl, new_bal)

    print("🏁 SCAN COMPLETE.")

if __name__ == "__main__":
    # No loops, no arguments. Just run once and die.
    try:
        run_watchdog()
    except Exception as e:
        print(f"   ❌ Watchdog Error: {e}")