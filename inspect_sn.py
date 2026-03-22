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

sn = 'KT022'
print(f"\n--- Checking SN: {sn} ---")

# 1. products 테이블에서 정보 확인
cursor.execute("SELECT id, serial_no, part_no, delivery_id FROM products WHERE serial_no = ?", (sn,))
product = cursor.fetchone()
print(f"Product info from 'products' table: {product}")

if product:
    p_id = product[0]
    # 2. delivery_items 테이블에서 해당 제품의 납품 내역 확인
    cursor.execute("""
        SELECT di.id, di.delivery_id, d.invoice_no, d.ship_datetime, d.invoice_done
        FROM delivery_items di
        JOIN deliveries d ON di.delivery_id = d.id
        WHERE di.serial_no = ?
        ORDER BY d.ship_datetime DESC
    """, (sn,))
    deliveries = cursor.fetchall()
    print("\nDeliveries associated with this SN:")
    if not deliveries:
        print("No delivery history found in delivery_items.")
    for d in deliveries:
        print(f"  ItemID: {d[0]}, DeliveryID: {d[1]}, Invoice: {d[2]}, Date: {d[3]}, Done: {d[4]}")

    # 3. recall_items 테이블에서도 확인
    cursor.execute("""
        SELECT ri.id, ri.recall_case_id, rc.case_no, ri.item_status
        FROM recall_items ri
        JOIN recall_cases rc ON ri.recall_case_id = rc.id
        WHERE ri.product_id = ?
    """, (p_id,))
    recalls = cursor.fetchall()
    print("\nRecall history (recall_items + recall_cases) for this product:")
    if not recalls:
        print("No recall history found.")
    for r in recalls:
        print(f"  RecallItemID: {r[0]}, CaseID: {r[1]}, CaseNo: {r[2]}, ItemStatus: {r[3]}")

conn.close()
