# migrate_purchases_table.py
# purchases 테이블에 actual_amount 컬럼 추가

from app.db import get_conn


def migrate():
    """purchases 테이블에 actual_amount 컬럼 추가"""
    try:
        conn = get_conn()
        cur = conn.cursor()

        # actual_amount 컬럼이 이미 있는지 확인
        cur.execute("PRAGMA table_info(purchases)")
        columns = [col[1] for col in cur.fetchall()]

        if 'actual_amount' not in columns:
            print("purchases 테이블에 actual_amount 컬럼 추가 중...")
            cur.execute("""
                ALTER TABLE purchases 
                ADD COLUMN actual_amount INTEGER DEFAULT 0
            """)
            conn.commit()
            print("✅ actual_amount 컬럼 추가 완료!")
        else:
            print("⚠️ actual_amount 컬럼이 이미 존재합니다.")

        # 확인
        cur.execute("PRAGMA table_info(purchases)")
        columns = cur.fetchall()
        print("\n현재 purchases 테이블 구조:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")

        conn.close()
        print("\n✅ 마이그레이션 완료!")

    except Exception as e:
        print(f"❌ 마이그레이션 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    migrate()