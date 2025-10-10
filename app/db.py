# app/db.py
# KOBATECH 제품 생산 관리 – 데이터베이스 (헤더-상세 구조)

import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _default_onedrive() -> Path:
    """시스템의 기본 OneDrive 경로를 추정합니다."""
    home = Path.home()
    guess = home / "OneDrive"
    return guess if guess.exists() else home


DB_DIR = os.environ.get("KOBATECH_DB_DIR") or str(_default_onedrive() / "KOBATECH_DB")
DB_NAME = os.environ.get("KOBATECH_DB_NAME", "production.db")
DB_PATH = Path(DB_DIR) / DB_NAME
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

/* 제품 마스터 정보 테이블 */
CREATE TABLE IF NOT EXISTS product_master (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_code TEXT NOT NULL,
  rev TEXT,
  product_name TEXT NOT NULL,
  unit_price_jpy INTEGER DEFAULT 0,
  purchase_price_krw INTEGER DEFAULT 0,
  description TEXT,
  is_active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  updated_at TEXT DEFAULT (datetime('now','localtime')),
  UNIQUE(item_code, rev)
);
CREATE INDEX IF NOT EXISTS idx_product_master_item_code ON product_master(item_code);
CREATE INDEX IF NOT EXISTS idx_product_master_product_name ON product_master(product_name);

/* 주문 헤더 */
CREATE TABLE IF NOT EXISTS orders (
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
);
CREATE INDEX IF NOT EXISTS idx_orders_order_no ON orders(order_no);
CREATE INDEX IF NOT EXISTS idx_orders_req_due ON orders(req_due);
CREATE INDEX IF NOT EXISTS idx_orders_final_due ON orders(final_due);
CREATE INDEX IF NOT EXISTS idx_orders_invoice_done ON orders(invoice_done);

/* 주문 상세 (품목) */
CREATE TABLE IF NOT EXISTS order_items (
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
);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_item_code ON order_items(item_code);

/* 발주 헤더 */
CREATE TABLE IF NOT EXISTS purchases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_no TEXT UNIQUE NOT NULL,
  purchase_dt TEXT,
  status TEXT DEFAULT '발주',
  actual_amount INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_purchases_purchase_no ON purchases(purchase_no);
CREATE INDEX IF NOT EXISTS idx_purchases_purchase_dt ON purchases(purchase_dt);

/* 발주 상세 (품목) */
CREATE TABLE IF NOT EXISTS purchase_items (
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
);
CREATE INDEX IF NOT EXISTS idx_purchase_items_purchase_id ON purchase_items(purchase_id);
CREATE INDEX IF NOT EXISTS idx_purchase_items_item_code ON purchase_items(item_code);

/* 발주-주문 연결 테이블 */
CREATE TABLE IF NOT EXISTS purchase_order_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_id INTEGER NOT NULL,
  order_id INTEGER NOT NULL,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE,
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
  UNIQUE(purchase_id, order_id)
);
CREATE INDEX IF NOT EXISTS idx_purchase_order_links_purchase ON purchase_order_links(purchase_id);
CREATE INDEX IF NOT EXISTS idx_purchase_order_links_order ON purchase_order_links(order_id);

/* 납품 헤더 */
CREATE TABLE IF NOT EXISTS deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_no TEXT UNIQUE NOT NULL,
  ship_datetime TEXT,
  carrier TEXT,
  secondary_packaging TEXT,
  delivery_type TEXT DEFAULT '일반',  -- ✅ 추가: 납품 타입 ('일반', '수리')
  created_at TEXT DEFAULT (datetime('now','localtime')),
  updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_deliveries_invoice_no ON deliveries(invoice_no);
CREATE INDEX IF NOT EXISTS idx_deliveries_ship_datetime ON deliveries(ship_datetime);

/* 납품-주문 연결 테이블 (다대다 관계) */
CREATE TABLE IF NOT EXISTS delivery_order_links (
  delivery_id INTEGER NOT NULL,
  order_id INTEGER NOT NULL,
  PRIMARY KEY (delivery_id, order_id),
  FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE,
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);

