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

print("\n--- Rows from purchases (LIMIT 20) ---")
# 실제 UI에서 사용하는 쿼리와 유사하게 구성 (단순화)
query = """
    SELECT 
        p.id, 
        p.purchase_dt, 
        p.purchase_no, 
        p.status, 
        p.actual_amount,
        (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE purchase_id = p.id) as paid_amount
    FROM purchases p
    ORDER BY p.purchase_dt DESC
    LIMIT 20
"""
try:
    cursor.execute(query)
    rows = cursor.fetchall()
    for r in rows:
        print(r)
except Exception as e:
    print(f"Query Error: {e}")

conn.close()
