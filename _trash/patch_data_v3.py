import sqlite3
import os
import sys
from pathlib import Path

# encoding setup for windows console
sys.stdout.reconfigure(encoding='utf-8')

def get_conn():
    # User home dir
    home = Path.home()
    db_path = home / "OneDrive" / "KOBATECH_DB" / "production.db"
    if not db_path.exists():
        guess = home / "OneDrive"
        if not guess.exists():
             guess = home
        db_path = guess / "KOBATECH_DB" / "production.db"
    return sqlite3.connect(str(db_path))

def patch_data():
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("SELECT id, new_schedule FROM shipment_date_changes WHERE id = 62")
    row = cur.fetchone()
    
    if row:
        cid, new_schedule = row
        print(f"Current: {new_schedule}")
        
        if new_schedule.endswith("개"):
             new_s = new_schedule + ")"
             print(f"Fixing to: {new_s}")
             cur.execute("UPDATE shipment_date_changes SET new_schedule = ? WHERE id = ?", (new_s, cid))
             print("Update executed.")
        else:
            print("No fix needed (doesn't end with '개').")
            
    conn.commit()
    conn.close()
    print("Patch V3 complete.")

if __name__ == "__main__":
    patch_data()
