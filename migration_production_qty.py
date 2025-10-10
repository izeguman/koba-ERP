# migration_production_qty.py
# 이 파일은 프로젝트 루트 폴더(Product_Management_System)에 저장하세요
# products 테이블에 production_qty 컬럼을 수동으로 추가하는 스크립트

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db import get_conn


def add_production_qty_column():
    """products 테이블에 production_qty 컬럼 추가"""
    try:
        conn = get_conn()
        cur = conn.cursor()

        # 현재 products 테이블 구조 확인
        cur.execute("PRAGMA table_info(products)")
        columns = cur.fetchall()
        column_names = [col[1] for col in columns]

        print("현재 products 테이블 컬럼들:")
        for col in columns:
            print(f"  {col[1]} {col[2]}")

        if 'production_qty' in column_names:
            print("production_qty 컬럼이 이미 존재합니다.")
        else:
            print("\nproduction_qty 컬럼을 추가합니다...")

            # production_qty 컬럼 추가 (기본값 1)
            cur.execute("ALTER TABLE products ADD COLUMN production_qty INTEGER DEFAULT 1")

            conn.commit()
            print("production_qty 컬럼 추가 완료!")

            # 확인
            cur.execute("PRAGMA table_info(products)")
            updated_columns = cur.fetchall()
            print("\n업데이트된 products 테이블 컬럼들:")
            for col in updated_columns:
                print(f"  {col[1]} {col[2]}")

        conn.close()

    except Exception as e:
        print(f"오류 발생: {e}")


if __name__ == "__main__":
    add_production_qty_column()