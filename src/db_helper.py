from sqlalchemy import text
import pandas as pd

def place_or_update_trade(engine, strategy_name, ticker, signal_qty, signal_price, target, stoploss):
    """
    Logs a trade into the database.
    - If Position is OPEN: Updates Quantity and calculates Weighted Average Entry Price.
    - If New: Inserts a new row (Fix: Now includes 'signal' column).
    """
    try:
        with engine.connect() as conn:
            # 1. CHECK FOR EXISTING OPEN POSITION
            query = text("""
                SELECT id, quantity, entry_price 
                FROM trades 
                WHERE ticker = :ticker 
                  AND strategy_name = :strat 
                  AND status = 'OPEN' 
                LIMIT 1
            """)
            existing = conn.execute(query, {"ticker": ticker, "strat": strategy_name}).fetchone()

            if existing:
                # --- UPDATE EXISTING POSITION (AVERAGING) ---
                trade_id = existing[0]
                old_qty = existing[1]
                old_price = existing[2]

                # Calculate New Weighted Average Price
                total_cost_old = old_qty * old_price
                total_cost_new = signal_qty * signal_price
                new_total_qty = old_qty + signal_qty
                
                if new_total_qty > 0:
                    new_avg_price = (total_cost_old + total_cost_new) / new_total_qty
                else:
                    new_avg_price = signal_price

                # Update Query
                update_query = text("""
                    UPDATE trades 
                    SET quantity = :new_qty, 
                        entry_price = :new_price,
                        target_price = :new_target,
                        stop_loss = :new_sl,
                        updated_at = NOW()
                    WHERE id = :trade_id
                """)
                
                conn.execute(update_query, {
                    "new_qty": new_total_qty,
                    "new_price": new_avg_price,
                    "new_target": target,
                    "new_sl": stoploss,
                    "trade_id": trade_id
                })
                conn.commit()
                print(f"🔄 [DB] MERGED {ticker}: {old_qty}@{old_price:.2f} + {signal_qty}@{signal_price:.2f} -> Avg: {new_avg_price:.2f}")

            else:
                # --- INSERT NEW POSITION (FIXED) ---
                # Added 'signal' column with value 'BUY'
                insert_query = text("""
                    INSERT INTO trades (strategy_name, ticker, quantity, entry_price, target_price, stop_loss, status, signal, entry_time)
                    VALUES (:strat, :ticker, :qty, :price, :target, :sl, 'OPEN', 'BUY', NOW())
                """)
                
                conn.execute(insert_query, {
                    "strat": strategy_name,
                    "ticker": ticker,
                    "qty": signal_qty,
                    "price": signal_price,
                    "target": target,
                    "sl": stoploss
                })
                conn.commit()
                print(f"✅ [DB] NEW TRADE: {ticker} | {signal_qty} qty @ {signal_price}")
                
    except Exception as e:
        print(f"❌ [DB Error] Could not save trade: {e}")