/* 납품-발주 연결 테이블 (다대다 관계) */
CREATE TABLE IF NOT EXISTS delivery_purchase_links (
  delivery_id INTEGER NOT NULL,
  purchase_id INTEGER NOT NULL,
  PRIMARY KEY (delivery_id, purchase_id),
  FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE,
  FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE
);

/* 납품 상세 (품목) */
CREATE TABLE IF NOT EXISTS delivery_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  delivery_id INTEGER NOT NULL,
  item_code TEXT,
  serial_no TEXT,
  manufacture_code TEXT,
  product_name TEXT,
  qty INTEGER NOT NULL,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_delivery_items_delivery_id ON delivery_items(delivery_id);
CREATE INDEX IF NOT EXISTS idx_delivery_items_serial_code ON delivery_items(serial_no, manufacture_code);

/* 제품 정보 */
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  manufacture_date TEXT,
  part_no TEXT,
  product_name TEXT,
  serial_no TEXT,
  manufacture_code TEXT,
  production_qty INTEGER DEFAULT 1,
  purchase_id INTEGER,
  delivery_id INTEGER,
  delivered_at TEXT,
  repair_count INTEGER DEFAULT 0,   -- ✅ 추가: 수리 횟수
  created_at TEXT DEFAULT (datetime('now','localtime')),
  FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE SET NULL,
  FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_products_manufacture_date ON products(manufacture_date);
CREATE INDEX IF NOT EXISTS idx_products_purchase_id ON products(purchase_id);
CREATE INDEX IF NOT EXISTS idx_products_delivery_id ON products(delivery_id);

/* ✅ 신규: 제품 수리 이력 테이블 */
CREATE TABLE IF NOT EXISTS product_repairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    receipt_date TEXT,
    customer_name TEXT,
    defect_symptom TEXT,
    repair_details TEXT,
    status TEXT DEFAULT '접수',
    repair_date TEXT,
    redelivery_invoice_no TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_product_repairs_product_id ON product_repairs(product_id);
CREATE INDEX IF NOT EXISTS idx_product_repairs_status ON product_repairs(status);


/* 납기 변경 이력 */
CREATE TABLE IF NOT EXISTS due_date_changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL,
  change_date TEXT NOT NULL,
  old_due_date TEXT,
  new_due_date TEXT NOT NULL,
  change_reason TEXT,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_due_date_changes_order_id ON due_date_changes(order_id);
CREATE INDEX IF NOT EXISTS idx_due_date_changes_change_date ON due_date_changes(change_date);

/* 주문 금액 뷰 */
CREATE VIEW IF NOT EXISTS order_amounts AS
SELECT
  o.id AS order_id,
  o.order_no,
  SUM(oi.qty * oi.unit_price_cents) AS total_cents,
  oi.currency
FROM orders o
JOIN order_items oi ON o.id = oi.order_id
GROUP BY o.id, o.order_no, oi.currency;

/* 발주 금액 뷰 */
CREATE VIEW IF NOT EXISTS purchase_amounts AS
SELECT
  p.id AS purchase_id,
  p.purchase_no,
  SUM(pi.qty * pi.unit_price_cents) AS total_cents,
  pi.currency
FROM purchases p
JOIN purchase_items pi ON p.id = pi.purchase_id
GROUP BY p.id, p.purchase_no, pi.currency;
"""


def get_conn() -> sqlite3.Connection:
    """SQLite 연결을 생성/반환합니다."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def execute(sql: str, params: tuple | dict = ()) -> None:
    conn = get_conn()
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def query_all(sql: str, params: tuple | dict = ()) -> list[tuple]:
    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def query_one(sql: str, params: tuple | dict = ()) -> tuple | None:
    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


# ===== 제품 마스터 관련 함수 =====

def get_product_master_by_code(item_code: str, rev: str = None):
    """품목코드와 Rev로 제품 마스터 정보 조회"""
    if rev:
        sql = """
            SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description
            FROM product_master 
            WHERE item_code = ? AND rev = ? AND is_active = 1
        """
        return query_one(sql, (item_code, rev))
    else:
        sql = """
            SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description
            FROM product_master 
            WHERE item_code = ? AND (rev IS NULL OR rev = '') AND is_active = 1
        """
        return query_one(sql, (item_code,))


