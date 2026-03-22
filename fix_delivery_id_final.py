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
    # 모든 제품에 대해 가장 최신의 납품 내역을 찾아 delivery_id를 동기화
    cursor.execute("SELECT id, serial_no FROM products")
    products = cursor.fetchall()
    
    count = 0
    for p_id, sn in products:
        if not sn: continue
        
        # 가장 최근의 납품 ID 조회
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
            # 현재 delivery_id와 다른 경우에만 업데이트
            cursor.execute("SELECT delivery_id FROM products WHERE id = ?", (p_id,))
            curr_did = cursor.fetchone()[0]
            if curr_did != best_did:
                cursor.execute("UPDATE products SET delivery_id = ? WHERE id = ?", (best_did, p_id))
                count += 1
                if sn == 'KT022':
                    print(f"  Fixed KT022: {curr_did} -> {best_did}")

    conn.commit()
    print(f"\nSuccessfully synchronized {count} products' delivery_id with latest history.")

except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    conn.close()
