import sqlite3
import os

db_path = "product_management.db"
print(f"Checking DB: {db_path}")

if not os.path.exists(db_path):
    print("DB File NOT FOUND!")
    exit(1)

try:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM orders")
    print(f"Total Orders: {cur.fetchone()[0]}")
    
    cur.execute("SELECT id, order_name, final_due FROM orders WHERE final_due IS NOT NULL LIMIT 5")
    rows = cur.fetchall()
    print(f"Sample Valid Dates: {len(rows)}")
    for r in rows:
        print(f"ID: {r[0]}, Name: {r[1]}, Date: {r[2]}")
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
