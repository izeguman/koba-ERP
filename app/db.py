# app/db.py
# KOBATECH 제품 생산 관리 – 데이터베이스 (헤더-상세 구조)

import os
import sqlite3
from collections import defaultdict
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
  item_type TEXT DEFAULT 'SELLABLE',
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

/* 주문 품목별 분할 납기 테이블 */
CREATE TABLE IF NOT EXISTS order_shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_item_id INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    ship_qty INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (order_item_id) REFERENCES order_items(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_order_shipments_order_item_id ON order_shipments(order_item_id);

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
  delivery_type TEXT DEFAULT '일반',

  invoice_done INTEGER DEFAULT 0, /* ✅ [추가] 납품 건별 청구완료 여부 */

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
  order_id INTEGER,
  purchase_id INTEGER,
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
  repair_count INTEGER DEFAULT 0,
  consumed_by_product_id INTEGER,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE SET NULL,
  FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_products_manufacture_date ON products(manufacture_date);
CREATE INDEX IF NOT EXISTS idx_products_purchase_id ON products(purchase_id);
CREATE INDEX IF NOT EXISTS idx_products_delivery_id ON products(delivery_id);

/* [수정] 제품 수리 이력 테이블 */
CREATE TABLE IF NOT EXISTS product_repairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    receipt_date TEXT,
    quality_report_no TEXT, -- 품질보고서 번호
    defect_symptom TEXT, -- 불량 증상
    investigation_customer TEXT, -- 고객사 조사내용
    investigation_internal TEXT, -- 당사 조사내용
    immediate_action TEXT, -- 즉각 대응조치
    root_cause_occurrence TEXT, -- 근본원인 (발생)
    root_cause_outflow TEXT, -- 근본원인 (유출)
    repair_details TEXT, -- 수리 내역
    prevention_occurrence TEXT, -- 재발방지대책 (발생)
    prevention_outflow TEXT, -- 재발방지대책 (유출)
    status TEXT DEFAULT '접수', -- 상태
    repair_date TEXT, -- 수리일
    redelivery_invoice_no TEXT, -- 재출고 인보이스

    cost_deposit INTEGER DEFAULT 0,
    cost_air_freight INTEGER DEFAULT 0,
    cost_shipping_jp INTEGER DEFAULT 0,
    cost_tax_jp INTEGER DEFAULT 0,
    repair_pic TEXT,
    ncr_qty INTEGER DEFAULT 0,
    import_invoice_no TEXT,
    import_declaration_no TEXT,
    import_carrier TEXT,
    defect_date TEXT,

    attachments TEXT, -- ✅ [추가] 첨부 파일 경로 (SCHEMA_SQL에 추가)

    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_product_repairs_product_id ON product_repairs(product_id);
CREATE INDEX IF NOT EXISTS idx_product_repairs_status ON product_repairs(status);
CREATE INDEX IF NOT EXISTS idx_product_repairs_quality_report_no ON product_repairs(quality_report_no);

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


/* 분할 납기 건별 변경 이력 테이블 */
CREATE TABLE IF NOT EXISTS shipment_date_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_item_id INTEGER NOT NULL,
    change_request_date TEXT NOT NULL,
    old_schedule TEXT,
    new_schedule TEXT,
    reason TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (order_item_id) REFERENCES order_items(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_shipment_date_changes_item_id ON shipment_date_changes(order_item_id);

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
CREATE TABLE IF NOT EXISTS bom_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_item_code TEXT NOT NULL,
  child_item_code TEXT NOT NULL,
  quantity_required REAL NOT NULL DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now','localtime')),
  UNIQUE(parent_item_code, child_item_code)
);
CREATE INDEX IF NOT EXISTS idx_bom_items_parent ON bom_items(parent_item_code);
CREATE INDEX IF NOT EXISTS idx_bom_items_child ON bom_items(child_item_code);
"""


def get_conn() -> sqlite3.Connection:
    """SQLite 연결을 생성/반환하고, 필요한 경우 스키마를 마이그레이션합니다."""
    conn = sqlite3.connect(str(DB_PATH))

    # --- 1. product_repairs 테이블 마이그레이션 (수리 이력 관련 컬럼) ---
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(product_repairs);")
        columns = [info[1] for info in cursor.fetchall()]

        all_new_columns = {
            "quality_report_no": "TEXT",
            "investigation_customer": "TEXT",
            "investigation_internal": "TEXT",
            "immediate_action": "TEXT",
            "root_cause_occurrence": "TEXT",
            "root_cause_outflow": "TEXT",
            "prevention_occurrence": "TEXT",
            "prevention_outflow": "TEXT",
            "cost_deposit": "INTEGER DEFAULT 0",
            "cost_air_freight": "INTEGER DEFAULT 0",
            "cost_shipping_jp": "INTEGER DEFAULT 0",
            "cost_tax_jp": "INTEGER DEFAULT 0",
            "repair_pic": "TEXT",
            "ncr_qty": "INTEGER DEFAULT 0",
            "import_invoice_no": "TEXT",
            "import_declaration_no": "TEXT",
            "import_carrier": "TEXT",
            "defect_date": "TEXT",
            "attachments": "TEXT"
        }

        for col_name, col_type in all_new_columns.items():
            if col_name not in columns:
                print(f"Applying migration: Adding column '{col_name}' to 'product_repairs' table...")
                cursor.execute(f"ALTER TABLE product_repairs ADD COLUMN {col_name} {col_type};")

        conn.commit()
    except sqlite3.Error:
        # 테이블이 없으면 아래 executescript에서 생성되므로 패스
        conn.rollback()

    # --- 2. deliveries 테이블 마이그레이션 (청구 완료 여부) ---
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(deliveries);")
        columns = [info[1] for info in cursor.fetchall()]

        if "invoice_done" not in columns:
            print("Applying migration: Adding column 'invoice_done' to 'deliveries' table...")
            cursor.execute("ALTER TABLE deliveries ADD COLUMN invoice_done INTEGER DEFAULT 0;")
            conn.commit()

    except sqlite3.Error as e:
        print(f"Deliveries migration failed: {e}")
        conn.rollback()

    # --- 3. BOM 관련 마이그레이션 (product_master, products) ---
    try:
        cursor = conn.cursor()

        # 3-1. product_master에 item_type 추가
        cursor.execute("PRAGMA table_info(product_master);")
        columns_pm = [info[1] for info in cursor.fetchall()]
        if "item_type" not in columns_pm:
            print("Applying migration: Adding column 'item_type' to 'product_master' table...")
            cursor.execute("ALTER TABLE product_master ADD COLUMN item_type TEXT DEFAULT 'SELLABLE';")

        # 3-2. products에 consumed_by_product_id 추가
        cursor.execute("PRAGMA table_info(products);")
        columns_p = [info[1] for info in cursor.fetchall()]
        if "consumed_by_product_id" not in columns_p:
            print("Applying migration: Adding column 'consumed_by_product_id' to 'products' table...")
            cursor.execute("ALTER TABLE products ADD COLUMN consumed_by_product_id INTEGER;")

        conn.commit()
    except sqlite3.Error as e:
        print(f"BOM Step 1 migration failed: {e}")
        conn.rollback()

    # --- 4. products 테이블 updated_at 컬럼 추가 (시리얼 삭제 기능용) ---
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(products);")
        columns_p = [info[1] for info in cursor.fetchall()]

        if "updated_at" not in columns_p:
            print("Applying migration: Adding column 'updated_at' to 'products' table...")

            # ✅ [수정] ALTER TABLE에서는 변수가 포함된 DEFAULT를 쓸 수 없는 경우가 많음
            # 1. 일단 컬럼을 생성 (NULL 허용)
            cursor.execute("ALTER TABLE products ADD COLUMN updated_at TEXT;")

            # 2. 기존 데이터들에 현재 시간 일괄 입력
            cursor.execute("UPDATE products SET updated_at = datetime('now', 'localtime');")

        conn.commit()
    except sqlite3.Error as e:
        print(f"Products updated_at migration failed: {e}")
        conn.rollback()

        # ... (기존 마이그레이션 코드들 아래에 추가)

    # --- 5. products 테이블 reserved_order_id 추가 (주문 예약 기능) ---
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(products);")
        columns_p = [info[1] for info in cursor.fetchall()]

        if "reserved_order_id" not in columns_p:
            print("Applying migration: Adding column 'reserved_order_id' to 'products' table...")
            cursor.execute(
                "ALTER TABLE products ADD COLUMN reserved_order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL;")

        conn.commit()
    except sqlite3.Error as e:
        print(f"Products reserved_order_id migration failed: {e}")
        conn.rollback()

    # --- 6. exchange_rates 테이블 추가 (월별 환율 관리) ---
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exchange_rates';")
        if not cursor.fetchone():
            print("Applying migration: Creating 'exchange_rates' table...")
            cursor.execute("""
                CREATE TABLE exchange_rates (
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    rate REAL NOT NULL, -- 100엔당 원화 금액 (예: 905.5)
                    updated_at TEXT DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (year, month)
                );
            """)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Exchange rates migration failed: {e}")
        conn.rollback()

    # --- 공통 설정 ---
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
                                 description: str = None, item_type: str = 'SELLABLE') -> str:  # ✅ item_type 인자 추가
    """
    제품 마스터 정보를 추가 또는 업데이트하고, 처리 결과를 문자열로 반환합니다.
    - 'INSERTED': 신규 추가 성공
    - 'UPDATED': 기존 정보 업데이트 성공
    - 'DUPLICATE_INACTIVE': 단종된 중복 품목 발견 (오류 처리 필요)
    """
    rev = rev if rev and rev.strip() else None

    # is_active 상태와 상관없이 기존 제품을 먼저 찾습니다.
    conn = get_conn()
    cur = conn.cursor()
    if rev:
        cur.execute("SELECT id, is_active FROM product_master WHERE item_code = ? AND rev = ?", (item_code, rev))
    else:
        cur.execute("SELECT id, is_active FROM product_master WHERE item_code = ? AND (rev IS NULL OR rev = '')",
                    (item_code,))
    existing_row = cur.fetchone()
    conn.close()

    if existing_row:
        existing_id, is_active = existing_row

        # 기존 품목이 '생산 가능(활성)' 상태일 때만 업데이트를 진행합니다.
        if is_active == 1:
            update_fields = ["product_name=?", "updated_at=datetime('now','localtime')"]
            params = [product_name]

            if unit_price_jpy is not None:
                update_fields.append("unit_price_jpy=?")
                params.append(unit_price_jpy)
            if purchase_price_krw is not None:
                update_fields.append("purchase_price_krw=?")
                params.append(purchase_price_krw)
            if description is not None:
                update_fields.append("description=?")
                params.append(description)

            # ✅ [추가] item_type 업데이트
            if item_type:
                update_fields.append("item_type=?")
                params.append(item_type)

            params.append(existing_id)  # ⬅️ [수정] WHERE 절의 ID는 항상 마지막에 추가해야 합니다.

            sql = f"UPDATE product_master SET {', '.join(update_fields)} WHERE id=?"
            execute(sql, tuple(params))
            return 'UPDATED'
        # 기존 품목이 '단종(비활성)' 상태이면, 아무것도 하지 않고 '중복' 신호를 보냅니다.
        else:
            return 'DUPLICATE_INACTIVE'
    else:
        # 기존 제품이 전혀 없으면, 새로 추가합니다.
        sql = """
            INSERT INTO product_master 
            (item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, item_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        execute(sql,
                (item_code, rev, product_name, unit_price_jpy or 0, purchase_price_krw or 0, description, item_type))
        return 'INSERTED'


def update_product_master_purchase_price(item_code: str, rev: str, product_name: str,
                                         purchase_price_krw: int):
    """제품 마스터의 발주단가만 업데이트"""
    rev = rev if rev and rev.strip() else None

    conn = get_conn()
    cur = conn.cursor()
    if rev:
        cur.execute("SELECT id, is_active FROM product_master WHERE item_code = ? AND rev = ?", (item_code, rev))
    else:
        cur.execute("SELECT id, is_active FROM product_master WHERE item_code = ? AND (rev IS NULL OR rev = '')",
                    (item_code,))
    existing_row = cur.fetchone()
    conn.close()

    if existing_row:
        sql_update = """
            UPDATE product_master 
            SET product_name=?, purchase_price_krw=?, is_active=1,
                updated_at=datetime('now','localtime')
            WHERE id=?
        """
        execute(sql_update, (product_name, purchase_price_krw, existing_row[0]))
        return False
    else:
        sql_insert = """
            INSERT INTO product_master (item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description)
            VALUES (?, ?, ?, 0, ?, NULL)
        """
        execute(sql_insert, (item_code, rev, product_name, purchase_price_krw))
        return True


# app/db.py

def get_all_product_master(include_inactive=False, order_by_clause="item_code ASC"):
    """모든 제품 마스터 목록 조회 (동적 정렬 추가)"""

    base_sql = """
        SELECT id, item_code, rev, product_name, unit_price_jpy, 
               purchase_price_krw, description, created_at, updated_at,
               is_active, item_type 
        FROM product_master 
    """

    if include_inactive:
        # 전체보기: 단종 제품 포함
        pass  # WHERE 절 없음
    else:
        # 생산 가능만: 활성 제품만
        base_sql += " WHERE is_active = 1"

    # 동적 정렬 적용
    base_sql += f" ORDER BY {order_by_clause}"

    return query_all(base_sql)


def delete_product_master(product_id: int):
    """제품 마스터 삭제 (비활성화)"""
    sql = "UPDATE product_master SET is_active = 0 WHERE id = ?"
    execute(sql, (product_id,))


def create_order_with_items(order_data: dict, items: list, shipment_data: dict = None, purchase_ids: list = None):
    """주문 생성: 헤더, 품목, 납기, 연결 정보 저장 (+ 즉시 할당 실행)"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (order_no, recv_dt, order_dt, req_due, final_due) VALUES (?, ?, ?, ?, ?)",
            (order_data['order_no'], order_data.get('recv_dt'), order_data.get('order_dt'),
             order_data.get('req_due'), order_data.get('final_due'))
        )
        order_id = cur.lastrowid

        item_id_map = {}
        for i, item in enumerate(items):
            cur.execute(
                "INSERT INTO order_items (order_id, item_code, rev, product_name, qty, unit_price_cents) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, item.get('item_code'), item.get('rev'), item['product_name'], item['qty'],
                 item['unit_price_cents'])
            )
            item_id_map[i] = cur.lastrowid

        if shipment_data:
            for item_row_index, shipments in shipment_data.items():
                order_item_id = item_id_map.get(item_row_index)
                if order_item_id:
                    save_shipments_for_order_item(order_item_id, shipments, conn)

        # ✅ [수정] 발주 연결 및 '즉시 할당' 로직 추가
        if purchase_ids:
            for purchase_id in purchase_ids:
                cur.execute(
                    "INSERT INTO purchase_order_links (purchase_id, order_id) VALUES (?, ?)",
                    (purchase_id, order_id)
                )

            # 연결된 발주들에 대해 '재할당' 실행 (이 새 주문이 재고를 가져갈 수 있는지 확인)
            for p_id in purchase_ids:
                # 유효한 재고 조회
                cur.execute("""
                    SELECT id FROM products 
                    WHERE purchase_id = ? 
                      AND delivery_id IS NULL 
                      AND consumed_by_product_id IS NULL
                """, (p_id,))
                product_ids = [r[0] for r in cur.fetchall()]

                if product_ids:
                    # 현재 커넥션을 공유하여 할당 로직 실행
                    allocate_products_fifo(product_ids, p_id, conn=conn)

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


def update_order_with_items(order_id: int, order_data: dict, items: list, shipment_data: dict = None,
                            purchase_ids: list = None):
    """주문 수정: 헤더, 품목, 납기, 연결 정보 수정 (+ 연결 해제 시 정리, 연결 시 자동 할당)"""
    conn = get_conn()
    try:
        cur = conn.cursor()

        # 1. 주문 정보 업데이트
        cur.execute(
            "UPDATE orders SET order_no=?, recv_dt=?, order_dt=?, req_due=?, final_due=?, updated_at=datetime('now','localtime') WHERE id=?",
            (order_data['order_no'], order_data.get('recv_dt'), order_data.get('order_dt'),
             order_data.get('req_due'), order_data.get('final_due'), order_id)
        )

        # 2. 품목 재설정
        cur.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
        item_id_map = {}
        for i, item in enumerate(items):
            cur.execute(
                "INSERT INTO order_items (order_id, item_code, rev, product_name, qty, unit_price_cents) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, item.get('item_code'), item.get('rev'), item['product_name'], item['qty'],
                 item['unit_price_cents'])
            )
            item_id_map[i] = cur.lastrowid

        # 3. 분할 납기 저장
        if shipment_data:
            for item_row_index, shipments in shipment_data.items():
                order_item_id = item_id_map.get(item_row_index)
                if order_item_id:
                    save_shipments_for_order_item(order_item_id, shipments, conn)

        # 4. 발주 연결 정보 업데이트 및 자동화 로직
        if purchase_ids is not None:
            cur.execute("DELETE FROM purchase_order_links WHERE order_id = ?", (order_id,))
            for purchase_id in purchase_ids:
                cur.execute(
                    "INSERT INTO purchase_order_links (purchase_id, order_id) VALUES (?, ?)",
                    (purchase_id, order_id)
                )

            # A. [Cleanup] 연결 해제된 발주의 제품 예약 풀기
            if purchase_ids:
                placeholders = ', '.join('?' for _ in purchase_ids)
                cur.execute(f"""
                    UPDATE products
                    SET reserved_order_id = NULL, updated_at = datetime('now','localtime')
                    WHERE reserved_order_id = ?
                      AND purchase_id NOT IN ({placeholders})
                      AND delivery_id IS NULL
                """, [order_id] + purchase_ids)
            else:
                cur.execute("""
                    UPDATE products SET reserved_order_id = NULL 
                    WHERE reserved_order_id = ? AND delivery_id IS NULL
                """, (order_id,))

            # B. [Allocation] ✅ 연결된 발주들에 대해 '재할당' 실행 (새로 연결된 주문 챙겨주기)
            #    (이 주문이 새로 연결되었다면, FIFO 순위에 따라 재고를 가져오게 됨)
            if purchase_ids:
                for p_id in purchase_ids:
                    # 해당 발주의 '유효한 재고' 조회
                    cur.execute("""
                        SELECT id FROM products 
                        WHERE purchase_id = ? 
                          AND delivery_id IS NULL 
                          AND consumed_by_product_id IS NULL
                    """, (p_id,))
                    product_ids = [r[0] for r in cur.fetchall()]

                    if product_ids:
                        # 현재 커넥션을 공유하여 할당 로직 실행
                        allocate_products_fifo(product_ids, p_id, conn=conn)

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def update_purchase_with_items(purchase_id: int, purchase_data: dict, items: list, order_ids: list = None):
    """발주 수정: 헤더, 품목, 주문 연결 정보 수정 (+ 연결 해제 시 정리, 연결 시 자동 할당)"""
    conn = get_conn()
    try:
        cur = conn.cursor()

        # 1. 헤더 업데이트
        cur.execute("""
            UPDATE purchases SET 
                purchase_no = ?, purchase_dt = ?, actual_amount = ?, status = ?, 
                updated_at = datetime('now','localtime')
            WHERE id = ?
        """, (purchase_data['purchase_no'], purchase_data.get('purchase_dt'),
              purchase_data.get('actual_amount', 0), purchase_data.get('status', '발주'),
              purchase_id))

        # 2. 품목 재설정
        cur.execute("DELETE FROM purchase_items WHERE purchase_id = ?", (purchase_id,))
        for item in items:
            cur.execute("""
                INSERT INTO purchase_items (
                    purchase_id, item_code, rev, product_name,
                    qty, unit_price_cents, currency
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                purchase_id, item.get('item_code'), item.get('rev'), item['product_name'],
                item['qty'], item['unit_price_cents'], item.get('currency', 'KRW')
            ))

        # 3. 주문 연결 정보 업데이트
        if order_ids is not None:
            cur.execute("DELETE FROM purchase_order_links WHERE purchase_id = ?", (purchase_id,))
            for order_id in order_ids:
                cur.execute("INSERT INTO purchase_order_links (purchase_id, order_id) VALUES (?, ?)",
                            (purchase_id, order_id))

            # A. [Cleanup] 연결 해제된 주문에 대한 예약 풀기
            if order_ids:
                placeholders = ', '.join('?' for _ in order_ids)
                cur.execute(f"""
                    UPDATE products 
                    SET reserved_order_id = NULL, updated_at = datetime('now','localtime')
                    WHERE purchase_id = ? 
                      AND reserved_order_id IS NOT NULL
                      AND reserved_order_id NOT IN ({placeholders})
                      AND delivery_id IS NULL
                """, [purchase_id] + order_ids)
            else:
                # 연결된 주문이 없으면 모든 예약 해제
                cur.execute("""
                    UPDATE products SET reserved_order_id = NULL 
                    WHERE purchase_id = ? AND delivery_id IS NULL
                """, (purchase_id,))

        # 4. [Allocation] ✅ 이 발주의 재고에 대해 '재할당' 실행
        #    (새로 연결된 주문이 있거나 연결이 끊긴 후 남는 재고를 다시 분배)
        cur.execute("""
            SELECT id FROM products 
            WHERE purchase_id = ? 
              AND delivery_id IS NULL 
              AND consumed_by_product_id IS NULL
        """, (purchase_id,))
        product_ids = [r[0] for r in cur.fetchall()]

        if product_ids:
            allocate_products_fifo(product_ids, purchase_id, conn=conn)

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
    """발주 생성: 헤더, 품목, **주문 연결 정보** 저장"""
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
            purchase_data.get('actual_amount', 0)
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

        # ✅ [수정] 주문 연결 정보 저장 (필수!)
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
        SELECT 
            o.id, 
            o.order_no, 
            GROUP_CONCAT(oi.product_name, ' | ') as desc, 
            SUM(oi.qty) as qty, 

            /* [수정] 분할 납기를 포함한 '진짜' 최종 납기일 조회 */
            COALESCE(
                (SELECT MAX(s.due_date) 
                 FROM order_shipments s 
                 JOIN order_items oi_s ON s.order_item_id = oi_s.id 
                 WHERE oi_s.order_id = o.id), 
                o.final_due, 
                o.req_due
            ) as due_date

        FROM orders o
        LEFT JOIN order_items oi ON o.id = oi.order_id
        WHERE o.order_no IS NOT NULL 
        GROUP BY o.id

        /* [수정] 날짜가 빠른 순 (오름차순)으로 정렬 */
        ORDER BY due_date ASC, o.order_no ASC
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


def get_linked_purchases(order_id: int):
    """(새 함수) 특정 주문에 연결된 발주 목록을 반환"""
    sql = """
        SELECT p.id, p.purchase_no, GROUP_CONCAT(pi.product_name, ' | ') as description,
               SUM(pi.qty) as qty, p.purchase_dt
        FROM purchases p
        JOIN purchase_order_links pol ON p.id = pol.order_id
        LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
        WHERE pol.order_id = ?
        GROUP BY p.id
        ORDER BY p.purchase_dt
    """
    return query_all(sql, (order_id,))


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
            cur.execute("""
                INSERT INTO delivery_items (
                    delivery_id, item_code, serial_no, manufacture_code, product_name, qty
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                delivery_id,
                item.get('item_code'),
                item.get('serial_no'),
                item.get('manufacture_code'),
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


# app/db.py 파일의 mark_products_as_delivered 함수를 아래 코드로 교체하세요.

# app/db.py

def mark_products_as_delivered(delivery_id: int, conn=None):
    """
    납품됨으로 표시 (수정: S/N을 >= (범위)가 아닌 = (정확히) 일치시킴)
    """
    should_close = False
    if conn is None:
        conn = get_conn()
        should_close = True

    try:
        cur = conn.cursor()

        # 1. 이 납품에 포함된 *개별* 품목/S/N 정보를 가져옴
        cur.execute("""
            SELECT item_code, serial_no, qty
            FROM delivery_items 
            WHERE delivery_id = ? AND serial_no IS NOT NULL
        """, (delivery_id,))
        items_to_deliver = cur.fetchall()

        for item_code, serial_no_to_deliver, qty_to_deliver in items_to_deliver:

            # 2. ✅ [버그 수정]
            #    serial_no >= ? (시작 S/N) 가 아닌,
            #    serial_no = ? (정확한 S/N) 로 제품을 찾아야 함
            #    또한, 이미 다른 납품에 연결된 S/N은 업데이트하지 않도록 (delivery_id IS NULL) 방어
            cur.execute("""
                SELECT id FROM products
                WHERE part_no = ? AND serial_no = ? AND delivery_id IS NULL
                LIMIT ?
            """, (item_code, serial_no_to_deliver, qty_to_deliver))  # qty_to_deliver는 항상 1

            product_ids_to_update = [row[0] for row in cur.fetchall()]

            # 3. 조회된 제품들의 delivery_id를 한 번에 업데이트
            if not product_ids_to_update:
                continue

            placeholders = ', '.join('?' for _ in product_ids_to_update)
            sql = f"""
                UPDATE products
                SET delivery_id = ?, delivered_at = datetime('now', 'localtime')
                WHERE id IN ({placeholders})
            """

            params = [delivery_id] + product_ids_to_update
            cur.execute(sql, tuple(params))

        if should_close:
            conn.commit()

    except Exception as e:
        if should_close: conn.rollback()
        raise e
    finally:
        if should_close: conn.close()


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


def get_repairs_for_product(product_id: int):
    """특정 제품에 대한 모든 수리 이력 조회"""
    sql = """
        SELECT
            id, receipt_date, quality_report_no, defect_symptom, 
            repair_details, status, repair_date, redelivery_invoice_no
        FROM product_repairs
        WHERE product_id = ?
        ORDER BY receipt_date DESC, id DESC
    """
    return query_all(sql, (product_id,))


# app/db.py 내부의 get_all_repairs 함수 수정

def get_all_repairs(status_filter="전체", order_by_clause="r.receipt_date DESC"):
    conn = get_conn()
    cur = conn.cursor()

    # ✅ [수정] 8번째 컬럼을 r.root_cause_occurrence -> r.investigation_internal 로 변경
    sql = """
        SELECT 
            r.id,
            r.receipt_date, 
            r.quality_report_no,
            p.part_no, 
            p.product_name, 
            p.serial_no,
            r.defect_symptom,
            r.investigation_internal, -- 당사 조사내용으로 변경
            r.status,
            r.repair_date,
            r.redelivery_invoice_no,
            r.product_id
        FROM product_repairs r
        LEFT JOIN products p ON r.product_id = p.id
    """

    params = []
    if status_filter != "전체":
        sql += " WHERE r.status = ?"
        params.append(status_filter)

    sql += f" ORDER BY {order_by_clause}"

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_repair_details(repair_id: int):
    sql = """
        SELECT
            product_id, receipt_date, quality_report_no, defect_symptom,
            investigation_customer, investigation_internal, immediate_action,
            root_cause_occurrence, root_cause_outflow, repair_details,
            prevention_occurrence, prevention_outflow, status, repair_date,
            redelivery_invoice_no,

            cost_deposit, cost_air_freight, cost_shipping_jp, cost_tax_jp,

            repair_pic, ncr_qty, 

            import_invoice_no, import_declaration_no, import_carrier,

            defect_date, -- 25th field
            r.attachments -- ✅ [추가] attachments 필드 (26th field)

        FROM product_repairs r
        WHERE id = ?
    """
    return query_one(sql, (repair_id,))


def add_or_update_repair(data, repair_id=None, external_cursor=None):  # ✅ external_cursor 인자 추가
    """
    수리 내역 추가 또는 수정
    :param external_cursor: 외부에서 트랜잭션을 묶을 때 전달받는 커서
    """
    # 외부 커서가 있으면 그것을 사용, 없으면 새로 연결 생성 (기존 방식 호환)
    conn = None
    if external_cursor:
        cur = external_cursor
    else:
        conn = get_conn()
        cur = conn.cursor()

    try:
        # 쿼리문 준비 (기존 로직 유지)
        columns = [
            'product_id', 'receipt_date', 'quality_report_no', 'defect_symptom',
            'root_cause_occurrence', 'root_cause_outflow', 'prevention_occurrence', 'prevention_outflow',
            'repair_date', 'status', 'redelivery_invoice_no',
            'investigation_customer', 'investigation_internal', 'immediate_action', 'repair_details',
            'cost_deposit', 'cost_air_freight', 'cost_shipping_jp', 'cost_tax_jp',
            'repair_pic', 'ncr_qty',
            'import_invoice_no', 'import_declaration_no', 'import_carrier',
            'defect_date',
            'attachments'  # ✅ [추가] attachments 필드
        ]

        # 딕셔너리에서 값 추출 (없으면 None)
        values = [data.get(col) for col in columns]

        if repair_id:
            # UPDATE
            set_clause = ", ".join([f"{col}=?" for col in columns])
            # updated_at 자동 갱신을 위해 쿼리에 포함
            sql = f"UPDATE product_repairs SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?"
            cur.execute(sql, values + [repair_id])
        else:
            # INSERT
            placeholders = ", ".join(["?" for _ in columns])
            sql = f"INSERT INTO product_repairs ({', '.join(columns)}) VALUES ({placeholders})"
            cur.execute(sql, values)

        # 외부 커서가 없을 때만 여기서 커밋 및 종료
        if conn:
            conn.commit()

    except Exception as e:
        print(f"수리 내역 저장 오류: {e}")
        if conn: conn.rollback()
        raise e
    finally:
        # 외부 커서가 없을 때만 닫기
        if conn:
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


def update_repair_redelivery_status(repair_id: int, invoice_no: str):
    """수리품 재출고 후 상태를 '재출고'로 변경하고 인보이스 번호를 기록"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE product_repairs
            SET status = '재출고',
                redelivery_invoice_no = ?,
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (invoice_no, repair_id))
        conn.commit()
    finally:
        conn.close()


def get_shipments_for_order_item(order_item_id: int):
    """특정 주문 품목에 대한 모든 분할 납기 일정 조회"""
    sql = "SELECT id, due_date, ship_qty FROM order_shipments WHERE order_item_id = ? ORDER BY due_date"
    return query_all(sql, (order_item_id,))


def save_shipments_for_order_item(order_item_id: int, shipments: list, conn):
    """특정 주문 품목에 대한 분할 납기 일정을 저장 (기존 데이터는 삭제 후 재등록)"""
    cur = conn.cursor()
    # 기존 데이터 삭제
    cur.execute("DELETE FROM order_shipments WHERE order_item_id = ?", (order_item_id,))
    # 새 데이터 추가
    for shipment in shipments:
        cur.execute(
            "INSERT INTO order_shipments (order_item_id, due_date, ship_qty) VALUES (?, ?, ?)",
            (order_item_id, shipment['due_date'], shipment['ship_qty'])
        )


def get_full_schedule_for_order(order_id: int):
    """특정 주문에 대한 모든 품목 및 분할 납기 일정을 조회 (단순 납기 포함)"""
    order_info = query_one("SELECT req_due FROM orders WHERE id = ?", (order_id,))
    default_due_date = order_info[0] if order_info else None

    items_sql = "SELECT id, product_name, qty FROM order_items WHERE order_id = ?"
    order_items = query_all(items_sql, (order_id,))

    schedule = []
    for item_id, product_name, total_qty in order_items:
        item_info = {
            'item_id': item_id,
            'product_name': product_name,
            'total_qty': total_qty,
            'shipments': []
        }

        shipments_sql = "SELECT id, due_date, ship_qty FROM order_shipments WHERE order_item_id = ? ORDER BY due_date"
        shipments = query_all(shipments_sql, (item_id,))

        if shipments:
            item_info['shipments'] = [
                {'shipment_id': s[0], 'due_date': s[1], 'ship_qty': s[2]} for s in shipments
            ]
        else:
            item_info['shipments'] = [{
                'shipment_id': None,
                'due_date': default_due_date,
                'ship_qty': total_qty
            }]

        schedule.append(item_info)

    return schedule


def save_schedule_for_item(order_item_id: int, new_shipments: list, reason: str):
    """주문 품목의 전체 납기 일정을 새로 저장하고, 변경 이력을 기록합니다."""
    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("SELECT due_date, ship_qty FROM order_shipments WHERE order_item_id = ?", (order_item_id,))
        old_shipments_raw = cur.fetchall()
        old_schedule_str = ", ".join([f"{s[0]} ({s[1]}개)" for s in old_shipments_raw])

        cur.execute("DELETE FROM order_shipments WHERE order_item_id = ?", (order_item_id,))

        new_schedule_str = ", ".join([f"{s['due_date']} ({s['ship_qty']}개)" for s in new_shipments])
        for shipment in new_shipments:
            cur.execute(
                "INSERT INTO order_shipments (order_item_id, due_date, ship_qty) VALUES (?, ?, ?)",
                (order_item_id, shipment['due_date'], shipment['ship_qty'])
            )

        if old_schedule_str != new_schedule_str:
            cur.execute("""
                INSERT INTO shipment_date_changes 
                (order_item_id, change_request_date, old_schedule, new_schedule, reason)
                VALUES (?, date('now','localtime'), ?, ?, ?)
            """, (order_item_id, old_schedule_str, new_schedule_str, reason))

        conn.commit()
    finally:
        conn.close()


def get_shipment_change_history(order_item_id: int):
    """특정 주문 품목의 모든 변경 이력을 조회합니다."""
    sql = "SELECT change_request_date, old_schedule, new_schedule, reason FROM shipment_date_changes WHERE order_item_id = ? ORDER BY created_at DESC"
    return query_all(sql, (order_item_id,))


def is_purchase_completed(purchase_id: int) -> bool:
    """
    발주가 완료되었는지 확인 (수정: 재고 유무 우선)
    [수정된 로직]
    1. 수동 완료 (status == '완료')
    2. (재고 확인) 재고가 1개라도 남아있으면 (produced > delivered) -> 무조건 미완료(False)
    3. (주문 연결 시) 연결된 모든 주문이 '청구 완료'
    4. (주문 미연결 시) 발주량 = 생산량 = 납품량
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        # 조건 1: 수동으로 '완료' 상태인지 확인
        cur.execute("SELECT status FROM purchases WHERE id = ?", (purchase_id,))
        result = cur.fetchone()
        if result and result[0] == '완료':
            return True

        # --- [수정] 재고 및 주문 상태를 확인하기 위해 2개 쿼리를 먼저 실행 ---

        # 쿼리 A: 주문 연결 상태
        cur.execute("""
            SELECT COUNT(o.id) as total_orders,
                   SUM(CASE WHEN COALESCE(o.invoice_done, 0) = 1 THEN 1 ELSE 0 END) as completed_orders
            FROM purchase_order_links pol
            JOIN orders o ON pol.order_id = o.id
            WHERE pol.purchase_id = ?
        """, (purchase_id,))
        inv_result = cur.fetchone()
        total_orders, completed_orders = 0, 0
        if inv_result:
            total_orders, completed_orders = inv_result

        # 쿼리 B: 수량 상태 (소모량 포함)
        cur.execute("""
            SELECT 
                SUM(pi.qty) as order_qty,
                (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id) as produced_qty,
                (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id AND pr.delivery_id IS NOT NULL) as delivered_qty,
                (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id AND pr.consumed_by_product_id IS NOT NULL) as consumed_qty
            FROM purchases p
            LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
            WHERE p.id = ?
            GROUP BY p.id
        """, (purchase_id,))

        qty_result = cur.fetchone()
        order_qty, produced_qty, delivered_qty, consumed_qty = 0, 0, 0, 0
        if qty_result:
            # None을 0으로 처리
            order_qty = qty_result[0] or 0
            produced_qty = qty_result[1] or 0
            delivered_qty = qty_result[2] or 0
            consumed_qty = qty_result[3] or 0

        # --- 조건 2: (재고 유무) 재고가 남아있으면 무조건 미완료 ---
        # (생산량) - (납품량) - (소모량) > 0 이면 재고가 있는 것
        if produced_qty > (delivered_qty + consumed_qty):
            return False

        # --- 조건 3: (주문 연결 시) 재고가 0일 때, 연결된 주문들의 청구 상태 확인 ---
        if total_orders > 0:
            return total_orders == completed_orders  # (예: total=1, completed=0) -> False

        # --- 조건 4: (주문 미연결 시) 재고가 0이고 주문도 없을 때, 수량 일치 확인 ---
        # 발주량 == (납품량 + 소모량) 인지 확인
        if order_qty > 0 and order_qty == produced_qty and order_qty == (delivered_qty + consumed_qty):
            return True

        # 위 모든 조건에 해당하지 않으면 미완료
        return False

    finally:
        if conn:
            conn.close()


def check_and_update_order_completion(order_id: int, conn):
    """
    (새 함수) 주어진 order_id에 대해, 연결된 모든 납품의 청구 완료 상태를 확인하고
    주문(orders) 테이블의 invoice_done 플래그를 자동으로 업데이트합니다.

    (납품 탭에서 체크박스를 누를 때마다 이 함수가 호출됩니다.)
    """
    cur = conn.cursor()

    # 1. 이 주문이 완료되기 위해 필요한 품목별 총 수량 (e.g., A: 10개, B: 5개)
    cur.execute("SELECT item_code, SUM(qty) FROM order_items WHERE order_id = ? GROUP BY item_code", (order_id,))
    order_qtys_needed = {row[0]: row[1] for row in cur.fetchall() if row[0]}

    if not order_qtys_needed:
        return  # 주문에 품목이 없으면(이상한 경우) 자동 완료 대상이 아님

    # 2. 이 주문에 연결된 *'청구완료(invoice_done=1)'된* 납품들의 품목별 총 수량
    cur.execute("""
        SELECT di.item_code, SUM(di.qty)
        FROM delivery_items di
        JOIN deliveries d ON di.delivery_id = d.id
        JOIN delivery_order_links dol ON d.id = dol.delivery_id
        WHERE dol.order_id = ? AND d.invoice_done = 1 AND di.item_code IS NOT NULL
        GROUP BY di.item_code
    """, (order_id,))
    delivered_qtys_done = {row[0]: row[1] for row in cur.fetchall()}

    # 3. 두 수량을 비교
    is_fully_completed = True
    for item_code, qty_needed in order_qtys_needed.items():
        qty_delivered_done = delivered_qtys_done.get(item_code, 0)

        if qty_delivered_done < qty_needed:
            is_fully_completed = False  # 하나라도 부족하면 미완료
            break

    # 4. orders 테이블의 invoice_done 플래그를 자동 업데이트
    new_status = 1 if is_fully_completed else 0
    cur.execute("UPDATE orders SET invoice_done = ? WHERE id = ?", (new_status, order_id))


def get_schedule_for_month(year: int, month: int) -> dict:
    """
    - [수정] 'orders'와 'order_shipments' 테이블 모두에서 날짜를 검색
    """
    month_str = f"{year}-{month:02d}"

    # ✅ [수정] '단순 납기'와 '분할 납기'를 모두 합쳐서 조회
    sql = """
        SELECT 
            AllDueDates as due_date, 
            COUNT(*) as shipment_count
        FROM (
            -- 1. 분할 납기
            SELECT 
                os.due_date as AllDueDates
            FROM order_shipments os
            WHERE strftime('%Y-%m', os.due_date) = ?

            UNION ALL

            -- 2. 단순 납기 (분할 납기에 없는 주문)
            SELECT 
                COALESCE(o.final_due, o.req_due) as AllDueDates
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            WHERE 
                oi.id NOT IN (SELECT DISTINCT order_item_id FROM order_shipments)
                AND strftime('%Y-%m', COALESCE(o.final_due, o.req_due)) = ?
        )
        WHERE AllDueDates IS NOT NULL
        GROUP BY AllDueDates
    """

    try:
        # ✅ [수정] 파라미터를 2개 전달 (UNION ALL의 각 쿼리용)
        rows = query_all(sql, (month_str, month_str))
        # 딕셔너리로 변환
        return {date: count for date, count in rows}
    except Exception as e:
        print(f"월별 납품 일정 조회 오류: {e}")
        return {}


def get_schedule_details_for_date(date_str: str) -> list:
    """
    (새 함수) 납품 달력의 '상세 목록'용 데이터를 반환합니다.
    - [수정] 'orders'와 'order_shipments' 테이블 모두에서 날짜를 검색
    """
    sql = """
        SELECT * FROM (
            -- 쿼리 A: '분할 납기'가 설정된 건 (order_shipments)
            SELECT
                o.order_no,
                oi.product_name,
                os.ship_qty,
                (oi.unit_price_cents * os.ship_qty) / 100.0 as amount_jpy,
                o.id as order_id,
                oi.item_code
            FROM order_shipments os
            JOIN order_items oi ON os.order_item_id = oi.id
            JOIN orders o ON oi.order_id = o.id
            WHERE os.due_date = ?

            UNION ALL

            -- 쿼리 B: '단순 납기' 건 (orders.final_due 또는 req_due)
            SELECT 
                o.order_no,
                oi.product_name,
                oi.qty as ship_qty,
                (oi.unit_price_cents * oi.qty) / 100.0 as amount_jpy,
                o.id as order_id,
                oi.item_code
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            WHERE 
                oi.id NOT IN (SELECT DISTINCT order_item_id FROM order_shipments)
                AND COALESCE(o.final_due, o.req_due) = ?
        )
        ORDER BY order_no, product_name
    """
    try:
        # ✅ [수정] 파라미터가 2개가 필요합니다 (date_str, date_str)
        return query_all(sql, (date_str, date_str))
    except Exception as e:
        print(f"일자별 납품 상세 조회 오류: {e}")
        return []


def calculate_fifo_allocation_margins():
    """
    (새 함수) FIFO 방식으로 발주별 할당 여유 수량을 정밀 계산합니다.
    1. 발주별 초기 여유분 = (총 발주량) - (조립 소모량)
    2. 주문별 필요 수량을 발주일에 따라 오래된 발주부터 차감 (선입선출)
    3. 최종 남은 수량이 할당 여유분이 됨
    """
    conn = get_conn()
    cur = conn.cursor()

    allocations = {}  # {purchase_id: remaining_qty}

    try:
        # 1. 모든 발주 정보 조회 (ID, 날짜, 총수량, 소모량)
        #    Python 리스트에 저장하여 메모리상에서 계산
        cur.execute("""
            SELECT 
                p.id, p.purchase_dt,
                SUM(pi.qty) as total_qty,
                (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id AND pr.consumed_by_product_id IS NOT NULL) as consumed_qty
            FROM purchases p
            JOIN purchase_items pi ON p.id = pi.purchase_id
            GROUP BY p.id
            ORDER BY p.purchase_dt, p.id
        """)

        purchases = []
        for row in cur.fetchall():
            p_id, p_dt, total, consumed = row

            # 해당 발주가 포함하는 품목 코드 조회 (품목별 매칭을 위해)
            cur.execute("SELECT item_code FROM purchase_items WHERE purchase_id = ?", (p_id,))
            item_codes = {r[0] for r in cur.fetchall()}

            remaining = (total or 0) - (consumed or 0)
            purchases.append({
                'id': p_id, 'dt': p_dt, 'remaining': remaining, 'items': item_codes
            })
            allocations[p_id] = remaining  # 초기값 설정

        # 2. 발주와 연결된 모든 주문 조회 (오래된 주문부터 처리)
        cur.execute("""
            SELECT DISTINCT o.id, o.order_dt 
            FROM orders o
            JOIN purchase_order_links pol ON o.id = pol.order_id
            ORDER BY o.order_dt, o.id
        """)
        orders = cur.fetchall()

        for o_id, o_dt in orders:
            # 2-1. 이 주문의 품목별 수량 조회
            cur.execute("SELECT item_code, qty FROM order_items WHERE order_id = ?", (o_id,))
            order_items = cur.fetchall()  # [(item_code, qty), ...]

            # 2-2. 이 주문에 연결된 발주 ID 목록 조회
            cur.execute("SELECT purchase_id FROM purchase_order_links WHERE order_id = ?", (o_id,))
            linked_p_ids = {r[0] for r in cur.fetchall()}

            # 2-3. FIFO 할당 로직 (품목별로 처리)
            for item_code, qty_needed in order_items:
                # 이 주문에 연결된 발주 중, 해당 품목을 취급하는 발주들을 날짜순으로 필터링
                # (purchases 리스트가 이미 날짜순으로 정렬되어 있으므로 순서대로 찾으면 됨)
                candidate_purchases = [
                    p for p in purchases
                    if p['id'] in linked_p_ids and item_code in p['items']
                ]

                for p in candidate_purchases:
                    if qty_needed <= 0:
                        break

                    # 남은 수량이 있으면 가져다 씀
                    if p['remaining'] > 0:
                        take = min(qty_needed, p['remaining'])
                        p['remaining'] -= take
                        qty_needed -= take

                        # 결과 딕셔너리 갱신
                        allocations[p['id']] = p['remaining']

    except Exception as e:
        print(f"FIFO 계산 오류: {e}")
    finally:
        conn.close()

    return allocations


def get_available_purchases():
    """
    '새 제품 추가' 등에서 사용하는 발주 목록 반환 (수정됨: FIFO 할당 적용)
    """
    # 1. 기본 정보 조회 (기존 쿼리 사용하되 linked_order_qty 계산은 무시)
    sql = """
        SELECT
            p.id,
            p.purchase_no,
            GROUP_CONCAT(pi.product_name, ' | ') as purchase_desc,
            SUM(pi.qty) as ordered_qty, 
            p.purchase_dt,
            (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id) as produced_qty,
            (SELECT COUNT(*) FROM products pr 
             WHERE pr.purchase_id = p.id AND pr.delivery_id IS NOT NULL) as delivered_qty,
            (SELECT COUNT(*) FROM products pr
             WHERE pr.purchase_id = p.id AND pr.consumed_by_product_id IS NOT NULL) as consumed_qty,
            0 as dummy_linked_qty, -- (Python에서 계산하므로 SQL 계산 제외)
            (SELECT pr.serial_no FROM products pr
             WHERE pr.purchase_id = p.id AND pr.delivery_id IS NULL
             ORDER BY pr.serial_no ASC LIMIT 1
            ) as first_available_serial
        FROM purchases p
        LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
        WHERE p.purchase_no IS NOT NULL
        AND COALESCE(p.status, '발주') != '완료'
        GROUP BY p.id
        ORDER BY p.purchase_dt DESC
    """
    all_purchases = query_all(sql)

    # ✅ [추가] FIFO 방식으로 정확한 잔여 할당량 계산
    fifo_margins = calculate_fifo_allocation_margins()

    available_list = []
    for row in all_purchases:
        (p_id, p_no, p_desc, ordered_qty, p_dt, produced_qty, delivered_qty, consumed_qty, _, first_serial) = row

        ordered_qty = ordered_qty or 0
        produced_qty = produced_qty or 0
        delivered_qty = delivered_qty or 0
        consumed_qty = consumed_qty or 0

        # 재고 수량
        stock_qty = produced_qty - delivered_qty - consumed_qty

        # ✅ [수정] 할당 여유분: FIFO 계산 결과 사용 (없으면 0)
        allocation_margin = fifo_margins.get(p_id, 0)

        # 필터링
        production_needed = (produced_qty < ordered_qty)
        stock_available = (stock_qty > 0)

        if not production_needed and not stock_available:
            continue

        available_list.append(
            (p_id, p_no, p_desc, ordered_qty, p_dt, stock_qty, allocation_margin, produced_qty, first_serial))

    return available_list


def get_linked_purchase_ids_from_orders(order_ids: list[int]) -> set[int]:
    """(새 함수) '납품 수정' 창에서 주문 선택 시, 연결된 발주 ID를 찾기 위한 헬퍼"""
    if not order_ids:
        return set()

    placeholders = ', '.join('?' for _ in order_ids)
    sql = f"""
        SELECT DISTINCT purchase_id 
        FROM purchase_order_links 
        WHERE order_id IN ({placeholders})
    """
    try:
        rows = query_all(sql, tuple(order_ids))
        return {row[0] for row in rows}
    except Exception as e:
        print(f"주문->발주 ID 조회 오류: {e}")
        return set()


def get_bom_requirements(parent_item_code: str) -> list[dict]:
    """
    (새 함수) 조립품(부모) 코드를 기반으로 필요한 자식 부품 목록(BOM)을 반환합니다.
    """
    sql = """
        SELECT b.child_item_code, b.quantity_required, pm.product_name
        FROM bom_items b
        LEFT JOIN product_master pm ON b.child_item_code = pm.item_code
        WHERE b.parent_item_code = ?
        ORDER BY pm.product_name
    """
    try:
        rows = query_all(sql, (parent_item_code,))
        return [
            {'child_code': row[0], 'qty_req': row[1], 'name': row[2]}
            for row in rows
        ]
    except Exception as e:
        print(f"BOM 요구사항 조회 오류: {e}")
        return []


def get_available_stock_for_bom(child_item_codes: list[str]) -> dict:
    """
    (새 함수) 조립에 필요한 자식 부품 목록을 받아, 현재 납품/소모되지 않은 재고(S/N)를 반환합니다.
    [수정] 품목 유형(item_type)에 따라 S/N 정렬 순서를 변경합니다.
    """
    if not child_item_codes:
        return {}

    placeholders = ', '.join('?' for _ in child_item_codes)
    sql = f"""
        SELECT 
            pr.id, pr.part_no, pr.serial_no, pr.product_name,
            COALESCE(pm.item_type, 'SELLABLE') as item_type
        FROM products pr
        -- ✅ [추가] product_master와 JOIN하여 item_type 확인
        LEFT JOIN product_master pm ON pr.part_no = pm.item_code
        WHERE pr.part_no IN ({placeholders})
        AND pr.delivery_id IS NULL          -- 납품되지 않았고
        AND pr.consumed_by_product_id IS NULL -- 다른 조립에 소모되지 않은
        AND pr.reserved_order_id IS NULL      -- ✅ [추가] 다른 주문에 예약되지 않은 것만!

        -- ✅ [수정] 정렬 로직 변경
        ORDER BY
            pr.part_no,
            -- item_type이 'SELLABLE'이면 DESC (KT112가 위로), 그 외('SUB_COMPONENT')는 ASC (KT011이 위로)
            CASE COALESCE(pm.item_type, 'SELLABLE')
                WHEN 'SELLABLE' THEN pr.serial_no END DESC,
            CASE COALESCE(pm.item_type, 'SELLABLE')
                WHEN 'SUB_COMPONENT' THEN pr.serial_no END ASC,
            pr.serial_no ASC -- 기본값 (혹시 모를 경우)
    """
    try:
        rows = query_all(sql, tuple(child_item_codes))

        # 품목코드별로 재고 리스트를 그룹화
        stock_map = defaultdict(list)
        # ✅ [수정] 5개 항목 언패킹
        for prod_id, part_no, serial_no, name, item_type in rows:
            # ⬇︎ [수정] 이 블록의 들여쓰기를 확인하세요.
            stock_map[part_no].append({
                'product_id': prod_id,
                'serial_no': serial_no,
                'name': name,
                'item_type': item_type
            })
        return stock_map
    except Exception as e:
        print(f"BOM 재고 조회 오류: {e}")
        return {}


def create_products(product_data: dict, production_qty: int, consumed_items: list[int] = None):
    """
    (수정됨) 새 제품을 생성하고, 연결된 주문에 FIFO 방식으로 자동 할당합니다.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        purchase_id = product_data.get('purchase_id')

        newly_created_product_ids = []

        # 1. 새 제품(부모)을 'production_qty'만큼 생성
        for i in range(production_qty):
            cur.execute("""
                INSERT INTO products
                (manufacture_date, part_no, product_name, serial_no, manufacture_code, purchase_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                product_data.get('manufacture_date'),  # 신규 생성시엔 보통 NULL이지만 받아옴
                product_data.get('part_no'),
                product_data.get('product_name'),
                product_data.get('serial_no'),  # 신규 생성시엔 NULL일 수 있음
                product_data.get('manufacture_code'),
                purchase_id
            ))
            newly_created_product_ids.append(cur.lastrowid)

        # 2. (조립 생산 시) 부품 소모 처리
        if consumed_items and newly_created_product_ids:
            if len(newly_created_product_ids) > 1:
                # 조립은 1개씩만 생성한다고 가정 (로직 복잡도 방지)
                raise Exception("BOM 조립 시 1개 초과 동시 생성은 아직 지원되지 않습니다.")

            parent_product_id = newly_created_product_ids[0]
            placeholders = ', '.join('?' for _ in consumed_items)
            sql = f"UPDATE products SET consumed_by_product_id = ? WHERE id IN ({placeholders})"
            params = [parent_product_id] + consumed_items
            cur.execute(sql, tuple(params))

        conn.commit()

        # 3. [핵심] 생산된 제품들에 대해 FIFO 주문 할당 실행
        #    (트랜잭션을 분리하여 안전하게 처리)
        if purchase_id and newly_created_product_ids:
            allocate_products_fifo(newly_created_product_ids, purchase_id)

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def assign_product_info_batch(product_ids: list, manufacture_date: str, manufacture_code: str, start_serial_seq: int):
    """
    (새 함수) 선택된 미확정 제품들에게 S/N과 제조 정보를 일괄 부여합니다.
    :param start_serial_seq: 시작 시리얼 번호의 숫자 부분 (예: 101 -> KT101)
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        current_seq = start_serial_seq

        for p_id in product_ids:
            # S/N 생성 (KT + 3자리 숫자)
            # 999를 넘어가면 001로 순환하도록 로직 추가 (필요 시)
            sn_num = ((current_seq - 1) % 999) + 1
            new_serial_no = f"KT{sn_num:03d}"

            cur.execute("""
                UPDATE products
                SET manufacture_date = ?,
                    manufacture_code = ?,
                    serial_no = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE id = ?
            """, (manufacture_date, manufacture_code, new_serial_no, p_id))

            current_seq += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_next_purchase_number(year: int, month: int) -> str:
    """TOYYMM-NNN 형식의 다음 발주번호를 생성합니다. (일련번호는 연도 기준)"""

    # 1. [수정] 검색용 접두사 (올해 전체)
    search_prefix = f"TO{year % 100:02d}"  # 예: TO25

    # 2. [수정] 새로 생성할 접두사 (현재 월)
    new_prefix = f"TO{year % 100:02d}{month:02d}-"  # 예: TO2511-

    sql = """
        SELECT purchase_no FROM purchases
        WHERE purchase_no LIKE ?
        ORDER BY purchase_no DESC
        LIMIT 1
    """

    # 3. [수정] '올해 전체' 접두사로 검색
    last_number_row = query_one(sql, (f"{search_prefix}%",))

    if not last_number_row:
        # 올해 첫 발주
        return f"{new_prefix}001"

    try:
        # 4. [수정] 마지막 번호(예: TO2509-017)에서 일련번호(-017)만 추출
        last_serial_str = last_number_row[0].split('-')[-1]  # 예: "017"
        next_serial = int(last_serial_str) + 1

        # 5. [수정] '새로운' 접두사와 '다음' 일련번호를 조합
        return f"{new_prefix}{next_serial:03d}"  # 예: TO2511-018

    except Exception as e:
        print(f"발주번호 생성 오류: {e}")
        return f"{new_prefix}001"


def get_next_delivery_number(year: int, month: int, day: int) -> str:
    """KIYYYYMMDD-NNN 형식의 다음 납품번호를 생성합니다."""
    prefix = f"KI{year:04d}{month:02d}{day:02d}-"  # 예: KI20250121-

    sql = """
        SELECT invoice_no FROM deliveries
        WHERE invoice_no LIKE ?
        ORDER BY invoice_no DESC
        LIMIT 1
    """

    last_number_row = query_one(sql, (f"{prefix}%",))

    if not last_number_row:
        return f"{prefix}001"

    try:
        last_serial = last_number_row[0].split('-')[-1]  # 예: "001"
        next_serial = int(last_serial) + 1
        return f"{prefix}{next_serial:03d}"
    except Exception as e:
        print(f"납품번호 생성 오류: {e}")
        return f"{prefix}001"


def update_repair_status_on_delivery(product_id: int, invoice_no: str):
    """
    납품 시: 해당 제품의 '수리완료' 상태인 수리 이력을 '재출고'로 변경하고 인보이스 기입.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        # 가장 최근의 '수리완료' 건을 찾음 (혹시 모를 공백 제거를 위해 TRIM 사용)
        cur.execute("""
            SELECT id FROM product_repairs 
            WHERE product_id = ? AND TRIM(status) = '수리완료'
            ORDER BY receipt_date DESC, id DESC 
            LIMIT 1
        """, (product_id,))
        result = cur.fetchone()

        if result:
            repair_id = result[0]
            cur.execute("""
                UPDATE product_repairs
                SET status = '재출고',
                    redelivery_invoice_no = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE id = ?
            """, (invoice_no, repair_id))
            conn.commit()
            print(f"✅ 수리 이력 업데이트 완료: RepairID {repair_id} -> 재출고 ({invoice_no})")
        else:
            print(f"⚠️ 업데이트 대상 수리 이력 없음 (ProductID: {product_id})")

    except Exception as e:
        print(f"수리 이력 업데이트 실패: {e}")
    finally:
        conn.close()


def revert_repair_status_on_delivery_delete(delivery_id: int):
    """
    납품 삭제 시: 이 납품에 포함되었던 '재출고' 상태의 수리 이력을 다시 '수리완료'로 되돌림.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        # 1. 이 납품(delivery_id)에 포함된 제품들의 ID를 찾음
        cur.execute("SELECT id FROM products WHERE delivery_id = ?", (delivery_id,))
        product_ids = [row[0] for row in cur.fetchall()]

        if not product_ids:
            return

        # 2. 찾은 제품들 중, 현재 상태가 '재출고'인 수리 이력을 '수리완료'로 롤백
        #    (인보이스 번호도 지움)
        placeholders = ', '.join('?' for _ in product_ids)
        sql = f"""
            UPDATE product_repairs
            SET status = '수리완료',
                redelivery_invoice_no = NULL,
                updated_at = datetime('now', 'localtime')
            WHERE product_id IN ({placeholders}) AND status = '재출고'
        """
        cur.execute(sql, tuple(product_ids))
        conn.commit()
        print(f"✅ 납품 삭제로 인한 수리 이력 롤백 완료 ({cur.rowcount}건)")

    except Exception as e:
        print(f"수리 이력 롤백 실패: {e}")
    finally:
        conn.close()


def reset_product_info_batch(product_ids: list):
    """
    (새 함수) 선택된 제품들의 S/N, 제조일자, 제조코드를 초기화(NULL)하여 미확정 재고로 되돌립니다.
    단, 이미 납품되었거나(delivery_id IS NOT NULL) 소모된(consumed_by...) 제품은 제외합니다.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        placeholders = ', '.join('?' for _ in product_ids)

        # 안전 장치: delivery_id와 consumed_by_product_id가 없는 것만 초기화
        sql = f"""
            UPDATE products
            SET serial_no = NULL,
                manufacture_date = NULL,
                manufacture_code = NULL,
                updated_at = datetime('now', 'localtime')
            WHERE id IN ({placeholders})
              AND delivery_id IS NULL 
              AND consumed_by_product_id IS NULL
        """
        cur.execute(sql, tuple(product_ids))
        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def allocate_products_fifo(product_ids: list, purchase_id: int, conn=None):  # ✅ conn 인자 추가
    """
    (수정됨) 외부 연결(conn)을 받아 트랜잭션을 공유할 수 있도록 변경
    """
    should_close = False
    if conn is None:
        conn = get_conn()
        should_close = True

    try:
        cur = conn.cursor()

        # 1. 입력받은 제품들의 ID와 품목코드(part_no)를 조회하여 그룹화
        placeholders = ', '.join('?' for _ in product_ids)
        cur.execute(f"SELECT id, part_no FROM products WHERE id IN ({placeholders})", tuple(product_ids))

        products_by_item = {}
        for p_id, part_no in cur.fetchall():
            if part_no not in products_by_item:
                products_by_item[part_no] = []
            products_by_item[part_no].append(p_id)

        # 2. 연결된 주문 목록 조회 (날짜순)
        cur.execute("""
            SELECT o.id, 
                   COALESCE(o.final_due, o.req_due) as due_date
            FROM orders o
            JOIN purchase_order_links pol ON o.id = pol.order_id
            WHERE pol.purchase_id = ?
            AND COALESCE(o.invoice_done, 0) = 0
            ORDER BY due_date ASC, o.id ASC
        """, (purchase_id,))
        linked_orders = cur.fetchall()

        if not linked_orders:
            return

        # 3. 품목별로 순회하며 할당 로직 수행
        for part_no, available_ids in products_by_item.items():
            if not part_no: continue

            current_available_ids = list(available_ids)

            for order_id, due_date in linked_orders:
                if not current_available_ids: break

                # A. 필요 수량 조회
                cur.execute("""
                    SELECT SUM(qty) FROM order_items 
                    WHERE order_id = ? AND item_code = ?
                """, (order_id, part_no))
                result = cur.fetchone()
                total_req = result[0] or 0

                if total_req == 0: continue

                # B. 예약된 수량 (소모된 것 제외)
                cur.execute("""
                    SELECT COUNT(*) FROM products 
                    WHERE reserved_order_id = ? 
                      AND part_no = ? 
                      AND delivery_id IS NULL 
                      AND consumed_by_product_id IS NULL
                """, (order_id, part_no))
                reserved_qty = cur.fetchone()[0]

                # C. 납품된 수량
                cur.execute("""
                    SELECT COALESCE(SUM(qty), 0)
                    FROM delivery_items 
                    WHERE order_id = ? AND item_code = ?
                """, (order_id, part_no))
                delivered_qty = cur.fetchone()[0]

                # D. 부족분 계산
                needed_qty = total_req - reserved_qty - delivered_qty

                if needed_qty <= 0: continue

                # E. 할당 실행
                take_qty = min(len(current_available_ids), needed_qty)
                ids_to_assign = current_available_ids[:take_qty]
                current_available_ids = current_available_ids[take_qty:]

                placeholders_update = ', '.join('?' for _ in ids_to_assign)
                cur.execute(f"""
                    UPDATE products 
                    SET reserved_order_id = ?, updated_at = datetime('now','localtime')
                    WHERE id IN ({placeholders_update})
                """, [order_id] + ids_to_assign)

                print(f"✅ 할당 성공: 품목 {part_no} {take_qty}개 -> 주문 {order_id}")

        # ✅ 외부에서 연결을 받은 경우 여기서는 커밋하지 않고 부모에게 맡김
        if should_close:
            conn.commit()

    except Exception as e:
        print(f"FIFO 할당 오류: {e}")
        if should_close:  # 내 거면 롤백
            conn.rollback()
        raise e  # 에러를 상위로 전파
    finally:
        if should_close:
            conn.close()


def recalculate_all_allocations():
    """
    (전체 재계산) 트랜잭션을 하나로 묶어서 처리 (Lock 방지)
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        print("🔄 전체 재고 할당 재계산 시작 (날짜순 FIFO)...")

        # 1. 모든 미출하 재고의 예약 초기화
        cur.execute("UPDATE products SET reserved_order_id = NULL WHERE delivery_id IS NULL")

        # 2. 모든 활성 발주 조회
        cur.execute("""
            SELECT id FROM purchases 
            WHERE status != '완료' 
            ORDER BY purchase_dt ASC, id ASC
        """)
        active_purchases = cur.fetchall()

        # 3. 각 발주별로 재할당 실행
        for (p_id,) in active_purchases:
            # 소모된 것 제외하고 재고 조회
            cur.execute("""
                SELECT id FROM products 
                WHERE purchase_id = ? 
                  AND delivery_id IS NULL 
                  AND consumed_by_product_id IS NULL 
            """, (p_id,))
            p_ids = [r[0] for r in cur.fetchall()]

            if p_ids:
                # ✅ [핵심] 현재 사용 중인 conn을 인자로 넘겨줍니다!
                allocate_products_fifo(p_ids, p_id, conn=conn)

        conn.commit()  # 모든 작업이 끝나면 한 번에 커밋
        print("✅ 전체 재계산 완료.")
        return True

    except Exception as e:
        print(f"재계산 오류: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_defect_stats_by_symptom():
    """(분석용) 불량 증상별 발생 횟수 (내림차순)"""
    sql = """
        SELECT defect_symptom, COUNT(*) as cnt
        FROM product_repairs
        WHERE defect_symptom IS NOT NULL AND defect_symptom != ''
        GROUP BY defect_symptom
        ORDER BY cnt DESC
        LIMIT 10
    """
    return query_all(sql)

def get_defect_stats_by_model(months=60):
    """(분석용) 제품(모델)별 불량 발생 횟수"""
    offset = f"-{months} months"
    sql = """
        SELECT p.product_name, COUNT(*) as cnt
        FROM product_repairs r
        JOIN products p ON r.product_id = p.id
        WHERE r.receipt_date >= date('now', 'start of month', ?)
        GROUP BY p.product_name
        ORDER BY cnt DESC
        LIMIT 10
    """
    return query_all(sql, (offset,))


def get_defect_trend_monthly(months=12):
    """(분석용) 월별 불량 접수 건수 추이 (지정된 개월 수 만큼)"""
    sql = """
        SELECT strftime('%Y-%m', receipt_date) as month, COUNT(*) as cnt
        FROM product_repairs
        WHERE receipt_date IS NOT NULL
        GROUP BY month
        ORDER BY month ASC
        LIMIT ?  -- ✅ 개월 수를 파라미터로 받음
    """
    # (최신 데이터부터 가져오기 위해 서브쿼리를 써야 정확하지만,
    #  여기서는 간단히 LIMIT을 쓰되, ORDER BY DESC 후 다시 정렬하는 게 정석입니다.
    #  하지만 SQLite 특성상 전체 기간이 길지 않다면 ASC로 조회 후 뒷부분을 잘라도 무방합니다.
    #  가장 정확한 로직: 최근 N개월을 가져오려면 날짜 필터링을 하는 게 좋습니다.)

    # [개선된 쿼리] 오늘로부터 N개월 전 데이터부터 조회
    sql = """
        SELECT strftime('%Y-%m', receipt_date) as month, COUNT(*) as cnt
        FROM product_repairs
        WHERE receipt_date >= date('now', 'start of month', ?)
        GROUP BY month
        ORDER BY month ASC
    """
    offset = f"-{months} months"
    return query_all(sql, (offset,))

def get_root_cause_analysis():
    """(분석용) 근본 원인(발생/유출) 텍스트 데이터 조회"""
    sql = """
        SELECT root_cause_occurrence, root_cause_outflow
        FROM product_repairs
        WHERE (root_cause_occurrence IS NOT NULL AND root_cause_occurrence != '')
           OR (root_cause_outflow IS NOT NULL AND root_cause_outflow != '')
    """
    return query_all(sql)


def get_defect_rate_by_model(months=60):
    """
    (분석용) 모델별 판매량(납품) 대비 불량률 조회 (불량률 높은 순)
    - 분모: 선택된 기간(months) 동안의 판매(납품) 수량 (Sales Quantity)
    - 분자: 선택된 기간(months) 동안 접수된 불량 건수
    """
    # 파라미터: "-60 months" 형태의 문자열
    offset = f"-{months} months"

    sql = """
        SELECT 
            D.product_name,
            D.total_qty as sales_count,
            COALESCE(R.defect_qty, 0) as defect_count,
            (CAST(COALESCE(R.defect_qty, 0) AS FLOAT) / D.total_qty) * 100 as defect_rate
        FROM 
            -- 1. 모델별 기간 내 판매량 (분모) - 납품 기준
            (SELECT di.product_name, SUM(di.qty) as total_qty 
             FROM delivery_items di
             JOIN deliveries d ON di.delivery_id = d.id
             WHERE d.ship_datetime >= date('now', 'start of month', ?)
             GROUP BY di.product_name) D
        JOIN
            -- 2. 선택된 기간 내 불량 발생 수 (분자)
            (SELECT p_sub.product_name, COUNT(*) as defect_qty 
             FROM product_repairs r 
             JOIN products p_sub ON r.product_id = p_sub.id 
             WHERE r.receipt_date >= date('now', 'start of month', ?)
             GROUP BY p_sub.product_name) R
        ON D.product_name = R.product_name

        ORDER BY defect_rate DESC
        LIMIT 10
    """
    # 파라미터를 2번 전달 (분모 쿼리용, 분자 쿼리용)
    return query_all(sql, (offset, offset))


def get_monthly_exchange_rates(year: int) -> dict:
    """특정 연도의 월별 환율 정보를 딕셔너리로 반환 {월: 환율}"""
    sql = "SELECT month, rate FROM exchange_rates WHERE year = ?"
    rows = query_all(sql, (year,))
    rates = {row[0]: row[1] for row in rows}

    # 데이터가 없는 달은 기본값(None)으로 채움
    full_data = {}
    for m in range(1, 13):
        full_data[m] = rates.get(m, 0.0)
    return full_data


def save_monthly_exchange_rates(year: int, rates_data: dict):
    """월별 환율 정보를 일괄 저장 (rates_data: {월: 환율})"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        for month, rate in rates_data.items():
            if rate > 0:
                # 있으면 업데이트, 없으면 삽입 (UPSERT)
                cur.execute("""
                    INSERT INTO exchange_rates (year, month, rate, updated_at)
                    VALUES (?, ?, ?, datetime('now','localtime'))
                    ON CONFLICT(year, month) 
                    DO UPDATE SET rate=excluded.rate, updated_at=excluded.updated_at
                """, (year, month, rate))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_yearly_financials(filter_type='range', value=3):
    """
    연도별 매출, 원가, 이익 데이터 조회 (실제 납품 완료 기준)
    - deliveries 테이블을 기준으로, invoice_done=1 인 건만 집계
    - 매출 인식일: deliveries.ship_datetime
    """

    if filter_type == 'year':
        # value가 2025 같은 숫자일 수도 있고 문자열일 수도 있음
        date_cond = f"strftime('%Y', d.ship_datetime) = '{value}'"
        target_years = [str(value)]
    else:
        # 최근 N년
        offset = f"-{value} years"
        date_cond = f"d.ship_datetime >= date('now', 'start of year', '{offset}')"

        from datetime import datetime
        curr = datetime.now().year
        target_years = [str(curr - i) for i in range(value, -1, -1)]

    sql = f"""
        SELECT 
            strftime('%Y', d.ship_datetime) as year,

            -- 1. 매출 (수량 * 주문단가/100 * 환율/100)
            --    주문과 연결된(order_id IS NOT NULL) 항목만 계산
            SUM(
                (di.qty * oi.unit_price_cents / 100.0) * (COALESCE(er.rate, 900.0) / 100.0)
            ) as revenue_krw,

            -- 2. 원가 (수량 * 표준매입단가/100)
            SUM(
                di.qty * (COALESCE(pm.purchase_price_krw, 0) / 100.0)
            ) as cost_krw,

            -- 3. 판매 수량
            SUM(di.qty) as sales_qty

        FROM deliveries d
        JOIN delivery_items di ON d.id = di.delivery_id
        -- 주문 단가를 가져오기 위해 order_items 조인 (주문 연결된 건만)
        JOIN order_items oi ON di.order_id = oi.order_id AND di.item_code = oi.item_code
        -- 표준 원가를 가져오기 위해 product_master 조인
        LEFT JOIN product_master pm ON di.item_code = pm.item_code
        -- 환율 정보 조인 (납품일 기준)
        LEFT JOIN exchange_rates er 
               ON er.year = CAST(strftime('%Y', d.ship_datetime) AS INTEGER)
              AND er.month = CAST(strftime('%m', d.ship_datetime) AS INTEGER)

        WHERE {date_cond}
          AND d.invoice_done = 1
          AND di.order_id IS NOT NULL  -- 주문과 연결된 건만 매출로 인정

        GROUP BY year
    """

    rows = query_all(sql)
    data_map = {row[0]: {'rev': row[1], 'cost': row[2], 'qty': row[3]} for row in rows}

    result = []
    for y in target_years:
        d = data_map.get(y, {'rev': 0, 'cost': 0, 'qty': 0})
        rev = d['rev'] or 0
        cost = d['cost'] or 0
        qty = d['qty'] or 0

        profit = rev - cost
        margin = (profit / rev * 100) if rev > 0 else 0.0

        result.append({
            'year': y,
            'revenue': rev,
            'cost': cost,
            'profit': profit,
            'margin': margin,
            'production_qty': qty
        })

    return result


def get_model_profitability(filter_type='range', value=3):
    """
    모델별 수익성 분석 (실제 납품 완료 기준)
    """
    if filter_type == 'year':
        date_cond = f"strftime('%Y', d.ship_datetime) = '{value}'"
    else:
        offset = f"-{value} years"
        date_cond = f"d.ship_datetime >= date('now', 'start of year', '{offset}')"

    sql = f"""
        SELECT 
            pm.product_name,

            -- 1. 판매수량
            SUM(di.qty) as sales_qty,

            0, 0, -- (평균 단가는 Python에서 계산)

            -- 4. 총 매출액 (KRW)
            SUM(
                (di.qty * oi.unit_price_cents / 100.0) * (COALESCE(er.rate, 900.0) / 100.0)
            ) as total_revenue_krw,

            -- 5. 총 매출원가 (KRW)
            SUM(
                di.qty * (COALESCE(pm.purchase_price_krw, 0) / 100.0)
            ) as total_cost_krw,

            -- 6. 총 마진액
            SUM(
                (di.qty * oi.unit_price_cents / 100.0) * (COALESCE(er.rate, 900.0) / 100.0)
            ) - 
            SUM(
                di.qty * (COALESCE(pm.purchase_price_krw, 0) / 100.0)
            ) as total_margin_krw

        FROM deliveries d
        JOIN delivery_items di ON d.id = di.delivery_id
        JOIN order_items oi ON di.order_id = oi.order_id AND di.item_code = oi.item_code
        LEFT JOIN product_master pm ON di.item_code = pm.item_code
        LEFT JOIN exchange_rates er 
               ON er.year = CAST(strftime('%Y', d.ship_datetime) AS INTEGER)
              AND er.month = CAST(strftime('%m', d.ship_datetime) AS INTEGER)

        WHERE {date_cond}
          AND d.invoice_done = 1
          AND di.order_id IS NOT NULL

        GROUP BY pm.product_name
        ORDER BY total_margin_krw DESC
    """
    return query_all(sql)


def get_available_data_years():
    """데이터가 존재하는 모든 연도 목록을 내림차순으로 반환"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        # 납품일(매출)과 발주일(원가)에 해당하는 모든 연도를 수집
        sql = "SELECT DISTINCT strftime('%Y', ship_datetime) as year FROM deliveries WHERE invoice_done=1 UNION SELECT DISTINCT strftime('%Y', purchase_dt) as year FROM purchases ORDER BY year DESC"
        rows = query_all(sql)
        # 빈 값 제외하고 정수형 리스트로 반환
        return [int(r[0]) for r in rows if r[0] and r[0].isdigit()]
    except Exception:
        return []