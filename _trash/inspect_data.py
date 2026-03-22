import sqlite3
import os

def get_conn():
    return sqlite3.connect("data.db")

def check_data():
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
            print(f"    New: {new}")
            print(f"    Reason: {reason}")

if __name__ == "__main__":
    check_data()
