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

print(f"Connecting to: {DB_PATH}")

try:
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute('SELECT item_code, unit_price_cents, currency FROM purchase_items LIMIT 5')
    print('Purchase Items (unit_price_cents):', cursor.fetchall())
    
    cursor.execute('SELECT item_code, unit_price_jpy FROM product_master LIMIT 5')
    print('Product Master (unit_price_jpy):', cursor.fetchall())
    
    conn.close()
except Exception as e:
    print(e)