def search_product_master(search_term: str, limit: int = 10):
    """품목코드나 제품명으로 제품 마스터 검색"""
    sql = """
        SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw
        FROM product_master 
        WHERE is_active = 1 
        AND (item_code LIKE ? OR product_name LIKE ?)
        ORDER BY item_code, rev
        LIMIT ?
    """
    search_pattern = f"%{search_term}%"
    return query_all(sql, (search_pattern, search_pattern, limit))


def add_or_update_product_master(item_code: str, rev: str, product_name: str,
                                 unit_price_jpy: int = None, purchase_price_krw: int = None,
                                 description: str = None):
    """제품 마스터 정보 추가 또는 업데이트"""
    rev = rev if rev and rev.strip() else None
    existing = get_product_master_by_code(item_code, rev)

    if existing:
        update_fields = []
        params = []

        update_fields.append("product_name=?")
        params.append(product_name)

        if unit_price_jpy is not None:
            update_fields.append("unit_price_jpy=?")
            params.append(unit_price_jpy)

        if purchase_price_krw is not None:
            update_fields.append("purchase_price_krw=?")
            params.append(purchase_price_krw)

        if description is not None:
            update_fields.append("description=?")
            params.append(description)

        update_fields.append("updated_at=datetime('now','localtime')")

        if rev:
            params.extend([item_code, rev])
            where_clause = "WHERE item_code=? AND rev=?"
        else:
            params.append(item_code)
            where_clause = "WHERE item_code=? AND (rev IS NULL OR rev = '')"

        sql = f"UPDATE product_master SET {', '.join(update_fields)} {where_clause}"
        execute(sql, tuple(params))
        return False
    else:
        sql = """
            INSERT INTO product_master (item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        execute(sql, (item_code, rev, product_name, unit_price_jpy or 0, purchase_price_krw or 0, description))
        return True


def update_product_master_purchase_price(item_code: str, rev: str, product_name: str,
                                         purchase_price_krw: int):
    """제품 마스터의 발주단가만 업데이트"""
    rev = rev if rev and rev.strip() else None
    existing = get_product_master_by_code(item_code, rev)

    if existing:
        if rev:
            sql = """
                UPDATE product_master 
                SET product_name=?, purchase_price_krw=?, 
                    updated_at=datetime('now','localtime')
                WHERE item_code=? AND rev=?
            """
            execute(sql, (product_name, purchase_price_krw, item_code, rev))
        else:
            sql = """
                UPDATE product_master 
                SET product_name=?, purchase_price_krw=?, 
                    updated_at=datetime('now','localtime')
                WHERE item_code=? AND (rev IS NULL OR rev = '')
            """
            execute(sql, (product_name, purchase_price_krw, item_code))
        return False
    else:
        sql = """
            INSERT INTO product_master (item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description)
            VALUES (?, ?, ?, 0, ?, NULL)
        """
        execute(sql, (item_code, rev, product_name, purchase_price_krw))
        return True


# app/db.py

def get_all_product_master(include_inactive=False):
    """모든 제품 마스터 목록 조회"""
    if include_inactive:
        # 전체보기: 단종 제품 포함
        sql = """
            SELECT id, item_code, rev, product_name, unit_price_jpy, 
                   purchase_price_krw, description, created_at, updated_at
            FROM product_master 
            ORDER BY item_code
        """
    else:
        # 생산 가능만: 활성 제품만
        sql = """
            SELECT id, item_code, rev, product_name, unit_price_jpy, 
                   purchase_price_krw, description, created_at, updated_at
            FROM product_master 
            WHERE is_active = 1
            ORDER BY item_code
        """
    return query_all(sql)


def delete_product_master(product_id: int):
    """제품 마스터 삭제 (비활성화)"""
    sql = "UPDATE product_master SET is_active = 0 WHERE id = ?"
    execute(sql, (product_id,))


# ===== 주문 관련 함수 (헤더-상세 구조) =====

def create_order_with_items(order_data: dict, items: list):
    """주문 헤더와 품목들을 함께 생성"""
    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO orders (
                order_no, recv_dt, order_dt, req_due, final_due,
                oa_sent, invoice_done, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_data['order_no'],
            order_data.get('recv_dt'),
            order_data.get('order_dt'),
            order_data.get('req_due'),
            order_data.get('final_due'),
            order_data.get('oa_sent', 0),
            order_data.get('invoice_done', 0),
            order_data.get('status', '계획')
        ))

        order_id = cur.lastrowid

        for item in items:
            cur.execute("""
                INSERT INTO order_items (
                    order_id, item_code, rev, product_name,
                    qty, unit_price_cents, currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                item.get('item_code'),
                item.get('rev'),
                item['product_name'],
                item['qty'],
                item['unit_price_cents'],
                item.get('currency', 'JPY')
            ))

        conn.commit()
        return order_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_order_with_items(order_id: int):
    """주문 헤더와 품목들 함께 조회"""
    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT id, order_no, customer_id, recv_dt, order_dt,
                   req_due, final_due, oa_sent, invoice_done, status
            FROM orders WHERE id = ?
        """, (order_id,))

        header = cur.fetchone()
        if not header:
            return None

        cur.execute("""
            SELECT id, item_code, rev, product_name,
                   qty, unit_price_cents, currency
            FROM order_items WHERE order_id = ?
            ORDER BY id
        """, (order_id,))

        items = cur.fetchall()

        return {'header': header, 'items': items}
    finally:
        conn.close()


def update_order_with_items(order_id: int, order_data: dict, items: list):
    """주문 헤더와 품목들을 함께 수정"""
    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("""
            UPDATE orders 
            SET order_no=?, recv_dt=?, order_dt=?, req_due=?, final_due=?,
                oa_sent=?, invoice_done=?, status=?, updated_at=datetime('now','localtime')
            WHERE id=?
        """, (
            order_data['order_no'],
            order_data.get('recv_dt'),
            order_data.get('order_dt'),
            order_data.get('req_due'),
            order_data.get('final_due'),
            order_data.get('oa_sent', 0),
            order_data.get('invoice_done', 0),
            order_data.get('status', '계획'),
            order_id
        ))

        cur.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))

        for item in items:
            cur.execute("""
                INSERT INTO order_items (
                    order_id, item_code, rev, product_name,
                    qty, unit_price_cents, currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                item.get('item_code'),
                item.get('rev'),
                item['product_name'],
                item['qty'],
                item['unit_price_cents'],
                item.get('currency', 'JPY')
            ))

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def delete_order(order_id: int):
    """주문 삭제 (CASCADE로 품목들도 자동 삭제)"""
    execute("DELETE FROM orders WHERE id=?", (order_id,))


