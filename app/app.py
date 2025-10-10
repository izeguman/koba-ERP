# 데이터베이스 수동 초기화 스크립트
# 문제가 계속되면 이 코드를 실행해서 확인해보세요

from app.db import get_conn, SCHEMA_SQL


def init_database():
    """데이터베이스를 강제로 초기화합니다."""
    try:
        conn = get_conn()
        cur = conn.cursor()

        # 기존 테이블 삭제 (주의!)
        print("기존 테이블 삭제 중...")
        cur.execute("DROP TABLE IF EXISTS purchase_order_links")
        cur.execute("DROP TABLE IF EXISTS purchases")
        cur.execute("DROP TABLE IF EXISTS orders")
        cur.execute("DROP VIEW IF EXISTS order_amounts")
        cur.execute("DROP VIEW IF EXISTS purchase_amounts")

        # 스키마 다시 생성
        print("새 스키마 생성 중...")
        conn.executescript(SCHEMA_SQL)
        conn.commit()

        # 테이블 생성 확인
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cur.fetchall()
        print(f"생성된 테이블: {[table[0] for table in tables]}")

        # orders 테이블 구조 확인
        cur.execute("PRAGMA table_info(orders)")
        columns = cur.fetchall()
        print(f"orders 테이블 컬럼: {[col[1] for col in columns]}")

        conn.close()
        print("데이터베이스 초기화 완료!")

    except Exception as e:
        print(f"초기화 실패: {e}")


if __name__ == "__main__":
    init_database()