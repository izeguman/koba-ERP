
import sqlite3
import os
from pathlib import Path

def get_conn():
    # Attempt to locate DB
    import os
    # Check environment variable first
    db_path = os.environ.get("KOBATECH_DB_PATH")
    if db_path and os.path.exists(db_path):
        return sqlite3.connect(db_path)
        
    # Check relative path
    rel_path = Path("production.db")
    if rel_path.exists():
         return sqlite3.connect(str(rel_path.absolute()))
         
    # Check default OneDrive paths
    home = Path.home()
    candidates = [
        home / "OneDrive" / "Product_Management_System" / "production.db",
        home / "OneDrive" / "KOBATECH_DB" / "production.db",
        Path("C:/Users/kobat/OneDrive/Product_Management_System/production.db")
    ]
    
    for path in candidates:
        if path.exists():
            print(f"Using DB at: {path}")
            return sqlite3.connect(str(path))
            
    print("DB not found.")
    return None

def debug_products(item_code):
    conn = get_conn()
    if not conn:
        return

    cur = conn.cursor()
    print(f"--- Debugging Products with part_no = '{item_code}' ---")
    
    # Check if products exist
    cur.execute("SELECT id, serial_no, delivery_id, consumed_by_product_id, purchase_id FROM products WHERE part_no = ?", (item_code,))
    rows = cur.fetchall()
    
    if not rows:
        print("No products found with this part_no.")
        # Check if maybe whitespace issue
        cur.execute("SELECT part_no FROM products WHERE part_no LIKE ?", (f"%{item_code}%",))
        similar = cur.fetchall()
        print(f"Similar part_nos found: {similar}")
    else:
        for row in rows:
            pid, serial, delivery, consumed, purchase = row
            print(f"ID: {pid}, S/N: {serial}, DeliveryID: {delivery}, ConsumedBy: {consumed}, PurchaseID: {purchase}")

    conn.close()

    # Check product_master
    conn = get_conn()
    cur = conn.cursor()
    print(f"\n--- Debugging Product Master with item_code = '{item_code}' ---")
    cur.execute("SELECT id, rev, item_type, created_at, is_active, product_name FROM product_master WHERE item_code = ?", (item_code,))
    rows = cur.fetchall()
    if not rows:
        print("No product_master entries found.")
    else:
        for row in rows:
            print(f"ID: {row[0]}, Rev: {row[1]}, Type: {row[2]}, Created: {row[3]}, Active: {row[4]}, Name: {row[5]}")
    conn.close()

if __name__ == "__main__":
    print("Starting debug script...", flush=True)
    try:
        debug_products("B10000852323")
    except Exception as e:
        print(f"CRITICAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
    print("Finished debug script.", flush=True)
