# add_serial_column.py
from app.db import get_conn


def add_serial_column():
    """delivery_items 테이블에 serial_no, manufacture_code 컬럼 추가"""
    try:
        conn = get_conn()
        cur = conn.cursor()

        # 컬럼 존재 여부 확인
        cur.execute("PRAGMA table_info(delivery_items)")
        columns = [col[1] for col in cur.fetchall()]

        # serial_no 컬럼 추가
        if 'serial_no' not in columns:
            print("serial_no 컬럼 추가 중...")
            cur.execute("ALTER TABLE delivery_items ADD COLUMN serial_no TEXT")
            print("✓ serial_no 컬럼 추가 완료")
        else:
            print("serial_no 컬럼이 이미 존재합니다.")

        # manufacture_code 컬럼 추가
        if 'manufacture_code' not in columns:
            print("manufacture_code 컬럼 추가 중...")
            cur.execute("ALTER TABLE delivery_items ADD COLUMN manufacture_code TEXT")
            print("✓ manufacture_code 컬럼 추가 완료")
        else:
            print("manufacture_code 컬럼이 이미 존재합니다.")

        conn.commit()

        # 인덱스 생성
        print("인덱스 생성 중...")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_delivery_items_serial_code 
            ON delivery_items(serial_no, manufacture_code)
        """)
        conn.commit()
        print("✓ 인덱스 생성 완료")

        conn.close()
        print("\n모든 작업이 완료되었습니다!")

    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    add_serial_column()