# ===== 발주 관련 함수 (헤더-상세 구조) =====

def create_purchase_with_items(purchase_data: dict, items: list, order_ids: list = None):
    """발주 헤더와 품목들을 함께 생성"""
    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO purchases (purchase_no, purchase_dt, status, actual_amount)
            VALUES (?, ?, ?, ?)
        """, (
            purchase_data['purchase_no'],
            purchase_data.get('purchase_dt'),
            purchase_data.get('status', '발주'),
            purchase_data.get('actual_amount', 0)  # ✅ 추가
        ))

        purchase_id = cur.lastrowid

        for item in items:
            cur.execute("""
                INSERT INTO purchase_items (
                    purchase_id, item_code, rev, product_name,
                    qty, unit_price_cents, currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                purchase_id,
                item.get('item_code'),
                item.get('rev'),
                item['product_name'],
                item['qty'],
                item['unit_price_cents'],
                item.get('currency', 'KRW')
            ))

        if order_ids:
            for order_id in order_ids:
                cur.execute("""
                    INSERT INTO purchase_order_links (purchase_id, order_id)
                    VALUES (?, ?)
                """, (purchase_id, order_id))

        conn.commit()
        return purchase_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_purchase_with_items(purchase_id: int):
    """발주 헤더와 품목들 함께 조회"""
    conn = get_conn()
    try:
        cur = conn.cursor()

        # ✅ actual_amount 추가
        cur.execute("""
            SELECT id, purchase_no, purchase_dt, status, actual_amount
            FROM purchases WHERE id = ?
        """, (purchase_id,))

        header = cur.fetchone()
        if not header:
            return None

        cur.execute("""
            SELECT id, item_code, rev, product_name,
                   qty, unit_price_cents, currency
            FROM purchase_items WHERE purchase_id = ?
            ORDER BY id
        """, (purchase_id,))

        items = cur.fetchall()

        return {'header': header, 'items': items}
    finally:
        conn.close()


