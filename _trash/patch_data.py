import sqlite3
import os

def get_conn():
    return sqlite3.connect("data.db")

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
        print(f"Checking Item: {product_name} (ID: {item_id})")
        cur.execute("SELECT id, new_schedule FROM shipment_date_changes WHERE order_item_id = ?", (item_id,))
        changes = cur.fetchall()
        
        for c in changes:
            cid, new_schedule = c
            if "媛?" in new_schedule:
                print(f"  Found garbled data in Change ID {cid}: {new_schedule}")
                fixed_schedule = new_schedule.replace("媛?", "개")
                print(f"  -> Fixing to: {fixed_schedule}")
                
                cur.execute("UPDATE shipment_date_changes SET new_schedule = ? WHERE id = ?", (fixed_schedule, cid))
                print("  -> Update executed.")
            else:
                print(f"  Data seems OK (or not matching target): {new_schedule}")

    conn.commit()
    conn.close()
    print("Patch complete.")

if __name__ == "__main__":
    patch_data()
