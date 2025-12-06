
import sqlite3
import os
import sys
from pathlib import Path

def get_db_path():
    # Try to find the DB path as in the app
    onedrive_paths = [
        os.environ.get("KOBATECH_DB_DIR"),
        os.environ.get("OneDrive"),
        os.environ.get("OneDriveConsumer"),
        os.environ.get("OneDriveCommercial"),
    ]
    
    base_path = None
    for path in onedrive_paths:
        if path and os.path.exists(path):
            if "KOBATECH_DB" in path:
                return str(Path(path) / "production.db")
            base_path = Path(path)
            break
            
    if base_path is None:
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            potential_path = Path(user_profile) / "OneDrive"
            if potential_path.exists():
                base_path = potential_path
                
    if base_path is None:
        return str(Path.home() / "OneDrive" / "KOBATECH_DB" / "production.db")
        
    return str(base_path / "KOBATECH_DB" / "production.db")

db_path = get_db_path()
print(f"DB Path: {db_path}")

if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT status FROM orders")
        statuses = cursor.fetchall()
        print("Distinct Statuses in Orders:")
        for s in statuses:
            print(f"'{s[0]}'")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
else:
    print("DB not found")