def get_available_orders():
    """발주와 연결할 수 있는 주문 목록을 반환"""
    sql = """
        SELECT id, order_no, GROUP_CONCAT(oi.product_name, ' | ') as desc, 
               SUM(oi.qty) as qty, COALESCE(o.final_due, o.req_due) as due_date
        FROM orders o
        LEFT JOIN order_items oi ON o.id = oi.order_id
        WHERE o.order_no IS NOT NULL 
        GROUP BY o.id
        ORDER BY o.order_no
    """
    return query_all(sql)


def get_linked_orders(purchase_id: int):
    """특정 발주와 연결된 주문 목록을 반환"""
    sql = """
        SELECT o.id, o.order_no, GROUP_CONCAT(oi.product_name, ' | ') as desc,
               SUM(oi.qty) as qty, COALESCE(o.final_due, o.req_due) as due_date
        FROM orders o
        JOIN purchase_order_links pol ON o.id = pol.order_id
        LEFT JOIN order_items oi ON o.id = oi.order_id
        WHERE pol.purchase_id = ?
        GROUP BY o.id
        ORDER BY o.order_no
    """
    return query_all(sql, (purchase_id,))


def get_orders_for_purchase_display(purchase_id: int) -> str:
    """발주 목록 표시용 주문번호 문자열 반환"""
    linked_orders = get_linked_orders(purchase_id)
    if not linked_orders:
        return ""
    return ", ".join([order[1] for order in linked_orders])


# ===== 납품 관련 함수 (헤더-상세 구조) =====

def create_delivery_with_items(delivery_data: dict, items: list):
    """납품 헤더와 품목들을 함께 생성"""
    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO deliveries (
                invoice_no, ship_datetime, carrier, secondary_packaging,
                order_id, purchase_id
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            delivery_data['invoice_no'],
            delivery_data.get('ship_datetime'),
            delivery_data.get('carrier'),
            delivery_data.get('secondary_packaging'),
            delivery_data.get('order_id'),
            delivery_data.get('purchase_id')
        ))

        delivery_id = cur.lastrowid

        for item in items:
            # ✅ serial_no, manufacture_code 추가
            cur.execute("""
                INSERT INTO delivery_items (
                    delivery_id, item_code, serial_no, manufacture_code, product_name, qty
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                delivery_id,
                item.get('item_code'),
                item.get('serial_no'),  # ✅
                item.get('manufacture_code'),  # ✅
                item.get('product_name'),
                item['qty']
            ))

        conn.commit()
        return delivery_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_delivery_with_items(delivery_id: int):
    """납품 헤더와 품목들 함께 조회"""
    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT id, invoice_no, ship_datetime, carrier,
                   secondary_packaging, order_id, purchase_id
            FROM deliveries WHERE id = ?
        """, (delivery_id,))

        header = cur.fetchone()
        if not header:
            return None

        # ✅ serial_no, manufacture_code 추가
        cur.execute("""
            SELECT id, item_code, serial_no, manufacture_code, product_name, qty
            FROM delivery_items WHERE delivery_id = ?
            ORDER BY id
        """, (delivery_id,))

        items = cur.fetchall()

        return {'header': header, 'items': items}
    finally:
        conn.close()


