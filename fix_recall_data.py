
import sqlite3
import os

db_path = r'c:\Users\kobat\OneDrive\Product_Management_System\database.db'

def fix_recall_products():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    serials = ('KT026', 'KT022', 'KT038', 'KT040', 'KT053', 'KT065', 'KT067')
    part_no = 'B10000850490'

    print(f"--- Fixing delivery_id for recalled products ({part_no}) ---")
    
    # 1. 먼저 상태 확인
    cur.execute(f"""
        SELECT p.id, p.serial_no, p.delivery_id, ri.item_status
        FROM products p
        JOIN recall_items ri ON p.id = ri.product_id
        WHERE p.part_no = ? AND p.serial_no IN {serials}
    """, (part_no,))
    
    rows = cur.fetchall()
    for row in rows:
        p_id, sn, d_id, status = row
        print(f"Current -> S/N: {sn}, delivery_id: {d_id}, Status: {status}")
        
        if d_id is not None:
            print(f"  >>> Updating {sn} delivery_id to NULL...")
            cur.execute("UPDATE products SET delivery_id = NULL WHERE id = ?", (p_id,))

    conn.commit()
    print("--- Fix Completed ---")
    conn.close()

if __name__ == "__main__":
    fix_recall_products()
