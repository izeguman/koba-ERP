# migrate_orders_structure.py
# 주문 테이블을 헤더-상세 구조로 변경하는 마이그레이션 스크립트

import sqlite3
from pathlib import Path
from datetime import datetime

db_path = Path.home() / "OneDrive" / "KOBATECH_DB" / "production.db"

print("=" * 80)
print("주문 테이블 구조 변경 마이그레이션")
print("=" * 80)
print(f"데이터베이스: {db_path}")
print()

# 백업 파일 생성
backup_path = db_path.parent / f"production_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
print(f"1. 백업 생성 중: {backup_path}")

import shutil

shutil.copy2(db_path, backup_path)
print("   ✓ 백업 완료")
print()

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

try:
    print("2. 기존 데이터 분석 중...")

    # 기존 orders 테이블 데이터 조회
    cur.execute("""
        SELECT 
            id, customer_id, order_no, recv_dt, order_dt,
            item_code, rev, order_desc, qty,
            req_due, final_due, product_info,
            unit_price_cents, currency,
            oa_sent, invoice_done, status
        FROM orders
        ORDER BY order_no, id
    """)

    old_orders = cur.fetchall()
    print(f"   총 {len(old_orders)}개의 주문 레코드 발견")

    # 주문번호별 그룹핑 분석
    order_groups = {}
    for row in old_orders:
        order_no = row[2]
        if order_no not in order_groups:
            order_groups[order_no] = []
        order_groups[order_no].append(row)

    print(f"   고유 주문번호: {len(order_groups)}개")
    multi_item_orders = [k for k, v in order_groups.items() if len(v) > 1]
    if multi_item_orders:
        print(f"   복수 품목 주문: {len(multi_item_orders)}개")
        for order_no in multi_item_orders[:3]:
            print(f"     - {order_no}: {len(order_groups[order_no])}개 품목")
    print()

    print("3. 기존 테이블 백업...")
    cur.execute("DROP TABLE IF EXISTS orders_old")
    cur.execute("ALTER TABLE orders RENAME TO orders_old")
    print("   ✓ orders → orders_old")
    print()

    print("4. 새 테이블 구조 생성 중...")

    # 주문 헤더 테이블
    cur.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            customer_id INTEGER,
            recv_dt TEXT,
            order_dt TEXT,
            req_due TEXT,
            final_due TEXT,
            oa_sent INTEGER DEFAULT 0,
            invoice_done INTEGER DEFAULT 0,
            status TEXT DEFAULT '계획',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    print("   ✓ orders (헤더) 테이블 생성")

    # 주문 상세 테이블
    cur.execute("""
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            item_code TEXT,
            rev TEXT,
            product_name TEXT NOT NULL,
            qty INTEGER NOT NULL,
            unit_price_cents INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'JPY',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
    """)
    print("   ✓ order_items (상세) 테이블 생성")

    # 기존 인덱스 삭제 (있을 경우)
    indexes_to_drop = [
        'idx_orders_order_no', 'idx_orders_final_due', 'idx_orders_req_due',
        'idx_orders_invoice_done', 'idx_orders_item_code',
        'idx_order_items_order_id', 'idx_order_items_item_code'
    ]
    for idx in indexes_to_drop:
        try:
            cur.execute(f"DROP INDEX IF EXISTS {idx}")
        except:
            pass

    # 인덱스 생성
    cur.execute("CREATE INDEX idx_orders_order_no ON orders(order_no)")
    cur.execute("CREATE INDEX idx_orders_final_due ON orders(final_due)")
    cur.execute("CREATE INDEX idx_orders_req_due ON orders(req_due)")
    cur.execute("CREATE INDEX idx_orders_invoice_done ON orders(invoice_done)")
    cur.execute("CREATE INDEX idx_order_items_order_id ON order_items(order_id)")
    cur.execute("CREATE INDEX idx_order_items_item_code ON order_items(item_code)")
    print("   ✓ 인덱스 생성")
    print()

    print("5. 데이터 마이그레이션 중...")

    migrated_orders = 0
    migrated_items = 0

    for order_no, items in order_groups.items():
        # 첫 번째 레코드에서 헤더 정보 추출
        first_item = items[0]

        # orders 헤더 삽입
        cur.execute("""
            INSERT INTO orders (
                order_no, customer_id, recv_dt, order_dt,
                req_due, final_due, oa_sent, invoice_done, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_no,
            first_item[1],  # customer_id
            first_item[3],  # recv_dt
            first_item[4],  # order_dt
            first_item[9],  # req_due
            first_item[10],  # final_due
            first_item[14],  # oa_sent
            first_item[15],  # invoice_done
            first_item[16]  # status
        ))

        order_id = cur.lastrowid
        migrated_orders += 1

        # order_items 상세 삽입
        for item in items:
            cur.execute("""
                INSERT INTO order_items (
                    order_id, item_code, rev, product_name,
                    qty, unit_price_cents, currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                item[5],  # item_code
                item[6],  # rev
                item[7],  # order_desc
                item[8],  # qty
                item[12],  # unit_price_cents
                item[13]  # currency
            ))
            migrated_items += 1

    print(f"   ✓ {migrated_orders}개 주문 헤더 마이그레이션")
    print(f"   ✓ {migrated_items}개 주문 품목 마이그레이션")
    print()

    print("6. VIEW 재생성 중...")

    # 기존 VIEW 삭제
    cur.execute("DROP VIEW IF EXISTS order_amounts")

    # 새 VIEW 생성 (주문 전체 금액)
    cur.execute("""
        CREATE VIEW order_amounts AS
        SELECT
            o.id AS order_id,
            o.order_no,
            SUM(oi.qty * oi.unit_price_cents) AS total_cents,
            oi.currency
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        GROUP BY o.id, o.order_no, oi.currency
    """)
    print("   ✓ order_amounts VIEW 재생성")
    print()

    print("7. 데이터 검증 중...")

    cur.execute("SELECT COUNT(*) FROM orders")
    header_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM order_items")
    item_count = cur.fetchone()[0]

    print(f"   주문 헤더: {header_count}개")
    print(f"   주문 품목: {item_count}개")

    if header_count == migrated_orders and item_count == migrated_items:
        print("   ✓ 데이터 검증 성공")
    else:
        raise Exception("데이터 검증 실패!")

    print()

    # 커밋
    conn.commit()

    print("=" * 80)
    print("마이그레이션 완료!")
    print("=" * 80)
    print()
    print("다음 단계:")
    print("1. 프로그램 코드 업데이트 필요")
    print("2. 테스트 후 문제없으면 orders_old 테이블 삭제 가능")
    print(f"3. 백업 파일 보관: {backup_path}")
    print()

except Exception as e:
    print()
    print("=" * 80)
    print("오류 발생!")
    print("=" * 80)
    print(f"오류 내용: {e}")
    print()
    print("롤백 중...")
    conn.rollback()
    print("백업에서 복구하려면:")
    print(f"  1. {db_path} 삭제")
    print(f"  2. {backup_path} 를 {db_path}로 이름 변경")

finally:
    conn.close()

print()
print("스크립트 종료")