def get_all_deliveries_summary():
    """모든 납품 요약 조회 (링크 테이블 사용)"""
    sql = """
        SELECT 
            d.id,
            d.invoice_no,
            d.ship_datetime,
            d.carrier,
            COALESCE(SUM(di.qty), 0) as total_qty,
            GROUP_CONCAT(DISTINCT o.order_no, ', ') as order_nos,
            GROUP_CONCAT(DISTINCT p.purchase_no, ', ') as purchase_nos
        FROM deliveries d
        LEFT JOIN delivery_items di ON d.id = di.delivery_id
        LEFT JOIN delivery_order_links dol ON d.id = dol.delivery_id
        LEFT JOIN orders o ON dol.order_id = o.id
        LEFT JOIN delivery_purchase_links dpl ON d.id = dpl.delivery_id
        LEFT JOIN purchases p ON dpl.purchase_id = p.id
        GROUP BY d.id
        ORDER BY d.ship_datetime DESC
    """
    return query_all(sql)


# ===== 납기 변경 이력 관련 함수 =====

def get_due_change_history(order_id: int):
    """특정 주문의 납기 변경 이력을 반환"""
    sql = """
        SELECT id, change_date, old_due_date, new_due_date, change_reason, created_at
        FROM due_date_changes 
        WHERE order_id = ?
        ORDER BY change_date DESC, created_at DESC
    """
    return query_all(sql, (order_id,))


def add_due_change_record(order_id: int, change_date: str, old_due: str, new_due: str, reason: str = None):
    """납기 변경 이력 추가"""
    sql = """
        INSERT INTO due_date_changes (order_id, change_date, old_due_date, new_due_date, change_reason)
        VALUES (?, ?, ?, ?, ?)
    """
    execute(sql, (order_id, change_date, old_due, new_due, reason))


def update_order_final_due_date(order_id: int, new_due_date: str):
    """주문의 최종 납기일 업데이트"""
    sql = "UPDATE orders SET final_due = ?, updated_at=datetime('now','localtime') WHERE id = ?"
    execute(sql, (new_due_date, order_id))


def get_order_due_dates(order_id: int):
    """주문의 최초납기일과 최종납기일 반환"""
    sql = "SELECT req_due, final_due FROM orders WHERE id = ?"
    result = query_one(sql, (order_id,))
    if result:
        req_due, final_due = result
        return req_due, final_due or req_due
    return None, None

def mark_products_as_delivered(delivery_id: int, conn=None):
    """특정 납품에 포함된 제품들을 납품됨으로 표시 (수량 처리 및 시리얼 자동 증가 로직 추가)"""
    import re
    should_close = False
    if conn is None:
        conn = get_conn()
        should_close = True

    try:
        cur = conn.cursor()

        # ✅ 수정: qty 컬럼도 함께 조회합니다.
        cur.execute("""
            SELECT item_code, serial_no, manufacture_code, qty
            FROM delivery_items 
            WHERE delivery_id = ? 
            AND serial_no IS NOT NULL 
        """, (delivery_id,))

        delivered_items = cur.fetchall()

        for item_code, start_serial_no, manufacture_code, qty in delivered_items:
            # ✅ 시리얼 번호 파싱 로직 추가
            # 시리얼 번호 끝에 있는 숫자 부분을 찾습니다. (예: KT001 -> KT, 001)
            match = re.search(r'(\D*)(\d+)$', start_serial_no)

            if not match:
                # 숫자 부분을 찾지 못하면 기존 방식대로 1개만 처리
                cur.execute("""
                    UPDATE products 
                    SET delivery_id = ?, delivered_at = datetime('now', 'localtime')
                    WHERE part_no = ? AND serial_no = ?
                """, (delivery_id, item_code, start_serial_no))
                continue

            prefix, start_num_str = match.groups()
            start_num = int(start_num_str)
            num_width = len(start_num_str)  # 숫자의 자릿수 (예: 001 -> 3)

            # ✅ 수량만큼 반복하면서 시리얼 번호를 증가시켜 업데이트
            for i in range(qty):
                current_num = start_num + i
                current_serial = f"{prefix}{current_num:0{num_width}d}"

                cur.execute("""
                    UPDATE products 
                    SET delivery_id = ?, delivered_at = datetime('now', 'localtime')
                    WHERE part_no = ? AND serial_no = ?
                """, (delivery_id, item_code, current_serial))

        if should_close:
            conn.commit()

    except Exception as e:
        if 'conn' in locals() and should_close: conn.rollback()
        # 예외를 다시 발생시켜 상위 호출자에게 알림
        raise e
    finally:
        if 'conn' in locals() and should_close: conn.close()

