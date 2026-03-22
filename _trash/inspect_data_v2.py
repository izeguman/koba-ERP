import sqlite3
import os
import sys
from pathlib import Path

# encoding setup for windows console
sys.stdout.reconfigure(encoding='utf-8')

def get_conn():
    # User home dir
    home = Path.home()
    db_path = home / "OneDrive" / "KOBATECH_DB" / "production.db"
    if not db_path.exists():
        print(f"DB not found at {db_path}")
        # Try default onedrive path logic just in case
        guess = home / "OneDrive"
        if not guess.exists():
             guess = home
        db_path = guess / "KOBATECH_DB" / "production.db"
    
    print(f"Connecting to: {db_path}")
    return sqlite3.connect(str(db_path))

def check_data():
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        order_no = '4502648051'
        print(f"--- Inspecting Order: {order_no} ---")
        
        cur.execute("SELECT id FROM orders WHERE order_no = ?", (order_no,))
        row = cur.fetchone()
        if not row:
            print("Order not found!")
            return
        
        order_id = row[0]
        print(f"Order ID: {order_id}")
        
        cur.execute("SELECT id, product_name FROM order_items WHERE order_id = ?", (order_id,))
        items = cur.fetchall()
        
        for item_id, product_name in items:
            print(f"\nItem ID: {item_id}, Product: {product_name}")
            cur.execute("SELECT id, change_request_date, old_schedule, new_schedule, reason FROM shipment_date_changes WHERE order_item_id = ?", (item_id,))
            changes = cur.fetchall()
            for c in changes:
                cid, date, old, new, reason = c
                print(f"  Change ID: {cid}")
                print(f"    Date: {date}")
                print(f"    Old: {old}")
                print(f"    New: {repr(new)}") # Use repr to see hidden chars
                print(f"    Reason: {reason}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_data()
