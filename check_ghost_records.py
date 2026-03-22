import sqlite3
import os
from pathlib import Path

def get_db_path():
    # 1. 환경 변수 확인
    db_dir = os.environ.get("KOBATECH_DB_DIR")
    if db_dir:
        return Path(db_dir) / "production.db"
    
    # 2. 기본 경로 (OneDrive) 확인
    home = Path.home()
    onedrive_path = home / "OneDrive" / "KOBATECH_DB" / "production.db"
    
    # 3. 사용자 프로필 기반 경로 확인 (시스템 환경변수 활용)
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        onedrive_path_2 = Path(user_profile) / "OneDrive" / "KOBATECH_DB" / "production.db"
        if onedrive_path_2.exists():
            return onedrive_path_2
            
    if onedrive_path.exists():
        return onedrive_path
        
    return None

def check_records():
    db_path = get_db_path()
    # 경로를 못 찾았을 경우, 하드코딩된 경로 시도 (사용자 정보 기반)
    if not db_path:
        db_path = Path(r"c:\Users\kobat\OneDrive\KOBATECH_DB\production.db")

    if not db_path.exists():
        print(f"Error: DB not found at {db_path}")
        return

    print(f"Connecting to database: {db_path}")
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # 최근 20개 발주 레코드 조회 (ID 역순)
        print("\n--- Recent 20 Purchases (ID DESC) ---")
        cur.execute("SELECT id, purchase_dt, purchase_no, status, actual_amount, created_at FROM purchases ORDER BY id DESC LIMIT 20")
        rows = cur.fetchall()
        
        print(f"{'ID':<5} | {'Date':<12} | {'No':<15} | {'Status':<6} | {'Amount':<10} | {'Created At'}")
        print("-" * 80)
        
        problematic_ids = []
        
        for row in rows:
            p_id = row['id']
            p_dt = row['purchase_dt']
            p_no = row['purchase_no']
            p_st = row['status']
            p_amt = row['actual_amount']
            p_created = row['created_at']
            
            p_dt_str = str(p_dt) if p_dt else "NULL"
            p_no_str = str(p_no) if p_no else "NULL"
            
            print(f"{p_id:<5} | {p_dt_str:<12} | {p_no_str:<15} | {p_st:<6} | {p_amt:<10} | {p_created}")
            
            # 문제가 의심되는 레코드 식별 (발주번호가 없거나 날짜가 없는 경우)
            if not p_no or not p_dt:
                problematic_ids.append(p_id)

        print("-" * 80)
        
        if problematic_ids:
            print(f"\n[WARNING] Found {len(problematic_ids)} potentially problematic records with IDs: {problematic_ids}")
        else:
            print("\n[INFO] No obviously broken records found in the recent 20 entries.")
            
        conn.close()
        
    except Exception as e:
        print(f"Error accessing database: {e}")

if __name__ == "__main__":
    check_records()
