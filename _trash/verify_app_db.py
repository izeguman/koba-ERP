import sys
import os

# Adjust path
sys.path.append(os.getcwd())

from app.db import DB_PATH
print(f"Computed DB_PATH: {DB_PATH}")
print(f"Exists: {DB_PATH.exists()}")
if DB_PATH.exists():
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    try:
        cur.execute("SELECT count(*) FROM orders")
        print(f"Rows in 'orders': {cur.fetchone()[0]}")
    except Exception as e:
        print(f"Error reading 'orders': {e}")
    conn.close()
