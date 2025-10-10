# cleanup_product_master.py
# 제품 마스터 데이터베이스 정리 스크립트

import sqlite3
from pathlib import Path

# 데이터베이스 경로
db_path = Path.home() / "OneDrive" / "KOBATECH_DB" / "production.db"

print("제품 마스터 데이터 정리 시작...")

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

try:
    # 1. 현재 product_master 테이블의 모든 데이터 조회
    print("\n현재 제품 마스터 데이터:")
    cur.execute("""
        SELECT id, item_code, rev, product_name, is_active 
        FROM product_master 
        ORDER BY item_code, rev
    """)

    for row in cur.fetchall():
        product_id, item_code, rev, product_name, is_active = row
        print(f"  ID: {product_id}, 품목: {item_code}, Rev: {rev}, 제품명: {product_name[:30]}..., 활성: {is_active}")

    # 2. B10000805055 Rev G 데이터 확인
    print("\n\nB10000805055 Rev G 데이터 확인:")
    cur.execute("""
        SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, is_active
        FROM product_master 
        WHERE item_code = 'B10000805055' AND rev = 'G'
    """)

    existing = cur.fetchone()
    if existing:
        print(f"  발견됨: ID={existing[0]}, Rev={existing[2]}, 활성={existing[6]}")

        # 3. 중복 데이터 완전 삭제 또는 비활성화
        print("\n선택하세요:")
        print("  1. 완전 삭제 (DELETE)")
        print("  2. 비활성화 (is_active = 0)")
        print("  3. 취소")

        choice = input("선택 (1/2/3): ")

        if choice == '1':
            cur.execute("""
                DELETE FROM product_master 
                WHERE item_code = 'B10000805055' AND rev = 'G'
            """)
            conn.commit()
            print("  ✓ B10000805055 Rev G 데이터가 완전 삭제되었습니다.")
        elif choice == '2':
            cur.execute("""
                UPDATE product_master 
                SET is_active = 0 
                WHERE item_code = 'B10000805055' AND rev = 'G'
            """)
            conn.commit()
            print("  ✓ B10000805055 Rev G 데이터가 비활성화되었습니다.")
        else:
            print("  취소되었습니다.")
    else:
        print("  B10000805055 Rev G 데이터가 없습니다.")

    # 4. 최종 활성 데이터 확인
    print("\n\n최종 활성 제품 마스터 데이터:")
    cur.execute("""
        SELECT id, item_code, rev, product_name 
        FROM product_master 
        WHERE is_active = 1
        ORDER BY item_code, rev
    """)

    for row in cur.fetchall():
        product_id, item_code, rev, product_name = row
        print(f"  ID: {product_id}, 품목: {item_code}, Rev: {rev}, 제품명: {product_name[:40]}...")

    print("\n정리 완료!")

except Exception as e:
    print(f"\n오류 발생: {e}")
    conn.rollback()
finally:
    conn.close()

print("\n프로그램을 재시작한 후 다시 시도해주세요.")