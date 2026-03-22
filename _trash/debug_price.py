import sys
import os
sys.path.append(os.getcwd())
from app.db import get_conn

try:
    conn = get_conn()
    cur = conn.cursor()
    print("Checking product_master...")
    cur.execute("SELECT item_code, unit_price_jpy FROM product_master WHERE item_code = 'B10000850333'")
    print(f"Master: {cur.fetchall()}")
    print("Checking order_items...")
    cur.execute("SELECT item_code, unit_price_cents FROM order_items WHERE item_code = 'B10000850333'")
    print(f"OrderItems: {cur.fetchall()}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
