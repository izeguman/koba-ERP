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

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

try:
    cursor.execute("SELECT id, serial_no FROM products")
    products = cursor.fetchall()
    
    count_to_null = 0
    count_to_valid = 0
    
    for p_id, sn in products:
        if not sn: continue
        
        # 1. 가장 최근의 리콜 접수일 조회
        cursor.execute("""
            SELECT MAX(receipt_date) FROM product_repairs WHERE product_id = ?
        """, (p_id,))
        last_recall_date = cursor.fetchone()[0]
        
        # 2. 가장 최근의 납품일 및 ID 조회
        cursor.execute("""
            SELECT di.delivery_id, MAX(d.ship_datetime)
            FROM delivery_items di
            JOIN deliveries d ON di.delivery_id = d.id
            WHERE di.serial_no = ?
            GROUP BY di.serial_no
        """, (sn,))
        row_del = cursor.fetchone()
        
        best_did = None
        if row_del:
            did, last_ship_date = row_del
            # 리콜 접수일이 없거나, 납품일이 리콜 접수일보다 늦은 경우에만 유효한 납품으로 인정
            if not last_recall_date or last_ship_date > last_recall_date:
                best_did = did
        
        # 3. 업데이트
        cursor.execute("SELECT delivery_id FROM products WHERE id = ?", (p_id,))
        curr_did = cursor.fetchone()[0]
        
        if curr_did != best_did:
            cursor.execute("UPDATE products SET delivery_id = ? WHERE id = ?", (best_did, p_id))
            if best_did is None:
                count_to_null += 1
            else:
                count_to_valid += 1
            
            if sn == 'KT022':
                print(f"  Fixed KT022: {curr_did} -> {best_did} (LastShip: {last_ship_date}, LastRecall: {last_recall_date})")

    conn.commit()
    print(f"\nFinal Synchronization Completed:")
    print(f"  - Set to NULL (Stock): {count_to_null} products")
    print(f"  - Set to Valid Delivery: {count_to_valid} products")

except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    conn.close()
