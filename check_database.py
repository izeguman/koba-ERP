# find_real_database.py
# 실제 사용 중인 데이터베이스를 찾고 확인합니다

import sys
import os

# app 모듈을 import할 수 있도록 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import DB_PATH, get_conn
import sqlite3


def find_and_check_database():
    """실제 사용 중인 데이터베이스를 찾고 상태를 확인합니다"""

    print("=" * 80)
    print("실제 데이터베이스 위치 확인")
    print("=" * 80)
    print(f"✅ 실제 데이터베이스 경로: {DB_PATH}")
    print(f"   파일 존재 여부: {DB_PATH.exists()}")

    if not DB_PATH.exists():
        print("\n❌ 데이터베이스 파일이 없습니다!")
        print("   프로그램을 한 번 실행하면 자동으로 생성됩니다.")
        return

    file_size = DB_PATH.stat().st_size
    print(f"   파일 크기: {file_size:,} bytes ({file_size / 1024:.2f} KB)")

    # 데이터베이스 연결
    try:
        conn = get_conn()
        cur = conn.cursor()

        print("\n" + "=" * 80)
        print("데이터베이스 테이블 목록")
        print("=" * 80)
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cur.fetchall()

        if not tables:
            print("  ⚠️  테이블이 없습니다!")
            conn.close()
            return

        for table in tables:
            print(f"  ✓ {table[0]}")

        table_names = [t[0] for t in tables]

        # deliveries 테이블 확인
        if 'deliveries' not in table_names:
            print("\n❌ 'deliveries' 테이블이 없습니다!")
            conn.close()
            return

        print("\n" + "=" * 80)
        print("deliveries 테이블 구조")
        print("=" * 80)
        cur.execute("PRAGMA table_info(deliveries)")
        columns = cur.fetchall()
        for col in columns:
            print(f"  {col[1]:25s} {col[2]:10s}")

        print("\n" + "=" * 80)
        print("납품 데이터 현황")
        print("=" * 80)
        cur.execute("SELECT COUNT(*) FROM deliveries")
        delivery_count = cur.fetchone()[0]
        print(f"  총 {delivery_count}개의 납품 데이터")

        if delivery_count == 0:
            print("  ⚠️  납품 데이터가 없습니다!")
            conn.close()
            return

        # 최근 납품 10개 조회
        print("\n" + "=" * 80)
        print("최근 납품 목록 (최신 10개)")
        print("=" * 80)
        cur.execute("""
            SELECT id, invoice_no, ship_datetime, 
                   order_id, purchase_id
            FROM deliveries 
            ORDER BY id DESC 
            LIMIT 10
        """)
        deliveries = cur.fetchall()

        for d in deliveries:
            delivery_id, invoice_no, ship_datetime, order_id, purchase_id = d
            print(
                f"  [{delivery_id:3d}] {invoice_no:20s} | {ship_datetime or 'N/A':20s} | order_id={order_id}, purchase_id={purchase_id}")

        # 첫 번째 납품으로 상세 확인
        test_delivery = deliveries[0]
        delivery_id = test_delivery[0]
        invoice_no = test_delivery[1]

        print("\n" + "=" * 80)
        print(f"납품 상세 분석 (invoice_no: {invoice_no})")
        print("=" * 80)

        # delivery_order_links 확인
        if 'delivery_order_links' in table_names:
            print("\n[delivery_order_links] 연결된 주문:")
            cur.execute("""
                SELECT dol.order_id, o.order_no
                FROM delivery_order_links dol
                LEFT JOIN orders o ON dol.order_id = o.id
                WHERE dol.delivery_id = ?
            """, (delivery_id,))
            order_links = cur.fetchall()
            if order_links:
                for link in order_links:
                    print(f"  → order_id={link[0]}, order_no={link[1]}")
            else:
                print("  (연결된 주문 없음)")
        else:
            print("\n⚠️  delivery_order_links 테이블이 없습니다!")

        # delivery_purchase_links 확인
        if 'delivery_purchase_links' in table_names:
            print("\n[delivery_purchase_links] 연결된 발주:")
            cur.execute("""
                SELECT dpl.purchase_id, p.purchase_no
                FROM delivery_purchase_links dpl
                LEFT JOIN purchases p ON dpl.purchase_id = p.id
                WHERE dpl.delivery_id = ?
            """, (delivery_id,))
            purchase_links = cur.fetchall()
            if purchase_links:
                for link in purchase_links:
                    print(f"  → purchase_id={link[0]}, purchase_no={link[1]}")
            else:
                print("  (연결된 발주 없음)")
        else:
            print("\n⚠️  delivery_purchase_links 테이블이 없습니다!")

        # delivery_items 확인
        print("\n[delivery_items] 납품 품목:")
        cur.execute("""
            SELECT id, item_code, serial_no, manufacture_code, product_name, qty
            FROM delivery_items
            WHERE delivery_id = ?
        """, (delivery_id,))
        items = cur.fetchall()
        if items:
            print(f"  총 {len(items)}개 품목:")
            for item in items:
                print(
                    f"    [{item[0]:3d}] {item[1] or 'N/A':15s} | S/N:{item[2] or 'N/A':15s} | {item[4]:30s} | qty={item[5]}")
        else:
            print("  (품목 없음)")

        # 문제 진단
        print("\n" + "=" * 80)
        print("문제 진단")
        print("=" * 80)

        old_order_id = test_delivery[3]
        old_purchase_id = test_delivery[4]

        problems = []

        if old_order_id or old_purchase_id:
            problems.append("⚠️  deliveries.order_id 또는 purchase_id에 값이 있습니다")
            problems.append("    → 구 방식(단일 연결)을 사용 중입니다")

        if 'delivery_order_links' not in table_names or 'delivery_purchase_links' not in table_names:
            problems.append("❌ delivery_order_links 또는 delivery_purchase_links 테이블이 없습니다")
            problems.append("    → 데이터베이스 스키마가 최신 버전이 아닙니다")
        else:
            if not order_links and not purchase_links:
                if old_order_id or old_purchase_id:
                    problems.append("⚠️  구 방식 데이터(deliveries.order_id/purchase_id)는 있지만")
                    problems.append("    신규 방식 데이터(링크 테이블)는 없습니다")
                    problems.append("    → 데이터 마이그레이션이 필요합니다!")

        if not items or len(items) == 0:
            problems.append("⚠️  delivery_items가 비어있습니다")

        if problems:
            for problem in problems:
                print(f"  {problem}")
        else:
            print("  ✅ 문제가 발견되지 않았습니다!")

        conn.close()

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    find_and_check_database()