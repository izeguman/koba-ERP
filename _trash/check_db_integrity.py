import sys
import os
import sqlite3

# Adjust path to find app module
sys.path.append(os.getcwd())

try:
    from app.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    
    print("Checking 'orders' table...")
    cur.execute("SELECT count(*) FROM orders")
    total = cur.fetchone()[0]
    print(f"Total rows: {total}")
    
    cur.execute("SELECT count(*) FROM orders WHERE final_due IS NOT NULL AND final_due != ''")
    valid_dates = cur.fetchone()[0]
    print(f"Rows with valid final_due: {valid_dates}")
    
    cur.execute("SELECT id, order_name, final_due FROM orders LIMIT 5")
    print("Sample Data:")
    for r in cur.fetchall():
        print(r)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
    # Fallback if import fails
    try:
        db_path = "product_management.db"
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM orders")
            print(f"Fallback Total: {cur.fetchone()[0]}")
            conn.close()
    except:
        pass
