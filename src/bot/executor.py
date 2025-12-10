from src.risk.calculator import calculate_position_size
from src.database import get_current_balance, update_balance, log_trade
from src.portfolio.manager import check_portfolio_health # Optional usage
from src.database import update_trade_status, update_balance, get_current_balance

def execute_trade(ticker, strategy_name, signal, price, atr, decision_reason, confidence):
    """
    Handles Risk Management, Wallet Check, and Execution Logging.
    Returns the Quantity traded (0 if failed).
    """
    # 1. Calculate Risk Params
    stop_loss = price - (2 * atr)
    target_price = price + (4 * atr)
    
    # 2. Position Sizing
    qty = calculate_position_size(price, stop_loss, risk_per_trade=0.02)
    
    # 3. Wallet Check
    # Ensure get_current_balance accepts strategy_name!
    balance = get_current_balance(strategy_name) 
    cost = qty * price
    
    if cost > balance:
        # Resize if insufficient funds
        if balance > 0 and price > 0:
            qty = int((balance * 0.99) / price)
            cost = qty * price
        else:
            qty = 0
            
    if qty > 0:
        # 4. Execute (Paper or Live)
        update_balance(-cost, strategy_name) # Ensure this accepts strategy_name
        
        trade_data = {
            "ticker": ticker,
            "signal": signal,
            "entry_price": price,
            "target_price": target_price,
            "stop_loss": stop_loss,
            "reasoning": decision_reason,
            "confidence": confidence,
            "strategy_name": strategy_name
        }
        
        log_trade(trade_data, qty)
        return qty
    
    return 0


def execute_exit(trade_id, ticker, strategy_name, quantity, entry_price, exit_price, status):
    """
    Handles the math and DB updates for closing a trade.
    Returns: (pnl, new_balance)
    """
    # 1. Calculate PnL
    revenue = exit_price * quantity
    pnl = (exit_price - entry_price) * quantity
    
    # 2. Refund the Strategy Wallet
    # (We add the full revenue back to the wallet)
    update_balance(revenue, strategy_name=strategy_name)
    
    # 3. Close Trade in DB
    update_trade_status(trade_id, status, exit_price, pnl)
    
    # 4. Get New Balance (for reporting)
    new_balance = get_current_balance(strategy_name)
    
    print(f"   ⚡ {strategy_name}: Closed {ticker} ({status}) PnL: {pnl:.2f}")
    
    return pnl, new_balance