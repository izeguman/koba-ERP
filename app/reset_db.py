# reset_db.py
import os
from pathlib import Path

home = Path.home()
db_path = home / "OneDrive" / "KOBATECH_DB" / "production.db"
if db_path.exists():
    db_path.unlink()
    print("기존 데이터베이스 삭제 완료")