def unmark_products_as_delivered(delivery_id: int, conn=None):
    """특정 납품에 포함된 제품들의 납품 상태를 제거"""
    should_close = False
    if conn is None:
        conn = get_conn()
        should_close = True

    try:
        cur = conn.cursor()

        # 이 납품에 포함된 제품들의 납품 상태 제거
        cur.execute("""
            UPDATE products 
            SET delivery_id = NULL, 
                delivered_at = NULL
            WHERE delivery_id = ?
        """, (delivery_id,))

        if should_close:
            conn.commit()

    except Exception as e:
        if should_close:
            conn.rollback()
        raise e
    finally:
        if should_close:
            conn.close()


def _update_product_repair_count(product_id: int, conn):
    """특정 제품의 수리 횟수를 업데이트하는 내부 함수"""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM product_repairs WHERE product_id = ?", (product_id,))
    count = cur.fetchone()[0]
    cur.execute("UPDATE products SET repair_count = ? WHERE id = ?", (count, product_id))


def get_all_repairs(status_filter: str = None):
    """모든 수리 이력 조회. 상태별 필터링 기능 포함."""
    sql = """
        SELECT
            r.id,
            r.receipt_date,
            r.customer_name,
            p.part_no,
            p.product_name,
            p.serial_no,
            r.defect_symptom,
            r.repair_details,
            r.status,
            r.repair_date,
            r.redelivery_invoice_no,
            r.product_id
        FROM product_repairs r
        JOIN products p ON r.product_id = p.id
    """
    params = []
    if status_filter and status_filter != '전체':
        sql += " WHERE r.status = ?"
        params.append(status_filter)

    sql += " ORDER BY r.receipt_date DESC, r.id DESC"
    return query_all(sql, tuple(params))


def get_repairs_for_product(product_id: int):
    """특정 제품에 대한 모든 수리 이력 조회"""
    sql = """
        SELECT
            id, receipt_date, customer_name, defect_symptom, 
            repair_details, status, repair_date, redelivery_invoice_no
        FROM product_repairs
        WHERE product_id = ?
        ORDER BY receipt_date DESC, id DESC
    """
    return query_all(sql, (product_id,))


def add_or_update_repair(repair_data: dict, repair_id: int = None):
    """새 수리 내역을 추가하거나 기존 내역을 수정"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        if repair_id:  # 수정
            cur.execute("""
                UPDATE product_repairs SET
                    receipt_date = ?, customer_name = ?, defect_symptom = ?,
                    repair_details = ?, status = ?, repair_date = ?,
                    redelivery_invoice_no = ?, updated_at = datetime('now', 'localtime')
                WHERE id = ?
            """, (
                repair_data['receipt_date'], repair_data.get('customer_name'),
                repair_data.get('defect_symptom'), repair_data.get('repair_details'),
                repair_data.get('status'), repair_data.get('repair_date'),
                repair_data.get('redelivery_invoice_no'), repair_id
            ))
            product_id = repair_data['product_id']
        else:  # 추가
            cur.execute("""
                INSERT INTO product_repairs (
                    product_id, receipt_date, customer_name, defect_symptom,
                    repair_details, status, repair_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                repair_data['product_id'], repair_data['receipt_date'],
                repair_data.get('customer_name'), repair_data.get('defect_symptom'),
                repair_data.get('repair_details'), repair_data.get('status'),
                repair_data.get('repair_date')
            ))
            product_id = repair_data['product_id']

        # 수리 횟수 업데이트
        _update_product_repair_count(product_id, conn)
        conn.commit()
    finally:
        conn.close()


def delete_repair(repair_id: int):
    """수리 내역 삭제"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        # 삭제 전 product_id를 먼저 조회
        cur.execute("SELECT product_id FROM product_repairs WHERE id = ?", (repair_id,))
        result = cur.fetchone()
        if result:
            product_id = result[0]
            cur.execute("DELETE FROM product_repairs WHERE id = ?", (repair_id,))
            # 수리 횟수 업데이트
            _update_product_repair_count(product_id, conn)
            conn.commit()
    finally:
        conn.close()