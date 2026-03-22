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
        guess = home / "OneDrive"
        if not guess.exists():
             guess = home
        db_path = guess / "KOBATECH_DB" / "production.db"
    return sqlite3.connect(str(db_path))

def patch_data():
    conn = get_conn()
    cur = conn.cursor()
    
    order_no = '4502648051'
    print(f"--- Patching Order: {order_no} ---")
    
    cur.execute("SELECT id FROM orders WHERE order_no = ?", (order_no,))
    row = cur.fetchone()
    if not row:
        print("Order not found!")
        return
    
    order_id = row[0]
    
    cur.execute("SELECT id, product_name FROM order_items WHERE order_id = ?", (order_id,))
    items = cur.fetchall()
    
    for item_id, product_name in items:
        cur.execute("SELECT id, new_schedule, old_schedule FROM shipment_date_changes WHERE order_item_id = ?", (item_id,))
        changes = cur.fetchall()
        
        for c in changes:
            cid, new_schedule, old_schedule = c
            updated = False
            new_s = new_schedule
            old_s = old_schedule
            
            if "媛?" in new_schedule:
                print(f"  [ID {cid}] Fixing NEW: {new_schedule}")
                new_s = new_schedule.replace("媛?", "개")
                updated = True
                
            if "媛?" in old_schedule:
                print(f"  [ID {cid}] Fixing OLD: {old_schedule}")
                old_s = old_schedule.replace("媛?", "개")
                updated = True
            
            if updated:
                cur.execute("UPDATE shipment_date_changes SET new_schedule = ?, old_schedule = ? WHERE id = ?", (new_s, old_s, cid))
                print(f"  -> Updated ID {cid}")

    conn.commit()
    conn.close()
    print("Patch complete.")

if __name__ == "__main__":
    patch_data()
