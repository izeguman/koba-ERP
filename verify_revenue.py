import os
import sys
import sqlite3
from datetime import datetime

# Set test database name BEFORE importing app.db
os.environ["KOBATECH_DB_NAME"] = "test_revenue.db"

from app.db import (
    get_conn, 
    get_yearly_financials, 
    get_model_profitability,
    SCHEMA_SQL
)

def verify_revenue():
    print("Starting Revenue Verification...")
    conn = get_conn()
    cursor = conn.cursor()

    try:
        # 1. Create Dummy Product Master
        item_code = "TEST-REV-001"
        cursor.execute("DELETE FROM product_master WHERE item_code = ?", (item_code,))
        cursor.execute("""
            INSERT INTO product_master (item_code, product_name, unit_price_jpy, purchase_price_krw)
            VALUES (?, 'Revenue Test Product', 10000, 50000)
        """, (item_code,))
        
        # 2. Create Dummy Order
        order_no = "TEST-ORD-001"
        cursor.execute("DELETE FROM orders WHERE order_no = ?", (order_no,))
        cursor.execute("""
            INSERT INTO orders (order_no, order_dt, invoice_done)
            VALUES (?, datetime('now'), 0)
        """, (order_no,))
        order_id = cursor.lastrowid
        
        # 3. Create Dummy Order Item (Qty: 10, Price: 10000 JPY)
        cursor.execute("""
            INSERT INTO order_items (order_id, item_code, product_name, qty, unit_price_cents, currency)
            VALUES (?, ?, 'Revenue Test Product', 10, 1000000, 'JPY')
        """, (order_id, item_code))
        
        # 4. Create Dummy Delivery
        invoice_no = "TEST-INV-001"
        cursor.execute("DELETE FROM deliveries WHERE invoice_no = ?", (invoice_no,))
        # Ship date is today
        cursor.execute("""
            INSERT INTO deliveries (invoice_no, ship_datetime, invoice_done)
            VALUES (?, datetime('now'), 1)
        """, (invoice_no,))
        delivery_id = cursor.lastrowid
        
        # 5. Link Delivery Item to Order Item
        # Delivery Item Qty: 5 (Partial delivery)
        cursor.execute("""
            INSERT INTO delivery_items (delivery_id, item_code, product_name, qty, order_id)
            VALUES (?, ?, 'Revenue Test Product', 5, ?)
        """, (delivery_id, item_code, order_id))
        
        conn.commit()
        
        # 6. Run Analysis
        print("Running get_yearly_financials...")
        current_year = datetime.now().year
        financials = get_yearly_financials('year', current_year)
        
        print(f"Financials for {current_year}: {financials}")
        
        # Expected Calculation:
        # Qty: 5
        # Unit Price: 10000 JPY -> 1000000 cents
        # Exchange Rate: Default 900 (if not set)
        # Revenue = (5 * 1000000 / 100.0) * (900.0 / 100.0) = 50000 * 9 = 450,000 KRW
        
        # Cost:
        # Purchase Price: 50000 KRW
        # Cost = 5 * (50000 / 100.0) = 5 * 500 = 2500 KRW ??? 
        # Wait, purchase_price_krw in DB is usually integer KRW.
        # In the code: (COALESCE(pm.purchase_price_krw, 0) / 100.0)
        # If purchase_price_krw is 50000 (representing 50,000 KRW), then dividing by 100 gives 500.
        # This implies purchase_price_krw in DB is stored as cents? Or the logic assumes it is?
        # Let's check the schema or assumption.
        # In product_master, purchase_price_krw INTEGER DEFAULT 0.
        # Usually KRW doesn't have cents.
        # If the code divides by 100, it assumes the DB value is x100.
        # Let's assume standard behavior in this system is x100 for currency fields if they are 'cents'.
        # But `purchase_price_krw` name doesn't say 'cents'.
        # However, `unit_price_cents` in order_items definitely says cents.
        # Let's check `get_yearly_financials` code again.
        # `sv.qty * (COALESCE(pm.purchase_price_krw, 0) / 100.0)`
        # If I put 50000 in DB, result is 2500.
        # If I want 250,000 cost, I should put 5000000 in DB?
        # Or maybe the code is wrong to divide by 100 for KRW?
        # But `unit_price_cents` is JPY cents.
        
        # Let's check the result first.
        
        target_data = next((x for x in financials if str(x['year']) == str(current_year)), None)
        
        if target_data:
            rev = target_data['revenue']
            cost = target_data['cost']
            qty = target_data['production_qty']
            
            print(f"Result -> Revenue: {rev}, Cost: {cost}, Qty: {qty}")
            
            if qty == 5:
                print("Quantity matches (5)")
            else:
                print(f"Quantity mismatch (Expected 5, Got {qty})")
                
            # We will verify the magnitude of revenue/cost to deduce the unit convention
            
    except Exception as e:
        print(f"Verification Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if 'cursor' in locals():
            cursor.execute("DELETE FROM delivery_items WHERE delivery_id = ?", (delivery_id,))
            cursor.execute("DELETE FROM deliveries WHERE id = ?", (delivery_id,))
            cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
            cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
            cursor.execute("DELETE FROM product_master WHERE item_code = ?", (item_code,))
            conn.commit()
            conn.close()

if __name__ == "__main__":
    verify_revenue()
