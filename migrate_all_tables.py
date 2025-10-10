# migrate_all_tables.py
# 주문, 발주, 납품 테이블을 모두 헤더-상세 구조로 변경

import sqlite3
from pathlib import Path
from datetime import datetime
import shutil

db_path = Path.home() / "OneDrive" / "KOBATECH_DB" / "production.db"

print("=" * 80)
print("전체 테이블 구조 변경 마이그레이션 (주문 + 발주 + 납품)")
print("=" * 80)
print(f"데이터베이스: {db_path}")
print()

# 백업
backup_path = db_path.parent / f"production_backup_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
print(f"1. 백업 생성 중: {backup_path}")
shutil.copy2(db_path, backup_path)
print("   ✓ 백업 완료")
print()

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

try:
    # ========================================
    # 1. 주문(Orders) 마이그레이션
    # ========================================
    print("2. 주문(Orders) 테이블 마이그레이션...")

    # 기존 데이터 조회
    cur.execute("SELECT * FROM orders")
    old_orders = cur.fetchall()
    print(f"   기존 주문: {len(old_orders)}개")

    # 주문번호별 그룹핑
    order_groups = {}
    for row in old_orders:
        order_id, customer_id, order_no, recv_dt, order_dt, item_code, rev, order_desc, qty, req_due, final_due, product_info, unit_price_cents, currency, oa_sent, invoice_done, status = row
        if order_no not in order_groups:
            order_groups[order_no] = []
        order_groups[order_no].append(row)

    # 테이블 백업 및 재생성
    cur.execute("DROP TABLE IF EXISTS orders_old")
    cur.execute("ALTER TABLE orders RENAME TO orders_old")

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

    # 인덱스 생성
    for idx in ['idx_orders_order_no', 'idx_orders_final_due', 'idx_orders_req_due', 'idx_orders_invoice_done']:
        cur.execute(f"DROP INDEX IF EXISTS {idx}")

    cur.execute("CREATE INDEX idx_orders_order_no ON orders(order_no)")
    cur.execute("CREATE INDEX idx_orders_final_due ON orders(final_due)")
    cur.execute("CREATE INDEX idx_orders_req_due ON orders(req_due)")
    cur.execute("CREATE INDEX idx_orders_invoice_done ON orders(invoice_done)")
    cur.execute("CREATE INDEX idx_order_items_order_id ON order_items(order_id)")
    cur.execute("CREATE INDEX idx_order_items_item_code ON order_items(item_code)")

    # 데이터 마이그레이션
    for order_no, items in order_groups.items():
        first = items[0]
        cur.execute("""
            INSERT INTO orders (order_no, customer_id, recv_dt, order_dt, req_due, final_due, oa_sent, invoice_done, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_no, first[1], first[3], first[4], first[9], first[10], first[14], first[15], first[16]))

        order_id = cur.lastrowid
        for item in items:
            cur.execute("""
                INSERT INTO order_items (order_id, item_code, rev, product_name, qty, unit_price_cents, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (order_id, item[5], item[6], item[7], item[8], item[12], item[13]))

    print(f"   ✓ {len(order_groups)}개 주문 헤더 마이그레이션")
    print()

    # ========================================
    # 2. 발주(Purchases) 마이그레이션
    # ========================================
    print("3. 발주(Purchases) 테이블 마이그레이션...")

    cur.execute("SELECT * FROM purchases")
    old_purchases = cur.fetchall()
    print(f"   기존 발주: {len(old_purchases)}개")

    # 발주번호별 그룹핑
    purchase_groups = {}
    for row in old_purchases:
        purchase_id, purchase_dt, purchase_no, item_code, rev, purchase_desc, qty, unit_price_cents, currency, status, created_at = row
        if purchase_no not in purchase_groups:
            purchase_groups[purchase_no] = []
        purchase_groups[purchase_no].append(row)

    # 테이블 백업 및 재생성
    cur.execute("DROP TABLE IF EXISTS purchases_old")
    cur.execute("ALTER TABLE purchases RENAME TO purchases_old")

    cur.execute("""
        CREATE TABLE purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_no TEXT UNIQUE NOT NULL,
            purchase_dt TEXT,
            status TEXT DEFAULT '발주',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    cur.execute("""
        CREATE TABLE purchase_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER NOT NULL,
            item_code TEXT,
            rev TEXT,
            product_name TEXT NOT NULL,
            qty INTEGER NOT NULL,
            unit_price_cents INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'KRW',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE
        )
    """)

    # 인덱스 생성
    for idx in ['idx_purchases_purchase_dt', 'idx_purchases_item_code']:
        cur.execute(f"DROP INDEX IF EXISTS {idx}")

    cur.execute("CREATE INDEX idx_purchases_purchase_no ON purchases(purchase_no)")
    cur.execute("CREATE INDEX idx_purchases_purchase_dt ON purchases(purchase_dt)")
    cur.execute("CREATE INDEX idx_purchase_items_purchase_id ON purchase_items(purchase_id)")
    cur.execute("CREATE INDEX idx_purchase_items_item_code ON purchase_items(item_code)")

    # 데이터 마이그레이션
    for purchase_no, items in purchase_groups.items():
        first = items[0]
        cur.execute("""
            INSERT INTO purchases (purchase_no, purchase_dt, status)
            VALUES (?, ?, ?)
        """, (purchase_no, first[1], first[9]))

        purchase_id = cur.lastrowid
        for item in items:
            cur.execute("""
                INSERT INTO purchase_items (purchase_id, item_code, rev, product_name, qty, unit_price_cents, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (purchase_id, item[3], item[4], item[5], item[6], item[7], item[8]))

    print(f"   ✓ {len(purchase_groups)}개 발주 헤더 마이그레이션")
    print()

    # ========================================
    # 3. 납품(Deliveries) 마이그레이션
    # ========================================
    print("4. 납품(Deliveries) 테이블 마이그레이션...")

    cur.execute("SELECT * FROM deliveries")
    old_deliveries = cur.fetchall()
    print(f"   기존 납품: {len(old_deliveries)}개")

    # 인보이스번호별 그룹핑
    delivery_groups = {}
    for row in old_deliveries:
        delivery_id, ship_datetime, invoice_no, qty, carrier, secondary_packaging, order_id, purchase_id, created_at = row
        if invoice_no not in delivery_groups:
            delivery_groups[invoice_no] = []
        delivery_groups[invoice_no].append(row)

    # 테이블 백업 및 재생성
    cur.execute("DROP TABLE IF EXISTS deliveries_old")
    cur.execute("ALTER TABLE deliveries RENAME TO deliveries_old")

    cur.execute("""
        CREATE TABLE deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT UNIQUE NOT NULL,
            ship_datetime TEXT,
            carrier TEXT,
            secondary_packaging TEXT,
            order_id INTEGER,
            purchase_id INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
            FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE SET NULL
        )
    """)

    cur.execute("""
        CREATE TABLE delivery_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id INTEGER NOT NULL,
            item_code TEXT,
            product_name TEXT,
            qty INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE
        )
    """)

    # 인덱스 생성
    for idx in ['idx_deliveries_ship_datetime', 'idx_deliveries_order_id', 'idx_deliveries_purchase_id']:
        cur.execute(f"DROP INDEX IF EXISTS {idx}")

    cur.execute("CREATE INDEX idx_deliveries_invoice_no ON deliveries(invoice_no)")
    cur.execute("CREATE INDEX idx_deliveries_ship_datetime ON deliveries(ship_datetime)")
    cur.execute("CREATE INDEX idx_deliveries_order_id ON deliveries(order_id)")
    cur.execute("CREATE INDEX idx_deliveries_purchase_id ON deliveries(purchase_id)")
    cur.execute("CREATE INDEX idx_delivery_items_delivery_id ON delivery_items(delivery_id)")

    # 데이터 마이그레이션
    for invoice_no, items in delivery_groups.items():
        first = items[0]
        cur.execute("""
            INSERT INTO deliveries (invoice_no, ship_datetime, carrier, secondary_packaging, order_id, purchase_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (invoice_no, first[1], first[4], first[5], first[6], first[7]))

        delivery_id = cur.lastrowid
        for item in items:
            # 기존에는 품목 정보가 없으므로 purchase 또는 order에서 가져와야 함
            # 우선은 수량만 저장
            cur.execute("""
                INSERT INTO delivery_items (delivery_id, qty)
                VALUES (?, ?)
            """, (delivery_id, item[3]))

    print(f"   ✓ {len(delivery_groups)}개 납품 헤더 마이그레이션")
    print()

    # ========================================
    # 4. VIEW 재생성
    # ========================================
    print("5. VIEW 재생성 중...")

    cur.execute("DROP VIEW IF EXISTS order_amounts")
    cur.execute("DROP VIEW IF EXISTS purchase_amounts")

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

    cur.execute("""
        CREATE VIEW purchase_amounts AS
        SELECT
            p.id AS purchase_id,
            p.purchase_no,
            SUM(pi.qty * pi.unit_price_cents) AS total_cents,
            pi.currency
        FROM purchases p
        JOIN purchase_items pi ON p.id = pi.purchase_id
        GROUP BY p.id, p.purchase_no, pi.currency
    """)

    print("   ✓ VIEW 재생성 완료")
    print()

    # 커밋
    conn.commit()

    print("=" * 80)
    print("마이그레이션 완료!")
    print("=" * 80)
    print()
    print(f"✓ 주문: {len(order_groups)}개 헤더")
    print(f"✓ 발주: {len(purchase_groups)}개 헤더")
    print(f"✓ 납품: {len(delivery_groups)}개 헤더")
    print()
    print(f"백업 파일: {backup_path}")
    print()

except Exception as e:
    print()
    print("=" * 80)
    print("오류 발생!")
    print("=" * 80)
    print(f"오류: {e}")
    import traceback

    traceback.print_exc()
    print()
    conn.rollback()
    print("백업에서 복구 필요")

finally:
    conn.close()