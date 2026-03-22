import sqlite3
import os
from pathlib import Path

def _default_onedrive() -> Path:
    home = Path.home()
    guess = home / "OneDrive"
    return guess if guess.exists() else home

DB_DIR = os.environ.get("KOBATECH_DB_DIR") or str(_default_onedrive() / "KOBATECH_DB")
DB_NAME = os.environ.get("KOBATECH_DB_NAME", "production.db")
DB_PATH = Path(DB_DIR) / DB_NAME

print(f"Target DB Path: {DB_PATH}")

if not DB_PATH.exists():
    print(f"Error: {DB_PATH} not found.")
    exit(1)

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

try:
    # 1. 대상 제품 리스트 확인 (delivery_id가 NULL인데 delivery_items에는 있는 수리품/재고들)
    # 리콜 정보는 고려하지 않고, 순수하게 products와 delivery_items의 불일치를 찾아 복구합니다.
    query_target = """
        SELECT p.id, p.serial_no, p.delivery_id
        FROM products p
        WHERE p.delivery_id IS NULL
        AND EXISTS (SELECT 1 FROM delivery_items WHERE serial_no = p.serial_no)
    """
    cursor.execute(query_target)
    targets = cursor.fetchall()
    
    print(f"Found {len(targets)} products with missing delivery_id but has delivery history.")
    
    count = 0
    for tid, sn, cur_did in targets:
        # 각 제품별로 가장 최근의 delivery_id를 찾음
        cursor.execute("""
            SELECT di.delivery_id, d.invoice_no, d.ship_datetime
            FROM delivery_items di
            JOIN deliveries d ON di.delivery_id = d.id
            WHERE di.serial_no = ?
            ORDER BY d.ship_datetime DESC, d.id DESC LIMIT 1
        """, (sn,))
        row = cursor.fetchone()
        
        if row:
            best_did = row[0]
            invoice = row[1]
            dt = row[2]
            print(f"  Restoring SN: {sn} (ID:{tid}) -> DeliveryID: {best_did} (Invoice: {invoice}, Date: {dt})")
            cursor.execute("UPDATE products SET delivery_id = ? WHERE id = ?", (best_did, tid))
            count += 1
            
    conn.commit()
    print(f"\nSuccessfully restored {count} products' delivery_id.")

except Exception as e:
    print(f"Error during recovery: {e}")
    conn.rollback()
finally:
    conn.close()
