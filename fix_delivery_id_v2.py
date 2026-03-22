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
    # 1. '청구 완료(invoice_done=1)'된 납품에 묶여 있는 제품 조회
    # 리콜 중이거나 리콜 완료된 제품 중에서, 과거의 납품 완료 건에 묶여 있는 것들은 NULL로 풀어준다.
    # (이미 출고가 완료된 과거 제품이므로, 리콜 처리를 위해 다시 재고가 되어야 함)
    sql_cleanup = """
        UPDATE products 
        SET delivery_id = NULL
        WHERE delivery_id IN (SELECT id FROM deliveries WHERE invoice_done = 1)
        AND id IN (SELECT product_id FROM recall_items)
    """
    cursor.execute(sql_cleanup)
    cleanup_count = cursor.rowcount
    print(f"Cleaned up {cleanup_count} products (set delivery_id=NULL because their linked delivery was already completed).")

    # 2. 현재 작업 중인(invoice_done=0) 납품 건에 대해서는 상태를 유지해야 함.
    # (이미 아까 복구했으므로 특별히 건드릴 필요 없음)

    conn.commit()
    print("\nDatabase state cleanup completed.")

except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    conn.close()
