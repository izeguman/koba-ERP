
import sqlite3
import os

db_path = r'c:\Users\kobat\OneDrive\Product_Management_System\database.db'

def inspect_recall_products():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    serials = ('KT026', 'KT022', 'KT038', 'KT040', 'KT053', 'KT065', 'KT067')
    part_no = 'B10000850490'

    print(f"--- Inspecting products for {part_no} ---")
    for sn in serials:
        cur.execute("SELECT id, serial_no, delivery_id FROM products WHERE part_no = ? AND serial_no = ?", (part_no, sn))
        row = cur.fetchone()
        if row:
            p_id, serial, d_id = row
            # 리콜 아이템 상태도 확인
            cur.execute("SELECT item_status FROM recall_items WHERE product_id = ? ORDER BY id DESC LIMIT 1", (p_id,))
            recall_row = cur.fetchone()
            recall_status = recall_row[0] if recall_row else "None"
            print(f"S/N: {serial} | ID: {p_id} | delivery_id: {d_id} | recall_status: {recall_status}")
        else:
            print(f"S/N: {sn} | Not found in products table")

    conn.close()

if __name__ == "__main__":
    inspect_recall_products()
