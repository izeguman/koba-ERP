import sqlite3
import os

DB_PATH = r"c:\Users\kobat\OneDrive\Product_Management_System\app\database.db"

def check_dates():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    print("--- Orders (First 10) ---")
    cur.execute("SELECT id, order_no, req_due, final_due FROM orders LIMIT 10")
    for row in cur.fetchall():
        print(f"ID: {row[0]}, OrderNo: {row[1]}, ReqDue (Initial?): {row[2]}, FinalDue: {row[3]}")

    conn.close()

if __name__ == "__main__":
    check_dates()
