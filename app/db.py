# app/db.py

# KOBATECH ?쒗뭹 ?앹궛 愿由????곗씠?곕쿋?댁뒪 (?ㅻ뜑-?곸꽭 援ъ“)



import os

import sqlite3

from collections import defaultdict

from pathlib import Path

from dotenv import load_dotenv



load_dotenv()





def _default_onedrive() -> Path:

    """?쒖뒪?쒖쓽 湲곕낯 OneDrive 寃쎈줈瑜?異붿젙?⑸땲??"""

    home = Path.home()

    guess = home / "OneDrive"

    return guess if guess.exists() else home





DB_DIR = os.environ.get("KOBATECH_DB_DIR") or str(_default_onedrive() / "KOBATECH_DB")

DB_NAME = os.environ.get("KOBATECH_DB_NAME", "production.db")

DB_PATH = Path(DB_DIR) / DB_NAME

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def format_money(val: float | None) -> str:
    """숫자를 통화 형식(3자리 콤마)으로 변환합니다."""
    if val is None:
        return ""
    try:
        return f"{val:,.0f}"
    except Exception:
        return str(val)



SCHEMA_SQL = """

PRAGMA foreign_keys = ON;



/* ?쒗뭹 留덉뒪???뺣낫 ?뚯씠釉?*/

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

  items_per_box INTEGER DEFAULT 1,

  box_l INTEGER DEFAULT 0,

  box_w INTEGER DEFAULT 0,

  box_h INTEGER DEFAULT 0,

  box_weight REAL DEFAULT 0.0,

  max_layer INTEGER DEFAULT 0,

  abbreviation TEXT,

  updated_at TEXT DEFAULT (datetime('now','localtime')),

  UNIQUE(item_code, rev)

);

CREATE INDEX IF NOT EXISTS idx_product_master_item_code ON product_master(item_code);

CREATE INDEX IF NOT EXISTS idx_product_master_product_name ON product_master(product_name);



/* 二쇰Ц ?ㅻ뜑 */

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

  status TEXT DEFAULT '怨꾪쉷',

  created_at TEXT DEFAULT (datetime('now','localtime')),

  updated_at TEXT DEFAULT (datetime('now','localtime'))

);

CREATE INDEX IF NOT EXISTS idx_orders_order_no ON orders(order_no);

CREATE INDEX IF NOT EXISTS idx_orders_req_due ON orders(req_due);

CREATE INDEX IF NOT EXISTS idx_orders_final_due ON orders(final_due);

CREATE INDEX IF NOT EXISTS idx_orders_invoice_done ON orders(invoice_done);



/* 二쇰Ц ?곸꽭 (?덈ぉ) */

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



/* 二쇰Ц ?덈ぉ蹂?遺꾪븷 ?⑷린 ?뚯씠釉?*/

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



/* 諛쒖＜ ?ㅻ뜑 */

CREATE TABLE IF NOT EXISTS purchases (

  id INTEGER PRIMARY KEY AUTOINCREMENT,

  purchase_no TEXT UNIQUE NOT NULL,

  purchase_dt TEXT,

  status TEXT DEFAULT '諛쒖＜',

  actual_amount INTEGER DEFAULT 0,

  created_at TEXT DEFAULT (datetime('now','localtime')),

  updated_at TEXT DEFAULT (datetime('now','localtime'))

);

CREATE INDEX IF NOT EXISTS idx_purchases_purchase_no ON purchases(purchase_no);

CREATE INDEX IF NOT EXISTS idx_purchases_purchase_dt ON purchases(purchase_dt);



/* 諛쒖＜ ?곸꽭 (?덈ぉ) */

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





/* 諛쒖＜-二쇰Ц ?곌껐 ?뚯씠釉?*/

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



/* ?⑺뭹 ?ㅻ뜑 */

CREATE TABLE IF NOT EXISTS deliveries (

  id INTEGER PRIMARY KEY AUTOINCREMENT,

  invoice_no TEXT UNIQUE NOT NULL,

  ship_datetime TEXT,

  carrier TEXT,

  secondary_packaging TEXT,

  delivery_type TEXT DEFAULT '?쇰컲',



  invoice_done INTEGER DEFAULT 0, /* ??[異붽?] ?⑺뭹 嫄대퀎 泥?뎄?꾨즺 ?щ? */



  created_at TEXT DEFAULT (datetime('now','localtime')),

  updated_at TEXT DEFAULT (datetime('now','localtime'))

);

CREATE INDEX IF NOT EXISTS idx_deliveries_invoice_no ON deliveries(invoice_no);

CREATE INDEX IF NOT EXISTS idx_deliveries_ship_datetime ON deliveries(ship_datetime);



/* ?⑺뭹-二쇰Ц ?곌껐 ?뚯씠釉?(?ㅻ???愿怨? */

CREATE TABLE IF NOT EXISTS delivery_order_links (

  delivery_id INTEGER NOT NULL,

  order_id INTEGER NOT NULL,

  PRIMARY KEY (delivery_id, order_id),

  FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE,

  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE

);



/* ?⑺뭹-諛쒖＜ ?곌껐 ?뚯씠釉?(?ㅻ???愿怨? */

CREATE TABLE IF NOT EXISTS delivery_purchase_links (

  delivery_id INTEGER NOT NULL,

  purchase_id INTEGER NOT NULL,

  PRIMARY KEY (delivery_id, purchase_id),

  FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE,

  FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE

);



/* ?⑺뭹 ?곸꽭 (?덈ぉ) */

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

  items_per_box INTEGER DEFAULT 1,

  box_l INTEGER DEFAULT 0,

  box_w INTEGER DEFAULT 0,

  box_h INTEGER DEFAULT 0,

  box_weight REAL DEFAULT 0.0,

  max_layer INTEGER DEFAULT 0,

  created_at TEXT DEFAULT (datetime('now','localtime')),

  FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE

);

CREATE INDEX IF NOT EXISTS idx_delivery_items_delivery_id ON delivery_items(delivery_id);

CREATE INDEX IF NOT EXISTS idx_delivery_items_serial_code ON delivery_items(serial_no, manufacture_code);



/* ?쒗뭹 ?뺣낫 */

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



/* [?섏젙] ?쒗뭹 ?섎━ ?대젰 ?뚯씠釉?*/

CREATE TABLE IF NOT EXISTS product_repairs (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    product_id INTEGER NOT NULL,

    receipt_date TEXT,

    quality_report_no TEXT, -- ?덉쭏蹂닿퀬??踰덊샇

    defect_symptom TEXT, -- 遺덈웾 利앹긽

    investigation_customer TEXT, -- 怨좉컼??議곗궗?댁슜

    investigation_internal TEXT, -- ?뱀궗 議곗궗?댁슜

    immediate_action TEXT, -- 利됯컖 ??묒“移?

    root_cause_occurrence TEXT, -- 洹쇰낯?먯씤 (諛쒖깮)

    root_cause_outflow TEXT, -- 洹쇰낯?먯씤 (?좎텧)

    repair_details TEXT, -- ?섎━ ?댁뿭

    prevention_occurrence TEXT, -- ?щ컻諛⑹??梨?(諛쒖깮)

    prevention_outflow TEXT, -- ?щ컻諛⑹??梨?(?좎텧)

    status TEXT DEFAULT '?묒닔', -- ?곹깭

    repair_date TEXT, -- ?섎━??

    redelivery_invoice_no TEXT, -- ?ъ텧怨??몃낫?댁뒪



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



    attachments TEXT, -- ??[異붽?] 泥⑤? ?뚯씪 寃쎈줈 (SCHEMA_SQL??異붽?)



    created_at TEXT DEFAULT (datetime('now','localtime')),

    updated_at TEXT DEFAULT (datetime('now','localtime')),

    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE

);

CREATE INDEX IF NOT EXISTS idx_product_repairs_product_id ON product_repairs(product_id);

CREATE INDEX IF NOT EXISTS idx_product_repairs_status ON product_repairs(status);

CREATE INDEX IF NOT EXISTS idx_product_repairs_quality_report_no ON product_repairs(quality_report_no);



/* ?⑷린 蹂寃??대젰 */

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





/* 遺꾪븷 ?⑷린 嫄대퀎 蹂寃??대젰 ?뚯씠釉?*/

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



/* 二쇰Ц 湲덉븸 酉?*/

CREATE VIEW IF NOT EXISTS order_amounts AS

SELECT

  o.id AS order_id,

  o.order_no,

  SUM(oi.qty * oi.unit_price_cents) AS total_cents,

  oi.currency

FROM orders o

JOIN order_items oi ON o.id = oi.order_id

GROUP BY o.id, o.order_no, oi.currency;



/* 諛쒖＜ 湲덉븸 酉?*/

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

  remarks TEXT,  -- ??[異붽?] 鍮꾧퀬

  created_at TEXT DEFAULT (datetime('now','localtime')),

  UNIQUE(parent_item_code, child_item_code)

);

CREATE INDEX IF NOT EXISTS idx_bom_items_parent ON bom_items(parent_item_code);

CREATE INDEX IF NOT EXISTS idx_bom_items_child ON bom_items(child_item_code);

CREATE INDEX IF NOT EXISTS idx_bom_items_child ON bom_items(child_item_code);

/* 일련번호 관리 (OA, Invoice 등) */
CREATE TABLE IF NOT EXISTS serial_counters (
    category TEXT NOT NULL,         -- 'OA', 'INVOICE' 등
    context TEXT NOT NULL,          -- '2026', '20260201' 등 (기간/날짜 키)
    last_serial INTEGER DEFAULT 0,  -- 마지막으로 사용된 번호
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (category, context)
);


/* ===== 리콜 관리 테이블 ===== */

/* 리콜 건 (하나의 리콜에 여러 제품 + 여러 배송이 연결됨) */
CREATE TABLE IF NOT EXISTS recall_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_no TEXT UNIQUE,                 -- 리콜번호 (RC-YYMMDD-001)
    title TEXT,                          -- 리콜 제목
    receipt_date TEXT,                   -- 접수일
    quality_report_no TEXT,              -- 품질보고서번호
    defect_symptom TEXT,                 -- 불량 증상
    investigation_customer TEXT,         -- 고객사 조사내용
    investigation_internal TEXT,         -- 당사 조사내용
    root_cause_occurrence TEXT,          -- 근본원인 (발생)
    root_cause_outflow TEXT,             -- 근본원인 (유출)
    immediate_action TEXT,               -- 즉각 대응조치
    prevention_occurrence TEXT,          -- 재발방지대책 (발생)
    prevention_outflow TEXT,             -- 재발방지대책 (유출)
    status TEXT DEFAULT '접수',           -- 상태 (접수/진행중/완료)
    notes TEXT,                          -- 비고
    attachments TEXT,                    -- 첨부파일 (JSON)
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_recall_cases_case_no ON recall_cases(case_no);
CREATE INDEX IF NOT EXISTS idx_recall_cases_status ON recall_cases(status);

/* 리콜 대상 제품 (리콜 건 1 : 대상 제품 N) */
CREATE TABLE IF NOT EXISTS recall_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recall_case_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    item_status TEXT DEFAULT '대기',      -- 개별 상태 (대기/수리중/완료/자체처리)
    repair_date TEXT,                    -- 수리완료일
    notes TEXT,                          -- 개별 비고
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (recall_case_id) REFERENCES recall_cases(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE(recall_case_id, product_id)   -- 동일 리콜 건에 같은 제품 중복 방지
);

CREATE INDEX IF NOT EXISTS idx_recall_items_case_id ON recall_items(recall_case_id);
CREATE INDEX IF NOT EXISTS idx_recall_items_product_id ON recall_items(product_id);

/* 리콜 배송 건 (리콜 건 1 : 배송 N, 수입/수출 구분) */
CREATE TABLE IF NOT EXISTS recall_shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recall_case_id INTEGER NOT NULL,
    shipment_type TEXT NOT NULL,          -- 'IMPORT' 또는 'EXPORT'
    shipment_date TEXT,                  -- 배송일
    invoice_no TEXT,                     -- 인보이스 번호
    declaration_no TEXT,                 -- 수입/수출 신고필증번호
    carrier TEXT,                        -- 운송사
    cost_shipping INTEGER DEFAULT 0,     -- 운반비 (원 x 100)
    cost_customs INTEGER DEFAULT 0,      -- 관세/담보금 (원 x 100)
    cost_tax INTEGER DEFAULT 0,          -- 부가세 (원 x 100)
    cost_refund INTEGER DEFAULT 0,       -- 반환금 (원 x 100)
    cost_deposit INTEGER DEFAULT 0,      -- 담보금 (원 x 100) [추가]
    deposit_date TEXT,                   -- 담보금 입금 날짜
    deposit_return_date TEXT,            -- 담보금 반환 날짜
    notes TEXT,                          -- 비고
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (recall_case_id) REFERENCES recall_cases(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_recall_shipments_case_id ON recall_shipments(recall_case_id);

/* ===== 수리 배송 테이블 (기존 수리 관리 비용 구조 개선) ===== */

/* 수리 배송 건 (여러 수리가 하나의 배송을 공유할 수 있음) */
CREATE TABLE IF NOT EXISTS repair_shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shipment_type TEXT NOT NULL,          -- 'IMPORT' 또는 'EXPORT'
    shipment_date TEXT,                  -- 배송일
    invoice_no TEXT,                     -- 인보이스 번호
    declaration_no TEXT,                 -- 수입/수출 신고필증번호
    carrier TEXT,                        -- 운송사
    cost_shipping INTEGER DEFAULT 0,     -- 운반비 (원 x 100)
    cost_customs INTEGER DEFAULT 0,      -- 관세/담보금 (원 x 100)
    cost_tax INTEGER DEFAULT 0,          -- 부가세 (원 x 100)
    notes TEXT,                          -- 비고
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

/* 수리-배송 연결 테이블 (N:M 관계) */
CREATE TABLE IF NOT EXISTS repair_shipment_links (
    repair_shipment_id INTEGER NOT NULL,
    repair_id INTEGER NOT NULL,
    PRIMARY KEY (repair_shipment_id, repair_id),
    FOREIGN KEY (repair_shipment_id) REFERENCES repair_shipments(id) ON DELETE CASCADE,
    FOREIGN KEY (repair_id) REFERENCES product_repairs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_repair_shipment_links_shipment ON repair_shipment_links(repair_shipment_id);
CREATE INDEX IF NOT EXISTS idx_repair_shipment_links_repair ON repair_shipment_links(repair_id);

/* 공급처 정보 */
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    biz_no TEXT,              -- 사업자번호
    name TEXT UNIQUE NOT NULL, -- 상호
    ceo_name TEXT,            -- 대표자명
    biz_type TEXT,            -- 업태
    biz_item TEXT,            -- 종목
    contact TEXT,             -- 연락처
    email TEXT,               -- 이메일
    address TEXT,             -- 주소
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);

/* 매입 세금계산서 */
CREATE TABLE IF NOT EXISTS purchase_tax_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_date TEXT NOT NULL,       -- 발행일
    supplier_id INTEGER NOT NULL,   -- 공급처 FK
    supply_amount INTEGER DEFAULT 0, -- 공급가액 (원단위) [추가]
    tax_amount INTEGER DEFAULT 0,    -- 세액 (원단위) [추가]
    total_amount INTEGER DEFAULT 0, -- 총 공급가액+세액 (원단위)
    approval_number TEXT UNIQUE,    -- 국세청 승인번호
    status TEXT DEFAULT '미지불',   -- 미지불, 부분지불, 지불완료
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE RESTRICT
);

/* 지불 내역 (매입 세금계산서 기반) */
CREATE TABLE IF NOT EXISTS purchase_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_invoice_id INTEGER NOT NULL,  -- 대상 세금계산서 FK
    payment_date TEXT NOT NULL,       -- 지불일
    amount INTEGER NOT NULL,          -- 지불금액
    payment_method TEXT NOT NULL,     -- 현금, 수표, 어음, 외상
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (tax_invoice_id) REFERENCES purchase_tax_invoices(id) ON DELETE CASCADE
);

/* 매입 세금계산서 - 발주(PO) 연결 (N:M) */
CREATE TABLE IF NOT EXISTS purchase_invoice_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_invoice_id INTEGER NOT NULL,
    purchase_id INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (tax_invoice_id) REFERENCES purchase_tax_invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE,
    UNIQUE(tax_invoice_id, purchase_id)
);

/* 매입 세금계산서 상세 품목 */
CREATE TABLE IF NOT EXISTS purchase_tax_invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_invoice_id INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    spec TEXT,
    quantity INTEGER DEFAULT 1,
    unit_price INTEGER DEFAULT 0,
    supply_amount INTEGER DEFAULT 0,
    tax_amount INTEGER DEFAULT 0,
    purchase_id INTEGER,
    purchase_item_id INTEGER,       -- 발주 품목 원본 ID (중복 방지용) [추가]
    purchase_no TEXT,
    note TEXT,
    FOREIGN KEY (tax_invoice_id) REFERENCES purchase_tax_invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE SET NULL
);

"""

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    
    # 초기 사용자 등 (기존 코드에서 누락되지 않도록)
    cur.execute("SELECT count(*) FROM users")
    try:
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                        ('admin', 'admin123', 'admin'))
            cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                        ('koba', 'koba123', 'user'))
    except:
        pass # users table might be missing in partial schema
    
    conn.commit()
    conn.close()

def get_next_db_serial(category: str, context: str) -> int:
    """
    DB에서 해당 카테고리/컨텍스트의 다음 일련번호를 조회합니다.
    (현재 last_serial + 1 반환, DB 업데이트는 하지 않음)
    """
    sql = "SELECT last_serial FROM serial_counters WHERE category = ? AND context = ?"
    # query_one은 아래 정의되어 있음, 직접 연결 사용
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, (category, context))
    row = cur.fetchone()
    conn.close()
    
    if row:
        return row[0] + 1
    return 1

def update_db_serial(category: str, context: str, new_val: int):
    """
    일련번호 사용 확정 후 DB 업데이트.
    기존 값보다 작으면 업데이트하지 않음 (안전장치).
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        # 현재 값 확인
        cur.execute("SELECT last_serial FROM serial_counters WHERE category = ? AND context = ?", (category, context))
        row = cur.fetchone()
        
        if row:
            current_max = row[0]
            if new_val > current_max:
                cur.execute("UPDATE serial_counters SET last_serial = ?, updated_at=datetime('now','localtime') WHERE category = ? AND context = ?", 
                            (new_val, category, context))
        else:
            cur.execute("INSERT INTO serial_counters (category, context, last_serial) VALUES (?, ?, ?)", 
                        (category, context, new_val))
        conn.commit()
    except Exception as e:
        print(f"Serial Update Error: {e}")
    finally:
        conn.close()





def get_conn() -> sqlite3.Connection:

    """SQLite ?곌껐???앹꽦/諛섑솚?섍퀬, ?꾩슂??寃쎌슦 ?ㅽ궎留덈? 留덉씠洹몃젅?댁뀡?⑸땲??"""

    conn = sqlite3.connect(str(DB_PATH))



    # --- 1. product_repairs ?뚯씠釉?留덉씠洹몃젅?댁뀡 (?섎━ ?대젰 愿??而щ읆) ---

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

        # --- 2. 세금계산서 및 지불 분리 (공급가액/세액) 패치 ---
        _patch_db_for_tax_split(conn)

        # --- 2-1. suppliers 테이블 마이그레이션 (업태, 종목, 이메일) ---
        cursor.execute("PRAGMA table_info(suppliers);")
        sup_cols = [info[1] for info in cursor.fetchall()]
        sup_new_cols = {
            "biz_type": "TEXT",
            "biz_item": "TEXT",
            "email": "TEXT"
        }
        for col, dtype in sup_new_cols.items():
            if col not in sup_cols:
                print(f"Applying migration: Adding column '{col}' to 'suppliers'...")
                cursor.execute(f"ALTER TABLE suppliers ADD COLUMN {col} {dtype};")

        conn.commit()

    except sqlite3.Error:
        pass

    # --- 2. product_master 테이블 마이그레이션 (abbreviation 약어 추가) ---
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(product_master);")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "abbreviation" not in columns:
             print("Applying migration: Adding column 'abbreviation' to 'product_master' table...")
             cursor.execute("ALTER TABLE product_master ADD COLUMN abbreviation TEXT;")
             
        conn.commit()
    except sqlite3.Error as e:
        print(f"Migration error (product_master): {e}")


    # --- 4. Pot packing info columns (product_master) ---
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(product_master);")
        columns = [info[1] for info in cursor.fetchall()]

        new_cols = {
            "items_per_box": "INTEGER DEFAULT 1",
            "box_l": "INTEGER DEFAULT 0",
            "box_w": "INTEGER DEFAULT 0",
            "box_h": "INTEGER DEFAULT 0",
            "box_weight": "REAL DEFAULT 0.0",
            "max_layer": "INTEGER DEFAULT 0"
        }

        for col, dtype in new_cols.items():
            if col not in columns:
                print(f"Applying migration: Adding column '{col}' to 'product_master'...")
                cursor.execute(f"ALTER TABLE product_master ADD COLUMN {col} {dtype};")
        
        conn.commit()
    except sqlite3.Error as e:
        print(f"Product Master migration failed: {e}")
        conn.rollback()

    # --- 5.    # [2026-02-01] 포장 정보 및 팔레트 계산 결과 컬럼 추가
    # items_per_box, box_l, box_w, box_h, box_weight, max_layer (기존)
    # pallet_type, loading_pattern, boxes_per_pallet (신규)
    try:
        cur = conn.cursor()
        cols_to_add = {
            'items_per_box': 'INTEGER DEFAULT 1',
            'box_l': 'INTEGER DEFAULT 0',
            'box_w': 'INTEGER DEFAULT 0',
            'box_h': 'INTEGER DEFAULT 0',
            'box_weight': 'REAL DEFAULT 0.0',
            'max_layer': 'INTEGER DEFAULT 0',
            'pallet_type': 'TEXT',
            'loading_pattern': 'TEXT',
            'boxes_per_pallet': 'INTEGER DEFAULT 0'
        }
        
        cur.execute("PRAGMA table_info(delivery_items)")
        existing_cols = [row[1] for row in cur.fetchall()]
        
        for col_name, col_def in cols_to_add.items():
            if col_name not in existing_cols:
                 try:
                    print(f"Applying migration: Adding column '{col_name}' to 'delivery_items'...")
                    cur.execute(f"ALTER TABLE delivery_items ADD COLUMN {col_name} {col_def}")
                 except Exception as e:
                    print(f"Migration error (delivery_items add {col_name}): {e}")
                    
        conn.commit()
    except sqlite3.Error as e:
        print(f"Delivery Items migration failed: {e}")
        conn.rollback()



    # --- 2. deliveries ?뚯씠釉?留덉씠洹몃젅?댁뀡 (泥?뎄 ?꾨즺 ?щ?) ---

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



    # --- 3. BOM 愿??留덉씠洹몃젅?댁뀡 (product_master, products) ---

    try:

        cursor = conn.cursor()



        # 3-1. product_master??item_type 異붽?

        cursor.execute("PRAGMA table_info(product_master);")

        columns_pm = [info[1] for info in cursor.fetchall()]

        if "item_type" not in columns_pm:

            print("Applying migration: Adding column 'item_type' to 'product_master' table...")

            cursor.execute("ALTER TABLE product_master ADD COLUMN item_type TEXT DEFAULT 'PART';")

            

            # 湲곗〈 ?곗씠?곌? ?덈떎硫? 湲곕낯?곸쑝濡?'PRODUCT'(?꾩젣??濡?媛?뺥븯嫄곕굹 

            # ?뱀? 'SELLABLE'?대씪???댁쟾 湲곕낯媛믪씠 ?덉뿀?ㅻ㈃ 'PRODUCT'濡??낅뜲?댄듃

            cursor.execute("UPDATE product_master SET item_type = 'PRODUCT' WHERE item_type = 'SELLABLE'")





        # 3-2. products??consumed_by_product_id 異붽?

        cursor.execute("PRAGMA table_info(products);")

        columns_p = [info[1] for info in cursor.fetchall()]

        if "consumed_by_product_id" not in columns_p:

            print("Applying migration: Adding column 'consumed_by_product_id' to 'products' table...")

            cursor.execute("ALTER TABLE products ADD COLUMN consumed_by_product_id INTEGER;")



        conn.commit()

    except sqlite3.Error as e:

        print(f"BOM Step 1 migration failed: {e}")

        conn.rollback()



    # --- 4. products ?뚯씠釉?updated_at 而щ읆 異붽? (?쒕━????젣 湲곕뒫?? ---

    try:

        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(products);")
        columns = [info[1] for info in cursor.fetchall()]

        if "updated_at" not in columns:
            print("Applying migration: Adding column 'updated_at' to 'products' table...")
            cursor.execute("ALTER TABLE products ADD COLUMN updated_at TEXT DEFAULT (datetime('now','localtime'));")

        conn.commit()

    except sqlite3.Error as e:
        print(f"Products migration failed: {e}")
        conn.rollback()

    # --- 5. bom_items ?뚯씠釉?鍮꾧퀬(remarks) 而щ읆 異붽? ---
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(bom_items);")
        columns = [info[1] for info in cursor.fetchall()]

        if "remarks" not in columns:
            print("Applying migration: Adding column 'remarks' to 'bom_items' table...")
            cursor.execute("ALTER TABLE bom_items ADD COLUMN remarks TEXT;")
        
        # --- 6. bom_items ?뚯씠釉??⑥쐞(unit) 而щ읆 異붽? ---
        if "unit" not in columns:
            print("Applying migration: Adding column 'unit' to 'bom_items' table...")
            cursor.execute("ALTER TABLE bom_items ADD COLUMN unit TEXT;")

        conn.commit()
    except sqlite3.Error as e:
        print(f"BOM items migration failed: {e}")
        conn.rollback()

    # --- 7. recall_shipments 테이블 담보금 금액(cost_deposit) 컬럼 추가 ---
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(recall_shipments);")
        columns = [info[1] for info in cursor.fetchall()]

        if "cost_deposit" not in columns:
            print("Applying migration: Adding column 'cost_deposit' to 'recall_shipments' table...")
            cursor.execute("ALTER TABLE recall_shipments ADD COLUMN cost_deposit INTEGER DEFAULT 0;")
        
        conn.commit()
    except sqlite3.Error as e:
        print(f"Recall shipments migration failed: {e}")
        conn.rollback()

    # --- 6. products ?뚯씠釉?reserved_order_id 異붽? (二쇰Ц ?덉빟 湲곕뒫) ---
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

    # --- 7. exchange_rates ?뚯씠釉?異붽? (?붾퀎 ?섏쑉 愿由? ---
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exchange_rates';")
        if not cursor.fetchone():
            print("Applying migration: Creating 'exchange_rates' table...")
            cursor.execute("""
                CREATE TABLE exchange_rates (
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    rate REAL NOT NULL, -- 100?붾떦 ?먰솕 湲덉븸 (?? 905.5)
                    updated_at TEXT DEFAULT (datetime('now','localtime')),
                    PRIMARY KEY (year, month)
                );
            """)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Exchange rates migration failed: {e}")
        conn.rollback()

    # --- 8. 기존 수리 비용 데이터 → repair_shipments 마이그레이션 ---
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='repair_shipments';")
        if cursor.fetchone():
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='repair_shipment_links';")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM repair_shipment_links")
                existing_links = cursor.fetchone()[0]

                if existing_links == 0:
                    cursor.execute("""
                        SELECT id, cost_deposit, cost_air_freight, cost_shipping_jp, cost_tax_jp,
                               import_invoice_no, import_declaration_no, import_carrier
                        FROM product_repairs
                        WHERE (COALESCE(cost_deposit,0) > 0 OR COALESCE(cost_air_freight,0) > 0
                               OR COALESCE(cost_shipping_jp,0) > 0 OR COALESCE(cost_tax_jp,0) > 0)
                    """)
                    repairs_with_costs = cursor.fetchall()

                    for row in repairs_with_costs:
                        repair_id = row[0]
                        cost_dep, cost_air = row[1] or 0, row[2] or 0
                        cost_ship, cost_tax_val = row[3] or 0, row[4] or 0
                        imp_inv, imp_decl, imp_carrier = row[5], row[6], row[7]

                        # 수입 비용이 있으면 IMPORT 배송 레코드 생성
                        if cost_dep > 0 or cost_air > 0:
                            cursor.execute("""
                                INSERT INTO repair_shipments (shipment_type, invoice_no, declaration_no, carrier,
                                                              cost_shipping, cost_customs, cost_tax, notes)
                                VALUES ('IMPORT', ?, ?, ?, ?, ?, 0, '기존 수리 데이터 자동 마이그레이션')
                            """, (imp_inv, imp_decl, imp_carrier, cost_air, cost_dep))
                            cursor.execute(
                                "INSERT INTO repair_shipment_links (repair_shipment_id, repair_id) VALUES (?, ?)",
                                (cursor.lastrowid, repair_id))

                        # 수출 비용이 있으면 EXPORT 배송 레코드 생성
                        if cost_ship > 0 or cost_tax_val > 0:
                            cursor.execute("""
                                INSERT INTO repair_shipments (shipment_type, cost_shipping, cost_customs, cost_tax, notes)
                                VALUES ('EXPORT', ?, 0, ?, '기존 수리 데이터 자동 마이그레이션')
                            """, (cost_ship, cost_tax_val))
                            cursor.execute(
                                "INSERT INTO repair_shipment_links (repair_shipment_id, repair_id) VALUES (?, ?)",
                                (cursor.lastrowid, repair_id))

                    if repairs_with_costs:
                        print(f"Migration: {len(repairs_with_costs)}건의 수리 비용을 repair_shipments로 마이그레이션 완료")

                conn.commit()
    except sqlite3.Error as e:
        print(f"Repair shipments migration failed: {e}")
        conn.rollback()

    # --- 9. recall_shipments 테이블 담보금 날짜 컬럼 추가 ---
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(recall_shipments);")
        columns = [info[1] for info in cursor.fetchall()]

        if 'deposit_date' not in columns:
            print("Applying migration: Adding column 'deposit_date' to 'recall_shipments' table...")
            cursor.execute("ALTER TABLE recall_shipments ADD COLUMN deposit_date TEXT;")
        if 'deposit_return_date' not in columns:
            print("Applying migration: Adding column 'deposit_return_date' to 'recall_shipments' table...")
            cursor.execute("ALTER TABLE recall_shipments ADD COLUMN deposit_return_date TEXT;")
        if 'cost_refund' not in columns:
            print("Applying migration: Adding column 'cost_refund' to 'recall_shipments' table...")
            cursor.execute("ALTER TABLE recall_shipments ADD COLUMN cost_refund INTEGER DEFAULT 0;")

        conn.commit()
    except sqlite3.Error as e:
        print(f"Recall shipments migration failed: {e}")
        conn.rollback()

    conn.executescript(SCHEMA_SQL)

    conn.commit()

    conn.execute("PRAGMA foreign_keys = ON;")

    conn.execute("PRAGMA journal_mode = WAL;")

    conn.execute("PRAGMA busy_timeout = 5000;")

    return conn

def _patch_db_for_tax_split(conn: sqlite3.Connection):
    """
    세금계산서 및 지불 내역 테이블에 공급가액과 세액 컬럼을 추가하고
    기존 총액 데이터를 바탕으로 (총액/1.1) 값을 배분하여 초기화합니다.
    """
    cursor = conn.cursor()
    
    # 1. purchase_tax_invoices 테이블 패치
    cursor.execute("PRAGMA table_info(purchase_tax_invoices);")
    ti_cols = [info[1] for info in cursor.fetchall()]
    
    if "supply_amount" not in ti_cols:
        print("Migrating purchase_tax_invoices: adding supply_amount and tax_amount...")
        cursor.execute("ALTER TABLE purchase_tax_invoices ADD COLUMN supply_amount INTEGER DEFAULT 0;")
        cursor.execute("ALTER TABLE purchase_tax_invoices ADD COLUMN tax_amount INTEGER DEFAULT 0;")
        
        # 기존 total_amount 기반 데이터 배분 (총액 / 1.1 = 공급가액)
        cursor.execute("""
            UPDATE purchase_tax_invoices 
            SET supply_amount = ROUND(total_amount / 1.1),
                tax_amount = total_amount - ROUND(total_amount / 1.1)
            WHERE total_amount > 0 AND supply_amount = 0
        """)

    # 2. purchase_payments 테이블 패치
    cursor.execute("PRAGMA table_info(purchase_payments);")
    pay_cols = [info[1] for info in cursor.fetchall()]
    
    if "supply_amount" not in pay_cols:
        print("Migrating purchase_payments: adding supply_amount and tax_amount...")
        cursor.execute("ALTER TABLE purchase_payments ADD COLUMN supply_amount INTEGER DEFAULT 0;")
        cursor.execute("ALTER TABLE purchase_payments ADD COLUMN tax_amount INTEGER DEFAULT 0;")
        
        # 기존 amount 기반 데이터 배분
        cursor.execute("""
            UPDATE purchase_payments 
            SET supply_amount = ROUND(amount / 1.1),
                tax_amount = amount - ROUND(amount / 1.1)
            WHERE amount > 0 AND supply_amount = 0
        """)





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





# ===== ?쒗뭹 留덉뒪??愿???⑥닔 =====



def get_product_master_by_code(item_code: str, rev: str = None):

    """?덈ぉ肄붾뱶? Rev濡??쒗뭹 留덉뒪???뺣낫 議고쉶"""

    if rev:

        sql = """

            SELECT id, item_code, rev, product_name, abbreviation, unit_price_jpy, purchase_price_krw, description

            FROM product_master 

            WHERE item_code = ? AND rev = ? AND is_active = 1

        """

        return query_one(sql, (item_code, rev))

    else:

        sql = """

            SELECT id, item_code, rev, product_name, abbreviation, unit_price_jpy, purchase_price_krw, description

            FROM product_master 

            WHERE item_code = ? AND (rev IS NULL OR rev = '') AND is_active = 1

        """

        return query_one(sql, (item_code,))





def search_product_master(search_term: str, limit: int = 10):
    """품목코드나 제품명으로 제품 마스터 검색"""
    sql = """
        SELECT id, item_code, rev, product_name, abbreviation, unit_price_jpy, purchase_price_krw
        FROM product_master 
        WHERE is_active = 1 
        AND (item_code LIKE ? OR product_name LIKE ? OR abbreviation LIKE ?)
        ORDER BY item_code
        LIMIT ?
    """

    search_pattern = f"%{search_term}%"

    return query_all(sql, (search_pattern, search_pattern, search_pattern, limit))





def add_or_update_product_master(item_code: str, rev: str, product_name: str,
                                 unit_price_jpy: int = None, purchase_price_krw: int = None,
                                 description: str = None, item_type: str = 'PART',
                                 is_active: int = None,
                                 items_per_box: int = 1, box_l: int = 0, box_w: int = 0, box_h: int = 0,
                                 box_weight: float = 0.0, max_layer: int = 0,
                                 abbreviation: str = None) -> str:  # ??is_active 및 포장 정보 추가
    """
    ?쒗뭹 留덉뒪???뺣낫瑜?異붽? ?먮뒗 ?낅뜲?댄듃?섍퀬, 泥섎━ 寃곌낵瑜?臾몄옄?대줈 諛섑솚?⑸땲??
    - 'INSERTED': ?좉퇋 異붽? ?깃났
    - 'UPDATED': 湲곗〈 ?뺣낫 ?낅뜲?댄듃 ?깃났
    - 'DUPLICATE_INACTIVE': ?⑥쥌??以묐났 ?덈ぉ 諛쒓껄 (?ㅻ쪟 泥섎━ ?꾩슂)
    """
    rev = rev if rev and rev.strip() else None

    # is_active ?곹깭? ?곴??놁씠 湲곗〈 ?쒗뭹??癒쇱? 李얠뒿?덈떎.
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

        existing_id, db_is_active = existing_row



        # 湲곗〈 ?덈ぉ??'?앹궛 媛???쒖꽦)' ?곹깭???뚮쭔 ?낅뜲?댄듃瑜?吏꾪뻾?⑸땲??

        if db_is_active == 1:

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



            if abbreviation is not None:

                update_fields.append("abbreviation=?")

                params.append(abbreviation)



            # ??[異붽?] is_active ?낅뜲?댄듃 (紐낆떆?곸쑝濡?二쇱뼱吏?寃쎌슦)
            if is_active is not None:
                update_fields.append("is_active=?")
                params.append(is_active) 

            # ??[異붽?] item_type ?낅뜲?댄듃
            if item_type:
                update_fields.append("item_type=?")
                params.append(item_type)

            # 포장 정보 업데이트
            update_fields.extend([
                "items_per_box=?", "box_l=?", "box_w=?", "box_h=?", "box_weight=?", "max_layer=?"
            ])
            params.extend([items_per_box, box_l, box_w, box_h, box_weight, max_layer])



            params.append(existing_id)  # 燧낉툘 [?섏젙] WHERE ?덉쓽 ID????긽 留덉?留됱뿉 異붽??댁빞 ?⑸땲??



            sql = f"UPDATE product_master SET {', '.join(update_fields)} WHERE id=?"

            execute(sql, tuple(params))

            return 'UPDATED'

        # 湲곗〈 ?덈ぉ??'?⑥쥌(鍮꾪솢??' ?곹깭?대㈃, ?꾨Т寃껊룄 ?섏? ?딄퀬 '以묐났' ?좏샇瑜?蹂대깄?덈떎.

        else:

            return 'DUPLICATE_INACTIVE'

    else:

        # 湲곗〈 ?쒗뭹???꾪? ?놁쑝硫? ?덈줈 異붽??⑸땲??
        # ??is_active媛 None?대㈃ 湲곕낯媛?1(?쒖꽦) ?ъ슜 -> ?꾨땲?? ?댁젣 湲곕낯媛믪쓣 ?몄텧泥섏뿉???쒖뼱?섍굅???ш린??湲곕낯媛믪쓣 1濡?
        # ?좉퇋 ?앹꽦???몄텧泥섏뿉??is_active=0??二쇰㈃ 0?쇰줈 ?ㅼ뼱媛?
        final_is_active = is_active if is_active is not None else 1
        
        sql = """
            INSERT INTO product_master 
            (item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, item_type, is_active,
             items_per_box, box_l, box_w, box_h, box_weight, max_layer, abbreviation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        execute(sql,
                (item_code, rev, product_name, unit_price_jpy or 0, purchase_price_krw or 0, description, item_type, final_is_active,
                 items_per_box, box_l, box_w, box_h, box_weight, max_layer, abbreviation))
        return 'INSERTED'






def update_product_master(product_id: int, item_code: str, rev: str, product_name: str,
                          unit_price_jpy: int = None, purchase_price_krw: int = None,
                          description: str = None, item_type: str = 'PART',
                          items_per_box: int = 1, box_l: int = 0, box_w: int = 0, box_h: int = 0,
                          box_weight: float = 0.0, max_layer: int = 0,
                          abbreviation: str = None) -> bool:
    """?쒗뭹 留덉뒪???뺣낫 ?낅뜲?댄듃 (ID 湲곗?)"""
    rev = rev if rev and rev.strip() else None
    
    conn = get_conn()
    try:
        cur = conn.cursor()
        
        # 以묐났 泥댄겕 (?먯떊 ?쒖쇅)
        if rev:
            cur.execute("SELECT id FROM product_master WHERE item_code = ? AND rev = ? AND id != ?", (item_code, rev, product_id))
        else:
            cur.execute("SELECT id FROM product_master WHERE item_code = ? AND (rev IS NULL OR rev = '') AND id != ?", (item_code, product_id))
            
        if cur.fetchone():
            raise ValueError("?대? ?숈씪???덈ぉ肄붾뱶? Rev瑜?媛吏??쒗뭹??議댁옱?⑸땲??")

        # ?낅뜲?댄듃
        sql = """
            UPDATE product_master 
            SET item_code=?, rev=?, product_name=?, abbreviation=?, unit_price_jpy=?, purchase_price_krw=?, 
                description=?, item_type=?, updated_at=datetime('now','localtime'),
                items_per_box=?, box_l=?, box_w=?, box_h=?, box_weight=?, max_layer=?
            WHERE id=?
        """
        cur.execute(sql, (item_code, rev, product_name, abbreviation, unit_price_jpy, purchase_price_krw, description, item_type, 
                          items_per_box, box_l, box_w, box_h, box_weight, max_layer, product_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"update_product_master error: {e}")
        raise e
    finally:
        conn.close()

def update_product_master_purchase_price(item_code: str, rev: str, product_name: str,

                                         purchase_price_krw: int):

    """?쒗뭹 留덉뒪?곗쓽 諛쒖＜?④?留??낅뜲?댄듃"""

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



def get_all_product_master(include_inactive=False, order_by_clause="item_code ASC",

                           type_filter: list = None):

    """紐⑤뱺 ?쒗뭹 留덉뒪??紐⑸줉 議고쉶 (?숈쟻 ?뺣젹 + ????꾪꽣 異붽?)"""



    base_sql = """

        SELECT id, item_code, rev, product_name, abbreviation, unit_price_jpy, 

               purchase_price_krw, description, created_at, updated_at,

               is_active, item_type 

        FROM product_master 

    """

    

    conditions = []

    params = []



    if not include_inactive:

        # ?앹궛 媛?λ쭔: ?쒖꽦 ?쒗뭹留?

        conditions.append("is_active = 1")

        

    if type_filter:

        placeholders = ', '.join('?' for _ in type_filter)

        # ??[?섏젙] ??뚮Ц??援щ텇 ?놁씠 鍮꾧탳 (UPPER)
        conditions.append(f"UPPER(item_type) IN ({placeholders})")

        params.extend([str(t).upper() for t in type_filter])



    if conditions:

        base_sql += " WHERE " + " AND ".join(conditions)



    # ?숈쟻 ?뺣젹 ?곸슜

    base_sql += f" ORDER BY {order_by_clause}"



    return query_all(base_sql, tuple(params))





def delete_product_master(product_id: int):
    """?쒗뭹 留덉뒪????젣 (?꾩쟾 ??젣)"""
    sql = "DELETE FROM product_master WHERE id = ?"
    execute(sql, (product_id,))





def create_order_with_items(order_data: dict, items: list, shipment_data: dict = None, purchase_ids: list = None):

    """二쇰Ц ?앹꽦: ?ㅻ뜑, ?덈ぉ, ?⑷린, ?곌껐 ?뺣낫 ???(+ 利됱떆 ?좊떦 ?ㅽ뻾)"""

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



        # ??[?섏젙] 諛쒖＜ ?곌껐 諛?'利됱떆 ?좊떦' 濡쒖쭅 異붽?

        if purchase_ids:

            for purchase_id in purchase_ids:

                cur.execute(

                    "INSERT INTO purchase_order_links (purchase_id, order_id) VALUES (?, ?)",

                    (purchase_id, order_id)

                )



            # ?곌껐??諛쒖＜?ㅼ뿉 ???'?ы븷?? ?ㅽ뻾 (????二쇰Ц???ш퀬瑜?媛?멸컝 ???덈뒗吏 ?뺤씤)

        conn.commit()

        # ✅ [자동화] 모든 변경 후, 전체 할당 재계산 실행 (안전장치)
        # 기존 부분 할당(allocate_products_fifo) 대신 전체 재계산으로 정확도 보장
        recalculate_all_allocations()

        return order_id

    except Exception as e:

        conn.rollback()

        raise e

    finally:

        conn.close()





def get_order_with_items(order_id: int):

    """二쇰Ц ?ㅻ뜑? ?덈ぉ???④퍡 議고쉶"""

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

    """二쇰Ц ?섏젙: ?ㅻ뜑, ?덈ぉ, ?⑷린, ?곌껐 ?뺣낫 ?섏젙 (+ ?곌껐 ?댁젣 ???뺣━, ?곌껐 ???먮룞 ?좊떦)"""

    conn = get_conn()

    try:

        cur = conn.cursor()



        # 1. 二쇰Ц ?뺣낫 ?낅뜲?댄듃

        cur.execute(

            "UPDATE orders SET order_no=?, recv_dt=?, order_dt=?, req_due=?, final_due=?, updated_at=datetime('now','localtime') WHERE id=?",

            (order_data['order_no'], order_data.get('recv_dt'), order_data.get('order_dt'),

             order_data.get('req_due'), order_data.get('final_due'), order_id)

        )



        # 2. ?덈ぉ ?ъ꽕??

        # 2. 품목 목록 처리 (기존 항목 업데이트 및 신규 추가, 삭제)
        # 2-1. 기존 DB에 있는 품목 ID 조회
        cur.execute("SELECT id FROM order_items WHERE order_id=?", (order_id,))
        existing_ids = {row[0] for row in cur.fetchall()}
        
        # 2-2. 입력된 items 처리
        updated_or_new_ids = set()
        item_id_map = {} # item_row_index -> order_item_id

        for i, item in enumerate(items):
            # item 딕셔너리에 'id'가 있고, 그 id가 existing_ids에 존재하면 UPDATE
            item_id = item.get('id')
            
            if item_id and item_id in existing_ids:
                cur.execute(
                    """
                    UPDATE order_items 
                    SET item_code=?, rev=?, product_name=?, qty=?, unit_price_cents=?
                    WHERE id=?
                    """,
                    (item.get('item_code'), item.get('rev'), item['product_name'], 
                     item['qty'], item['unit_price_cents'], item_id)
                )
                updated_or_new_ids.add(item_id)
                item_id_map[i] = item_id
            else:
                # 없으면 INSERT
                cur.execute(
                    """
                    INSERT INTO order_items (order_id, item_code, rev, product_name, qty, unit_price_cents) 
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (order_id, item.get('item_code'), item.get('rev'), item['product_name'], 
                     item['qty'], item['unit_price_cents'])
                )
                new_id = cur.lastrowid
                updated_or_new_ids.add(new_id)
                item_id_map[i] = new_id

        # 2-3. 삭제된 항목 처리 (입력 목록에 없는 기존 항목 삭제)
        ids_to_delete = existing_ids - updated_or_new_ids
        if ids_to_delete:
            placeholders = ', '.join('?' for _ in ids_to_delete)
            cur.execute(f"DELETE FROM order_items WHERE id IN ({placeholders})", list(ids_to_delete))



        # 3. 遺꾪븷 ?⑷린 ???

        if shipment_data:

            for item_row_index, shipments in shipment_data.items():

                order_item_id = item_id_map.get(item_row_index)

                if order_item_id:

                    save_shipments_for_order_item(order_item_id, shipments, conn)



        # 4. 諛쒖＜ ?곌껐 ?뺣낫 ?낅뜲?댄듃 諛??먮룞??濡쒖쭅

        if purchase_ids is not None:

            cur.execute("DELETE FROM purchase_order_links WHERE order_id = ?", (order_id,))

            for purchase_id in purchase_ids:

                cur.execute(

                    "INSERT INTO purchase_order_links (purchase_id, order_id) VALUES (?, ?)",

                    (purchase_id, order_id)

                )



            # A. [Cleanup] ?곌껐 ?댁젣??諛쒖＜???쒗뭹 ?덉빟 ?湲?

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



            # B. [Allocation] ???곌껐??諛쒖＜?ㅼ뿉 ???'?ы븷?? ?ㅽ뻾 (?덈줈 ?곌껐??二쇰Ц 梨숆꺼二쇨린)

            #    (??二쇰Ц???덈줈 ?곌껐?섏뿀?ㅻ㈃, FIFO ?쒖쐞???곕씪 ?ш퀬瑜?媛?몄삤寃???

        conn.commit()

        # ✅ [자동화] 전체 할당 재계산 실행
        recalculate_all_allocations()

    except Exception as e:

        conn.rollback()

        raise e

    finally:

        conn.close()





def update_purchase_with_items(purchase_id: int, purchase_data: dict, items: list, order_ids: list = None):

    """諛쒖＜ ?섏젙: ?ㅻ뜑, ?덈ぉ, 二쇰Ц ?곌껐 ?뺣낫 ?섏젙 (+ ?곌껐 ?댁젣 ???뺣━, ?곌껐 ???먮룞 ?좊떦)"""

    conn = get_conn()

    try:

        cur = conn.cursor()



        # 1. ?ㅻ뜑 ?낅뜲?댄듃

        cur.execute("""

            UPDATE purchases SET 

                purchase_no = ?, purchase_dt = ?, actual_amount = ?, status = ?, 

                updated_at = datetime('now','localtime')

            WHERE id = ?

        """, (purchase_data['purchase_no'], purchase_data.get('purchase_dt'),

              purchase_data.get('actual_amount', 0), purchase_data.get('status', '諛쒖＜'),

              purchase_id))



        # 2. ?덈ぉ ?ъ꽕??

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



        # 3. 二쇰Ц ?곌껐 ?뺣낫 ?낅뜲?댄듃

        if order_ids is not None:

            cur.execute("DELETE FROM purchase_order_links WHERE purchase_id = ?", (purchase_id,))

            for order_id in order_ids:

                cur.execute("INSERT INTO purchase_order_links (purchase_id, order_id) VALUES (?, ?)",

                            (purchase_id, order_id))



            # A. [Cleanup] ?곌껐 ?댁젣??二쇰Ц??????덉빟 ?湲?

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

                # ?곌껐??二쇰Ц???놁쑝硫?紐⑤뱺 ?덉빟 ?댁젣

                cur.execute("""

                    UPDATE products SET reserved_order_id = NULL 

                    WHERE purchase_id = ? AND delivery_id IS NULL

                """, (purchase_id,))



        # 4. [Allocation] ????諛쒖＜???ш퀬?????'?ы븷?? ?ㅽ뻾

        #    (?덈줈 ?곌껐??二쇰Ц???덇굅???곌껐???딄릿 ???⑤뒗 ?ш퀬瑜??ㅼ떆 遺꾨같)

        cur.execute("""

            SELECT id FROM products 

            WHERE purchase_id = ? 

              AND delivery_id IS NULL 

              AND consumed_by_product_id IS NULL

        """, (purchase_id,))

        product_ids = [r[0] for r in cur.fetchall()]



        conn.commit()

        # ✅ [자동화] 전체 할당 재계산 실행
        recalculate_all_allocations()

    except Exception as e:

        conn.rollback()

        raise e

    finally:
        conn.close()





def delete_order(order_id: int):

    """二쇰Ц ??젣 (CASCADE濡??덈ぉ?ㅻ룄 ?먮룞 ??젣)"""

    execute("DELETE FROM orders WHERE id=?", (order_id,))





# ===== 諛쒖＜ 愿???⑥닔 (?ㅻ뜑-?곸꽭 援ъ“) =====



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



        # ??[?섏젙] 二쇰Ц ?곌껐 ?뺣낫 ???(?꾩닔!)

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

    """諛쒖＜ ?ㅻ뜑? ?덈ぉ???④퍡 議고쉶"""

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

    """諛쒖＜? ?곌껐?????덈뒗 二쇰Ц 紐⑸줉??諛섑솚"""

    sql = """

        SELECT 

            o.id, 

            o.order_no, 

            GROUP_CONCAT(oi.product_name, ' | ') as desc, 

            SUM(oi.qty) as qty, 



            /* [?섏젙] 遺꾪븷 ?⑷린瑜??ы븿??'吏꾩쭨' 理쒖쥌 ?⑷린??議고쉶 */

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



        /* [?섏젙] ?좎쭨媛 鍮좊Ⅸ ??(?ㅻ쫫李⑥닚)?쇰줈 ?뺣젹 */

        ORDER BY due_date ASC, o.order_no ASC

    """

    return query_all(sql)





def get_linked_orders(purchase_id: int):

    """?뱀젙 諛쒖＜? ?곌껐??二쇰Ц 紐⑸줉??諛섑솚"""

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

    """(???⑥닔) ?뱀젙 二쇰Ц???곌껐??諛쒖＜ 紐⑸줉??諛섑솚"""

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

    """諛쒖＜ 紐⑸줉 ?쒖떆??二쇰Ц踰덊샇 臾몄옄??諛섑솚"""

    linked_orders = get_linked_orders(purchase_id)

    if not linked_orders:

        return ""

    return ", ".join([order[1] for order in linked_orders])





# ===== ?⑺뭹 愿???⑥닔 (?ㅻ뜑-?곸꽭 援ъ“) =====



def create_delivery_with_items(delivery_data: dict, items: list):

    """?⑺뭹 ?ㅻ뜑? ?덈ぉ?ㅼ쓣 ?④퍡 ?앹꽦"""

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

    """?⑺뭹 ?ㅻ뜑? ?덈ぉ???④퍡 議고쉶"""

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

    """紐⑤뱺 ?⑺뭹 ?붿빟 議고쉶 (留곹겕 ?뚯씠釉??ъ슜)"""

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





# ===== ?⑷린 蹂寃??대젰 愿???⑥닔 =====



def get_due_change_history(order_id: int):

    """?뱀젙 二쇰Ц???⑷린 蹂寃??대젰??諛섑솚"""

    sql = """

        SELECT id, change_date, old_due_date, new_due_date, change_reason, created_at

        FROM due_date_changes 

        WHERE order_id = ?

        ORDER BY change_date DESC, created_at DESC

    """

    return query_all(sql, (order_id,))





def add_due_change_record(order_id: int, change_date: str, old_due: str, new_due: str, reason: str = None):

    """?⑷린 蹂寃??대젰 異붽?"""

    sql = """

        INSERT INTO due_date_changes (order_id, change_date, old_due_date, new_due_date, change_reason)

        VALUES (?, ?, ?, ?, ?)

    """

    execute(sql, (order_id, change_date, old_due, new_due, reason))





def update_order_final_due_date(order_id: int, new_due_date: str):

    """二쇰Ц??理쒖쥌 ?⑷린???낅뜲?댄듃"""

    sql = "UPDATE orders SET final_due = ?, updated_at=datetime('now','localtime') WHERE id = ?"

    execute(sql, (new_due_date, order_id))





def get_order_due_dates(order_id: int):

    """二쇰Ц??理쒖큹?⑷린?쇨낵 理쒖쥌?⑷린??諛섑솚"""

    sql = "SELECT req_due, final_due FROM orders WHERE id = ?"

    result = query_one(sql, (order_id,))

    if result:

        req_due, final_due = result

        return req_due, final_due or req_due

    return None, None





# app/db.py ?뚯씪??mark_products_as_delivered ?⑥닔瑜??꾨옒 肄붾뱶濡?援먯껜?섏꽭??



# app/db.py



def mark_products_as_delivered(delivery_id: int, conn=None):

    """

    ?⑺뭹?⑥쑝濡??쒖떆 (?섏젙: S/N??>= (踰붿쐞)媛 ?꾨땶 = (?뺥솗?? ?쇱튂?쒗궡)

    """

    should_close = False

    if conn is None:

        conn = get_conn()

        should_close = True



    try:

        cur = conn.cursor()



        # 1. ???⑺뭹???ы븿??*媛쒕퀎* ?덈ぉ/S/N ?뺣낫瑜?媛?몄샂

        cur.execute("""

            SELECT item_code, serial_no, qty

            FROM delivery_items 

            WHERE delivery_id = ? AND serial_no IS NOT NULL

        """, (delivery_id,))

        items_to_deliver = cur.fetchall()



        for item_code, serial_no_to_deliver, qty_to_deliver in items_to_deliver:



            # 2. ??[踰꾧렇 ?섏젙]

            #    serial_no >= ? (?쒖옉 S/N) 媛 ?꾨땶,

            #    serial_no = ? (?뺥솗??S/N) 濡??쒗뭹??李얠븘????

            #    ?먰븳, ?대? ?ㅻⅨ ?⑺뭹???곌껐??S/N? ?낅뜲?댄듃?섏? ?딅룄濡?(delivery_id IS NULL) 諛⑹뼱

            cur.execute("""

                SELECT id FROM products

                WHERE part_no = ? AND serial_no = ? AND delivery_id IS NULL

                LIMIT ?

            """, (item_code, serial_no_to_deliver, qty_to_deliver))  # qty_to_deliver????긽 1



            product_ids_to_update = [row[0] for row in cur.fetchall()]



            # 3. 議고쉶???쒗뭹?ㅼ쓽 delivery_id瑜???踰덉뿉 ?낅뜲?댄듃

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

    """?뱀젙 ?⑺뭹???ы븿???쒗뭹?ㅼ쓽 ?⑺뭹 ?곹깭瑜??쒓굅"""

    should_close = False

    if conn is None:

        conn = get_conn()

        should_close = True



    try:

        cur = conn.cursor()



        # ???⑺뭹???ы븿???쒗뭹?ㅼ쓽 ?⑺뭹 ?곹깭 ?쒓굅

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

    """?뱀젙 ?쒗뭹???섎━ ?잛닔瑜??낅뜲?댄듃?섎뒗 ?대? ?⑥닔"""

    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM product_repairs WHERE product_id = ?", (product_id,))

    count = cur.fetchone()[0]

    cur.execute("UPDATE products SET repair_count = ? WHERE id = ?", (count, product_id))





def get_repairs_for_product(product_id: int):

    """?뱀젙 ?쒗뭹?????紐⑤뱺 ?섎━ ?대젰 議고쉶"""

    sql = """

        SELECT

            id, receipt_date, quality_report_no, defect_symptom, 

            repair_details, status, repair_date, redelivery_invoice_no

        FROM product_repairs

        WHERE product_id = ?

        ORDER BY receipt_date DESC, id DESC

    """

    return query_all(sql, (product_id,))





# app/db.py ?대???get_all_repairs ?⑥닔 ?섏젙



def get_all_repairs(status_filter="전체", order_by_clause="r.receipt_date DESC"):

    conn = get_conn()

    cur = conn.cursor()



    # ??[?섏젙] 8踰덉㎏ 而щ읆??r.root_cause_occurrence -> r.investigation_internal 濡?蹂寃?

    sql = """

        SELECT 

            r.id,

            r.receipt_date, 

            r.quality_report_no,

            p.part_no, 

            p.product_name, 

            p.serial_no,

            r.defect_symptom,

            r.investigation_internal, -- ?뱀궗 議곗궗?댁슜?쇰줈 蹂寃?

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

            r.attachments -- ??[異붽?] attachments ?꾨뱶 (26th field)



        FROM product_repairs r

        WHERE id = ?

    """

    return query_one(sql, (repair_id,))





def add_or_update_repair(data, repair_id=None, external_cursor=None):  # ??external_cursor ?몄옄 異붽?

    """

    ?섎━ ?댁뿭 異붽? ?먮뒗 ?섏젙

    :param external_cursor: ?몃??먯꽌 ?몃옖??뀡??臾띠쓣 ???꾨떖諛쏅뒗 而ㅼ꽌

    """

    # ?몃? 而ㅼ꽌媛 ?덉쑝硫?洹멸쾬???ъ슜, ?놁쑝硫??덈줈 ?곌껐 ?앹꽦 (湲곗〈 諛⑹떇 ?명솚)

    conn = None

    if external_cursor:

        cur = external_cursor

    else:

        conn = get_conn()

        cur = conn.cursor()



    try:

        # 荑쇰━臾?以鍮?(湲곗〈 濡쒖쭅 ?좎?)

        columns = [

            'product_id', 'receipt_date', 'quality_report_no', 'defect_symptom',

            'root_cause_occurrence', 'root_cause_outflow', 'prevention_occurrence', 'prevention_outflow',

            'repair_date', 'status', 'redelivery_invoice_no',

            'investigation_customer', 'investigation_internal', 'immediate_action', 'repair_details',

            'cost_deposit', 'cost_air_freight', 'cost_shipping_jp', 'cost_tax_jp',

            'repair_pic', 'ncr_qty',

            'import_invoice_no', 'import_declaration_no', 'import_carrier',

            'defect_date',

            'attachments'  # ??[異붽?] attachments ?꾨뱶

        ]



        # ?뺤뀛?덈━?먯꽌 媛?異붿텧 (?놁쑝硫?None)

        values = [data.get(col) for col in columns]



        if repair_id:

            # UPDATE

            set_clause = ", ".join([f"{col}=?" for col in columns])

            # updated_at ?먮룞 媛깆떊???꾪빐 荑쇰━???ы븿

            sql = f"UPDATE product_repairs SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?"

            cur.execute(sql, values + [repair_id])

        else:

            # INSERT

            placeholders = ", ".join(["?" for _ in columns])

            sql = f"INSERT INTO product_repairs ({', '.join(columns)}) VALUES ({placeholders})"

            cur.execute(sql, values)



        # ?몃? 而ㅼ꽌媛 ?놁쓣 ?뚮쭔 ?ш린??而ㅻ컠 諛?醫낅즺

        if conn:

            conn.commit()



    except Exception as e:

        print(f"?섎━ ?댁뿭 ????ㅻ쪟: {e}")

        if conn: conn.rollback()

        raise e

    finally:

        # ?몃? 而ㅼ꽌媛 ?놁쓣 ?뚮쭔 ?リ린

        if conn:

            conn.close()





def delete_repair(repair_id: int):

    """?섎━ ?댁뿭 ??젣"""

    conn = get_conn()

    try:

        cur = conn.cursor()

        # ??젣 ??product_id瑜?癒쇱? 議고쉶

        cur.execute("SELECT product_id FROM product_repairs WHERE id = ?", (repair_id,))

        result = cur.fetchone()

        if result:

            product_id = result[0]

            cur.execute("DELETE FROM product_repairs WHERE id = ?", (repair_id,))

            # ?섎━ ?잛닔 ?낅뜲?댄듃

            _update_product_repair_count(product_id, conn)

            conn.commit()

    finally:

        conn.close()





def update_repair_redelivery_status(repair_id: int, invoice_no: str):

    """?섎━???ъ텧怨????곹깭瑜?'?ъ텧怨?濡?蹂寃쏀븯怨??몃낫?댁뒪 踰덊샇瑜?湲곕줉"""

    conn = get_conn()

    try:

        cur = conn.cursor()

        cur.execute("""

            UPDATE product_repairs

            SET status = '?ъ텧怨?,

                redelivery_invoice_no = ?,

                updated_at = datetime('now', 'localtime')

            WHERE id = ?

        """, (invoice_no, repair_id))

        conn.commit()

    finally:

        conn.close()





# ===== 리콜 관리 관련 DB 함수 =====

def get_next_recall_no():
    """다음 리콜 번호 생성 (RC-YYMMDD-XXX)"""
    from datetime import datetime
    today_str = datetime.now().strftime('%y%m%d')
    category = "RECALL"
    
    next_val = get_next_db_serial(category, today_str)
    return f"RC-{today_str}-{next_val:03d}"

def get_all_recall_cases(status_filter="전체"):
    """모든 리콜 건 목록 조회 (요약 정보 포함)"""
    conn = get_conn()
    cur = conn.cursor()
    
    sql = """
        SELECT 
            rc.id, rc.case_no, rc.title, rc.receipt_date, rc.status,
            (SELECT COUNT(*) FROM recall_items WHERE recall_case_id = rc.id) as total_qty,
            (SELECT COUNT(*) FROM recall_items WHERE recall_case_id = rc.id AND item_status = '완료') as handled_qty,
            (SELECT SUM(cost_shipping + cost_customs + cost_tax) FROM recall_shipments WHERE recall_case_id = rc.id AND shipment_type = 'IMPORT') as total_import_cost,
            (SELECT SUM(cost_shipping + cost_customs + cost_tax) FROM recall_shipments WHERE recall_case_id = rc.id AND shipment_type = 'EXPORT') as total_export_cost
        FROM recall_cases rc
    """
    
    params = []
    if status_filter != "전체":
        sql += " WHERE rc.status = ?"
        params.append(status_filter)
    
    sql += " ORDER BY rc.case_no DESC"
    
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_recall_case_details(case_id: int):
    """리콜 건 상세 정보 조회 (기본 정보 + 제품 목록 + 배송 목록)"""
    # 1. 기본 정보
    case_info = query_one("SELECT * FROM recall_cases WHERE id = ?", (case_id,))
    if not case_info:
        return None
        
    # 2. 제품 목록
    items = query_all("""
        SELECT ri.id, ri.product_id, p.part_no, p.product_name, p.serial_no, ri.item_status, ri.repair_date, ri.notes
        FROM recall_items ri
        JOIN products p ON ri.product_id = p.id
        WHERE ri.recall_case_id = ?
    """, (case_id,))
    
    # 3. 배송 목록 (컬럼 순서 명시적 지정)
    shipments = query_all("""
        SELECT id, recall_case_id, shipment_type, shipment_date, invoice_no,
               declaration_no, carrier, cost_shipping, cost_customs, cost_tax,
               deposit_date, deposit_return_date, cost_refund, cost_deposit
        FROM recall_shipments WHERE recall_case_id = ? ORDER BY shipment_date ASC
    """, (case_id,))
    
    return {
        'info': case_info,
        'items': items,
        'shipments': shipments
    }

def create_recall_case(case_data, product_ids, external_cursor=None):
    """리콜 건 생성"""
    conn = None
    if external_cursor:
        cur = external_cursor
    else:
        conn = get_conn()
        cur = conn.cursor()

    try:
        # 1. 일련번호 업데이트
        case_no = case_data.get('case_no')
        if case_no and case_no.startswith('RC-'):
            parts = case_no.split('-')
            if len(parts) == 3:
                date_str = parts[1]
                val = int(parts[2])
                update_db_serial("RECALL", date_str, val)
        
        # 2. 리콜 케이스 INSERT
        keys = list(case_data.keys())
        placeholders = ", ".join(["?"] * len(keys))
        columns = ", ".join(keys)
        sql = f"INSERT INTO recall_cases ({columns}) VALUES ({placeholders})"
        cur.execute(sql, [case_data[k] for k in keys])
        case_id = cur.lastrowid
        
        # 3. 대상 제품 등록
        for p_id in product_ids:
            cur.execute("""
                INSERT OR IGNORE INTO recall_items (recall_case_id, product_id, item_status)
                VALUES (?, ?, '대기')
            """, (case_id, p_id))
            
        if not external_cursor and conn:
            conn.commit()
        return case_id
    except Exception as e:
        if not external_cursor and conn:
            conn.rollback()
        raise e
    finally:
        if not external_cursor and conn:
            conn.close()

def update_recall_case(case_id, case_data, added_products=None, removed_product_ids=None, external_cursor=None):
    """리콜 건 수정"""
    conn = None
    if external_cursor:
        cur = external_cursor
    else:
        conn = get_conn()
        cur = conn.cursor()

    try:
        # 1. 기본 정보 업데이트
        if case_data:
            keys = list(case_data.keys())
            set_clause = ", ".join([f"{k} = ?" for k in keys])
            set_clause += ", updated_at = datetime('now', 'localtime')"
            sql = f"UPDATE recall_cases SET {set_clause} WHERE id = ?"
            cur.execute(sql, [case_data[k] for k in keys] + [case_id])
            
        # 2. 제품 추가
        if added_products:
            for p_id in added_products:
                cur.execute("""
                    INSERT OR IGNORE INTO recall_items (recall_case_id, product_id, item_status)
                    VALUES (?, ?, '대기')
                """, (case_id, p_id))
                
        # 3. 제품 제거
        if removed_product_ids:
            for p_id in removed_product_ids:
                cur.execute("DELETE FROM recall_items WHERE recall_case_id = ? AND product_id = ?", (case_id, p_id))
                
        if not external_cursor and conn:
            conn.commit()
    except Exception as e:
        if not external_cursor and conn:
            conn.rollback()
        raise e
    finally:
        if not external_cursor and conn:
            conn.close()

def delete_recall_case(case_id: int):
    """리콜 건 삭제 (CASCADE 설정에 의해 관련 제품/배송 자동 삭제)"""
    execute("DELETE FROM recall_cases WHERE id = ?", (case_id,))

def update_recall_item_status(recall_item_id: int, status: str, repair_date: str = None, notes: str = None, external_cursor=None):
    """리콜 대상 제품 개별 상태 업데이트"""
    sql = "UPDATE recall_items SET item_status = ?"
    params = [status]
    if repair_date is not None:
        sql += ", repair_date = ?"
        params.append(repair_date)
    if notes is not None:
        sql += ", notes = ?"
        params.append(notes)
    sql += " WHERE id = ?"
    params.append(recall_item_id)
    
    if external_cursor:
        external_cursor.execute(sql, tuple(params))
    else:
        execute(sql, tuple(params))

def add_or_update_recall_shipment(shipment_data, shipment_id=None, external_cursor=None):
    """리콜 배송 정보 추가/수정"""
    conn = None
    if external_cursor:
        cur = external_cursor
    else:
        conn = get_conn()
        cur = conn.cursor()

    try:
        keys = list(shipment_data.keys())
        if shipment_id:
            set_clause = ", ".join([f"{k} = ?" for k in keys])
            sql = f"UPDATE recall_shipments SET {set_clause} WHERE id = ?"
            cur.execute(sql, [shipment_data[k] for k in keys] + [shipment_id])
        else:
            placeholders = ", ".join(["?"] * len(keys))
            columns = ", ".join(keys)
            sql = f"INSERT INTO recall_shipments ({columns}) VALUES ({placeholders})"
            cur.execute(sql, [shipment_data[k] for k in keys])
            shipment_id = cur.lastrowid
            
        if not external_cursor and conn:
            conn.commit()
        return shipment_id
    except Exception as e:
        if not external_cursor and conn:
            conn.rollback()
        raise e
    finally:
        if not external_cursor and conn:
            conn.close()

def delete_recall_shipment(shipment_id: int, external_cursor=None):
    """리콜 배송 삭제"""
    if external_cursor:
        external_cursor.execute("DELETE FROM recall_shipments WHERE id = ?", (shipment_id,))
    else:
        execute("DELETE FROM recall_shipments WHERE id = ?", (shipment_id,))


# ===== 수리 배송 관리 관련 DB 함수 (개선된 구조) =====

def get_repair_shipments(repair_id: int):
    """특정 수리에 연결된 배송 목록 조회"""
    return query_all("""
        SELECT rs.* 
        FROM repair_shipments rs
        JOIN repair_shipment_links rsl ON rs.id = rsl.repair_shipment_id
        WHERE rsl.repair_id = ?
        ORDER BY rs.shipment_date ASC
    """, (repair_id,))

def add_or_update_repair_shipment(shipment_data, shipment_id=None, repair_ids=None, external_cursor=None):
    """수리 배송 추가/수정 및 수리 건 연결"""
    conn = None
    if external_cursor:
        cur = external_cursor
    else:
        conn = get_conn()
        cur = conn.cursor()

    try:
        keys = list(shipment_data.keys())
        if shipment_id:
            set_clause = ", ".join([f"{k} = ?" for k in keys])
            sql = f"UPDATE repair_shipments SET {set_clause} WHERE id = ?"
            cur.execute(sql, [shipment_data[k] for k in keys] + [shipment_id])
        else:
            placeholders = ", ".join(["?"] * len(keys))
            columns = ", ".join(keys)
            sql = f"INSERT INTO repair_shipments ({columns}) VALUES ({placeholders})"
            cur.execute(sql, [shipment_data[k] for k in keys])
            shipment_id = cur.lastrowid
            
        # 수리 건 연결 (N:M)
        if repair_ids is not None:
            # 기존 연결 삭제 후 재동기화 (이 배송 건에 대해서만)
            cur.execute("DELETE FROM repair_shipment_links WHERE repair_shipment_id = ?", (shipment_id,))
            for r_id in repair_ids:
                cur.execute("INSERT INTO repair_shipment_links (repair_shipment_id, repair_id) VALUES (?, ?)", (shipment_id, r_id))
                
        if not external_cursor and conn:
            conn.commit()
        return shipment_id
    except Exception as e:
        if not external_cursor and conn:
            conn.rollback()
        raise e
    finally:
        if not external_cursor and conn:
            conn.close()

def link_repair_to_shipment(repair_id: int, shipment_id: int):
    """기존 배송에 수리 건 추가 연결"""
    execute("INSERT OR IGNORE INTO repair_shipment_links (repair_id, repair_shipment_id) VALUES (?, ?)", (repair_id, shipment_id))

def unlink_repair_from_shipment(repair_id: int, shipment_id: int):
    """배송에서 수리 건 연결 해제 (배송 자체는 삭제 안됨)"""
    execute("DELETE FROM repair_shipment_links WHERE repair_id = ? AND repair_shipment_id = ?", (repair_id, shipment_id))

def delete_repair_shipment(shipment_id: int):
    """수리 배송 삭제 (연결 데이터는 CASCADE 처리됨)"""
    execute("DELETE FROM repair_shipments WHERE id = ?", (shipment_id,))


def get_shipments_for_order_item(order_item_id: int):

    """?뱀젙 二쇰Ц ?덈ぉ?????紐⑤뱺 遺꾪븷 ?⑷린 ?쇱젙 議고쉶"""

    sql = "SELECT id, due_date, ship_qty FROM order_shipments WHERE order_item_id = ? ORDER BY due_date"

    return query_all(sql, (order_item_id,))





def save_shipments_for_order_item(order_item_id: int, shipments: list, conn):

    """?뱀젙 二쇰Ц ?덈ぉ?????遺꾪븷 ?⑷린 ?쇱젙?????(湲곗〈 ?곗씠?곕뒗 ??젣 ???щ벑濡?"""

    cur = conn.cursor()

    # 湲곗〈 ?곗씠????젣

    cur.execute("DELETE FROM order_shipments WHERE order_item_id = ?", (order_item_id,))

    # ???곗씠??異붽?

    for shipment in shipments:

        cur.execute(

            "INSERT INTO order_shipments (order_item_id, due_date, ship_qty) VALUES (?, ?, ?)",

            (order_item_id, shipment['due_date'], shipment['ship_qty'])

        )





def get_full_schedule_for_order(order_id: int):

    """?뱀젙 二쇰Ц?????紐⑤뱺 ?덈ぉ 諛?遺꾪븷 ?⑷린 ?쇱젙??議고쉶 (?⑥닚 ?⑷린 ?ы븿)"""

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

    """二쇰Ц ?덈ぉ???꾩껜 ?⑷린 ?쇱젙???덈줈 ??ν븯怨? 蹂寃??대젰??湲곕줉?⑸땲??"""

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

    """?뱀젙 二쇰Ц ?덈ぉ??紐⑤뱺 蹂寃??대젰??議고쉶?⑸땲??"""

    sql = "SELECT change_request_date, old_schedule, new_schedule, reason FROM shipment_date_changes WHERE order_item_id = ? ORDER BY created_at DESC"

    return query_all(sql, (order_item_id,))





def is_purchase_completed(purchase_id: int) -> bool:

    """

    諛쒖＜媛 ?꾨즺?섏뿀?붿? ?뺤씤 (?섏젙: ?ш퀬 ?좊Т ?곗꽑)

    [?섏젙??濡쒖쭅]

    1. ?섎룞 ?꾨즺 (status == '?꾨즺')

    2. (?ш퀬 ?뺤씤) ?ш퀬媛 1媛쒕씪???⑥븘?덉쑝硫?(produced > delivered) -> 臾댁“嫄?誘몄셿猷?False)

    3. (二쇰Ц ?곌껐 ?? ?곌껐??紐⑤뱺 二쇰Ц??'泥?뎄 ?꾨즺'

    4. (주분 미연결 시) 발주량 = 생산량 = 납품량(최초 납품 이력 포함)

    """

    conn = get_conn()

    try:

        cur = conn.cursor()



        # 議곌굔 1: ?섎룞?쇰줈 '?꾨즺' ?곹깭?몄? ?뺤씤

        cur.execute("SELECT status FROM purchases WHERE id = ?", (purchase_id,))

        result = cur.fetchone()

        if result and result[0] == '?꾨즺':

            return True



        # --- [?섏젙] ?ш퀬 諛?二쇰Ц ?곹깭瑜??뺤씤?섍린 ?꾪빐 2媛?荑쇰━瑜?癒쇱? ?ㅽ뻾 ---



        # 荑쇰━ A: 二쇰Ц ?곌껐 ?곹깭

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



        # 荑쇰━ B: ?섎웾 ?곹깭 (?뚮え???ы븿)

        cur.execute("""

            SELECT 

                SUM(pi.qty) as order_qty,

                (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id) as produced_qty,

                (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id AND (pr.delivery_id IS NOT NULL OR pr.delivered_at IS NOT NULL)) as delivered_qty,

                (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id AND pr.consumed_by_product_id IS NOT NULL) as consumed_qty,

                p.purchase_dt  -- 날짜 필드 추가

            FROM purchases p

            LEFT JOIN purchase_items pi ON p.id = pi.purchase_id

            WHERE p.id = ?

            GROUP BY p.id

        """, (purchase_id,))



        qty_result = cur.fetchone()

        order_qty, produced_qty, delivered_qty, consumed_qty = 0, 0, 0, 0

        purchase_dt = ""

        if qty_result:

            # None??0?쇰줈 泥섎━

            order_qty = qty_result[0] or 0

            produced_qty = qty_result[1] or 0

            delivered_qty = qty_result[2] or 0

            consumed_qty = qty_result[3] or 0

            purchase_dt = qty_result[4] or ""



        # --- 議곌굔 2: (?ш퀬 ?좊Т) ?ш퀬媛 ?⑥븘?덉쑝硫?臾댁“嫄?誘몄셿猷?---

        # (?앹궛?? - (?⑺뭹?? - (?뚮え?? > 0 ?대㈃ ?ш퀬媛 ?덈뒗 寃?

        # --- [신규] 議곌굔 2-1: 2026년 이후 건에 대한 지불 상태 체크 ---

        # 사용자가 수동 완료한 경우는 이미 위에서 리턴되었으므로, 자동 판정 시에만 적용

        if purchase_dt and purchase_dt >= '2026-01-01':

            # 지불 상태 조회 함수 호출

            pay_info = get_purchase_payment_status_for_po(purchase_id)

            if pay_info['status'] != '지불완료':

                return False  # 지불 미완료 시 즉시 미완료 반환



        if produced_qty > (delivered_qty + consumed_qty):

            return False



        # --- 議곌굔 3: (二쇰Ц ?곌껐 ?? ?ш퀬媛 0???? ?곌껐??二쇰Ц?ㅼ쓽 泥?뎄 ?곹깭 ?뺤씤 ---

        if total_orders > 0:

            return total_orders == completed_orders  # (?? total=1, completed=0) -> False



        # --- 議곌굔 4: (二쇰Ц 誘몄뿰寃??? ?ш퀬媛 0?닿퀬 二쇰Ц???놁쓣 ?? ?섎웾 ?쇱튂 ?뺤씤 ---

        # 諛쒖＜??== (?⑺뭹??+ ?뚮え?? ?몄? ?뺤씤

        if order_qty > 0 and order_qty == produced_qty and order_qty == (delivered_qty + consumed_qty):

            return True



        # ??紐⑤뱺 議곌굔???대떦?섏? ?딆쑝硫?誘몄셿猷?

        return False



    finally:

        if conn:

            conn.close()





def check_and_update_order_completion(order_id: int, conn):

    """

    (???⑥닔) 二쇱뼱吏?order_id????? ?곌껐??紐⑤뱺 ?⑺뭹??泥?뎄 ?꾨즺 ?곹깭瑜??뺤씤?섍퀬

    二쇰Ц(orders) ?뚯씠釉붿쓽 invoice_done ?뚮옒洹몃? ?먮룞?쇰줈 ?낅뜲?댄듃?⑸땲??



    (?⑺뭹 ??뿉??泥댄겕諛뺤뒪瑜??꾨? ?뚮쭏?????⑥닔媛 ?몄텧?⑸땲??)

    """

    cur = conn.cursor()



    # 1. ??二쇰Ц???꾨즺?섍린 ?꾪빐 ?꾩슂???덈ぉ蹂?珥??섎웾 (e.g., A: 10媛? B: 5媛?

    cur.execute("SELECT item_code, SUM(qty) FROM order_items WHERE order_id = ? GROUP BY item_code", (order_id,))

    order_qtys_needed = {row[0]: row[1] for row in cur.fetchall() if row[0]}



    if not order_qtys_needed:

        return  # 二쇰Ц???덈ぉ???놁쑝硫??댁긽??寃쎌슦) ?먮룞 ?꾨즺 ??곸씠 ?꾨떂



    # 2. ??二쇰Ц???곌껐??*'泥?뎄?꾨즺(invoice_done=1)'?? ?⑺뭹?ㅼ쓽 ?덈ぉ蹂?珥??섎웾

    cur.execute("""
        SELECT di.item_code, SUM(di.qty)
        FROM delivery_items di
        JOIN deliveries d ON di.delivery_id = d.id
        JOIN delivery_order_links dol ON d.id = dol.delivery_id
        WHERE dol.order_id = ? AND d.invoice_done = 1 AND di.item_code IS NOT NULL
        GROUP BY di.item_code
    """, (order_id,))

    delivered_qtys_done = {row[0]: row[1] for row in cur.fetchall()}



    # 3. ???섎웾??鍮꾧탳

    is_fully_completed = True

    for item_code, qty_needed in order_qtys_needed.items():

        qty_delivered_done = delivered_qtys_done.get(item_code, 0)



        if qty_delivered_done < qty_needed:

            is_fully_completed = False  # ?섎굹?쇰룄 遺議깊븯硫?誘몄셿猷?

            break



    # 4. orders ?뚯씠釉붿쓽 invoice_done ?뚮옒洹몃? ?먮룞 ?낅뜲?댄듃

    new_status = 1 if is_fully_completed else 0

    cur.execute("UPDATE orders SET invoice_done = ? WHERE id = ?", (new_status, order_id))





def get_schedule_for_month(year: int, month: int) -> dict:

    """

    - [?섏젙] 'orders'? 'order_shipments' ?뚯씠釉?紐⑤몢?먯꽌 ?좎쭨瑜?寃??

    """

    month_str = f"{year}-{month:02d}"



    # ??[?섏젙] '?⑥닚 ?⑷린'? '遺꾪븷 ?⑷린'瑜?紐⑤몢 ?⑹퀜??議고쉶

    sql = """

        SELECT 

            AllDueDates as due_date, 

            COUNT(*) as shipment_count

        FROM (

            -- 1. 遺꾪븷 ?⑷린

            SELECT 

                os.due_date as AllDueDates

            FROM order_shipments os

            WHERE strftime('%Y-%m', os.due_date) = ?



            UNION ALL



            -- 2. ?⑥닚 ?⑷린 (遺꾪븷 ?⑷린???녿뒗 二쇰Ц)

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

        # ??[?섏젙] ?뚮씪誘명꽣瑜?2媛??꾨떖 (UNION ALL??媛?荑쇰━??

        rows = query_all(sql, (month_str, month_str))

        # ?뺤뀛?덈━濡?蹂??

        return {date: count for date, count in rows}

    except Exception as e:

        print(f"?붾퀎 ?⑺뭹 ?쇱젙 議고쉶 ?ㅻ쪟: {e}")

        return {}





def get_schedule_details_for_date(date_str: str) -> list:

    """

    (???⑥닔) ?⑺뭹 ?щ젰??'?곸꽭 紐⑸줉'???곗씠?곕? 諛섑솚?⑸땲??

    - [?섏젙] 'orders'? 'order_shipments' ?뚯씠釉?紐⑤몢?먯꽌 ?좎쭨瑜?寃??

    """

    sql = """

        SELECT * FROM (

            -- 荑쇰━ A: '遺꾪븷 ?⑷린'媛 ?ㅼ젙??嫄?(order_shipments)

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



            -- 荑쇰━ B: '?⑥닚 ?⑷린' 嫄?(orders.final_due ?먮뒗 req_due)

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

        # ??[?섏젙] ?뚮씪誘명꽣媛 2媛쒓? ?꾩슂?⑸땲??(date_str, date_str)

        return query_all(sql, (date_str, date_str))

    except Exception as e:

        print(f"?쇱옄蹂??⑺뭹 ?곸꽭 議고쉶 ?ㅻ쪟: {e}")

        return []





def calculate_fifo_allocation_margins():
    """
    (?섏젙?? FIFO 諛⑹떇?쇰줈 諛쒖＜蹂??덈ぉ蹂??좊떦 ?ъ쑀 ?섎웾???뺣? 怨꾩궛?⑸땲??
    Returns: {purchase_id: {item_code: remaining_qty}}
    """
    conn = get_conn()
    cur = conn.cursor()

    allocations = {}  # {purchase_id: {item_code: remaining_qty}}

    try:
        # 1. 紐⑤뱺 諛쒖＜???덈ぉ蹂?珥덇린 ?섎웾 諛??뚮え??議고쉶
        cur.execute("""
            SELECT 
                p.id, p.purchase_dt, pi.item_code,
                pi.qty as total_qty,
                (SELECT COUNT(*) FROM products pr 
                 WHERE pr.purchase_id = p.id 
                 AND pr.part_no = pi.item_code 
                 AND pr.consumed_by_product_id IS NOT NULL) as consumed_qty
            FROM purchases p
            JOIN purchase_items pi ON p.id = pi.purchase_id
            ORDER BY p.purchase_dt, p.id
        """)

        # ?곗씠?곕? 援ъ“??(purchase_id -> item_code -> qty)
        p_dict = {} 
        for row in cur.fetchall():
            p_id, p_dt, item_code, total, consumed = row
            if p_id not in p_dict:
                p_dict[p_id] = {'id': p_id, 'dt': p_dt, 'items': {}}
            
            remaining = (total or 0) - (consumed or 0)
            p_dict[p_id]['items'][item_code] = remaining

        # ?좎쭨???뺣젹 (?ㅻ옒??諛쒖＜遺???뚯쭊)
        purchases = sorted(p_dict.values(), key=lambda x: (x['dt'] or '', x['id']))
        
        # 珥덇린媛??ㅼ젙
        for p in purchases:
            allocations[p['id']] = p['items'].copy()

        # 2. 諛쒖＜? ?곌껐??紐⑤뱺 二쇰Ц 議고쉶 (?ㅻ옒??二쇰Ц遺??泥섎━)
        cur.execute("""
            SELECT DISTINCT o.id, o.order_dt 
            FROM orders o
            JOIN purchase_order_links pol ON o.id = pol.order_id
            ORDER BY o.order_dt, o.id
        """)
        orders = cur.fetchall()

        for o_id, o_dt in orders:
            # 2-1. ??二쇰Ц???덈ぉ蹂??섎웾 議고쉶
            cur.execute("SELECT item_code, qty FROM order_items WHERE order_id = ?", (o_id,))
            order_items = cur.fetchall()  # [(item_code, qty), ...]

            # 2-2. ??二쇰Ц???곌껐??諛쒖＜ ID 紐⑸줉 議고쉶
            cur.execute("SELECT purchase_id FROM purchase_order_links WHERE order_id = ?", (o_id,))
            linked_p_ids = {r[0] for r in cur.fetchall()}

            # 2-3. FIFO ?좊떦 濡쒖쭅
            for item_code, qty_needed in order_items:
                # ?대떦 ?덈ぉ??痍④툒?섎뒗 ?곌껐??諛쒖＜ 寃??
                candidate_purchases = [
                    p for p in purchases
                    if p['id'] in linked_p_ids and item_code in p['items']
                ]

                for p in candidate_purchases:
                    if qty_needed <= 0:
                        break
                    
                    remaining = p['items'][item_code]
                    if remaining > 0:
                        take = min(qty_needed, remaining)
                        p['items'][item_code] -= take
                        qty_needed -= take
                        
                        allocations[p['id']][item_code] = p['items'][item_code]

    except Exception as e:
        print(f"FIFO 怨꾩궛 ?ㅻ쪟: {e}")
    finally:
        conn.close()

    return allocations





def get_available_purchases():
    """
    '제품 추가' 등에서 사용하는 발주 목록 반환 (수정: FIFO 할당 적용 및 완료된 건 제외)
    """
    # 1. 기본 정보 조회
    sql = """
        SELECT
            p.id,
            p.purchase_no,
            GROUP_CONCAT(pi.product_name, ' | ') as purchase_desc,
            SUM(pi.qty) as ordered_qty, 
            p.purchase_dt,
            (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id) as produced_qty,
            (SELECT COUNT(*) FROM products pr 
             WHERE pr.purchase_id = p.id AND (pr.delivery_id IS NOT NULL OR pr.delivered_at IS NOT NULL)) as delivered_qty,
            (SELECT COUNT(*) FROM products pr
             WHERE pr.purchase_id = p.id AND pr.consumed_by_product_id IS NOT NULL) as consumed_qty,
            0 as dummy_linked_qty,
            (SELECT pr.serial_no FROM products pr
             WHERE pr.purchase_id = p.id AND pr.delivery_id IS NULL
             ORDER BY pr.serial_no ASC LIMIT 1
            ) as first_available_serial,
            p.status
        FROM purchases p
        LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
        WHERE p.purchase_no IS NOT NULL
        AND COALESCE(p.status, '발주') != '완료'
        GROUP BY p.id
        ORDER BY p.purchase_dt DESC
    """
    all_purchases = query_all(sql)

    # [추가] FIFO 방식으로 정확한 여유 할당량 계산
    fifo_margins = calculate_fifo_allocation_margins()

    available_list = []
    for row in all_purchases:
        # row의 각 값을 변수에 할당 (컬럼 개수: 11개)
        p_id, p_no, p_desc, ordered_qty, p_dt, produced_qty, delivered_qty, consumed_qty, _, first_serial, p_status = row

        ordered_qty = ordered_qty or 0
        produced_qty = produced_qty or 0
        delivered_qty = delivered_qty or 0
        consumed_qty = consumed_qty or 0

        # [수정] 발주가 논리적으로 완료되었는지 최종 확인 (is_purchase_completed 사용)
        if is_purchase_completed(p_id):
            continue

        # 재고 수량
        stock_qty = produced_qty - delivered_qty - consumed_qty

        # [수정] 할당 여유분 FIFO 계산 결과 사용 (dict 형태)
        allocation_margin = fifo_margins.get(p_id, {})

        # 필터링
        production_needed = (produced_qty < ordered_qty)
        stock_available = (stock_qty > 0)

        if not production_needed and not stock_available:
            continue

        available_list.append(
            (p_id, p_no, p_desc, ordered_qty, p_dt, stock_qty, allocation_margin, produced_qty, first_serial))

    return available_list

    # 1. 湲곕낯 ?뺣낫 議고쉶 (湲곗〈 荑쇰━ ?ъ슜?섎릺 linked_order_qty 怨꾩궛? 臾댁떆)

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

            0 as dummy_linked_qty, -- (Python?먯꽌 怨꾩궛?섎?濡?SQL 怨꾩궛 ?쒖쇅)

            (SELECT pr.serial_no FROM products pr

             WHERE pr.purchase_id = p.id AND pr.delivery_id IS NULL

             ORDER BY pr.serial_no ASC LIMIT 1

            ) as first_available_serial

        FROM purchases p

        LEFT JOIN purchase_items pi ON p.id = pi.purchase_id

        WHERE p.purchase_no IS NOT NULL

        AND COALESCE(p.status, '諛쒖＜') != '?꾨즺'

        GROUP BY p.id

        ORDER BY p.purchase_dt DESC

    """

    all_purchases = query_all(sql)



    # ??[異붽?] FIFO 諛⑹떇?쇰줈 ?뺥솗???붿뿬 ?좊떦??怨꾩궛

    fifo_margins = calculate_fifo_allocation_margins()



    available_list = []

    for row in all_purchases:

        (p_id, p_no, p_desc, ordered_qty, p_dt, produced_qty, delivered_qty, consumed_qty, _, first_serial) = row



        ordered_qty = ordered_qty or 0

        produced_qty = produced_qty or 0

        delivered_qty = delivered_qty or 0

        consumed_qty = consumed_qty or 0



        # ?ш퀬 ?섎웾

        stock_qty = produced_qty - delivered_qty - consumed_qty



        # ??[?섏젙] ?좊떦 ?ъ쑀遺? FIFO 怨꾩궛 寃곌낵 ?ъ슜 (dict ?뺥깭)
        allocation_margin = fifo_margins.get(p_id, {})



        # ?꾪꽣留?

        production_needed = (produced_qty < ordered_qty)

        stock_available = (stock_qty > 0)



        if not production_needed and not stock_available:

            continue



        available_list.append(

            (p_id, p_no, p_desc, ordered_qty, p_dt, stock_qty, allocation_margin, produced_qty, first_serial))



    return available_list





def get_linked_purchase_ids_from_orders(order_ids: list[int]) -> set[int]:

    """(???⑥닔) '?⑺뭹 ?섏젙' 李쎌뿉??二쇰Ц ?좏깮 ?? ?곌껐??諛쒖＜ ID瑜?李얘린 ?꾪븳 ?ы띁"""

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

        print(f"二쇰Ц->諛쒖＜ ID 議고쉶 ?ㅻ쪟: {e}")

        return set()





def get_bom_requirements(parent_item_code: str) -> list[dict]:

    """

    (???⑥닔) 議곕┰??遺紐? 肄붾뱶瑜?湲곕컲?쇰줈 ?꾩슂???먯떇 遺??紐⑸줉(BOM)??諛섑솚?⑸땲??

    """

    sql = """
        SELECT b.child_item_code, b.quantity_required, MAX(pm.product_name)
        FROM bom_items b
        LEFT JOIN product_master pm ON b.child_item_code = pm.item_code
        WHERE b.parent_item_code = ?
        GROUP BY b.child_item_code, b.quantity_required
        ORDER BY MAX(pm.product_name)
    """

    try:

        rows = query_all(sql, (parent_item_code,))

        return [

            {'child_code': row[0], 'qty_req': row[1], 'name': row[2]}

            for row in rows

        ]

    except Exception as e:

        print(f"BOM ?붽뎄?ы빆 議고쉶 ?ㅻ쪟: {e}")

        return []





def get_available_stock_for_bom(child_item_codes: list[str]) -> dict:

    """

    (???⑥닔) 議곕┰???꾩슂???먯떇 遺??紐⑸줉??諛쏆븘, ?꾩옱 ?⑺뭹/?뚮え?섏? ?딆? ?ш퀬(S/N)瑜?諛섑솚?⑸땲??

    [?섏젙] ?덈ぉ ?좏삎(item_type)???곕씪 S/N ?뺣젹 ?쒖꽌瑜?蹂寃쏀빀?덈떎.

    """

    if not child_item_codes:

        return {}



    placeholders = ', '.join('?' for _ in child_item_codes)

    sql = f"""

        SELECT 

            pr.id, pr.part_no, pr.serial_no, pr.product_name,

            COALESCE(pm.item_type, 'SELLABLE') as item_type

        FROM products pr

        -- ??[異붽?] product_master? JOIN?섏뿬 item_type ?뺤씤

        LEFT JOIN product_master pm ON pr.part_no = pm.item_code

        WHERE pr.part_no IN ({placeholders})

        AND pr.delivery_id IS NULL          -- ?⑺뭹?섏? ?딆븯怨?

        AND pr.consumed_by_product_id IS NULL -- ?ㅻⅨ 議곕┰???뚮え?섏? ?딆?

        AND pr.reserved_order_id IS NULL      -- ??[異붽?] ?ㅻⅨ 二쇰Ц???덉빟?섏? ?딆? 寃껊쭔!



        -- ??[?섏젙] ?뺣젹 濡쒖쭅 蹂寃?

        ORDER BY

            pr.part_no,

            -- item_type??'SELLABLE'?대㈃ DESC (KT112媛 ?꾨줈), 洹???'SUB_COMPONENT')??ASC (KT011???꾨줈)

            CASE COALESCE(pm.item_type, 'SELLABLE')

                WHEN 'SELLABLE' THEN pr.serial_no END DESC,

            CASE COALESCE(pm.item_type, 'SELLABLE')

                WHEN 'SUB_COMPONENT' THEN pr.serial_no END ASC,

            pr.serial_no ASC -- 湲곕낯媛?(?뱀떆 紐⑤? 寃쎌슦)

    """

    try:

        rows = query_all(sql, tuple(child_item_codes))



        # ?덈ぉ肄붾뱶蹂꾨줈 ?ш퀬 由ъ뒪?몃? 洹몃９??

        stock_map = defaultdict(list)

        # ??[?섏젙] 5媛???ぉ ?명뙣??

        for prod_id, part_no, serial_no, name, item_type in rows:

            # 燧뉛툗 [?섏젙] ??釉붾줉???ㅼ뿬?곌린瑜??뺤씤?섏꽭??

            stock_map[part_no].append({

                'product_id': prod_id,

                'serial_no': serial_no,

                'name': name,

                'item_type': item_type

            })

        return stock_map

    except Exception as e:

        print(f"BOM ?ш퀬 議고쉶 ?ㅻ쪟: {e}")

        return {}





def create_products(product_data: dict, production_qty: int, consumed_items: list[int] = None):

    """

    (?섏젙?? ???쒗뭹???앹꽦?섍퀬, ?곌껐??二쇰Ц??FIFO 諛⑹떇?쇰줈 ?먮룞 ?좊떦?⑸땲??

    """

    conn = get_conn()

    try:

        cur = conn.cursor()

        purchase_id = product_data.get('purchase_id')



        newly_created_product_ids = []



        # 1. ???쒗뭹(遺紐???'production_qty'留뚰겮 ?앹꽦

        for i in range(production_qty):

            cur.execute("""

                INSERT INTO products

                (manufacture_date, part_no, product_name, serial_no, manufacture_code, purchase_id)

                VALUES (?, ?, ?, ?, ?, ?)

            """, (

                product_data.get('manufacture_date'),  # ?좉퇋 ?앹꽦?쒖뿏 蹂댄넻 NULL?댁?留?諛쏆븘??

                product_data.get('part_no'),

                product_data.get('product_name'),

                product_data.get('serial_no'),  # ?좉퇋 ?앹꽦?쒖뿏 NULL?????덉쓬

                product_data.get('manufacture_code'),

                purchase_id

            ))

            newly_created_product_ids.append(cur.lastrowid)



        # 2. (議곕┰ ?앹궛 ?? 遺???뚮え 泥섎━

        if consumed_items and newly_created_product_ids:

            if len(newly_created_product_ids) > 1:

                # 議곕┰? 1媛쒖뵫留??앹꽦?쒕떎怨?媛??(濡쒖쭅 蹂듭옟??諛⑹?)

                raise Exception("BOM 議곕┰ ??1媛?珥덇낵 ?숈떆 ?앹꽦? ?꾩쭅 吏?먮릺吏 ?딆뒿?덈떎.")



            parent_product_id = newly_created_product_ids[0]

            placeholders = ', '.join('?' for _ in consumed_items)

            sql = f"UPDATE products SET consumed_by_product_id = ? WHERE id IN ({placeholders})"

            params = [parent_product_id] + consumed_items

            cur.execute(sql, tuple(params))



        conn.commit()



        # 3. [?듭떖] ?앹궛???쒗뭹?ㅼ뿉 ???FIFO 二쇰Ц ?좊떦 ?ㅽ뻾

        #    (?몃옖??뀡??遺꾨━?섏뿬 ?덉쟾?섍쾶 泥섎━)

        conn.commit()

        # ✅ [자동화] 입고(제품 생성) 후 전체 재계산 실행
        # 신규 입고된 자재를 기존 주문에 자동 할당하기 위함
        recalculate_all_allocations()

    except Exception as e:

        conn.rollback()

        raise e

    finally:

        conn.close()





def assign_product_info_batch(product_ids: list, manufacture_date: str, manufacture_code: str, start_serial_seq: int):

    """

    (???⑥닔) ?좏깮??誘명솗???쒗뭹?ㅼ뿉寃?S/N怨??쒖“ ?뺣낫瑜??쇨큵 遺?ы빀?덈떎.

    :param start_serial_seq: ?쒖옉 ?쒕━??踰덊샇???レ옄 遺遺?(?? 101 -> KT101)

    """

    conn = get_conn()

    try:

        cur = conn.cursor()



        current_seq = start_serial_seq



        for p_id in product_ids:

            # S/N ?앹꽦 (KT + 3?먮━ ?レ옄)

            # 999瑜??섏뼱媛硫?001濡??쒗솚?섎룄濡?濡쒖쭅 異붽? (?꾩슂 ??

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





def update_product_qc_info(product_id: int, serial_no: str, manufacture_date: str):
    """(신규) QC 결과에 따라 제품의 시리얼 번호와 제조일자를 업데이트합니다."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE products
            SET serial_no = ?,
                manufacture_date = ?,
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (serial_no, manufacture_date, product_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_next_purchase_number(year: int, month: int) -> str:

    """TOYYMM-NNN ?뺤떇???ㅼ쓬 諛쒖＜踰덊샇瑜??앹꽦?⑸땲?? (?쇰젴踰덊샇???곕룄 湲곗?)"""



    # 1. [?섏젙] 寃?됱슜 ?묐몢??(?ы빐 ?꾩껜)

    search_prefix = f"TO{year % 100:02d}"  # ?? TO25



    # 2. [?섏젙] ?덈줈 ?앹꽦???묐몢??(?꾩옱 ??

    new_prefix = f"TO{year % 100:02d}{month:02d}-"  # ?? TO2511-



    sql = """

        SELECT purchase_no FROM purchases

        WHERE purchase_no LIKE ?

        ORDER BY purchase_no DESC

        LIMIT 1

    """



    # 3. [?섏젙] '?ы빐 ?꾩껜' ?묐몢?щ줈 寃??

    last_number_row = query_one(sql, (f"{search_prefix}%",))



    if not last_number_row:

        # ?ы빐 泥?諛쒖＜

        return f"{new_prefix}001"



    try:

        # 4. [?섏젙] 留덉?留?踰덊샇(?? TO2509-017)?먯꽌 ?쇰젴踰덊샇(-017)留?異붿텧

        last_serial_str = last_number_row[0].split('-')[-1]  # ?? "017"

        next_serial = int(last_serial_str) + 1



        # 5. [?섏젙] '?덈줈?? ?묐몢?ъ? '?ㅼ쓬' ?쇰젴踰덊샇瑜?議고빀

        return f"{new_prefix}{next_serial:03d}"  # ?? TO2511-018



    except Exception as e:

        print(f"諛쒖＜踰덊샇 ?앹꽦 ?ㅻ쪟: {e}")

        return f"{new_prefix}001"





def get_next_delivery_number(year: int, month: int, day: int) -> str:

    """KIYYYYMMDD-NNN ?뺤떇???ㅼ쓬 ?⑺뭹踰덊샇瑜??앹꽦?⑸땲??"""

    # 연도별 일련번호 관리를 위해 연도 프리픽스 사용 (예: KI2026%)
    year_prefix = f"KI{year:04d}"
    prefix = f"KI{year:04d}{month:02d}{day:02d}-"

    sql = """
        SELECT invoice_no FROM deliveries
        WHERE invoice_no LIKE ?
        ORDER BY invoice_no DESC
        LIMIT 1
    """

    last_number_row = query_one(sql, (f"{year_prefix}%",))



    if not last_number_row:

        return f"{prefix}001"



    try:

        last_serial = last_number_row[0].split('-')[-1]  # ?? "001"

        next_serial = int(last_serial) + 1

        return f"{prefix}{next_serial:03d}"

    except Exception as e:

        print(f"?⑺뭹踰덊샇 ?앹꽦 ?ㅻ쪟: {e}")

        return f"{prefix}001"





def update_repair_status_on_delivery(product_id: int, invoice_no: str):

    """

    ?⑺뭹 ?? ?대떦 ?쒗뭹??'?섎━?꾨즺' ?곹깭???섎━ ?대젰??'?ъ텧怨?濡?蹂寃쏀븯怨??몃낫?댁뒪 湲곗엯.

    """

    conn = get_conn()

    try:

        cur = conn.cursor()

        # 媛??理쒓렐??'?섎━?꾨즺' 嫄댁쓣 李얠쓬 (?뱀떆 紐⑤? 怨듬갚 ?쒓굅瑜??꾪빐 TRIM ?ъ슜)

        cur.execute("""

            SELECT id FROM product_repairs 

            WHERE product_id = ? AND TRIM(status) = '?섎━?꾨즺'

            ORDER BY receipt_date DESC, id DESC 

            LIMIT 1

        """, (product_id,))

        result = cur.fetchone()



        if result:

            repair_id = result[0]

            cur.execute("""

                UPDATE product_repairs

                SET status = '?ъ텧怨?,

                    redelivery_invoice_no = ?,

                    updated_at = datetime('now', 'localtime')

                WHERE id = ?

            """, (invoice_no, repair_id))

            conn.commit()

            print(f"???섎━ ?대젰 ?낅뜲?댄듃 ?꾨즺: RepairID {repair_id} -> ?ъ텧怨?({invoice_no})")

        else:

            print(f"?좑툘 ?낅뜲?댄듃 ????섎━ ?대젰 ?놁쓬 (ProductID: {product_id})")



    except Exception as e:

        print(f"?섎━ ?대젰 ?낅뜲?댄듃 ?ㅽ뙣: {e}")

    finally:

        conn.close()





def revert_repair_status_on_delivery_delete(delivery_id: int):

    """

    ?⑺뭹 ??젣 ?? ???⑺뭹???ы븿?섏뿀??'?ъ텧怨? ?곹깭???섎━ ?대젰???ㅼ떆 '?섎━?꾨즺'濡??섎룎由?

    """

    conn = get_conn()

    try:

        cur = conn.cursor()



        # 1. ???⑺뭹(delivery_id)???ы븿???쒗뭹?ㅼ쓽 ID瑜?李얠쓬

        cur.execute("SELECT id FROM products WHERE delivery_id = ?", (delivery_id,))

        product_ids = [row[0] for row in cur.fetchall()]



        if not product_ids:

            return



        # 2. 李얠? ?쒗뭹??以? ?꾩옱 ?곹깭媛 '?ъ텧怨????섎━ ?대젰??'?섎━?꾨즺'濡?濡ㅻ갚

        #    (?몃낫?댁뒪 踰덊샇??吏?)

        placeholders = ', '.join('?' for _ in product_ids)

        sql = f"""

            UPDATE product_repairs

            SET status = '?섎━?꾨즺',

                redelivery_invoice_no = NULL,

                updated_at = datetime('now', 'localtime')

            WHERE product_id IN ({placeholders}) AND status = '?ъ텧怨?

        """

        cur.execute(sql, tuple(product_ids))

        conn.commit()

        print(f"???⑺뭹 ??젣濡??명븳 ?섎━ ?대젰 濡ㅻ갚 ?꾨즺 ({cur.rowcount}嫄?")



    except Exception as e:

        print(f"?섎━ ?대젰 濡ㅻ갚 ?ㅽ뙣: {e}")

    finally:

        conn.close()





def reset_product_info_batch(product_ids: list):

    """

    (???⑥닔) ?좏깮???쒗뭹?ㅼ쓽 S/N, ?쒖“?쇱옄, ?쒖“肄붾뱶瑜?珥덇린??NULL)?섏뿬 誘명솗???ш퀬濡??섎룎由쎈땲??

    ?? ?대? ?⑺뭹?섏뿀嫄곕굹(delivery_id IS NOT NULL) ?뚮え??consumed_by...) ?쒗뭹? ?쒖쇅?⑸땲??

    """

    conn = get_conn()

    try:

        cur = conn.cursor()



        placeholders = ', '.join('?' for _ in product_ids)



        # ?덉쟾 ?μ튂: delivery_id? consumed_by_product_id媛 ?녿뒗 寃껊쭔 珥덇린??

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





def allocate_products_fifo(product_ids: list, purchase_id: int, conn=None):  # ??conn ?몄옄 異붽?

    """

    (?섏젙?? ?몃? ?곌껐(conn)??諛쏆븘 ?몃옖??뀡??怨듭쑀?????덈룄濡?蹂寃?

    """

    should_close = False

    if conn is None:

        conn = get_conn()

        should_close = True



    try:

        cur = conn.cursor()



        # 1. ?낅젰諛쏆? ?쒗뭹?ㅼ쓽 ID? ?덈ぉ肄붾뱶(part_no)瑜?議고쉶?섏뿬 洹몃９??

        placeholders = ', '.join('?' for _ in product_ids)

        cur.execute(f"SELECT id, part_no FROM products WHERE id IN ({placeholders})", tuple(product_ids))



        products_by_item = {}

        for p_id, part_no in cur.fetchall():

            if part_no not in products_by_item:

                products_by_item[part_no] = []

            products_by_item[part_no].append(p_id)



        # 2. ?곌껐??二쇰Ц 紐⑸줉 議고쉶 (?좎쭨??

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



        # 3. ?덈ぉ蹂꾨줈 ?쒗쉶?섎ŉ ?좊떦 濡쒖쭅 ?섑뻾

        for part_no, available_ids in products_by_item.items():

            if not part_no: continue



            current_available_ids = list(available_ids)



            for order_id, due_date in linked_orders:

                if not current_available_ids: break



                # A. ?꾩슂 ?섎웾 議고쉶

                cur.execute("""

                    SELECT SUM(qty) FROM order_items 

                    WHERE order_id = ? AND item_code = ?

                """, (order_id, part_no))

                result = cur.fetchone()

                total_req = result[0] or 0



                if total_req == 0: continue



                # B. ?덉빟???섎웾 (?뚮え??寃??쒖쇅)

                cur.execute("""

                    SELECT COUNT(*) FROM products 

                    WHERE reserved_order_id = ? 

                      AND part_no = ? 

                      AND delivery_id IS NULL 

                      AND consumed_by_product_id IS NULL

                """, (order_id, part_no))

                reserved_qty = cur.fetchone()[0]



                # C. ?⑺뭹???섎웾

                cur.execute("""

                    SELECT COALESCE(SUM(qty), 0)

                    FROM delivery_items 

                    WHERE order_id = ? AND item_code = ?

                """, (order_id, part_no))

                delivered_qty = cur.fetchone()[0]



                # D. 遺議깅텇 怨꾩궛

                needed_qty = total_req - reserved_qty - delivered_qty



                if needed_qty <= 0: continue



                # E. ?좊떦 ?ㅽ뻾

                take_qty = min(len(current_available_ids), needed_qty)

                ids_to_assign = current_available_ids[:take_qty]

                current_available_ids = current_available_ids[take_qty:]



                placeholders_update = ', '.join('?' for _ in ids_to_assign)

                cur.execute(f"""

                    UPDATE products 

                    SET reserved_order_id = ?, updated_at = datetime('now','localtime')

                    WHERE id IN ({placeholders_update})

                """, [order_id] + ids_to_assign)



                print(f"???좊떦 ?깃났: ?덈ぉ {part_no} {take_qty}媛?-> 二쇰Ц {order_id}")



        # ???몃??먯꽌 ?곌껐??諛쏆? 寃쎌슦 ?ш린?쒕뒗 而ㅻ컠?섏? ?딄퀬 遺紐⑥뿉寃?留↔?

        if should_close:

            conn.commit()



    except Exception as e:

        print(f"FIFO ?좊떦 ?ㅻ쪟: {e}")

        if should_close:  # ??嫄곕㈃ 濡ㅻ갚

            conn.rollback()

        raise e  # ?먮윭瑜??곸쐞濡??꾪뙆

    finally:

        if should_close:

            conn.close()





def recalculate_all_allocations():

    """

    (?꾩껜 ?ш퀎?? ?몃옖??뀡???섎굹濡?臾띠뼱??泥섎━ (Lock 諛⑹?)

    """

    conn = get_conn()

    try:

        cur = conn.cursor()

        print("?봽 ?꾩껜 ?ш퀬 ?좊떦 ?ш퀎???쒖옉 (?좎쭨??FIFO)...")



        # 1. 紐⑤뱺 誘몄텧???ш퀬???덉빟 珥덇린??

        cur.execute("UPDATE products SET reserved_order_id = NULL WHERE delivery_id IS NULL")



        # 2. 紐⑤뱺 ?쒖꽦 諛쒖＜ 議고쉶

        cur.execute("""

            SELECT id FROM purchases 

            WHERE status != '?꾨즺' 

            ORDER BY purchase_dt ASC, id ASC

        """)

        active_purchases = cur.fetchall()



        # 3. 媛?諛쒖＜蹂꾨줈 ?ы븷???ㅽ뻾

        for (p_id,) in active_purchases:

            # ?뚮え??寃??쒖쇅?섍퀬 ?ш퀬 議고쉶

            cur.execute("""

                SELECT id FROM products 

                WHERE purchase_id = ? 

                  AND delivery_id IS NULL 

                  AND consumed_by_product_id IS NULL 

            """, (p_id,))

            p_ids = [r[0] for r in cur.fetchall()]



            if p_ids:

                # ??[?듭떖] ?꾩옱 ?ъ슜 以묒씤 conn???몄옄濡??섍꺼以띾땲??

                allocate_products_fifo(p_ids, p_id, conn=conn)



        conn.commit()  # 紐⑤뱺 ?묒뾽???앸굹硫???踰덉뿉 而ㅻ컠

        print("???꾩껜 ?ш퀎???꾨즺.")

        return True



    except Exception as e:

        print(f"?ш퀎???ㅻ쪟: {e}")

        conn.rollback()

        return False

    finally:

        conn.close()



def get_defect_stats_by_symptom():

    """(遺꾩꽍?? 遺덈웾 利앹긽蹂?諛쒖깮 ?잛닔 (?대┝李⑥닚)"""

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

    """(遺꾩꽍?? ?쒗뭹(紐⑤뜽)蹂?遺덈웾 諛쒖깮 ?잛닔"""

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

    """(遺꾩꽍?? ?붾퀎 遺덈웾 ?묒닔 嫄댁닔 異붿씠 (吏?뺣맂 媛쒖썡 ??留뚰겮)"""

    sql = """

        SELECT strftime('%Y-%m', receipt_date) as month, COUNT(*) as cnt

        FROM product_repairs

        WHERE receipt_date IS NOT NULL

        GROUP BY month

        ORDER BY month ASC

        LIMIT ?  -- ??媛쒖썡 ?섎? ?뚮씪誘명꽣濡?諛쏆쓬

    """

    # (理쒖떊 ?곗씠?곕???媛?몄삤湲??꾪빐 ?쒕툕荑쇰━瑜??⑥빞 ?뺥솗?섏?留?

    #  ?ш린?쒕뒗 媛꾨떒??LIMIT???곕릺, ORDER BY DESC ???ㅼ떆 ?뺣젹?섎뒗 寃??뺤꽍?낅땲??

    #  ?섏?留?SQLite ?뱀꽦???꾩껜 湲곌컙??湲몄? ?딅떎硫?ASC濡?議고쉶 ???룸?遺꾩쓣 ?섎씪??臾대갑?⑸땲??

    #  媛???뺥솗??濡쒖쭅: 理쒓렐 N媛쒖썡??媛?몄삤?ㅻ㈃ ?좎쭨 ?꾪꽣留곸쓣 ?섎뒗 寃?醫뗭뒿?덈떎.)



    # [媛쒖꽑??荑쇰━] ?ㅻ뒛濡쒕???N媛쒖썡 ???곗씠?곕???議고쉶

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

    """(遺꾩꽍?? 洹쇰낯 ?먯씤(諛쒖깮/?좎텧) ?띿뒪???곗씠??議고쉶"""

    sql = """

        SELECT root_cause_occurrence, root_cause_outflow

        FROM product_repairs

        WHERE (root_cause_occurrence IS NOT NULL AND root_cause_occurrence != '')

           OR (root_cause_outflow IS NOT NULL AND root_cause_outflow != '')

    """

    return query_all(sql)





def get_defect_rate_by_model(months=60):

    """

    (遺꾩꽍?? 紐⑤뜽蹂??먮ℓ???⑺뭹) ?鍮?遺덈웾瑜?議고쉶 (遺덈웾瑜??믪? ??

    - 遺꾨え: ?좏깮??湲곌컙(months) ?숈븞???먮ℓ(?⑺뭹) ?섎웾 (Sales Quantity)

    - 遺꾩옄: ?좏깮??湲곌컙(months) ?숈븞 ?묒닔??遺덈웾 嫄댁닔

    """

    # ?뚮씪誘명꽣: "-60 months" ?뺥깭??臾몄옄??

    offset = f"-{months} months"



    sql = """

        SELECT 

            D.product_name,

            D.total_qty as sales_count,

            COALESCE(R.defect_qty, 0) as defect_count,

            (CAST(COALESCE(R.defect_qty, 0) AS FLOAT) / D.total_qty) * 100 as defect_rate

        FROM 

            -- 1. 紐⑤뜽蹂?湲곌컙 ???먮ℓ??(遺꾨え) - ?⑺뭹 湲곗?

            (SELECT di.product_name, SUM(di.qty) as total_qty 

             FROM delivery_items di

             JOIN deliveries d ON di.delivery_id = d.id

             WHERE d.ship_datetime >= date('now', 'start of month', ?)

             GROUP BY di.product_name) D

        JOIN

            -- 2. ?좏깮??湲곌컙 ??遺덈웾 諛쒖깮 ??(遺꾩옄)

            (SELECT p_sub.product_name, COUNT(*) as defect_qty 

             FROM product_repairs r 

             JOIN products p_sub ON r.product_id = p_sub.id 

             WHERE r.receipt_date >= date('now', 'start of month', ?)

             GROUP BY p_sub.product_name) R

        ON D.product_name = R.product_name



        ORDER BY defect_rate DESC

        LIMIT 10

    """

    # ?뚮씪誘명꽣瑜?2踰??꾨떖 (遺꾨え 荑쇰━?? 遺꾩옄 荑쇰━??

    return query_all(sql, (offset, offset))





def get_monthly_exchange_rates(year: int) -> dict:

    """?뱀젙 ?곕룄???붾퀎 ?섏쑉 ?뺣낫瑜??뺤뀛?덈━濡?諛섑솚 {?? ?섏쑉}"""

    sql = "SELECT month, rate FROM exchange_rates WHERE year = ?"

    rows = query_all(sql, (year,))

    rates = {row[0]: row[1] for row in rows}



    # ?곗씠?곌? ?녿뒗 ?ъ? 湲곕낯媛?None)?쇰줈 梨꾩?

    full_data = {}

    for m in range(1, 13):

        full_data[m] = rates.get(m, 0.0)

    return full_data





def save_monthly_exchange_rates(year: int, rates_data: dict):

    """?붾퀎 ?섏쑉 ?뺣낫瑜??쇨큵 ???(rates_data: {?? ?섏쑉})"""

    conn = get_conn()

    try:

        cur = conn.cursor()

        for month, rate in rates_data.items():

            if rate > 0:

                # ?덉쑝硫??낅뜲?댄듃, ?놁쑝硫??쎌엯 (UPSERT)

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

    ?곕룄蹂?留ㅼ텧, ?먭?, ?댁씡 ?곗씠??議고쉶 (?ㅼ젣 ?⑺뭹 ?꾨즺 湲곗?)

    - deliveries ?뚯씠釉붿쓣 湲곗??쇰줈, invoice_done=1 ??嫄대쭔 吏묎퀎

    - 留ㅼ텧 ?몄떇?? deliveries.ship_datetime

    """



    if filter_type == 'year':

        # value媛 2025 媛숈? ?レ옄???섎룄 ?덇퀬 臾몄옄?댁씪 ?섎룄 ?덉쓬

        date_cond = f"strftime('%Y', d.ship_datetime) = '{value}'"

        target_years = [str(value)]

    else:

        # 理쒓렐 N??

        offset = f"-{value} years"

        date_cond = f"d.ship_datetime >= date('now', 'start of year', '{offset}')"



        from datetime import datetime

        curr = datetime.now().year

        target_years = [str(curr - i) for i in range(value, -1, -1)]



    sql = f"""

        SELECT 

            strftime('%Y', d.ship_datetime) as year,



            -- 1. 留ㅼ텧 (?섎웾 * 二쇰Ц?④?/100 * ?섏쑉/100)

            --    二쇰Ц怨??곌껐??order_id IS NOT NULL) ??ぉ留?怨꾩궛

            SUM(

                (di.qty * oi.unit_price_cents / 100.0) * (COALESCE(er.rate, 900.0) / 100.0)

            ) as revenue_krw,



            -- 2. ?먭? (?섎웾 * ?쒖?留ㅼ엯?④?/100)

            SUM(

                di.qty * (COALESCE(pm.purchase_price_krw, 0) / 100.0)

            ) as cost_krw,



            -- 3. ?먮ℓ ?섎웾

            SUM(di.qty) as sales_qty



        FROM deliveries d

        JOIN delivery_items di ON d.id = di.delivery_id

        -- 二쇰Ц ?④?瑜?媛?몄삤湲??꾪빐 order_items 議곗씤 (二쇰Ц ?곌껐??嫄대쭔)

        JOIN order_items oi ON di.order_id = oi.order_id AND di.item_code = oi.item_code

        -- ?쒖? ?먭?瑜?媛?몄삤湲??꾪빐 product_master 議곗씤

        LEFT JOIN product_master pm ON di.item_code = pm.item_code

        -- ?섏쑉 ?뺣낫 議곗씤 (?⑺뭹??湲곗?)

        LEFT JOIN exchange_rates er 

               ON er.year = CAST(strftime('%Y', d.ship_datetime) AS INTEGER)

              AND er.month = CAST(strftime('%m', d.ship_datetime) AS INTEGER)



        WHERE {date_cond}

          AND d.invoice_done = 1

          AND di.order_id IS NOT NULL  -- 二쇰Ц怨??곌껐??嫄대쭔 留ㅼ텧濡??몄젙



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



def get_expected_financials(year):

    """

    특정 연도의 예상 매출 및 예상 원가 조회

    - 기준: order_shipments 테이블의 due_date (전체 납품 일정)

    - 완료된 건과 예정된 건을 모두 포함하여 '해당 연도 전체의 매출 가능성'을 계산

    """

    from datetime import datetime

    

    sql = f"""

        WITH shipment_sum AS (

            -- 1. 개별 납품 일정이 등록된 항목들의 합계

            SELECT 

                SUM((s.ship_qty * oi.unit_price_cents / 100.0) * (COALESCE(er.rate, 900.0) / 100.0)) as rev,

                SUM(s.ship_qty * (COALESCE(pm.purchase_price_krw, 0) / 100.0)) as cost

            FROM order_shipments s

            JOIN order_items oi ON s.order_item_id = oi.id

            LEFT JOIN product_master pm ON oi.item_code = pm.item_code

            LEFT JOIN exchange_rates er 

                   ON er.year = CAST(strftime('%Y', s.due_date) AS INTEGER)

                  AND er.month = CAST(strftime('%m', s.due_date) AS INTEGER)

            WHERE strftime('%Y', s.due_date) = ?

        ),

        order_only_sum AS (

            -- 2. 납품 일정이 아예 등록되지 않은 주문 항목들의 합계 (주문 최종기한 기준)

            SELECT 

                SUM((oi.qty * oi.unit_price_cents / 100.0) * (COALESCE(er.rate, 900.0) / 100.0)) as rev,

                SUM(oi.qty * (COALESCE(pm.purchase_price_krw, 0) / 100.0)) as cost

            FROM order_items oi

            JOIN orders o ON oi.order_id = o.id

            LEFT JOIN product_master pm ON oi.item_code = pm.item_code

            LEFT JOIN exchange_rates er 

                   ON er.year = CAST(strftime('%Y', o.final_due) AS INTEGER)

                  AND er.month = CAST(strftime('%m', o.final_due) AS INTEGER)

            WHERE strftime('%Y', o.final_due) = ?

              AND NOT EXISTS (SELECT 1 FROM order_shipments s WHERE s.order_item_id = oi.id)

        )

        SELECT 

            (COALESCE((SELECT rev FROM shipment_sum), 0) + COALESCE((SELECT rev FROM order_only_sum), 0)) as total_rev,

            (COALESCE((SELECT cost FROM shipment_sum), 0) + COALESCE((SELECT cost FROM order_only_sum), 0)) as total_cost

    """



    row = query_all(sql, (str(year), str(year)))

    

    if row:

        # query_all은 리스트를 반환하므로 첫 번째 항목 확인

        r = row[0]

        rev = r[0] or 0.0

        cost = r[1] or 0.0

        return {

            'revenue': rev,

            'cost': cost,

            'profit': rev - cost

        }

    return {'revenue': 0, 'cost': 0, 'profit': 0}





def get_model_profitability(filter_type='range', value=3):

    """

    紐⑤뜽蹂??섏씡??遺꾩꽍 (?ㅼ젣 ?⑺뭹 ?꾨즺 湲곗?)

    """

    if filter_type == 'year':

        date_cond = f"strftime('%Y', d.ship_datetime) = '{value}'"

    else:

        offset = f"-{value} years"

        date_cond = f"d.ship_datetime >= date('now', 'start of year', '{offset}')"



    sql = f"""

        SELECT 

            pm.product_name,



            -- 1. ?먮ℓ?섎웾

            SUM(di.qty) as sales_qty,



            0, 0, -- (?됯퇏 ?④???Python?먯꽌 怨꾩궛)



            -- 4. 珥?留ㅼ텧??(KRW)

            SUM(

                (di.qty * oi.unit_price_cents / 100.0) * (COALESCE(er.rate, 900.0) / 100.0)

            ) as total_revenue_krw,



            -- 5. 珥?留ㅼ텧?먭? (KRW)

            SUM(

                di.qty * (COALESCE(pm.purchase_price_krw, 0) / 100.0)

            ) as total_cost_krw,



            -- 6. 珥?留덉쭊??

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

    """?곗씠?곌? 議댁옱?섎뒗 紐⑤뱺 ?곕룄 紐⑸줉???대┝李⑥닚?쇰줈 諛섑솚"""

    conn = get_conn()

    try:

        cur = conn.cursor()

        # ?⑺뭹??留ㅼ텧)怨?諛쒖＜???먭?)???대떦?섎뒗 紐⑤뱺 ?곕룄瑜??섏쭛

        sql = "SELECT DISTINCT strftime('%Y', ship_datetime) as year FROM deliveries WHERE invoice_done=1 UNION SELECT DISTINCT strftime('%Y', purchase_dt) as year FROM purchases ORDER BY year DESC"

        rows = query_all(sql)

        # 鍮?媛??쒖쇅?섍퀬 ?뺤닔??由ъ뒪?몃줈 諛섑솚

        return [int(r[0]) for r in rows if r[0] and r[0].isdigit()]

    except Exception:

        return []


# ===== BOM 愿由??⑥닔 (?먯옱 紐낆꽭?? =====

def add_bom_item(parent_code: str, child_code: str, qty: float = 1.0, remarks: str = None, unit: str = None) -> bool:
    """BOM ??ぉ 異붽? (?쒗솚 李몄“ 泥댄겕 ?ы븿)"""
    if parent_code == child_code:
        raise ValueError("遺紐??덈ぉ怨??먯떇 ?덈ぉ??媛숈쓣 ???놁뒿?덈떎.")

    if check_circular_dependency(parent_code, child_code):
        raise ValueError(f"?쒗솚 李몄“媛 媛먯??섏뿀?듬땲?? {parent_code}???대? {child_code}???섏쐞 ??ぉ???ы븿?섏뼱 ?덉뒿?덈떎.")

    conn = get_conn()
    try:
        cur = conn.cursor()
        # ?대? 議댁옱?섎㈃ ?섎웾/鍮꾧퀬/?⑥쐞 ?낅뜲?댄듃, ?놁쑝硫?異붽?
        cur.execute("""
            INSERT INTO bom_items (parent_item_code, child_item_code, quantity_required, remarks, unit)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(parent_item_code, child_item_code) 
            DO UPDATE SET quantity_required = excluded.quantity_required, 
                          remarks = excluded.remarks,
                          unit = excluded.unit,
                          created_at = datetime('now','localtime')
        """, (parent_code, child_code, qty, remarks, unit))
        conn.commit()
        return True
    except Exception as e:
        print(f"add_bom_item error: {e}")
        return False
    finally:
        conn.close()


def delete_bom_item(parent_code: str, child_code: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM bom_items WHERE parent_item_code = ? AND child_item_code = ?", (parent_code, child_code))
        conn.commit()
        return True
    except Exception as e:
        print(f"delete_bom_item error: {e}")
        return False
    finally:
        conn.close()


def update_bom_item_qty(parent_code: str, child_code: str, new_qty: float) -> bool:
    """(Deprecated) Use update_bom_item instead"""
    return update_bom_item(parent_code, child_code, new_qty=new_qty)

def update_bom_item(parent_code: str, child_code: str, new_qty: float = None, new_remarks: str = None, new_unit: str = None) -> bool:
    """BOM ??ぉ(?섎웾/鍮꾧퀬/?⑥쐞) ?낅뜲?댄듃"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        
        # ?숈쟻 荑쇰━ ?앹꽦
        update_parts = []
        params = []
        
        if new_qty is not None:
            update_parts.append("quantity_required = ?")
            params.append(new_qty)
            
        if new_remarks is not None:
            update_parts.append("remarks = ?")
            params.append(new_remarks)

        if new_unit is not None:
            update_parts.append("unit = ?")
            params.append(new_unit)
            
        if not update_parts:
            return True # 蹂寃쎌궗???놁쓬
            
        sql = f"UPDATE bom_items SET {', '.join(update_parts)} WHERE parent_item_code = ? AND child_item_code = ?"
        params.extend([parent_code, child_code])
        
        cur.execute(sql, tuple(params))
        conn.commit()
        return True
    except Exception as e:
        print(f"update_bom_item error: {e}")
        return False
    finally:
        conn.close()


def check_circular_dependency(current_code: str, target_parent: str, visited=None) -> bool:
    """
    ?쒗솚 李몄“ 寃??
    current_code媛 target_parent??遺紐⑥씤吏 (利? ?寃잛쓣 ?먯떇?쇰줈 異붽??섎㈃ 猷⑦봽媛 ?섎뒗吏) ?ш??곸쑝濡??뺤씤
    """
    if visited is None:
        visited = set()
    
    if current_code in visited:
        return False # ?대? 諛⑸Ц??
    visited.add(current_code)

    sql = "SELECT parent_item_code FROM bom_items WHERE child_item_code = ?"
    parents = query_all(sql, (current_code,))
    
    for (p_code,) in parents:
        if p_code == target_parent:
            return True # ?쒗솚 諛쒖깮!
        if check_circular_dependency(p_code, target_parent, visited):
            return True
            
    return False


def get_bom_tree(root_code: str, depth=0, max_depth=10) -> list:
    """
    ?뱀젙 ?덈ぉ??BOM ?몃━瑜??ш??곸쑝濡?議고쉶?섏뿬 諛섑솚
    """
    if depth > max_depth:
        return []

    # 1. ?먯떇 ?덈ぉ 議고쉶
    sql = ""
    sql += "SELECT b.child_item_code, b.quantity_required, pm.product_name, pm.item_type, b.remarks, b.unit "
    sql += "FROM bom_items b "
    sql += "LEFT JOIN ( "
    sql += "    SELECT item_code, product_name, item_type "
    sql += "    FROM product_master "
    sql += "    WHERE id IN ( "
    sql += "        SELECT MAX(id) "
    sql += "        FROM product_master "
    sql += "        GROUP BY item_code "
    sql += "    ) "
    sql += ") pm ON b.child_item_code = pm.item_code "
    sql += "WHERE b.parent_item_code = ? "
    sql += "ORDER BY pm.item_type DESC, pm.product_name"
    
    children = query_all(sql, (root_code,))
    
    result = []
    for code, qty, name, item_type, remarks, unit in children:
        node = {
            'code': code,
            'name': name or "(誘몃벑濡??덈ぉ)", # Name might be None if left join fails
            'qty': qty,
            'item_type': item_type or "PART",
            'remarks': remarks or "",
            'unit': unit or "",
            'children': get_bom_tree(code, depth + 1, max_depth)
        }
        result.append(node)
        


    return result

def update_item_code_references(old_code: str, new_code: str, conn=None):
    """item_code瑜?李몄“?섎뒗 紐⑤뱺 ?뚯씠釉붿쓣 ?낅뜲?댄듃?⑸땲??
    - BOM??寃쎌슦 UNIQUE(parent, child) ?쒖빟議곌굔???덉쑝誘濡?異⑸룎 ??湲곗〈(new_code) ?곗씠?곕? ?좎??섍퀬 old_code ?곗씠?곕뒗 ??젣?⑸땲??
    """
    should_close = False
    if conn is None:
        conn = get_conn()
        should_close = True

    try:
        cur = conn.cursor()
        
        # 1. ?덈ぉ 留덉뒪??(product_master)
        # (?대? ?곸쐞 濡쒖쭅?먯꽌 泥섎━?섏?留? ?덉쟾???꾪빐 ?ш린?쒕룄 ?섑뻾 媛?? ?? ?몄텧泥섏뿉???ㅽ궢?덈떎硫?pass)
        cur.execute("UPDATE product_master SET item_code = ? WHERE item_code = ?", (new_code, old_code))
        
        # 2-A. BOM (遺紐?肄붾뱶 蹂寃? -> 異⑸룎 媛?μ꽦 ?덉쓬
        # ?꾨왂: UPDATE OR IGNORE濡?蹂寃??쒕룄 -> 蹂寃쎈릺吏 ?딆?(異⑸룎?? ?쏅궇 ?됱? ??젣
        cur.execute("UPDATE OR IGNORE bom_items SET parent_item_code = ? WHERE parent_item_code = ?", (new_code, old_code))
        cur.execute("DELETE FROM bom_items WHERE parent_item_code = ?", (old_code,))
        
        # 2-B. BOM (?먯떇 肄붾뱶 蹂寃? -> 異⑸룎 媛?μ꽦 ?덉쓬
        cur.execute("UPDATE OR IGNORE bom_items SET child_item_code = ? WHERE child_item_code = ?", (new_code, old_code))
        cur.execute("DELETE FROM bom_items WHERE child_item_code = ?", (old_code,))
        
        # 3. ?쒗뭹 (products) -> 異⑸룎 ?놁쓬
        cur.execute("UPDATE products SET part_no = ? WHERE part_no = ?", (new_code, old_code))
        
        # 4. 二쇰Ц ?곸꽭 (order_items) -> 異⑸룎 ?놁쓬 (?쇰컲?곸쑝濡?
        cur.execute("UPDATE order_items SET item_code = ? WHERE item_code = ?", (new_code, old_code))
        
        # 5. 諛쒖＜ ?곸꽭 (purchase_items) -> 異⑸룎 ?놁쓬
        cur.execute("UPDATE purchase_items SET item_code = ? WHERE item_code = ?", (new_code, old_code))
        
        # 6. ?⑺뭹 ?곸꽭 (delivery_items) -> 異⑸룎 ?놁쓬
        cur.execute("UPDATE delivery_items SET item_code = ? WHERE item_code = ?", (new_code, old_code))
        
        if should_close:
            conn.commit()
            
    except Exception as e:
        if should_close:
            conn.rollback()
        raise e
    finally:
        if should_close:
            conn.close()


def get_parent_items(child_code: str) -> list[dict]:
    """
    ?뱀젙 ?먯떇 ?덈ぉ(child_code)???ы븿?섍퀬 ?덈뒗 遺紐??덈ぉ(BOM ?곸쐞) 紐⑸줉??諛섑솚?⑸땲?? (??쟾媛?
    """
    sql = """
        SELECT b.parent_item_code, pm.product_name, b.quantity_required, b.remarks, pm.item_type, b.unit
        FROM bom_items b
        LEFT JOIN product_master pm ON b.parent_item_code = pm.item_code
        WHERE b.child_item_code = ?
        ORDER BY pm.product_name
    """
    try:
        rows = query_all(sql, (child_code,))
        return [
            {
                'parent_code': row[0],
                'parent_name': row[1],
                'qty': row[2],
                'remarks': row[3],
                'item_type': row[4],
                'unit': row[5]
            }
            for row in rows
        ]
    except Exception as e:
        print(f"BOM ??쟾媛?議고쉶 ?ㅻ쪟: {e}")
        return []





def get_yearly_inventory_status_v2(year: int, include_consumed_in_unsold: bool = True) -> list[dict]:
    """
    특정 연도(year)에 발주된 품목 중, 해당 연도 말까지 납품되지 않은 재고를 계산.
    include_consumed_in_unsold: True이면, BOM에 소모되었더라도 모품목(Parent)이 미납품 상태면 재고로 인정.
    return: List[Dict] structure { 
        'purchase_no', 'purchase_dt', 'item_code', 'product_name', 
        'qty': 재고수량, 'unit_price': 단가, 'total_value': 총액
      }
    """
    conn = get_conn()
    cur = conn.cursor()
    
    # 내년 1월 1일 (이 날짜 이전Delivery만 납품으로 인정)
    next_year_str = f"{year + 1}-01-01"
    
    sql = """
        SELECT 
            p.purchase_no,
            p.purchase_dt,
            pi.item_code,
            pi.product_name,
            pi.unit_price_cents,
            pr.id, -- product_id
            pr.delivery_id,
            pr.delivered_at,
            pr.consumed_by_product_id,
            pm.unit_price_jpy -- 판매 단가 (JPY)
        FROM purchases p
        JOIN purchase_items pi ON p.id = pi.purchase_id
        JOIN products pr ON pr.purchase_id = p.id AND pr.part_no = pi.item_code
        LEFT JOIN product_master pm ON pi.item_code = pm.item_code AND (pi.rev IS NULL OR pi.rev = '' OR pi.rev = pm.rev)
        WHERE strftime('%Y', p.purchase_dt) = ?
    """
    
    cur.execute(sql, (str(year),))
    
    rows = cur.fetchall()
    
    inventory_items = []
    
    # 재귀적으로 부모의 납품 여부를 확인하기 위한 캐시
    parent_status_cache = {} # product_id -> is_inventory(True/False)

    def query_one(sql, args):
        c = conn.cursor()
        c.execute(sql, args)
        return c.fetchone()

    def check_parent_inventory(parent_id) -> bool:
        if parent_id in parent_status_cache:
            return parent_status_cache[parent_id]
        
        res = query_one("SELECT delivered_at, consumed_by_product_id FROM products WHERE id = ?", (parent_id,))
        if not res:
            # 부모가 없다면 재고로 볼 수 있음 (데이터 무결성 문제일 수 있으나 안전하게 True)
            parent_status_cache[parent_id] = True
            return True
            
        p_delivered_at, p_consumed_id = res
        is_inv = check_is_inventory(parent_id, p_delivered_at, p_consumed_id)
        parent_status_cache[parent_id] = is_inv
        return is_inv

    def check_is_inventory(prod_id, del_at, consumed_id) -> bool:
        # 1. 납품 되었는가?
        if del_at:
            # 납품일이 내년 1월 1일보다 작으면 (즉, 올해 또는 그 이전에 납품됨) -> 재고 아님
            if del_at < next_year_str:
                return False
            else:
                return True # 내년 이후 납품이면 올해 말 기준으론 재고임
        
        # 2. 소모 되었는가?
        if consumed_id:
            if not include_consumed_in_unsold:
                 return False # 소비되었으면 재고 아님 (옵션 OFF)
            else:
                 # 소비되었어도 부모가 재고라면 나도 재고 (옵션 ON)
                 return check_parent_inventory(consumed_id)
            
        # 3. 납품도 안되고 소모도 안됨 -> 재고
        return True

    grouped_inventory = {}

    for row in rows:
        pur_no, pur_dt, code, name, price_cents, prod_id, del_id, del_at, cons_id, sales_price_jpy = row
        
        if check_is_inventory(prod_id, del_at, cons_id):
            key = (pur_no, code)
            if key not in grouped_inventory:
                grouped_inventory[key] = {
                    'purchase_no': pur_no,
                    'purchase_dt': pur_dt,
                    'item_code': code,
                    'product_name': name,
                    'qty': 0,
                    'unit_price': (price_cents or 0) / 100.0 if price_cents else 0,
                    'sales_price_jpy': (sales_price_jpy or 0) / 100.0,
                    'total_value': 0,
                    'potential_revenue': 0
                }
            
            grouped_inventory[key]['qty'] += 1
            grouped_inventory[key]['total_value'] += grouped_inventory[key]['unit_price']
            grouped_inventory[key]['potential_revenue'] += grouped_inventory[key]['sales_price_jpy']

    return list(grouped_inventory.values())

def get_smart_allocation_status(target_purchase_id: int):
    """
    특정 발주(target_purchase_id)를 중심으로, 연결된 주문들의 할당 상태를 FIFO로 시뮬레이션하여
    '내 기여분', '타 발주 기여분', '최종 잔여 재고'를 정밀하게 계산합니다.
    [New] 부품으로 소진된 내역(consumption)도 상세 추적합니다.
    """
    conn = get_conn()
    cur = conn.cursor()

    # 1. 모든 발주의 초기 가용 재고 로드 (BOM 소모 제외 전)
    sql_purchases = """
        SELECT p.id, p.purchase_no, p.purchase_dt, pi.item_code, pi.qty
        FROM purchases p
        JOIN purchase_items pi ON p.id = pi.purchase_id
        ORDER BY p.purchase_dt, p.id
    """
    cur.execute(sql_purchases)
    purchases = {} # {pid: {'id':, 'no':, 'dt':, 'stock': {code: qty}}}
    for pid, pno, pdt, code, qty in cur.fetchall():
        if pid not in purchases: 
            purchases[pid] = {'id': pid, 'no': pno, 'dt': pdt, 'stock': defaultdict(int)}
        purchases[pid]['stock'][code] += qty 
        
    # BOM 소모 수량 차감 & 내역 저장
    consumption_map = defaultdict(int) # {code: qty} (Target Purchase Only)
    
    sql_consumed = """
        SELECT p.id, pr.part_no, SUM(COALESCE(pr.production_qty, 1))
        FROM products pr
        JOIN purchases p ON pr.purchase_id = p.id
        WHERE pr.consumed_by_product_id IS NOT NULL
        GROUP BY p.id, pr.part_no
    """
    cur.execute(sql_consumed)
    for pid, code, consumed_qty in cur.fetchall():
        if pid in purchases and code in purchases[pid]['stock']:
            purchases[pid]['stock'][code] -= consumed_qty
            
            # Target Purchase에 대한 소모량은 별도 기록
            if pid == target_purchase_id:
                consumption_map[code] = consumed_qty

    # 2. 모든 주문 및 아이템 로드
    sql_orders = """
        SELECT o.id, o.order_no, o.order_dt
        FROM orders o
        ORDER BY o.order_dt, o.id
    """
    cur.execute(sql_orders)
    orders_list = cur.fetchall()

    sql_order_items = "SELECT order_id, item_code, qty FROM order_items"
    cur.execute(sql_order_items)
    order_items_map = defaultdict(list)
    for oid, code, qty in cur.fetchall():
        order_items_map[oid].append({'code': code, 'qty': qty})

    # 3. 링크 로드
    sql_links = "SELECT order_id, purchase_id FROM purchase_order_links"
    cur.execute(sql_links)
    links_map = defaultdict(set)
    for oid, pid in cur.fetchall():
        links_map[oid].add(pid)

    # 4. FIFO 시뮬레이션
    allocation_log = [] 
    
    # 발주 리스트 정렬 (날짜순) -> FIFO의 공급 우선순위
    sorted_p_list = sorted(purchases.values(), key=lambda x: (x['dt'] or '9999-12-31', x['id']))

    for oid, ono, odt in orders_list:
        items = order_items_map.get(oid, [])
        linked_pids = links_map.get(oid, set())
        
        candidates = [p for p in sorted_p_list if p['id'] in linked_pids]
        
        for item in items:
            needed = item['qty']
            code = item['code']
            
            for p in candidates:
                if needed <= 0: break
                
                stock = p['stock'].get(code, 0)
                if stock > 0:
                    take = min(stock, needed)
                    p['stock'][code] -= take
                    needed -= take
                    
                    allocation_log.append({
                        'oid': oid, 'ono': ono,
                        'pid': p['id'], 'pno': p['no'],
                        'item_code': code, 'qty': take
                    })

    # 5. Target Purchase에 대한 결과 추출
    
    # A. 내 잔여 재고
    my_final_stock = purchases.get(target_purchase_id, {}).get('stock', {})
    
    # B. 내 기여분 (Logical Allocation)
    my_allocations = [
        log for log in allocation_log 
        if log['pid'] == target_purchase_id
    ]
    
    # C. 타 발주 기여분
    my_linked_orders = {oid for oid, pids in links_map.items() if target_purchase_id in pids}
    
    other_allocations = [
        log for log in allocation_log
        if log['oid'] in my_linked_orders and log['pid'] != target_purchase_id
    ]
    
    # D. 생산 소모 상세 (Consumption Details)
    # 어떤 상위 제품(Parent)을 위해 사용되었는지 조회
    sql_det = """
        SELECT 
            child.part_no, 
            parent.product_name, 
            parent.serial_no,
            o.order_no,
            SUM(COALESCE(child.production_qty, 1))
        FROM products child
        JOIN products parent ON child.consumed_by_product_id = parent.id
        LEFT JOIN deliveries d ON parent.delivery_id = d.id
        LEFT JOIN delivery_items di ON di.delivery_id = d.id 
                                   AND di.item_code = parent.part_no -- Match Item Code
        LEFT JOIN orders o ON di.order_id = o.id
        WHERE child.purchase_id = ? 
          AND child.consumed_by_product_id IS NOT NULL
        GROUP BY child.part_no, parent.product_name, parent.serial_no, o.order_no
    """
    cur.execute(sql_det, (target_purchase_id,))
    consumption_details = []
    for row in cur.fetchall():
        consumption_details.append({
            'item_code': row[0],
            'parent_name': row[1],
            'parent_serial': row[2] or '',
            'order_no': row[3] or '',
            'qty': row[4]
        })
    
    return {
        'my_surplus': my_final_stock, 
        'my_allocations': my_allocations, 
        'other_allocations': other_allocations,
        'my_consumption': consumption_map,         # {code: total_consumed_qty}
        'consumption_details': consumption_details # List of usage details
    }


def get_purchase_report_data(purchase_id: int) -> dict:
    """
    발주 상세 리포트용 데이터를 조회합니다.
    - 발주 기본 정보 (purchases)
    - 발주 품목 (purchase_items) -> 납품 수량, 잔량, [New] Smart FIFO Allocation Status
    - 연결된 주문 (orders)
    - 연결된 납품 (deliveries)
    """
    conn = get_conn()
    cur = conn.cursor()

    # 1. 발주 기본 정보 (실발주액 단위 보정 / 1000.0)
    sql_purchase = """
        SELECT id, purchase_no, purchase_dt, status, actual_amount 
        FROM purchases 
        WHERE id = ?
    """
    cur.execute(sql_purchase, (purchase_id,))
    p_row = cur.fetchone()
    if not p_row:
        return {}
    
    purchase_info = {
        'id': p_row[0],
        'purchase_no': p_row[1],
        'purchase_dt': p_row[2],
        'status': p_row[3],
        'actual_amount': (p_row[4] or 0) / 1000.0
    }

    # [New] 스마트 할당 계산 실행
    smart_data = get_smart_allocation_status(purchase_id)
    my_surplus_map = smart_data['my_surplus']
    
    # 2. 발주 품목 정보
    sql_items = """
        SELECT 
            pi.item_code, 
            pi.product_name, 
            pi.qty, 
            pi.unit_price_cents, 
            pi.currency, 
            pi.rev,
            (SELECT COALESCE(SUM(di.qty), 0) 
             FROM delivery_items di 
             WHERE di.purchase_id = pi.purchase_id AND di.item_code = pi.item_code) as delivered_qty,
            (SELECT COALESCE(SUM(oi.qty), 0)
             FROM order_items oi
             JOIN purchase_order_links pol ON pol.order_id = oi.order_id
             WHERE pol.purchase_id = pi.purchase_id AND oi.item_code = pi.item_code) as linked_req_qty
        FROM purchase_items pi
        WHERE pi.purchase_id = ?
        ORDER BY pi.item_code
    """
    cur.execute(sql_items, (purchase_id,))
    purchase_items = []
    total_ordered_qty = 0
    total_delivered_qty_history = 0 # (여기서는 계산 안 하고 아래에서 계산)
    
    for row in cur.fetchall():
        item_code = row[0]
        p_qty = row[2]
        d_qty = row[6]
        req_qty = row[7]
        
        total_ordered_qty += p_qty

        # [New] Smart Data 병합
        # 진정한 잔량은 Smart Allocation 후 남은 재고
        true_surplus = my_surplus_map.get(item_code, 0)
        
        purchase_items.append({
            'item_code': item_code,
            'product_name': row[1],
            'qty': p_qty,
            'delivered_qty': d_qty,
            'balance': p_qty - d_qty, # 물리적 잔량 (실제 미입고)
            'linked_req_qty': req_qty,
            'true_surplus': true_surplus, # 논리적 잔여량 (할당 후 남은 것)
            'unit_price': row[3] / 100.0 if row[3] else 0,
            'currency': row[4],
            'rev': row[5] or ''
        })

    # 3. 연결된 주문 정보
    sql_orders = """
        SELECT 
            o.order_no, 
            o.req_due, 
            o.final_due, 
            o.status, 
            pol.order_id,
            (SELECT GROUP_CONCAT(product_name, ', ') FROM order_items oi WHERE oi.order_id = o.id) as order_products,
            (SELECT COALESCE(SUM(oi.qty),0) FROM order_items oi WHERE oi.order_id = o.id) as total_order_qty,
            (SELECT COALESCE(SUM(di.qty),0) FROM delivery_items di WHERE di.order_id = o.id AND di.delivery_id IN (SELECT id FROM deliveries WHERE invoice_done=1 OR invoice_done=0)) as shipped_qty
        FROM purchase_order_links pol
        JOIN orders o ON pol.order_id = o.id
        WHERE pol.purchase_id = ?
        ORDER BY o.order_no
    """
    cur.execute(sql_orders, (purchase_id,))
    linked_orders = []
    total_linked_order_qty = 0
    total_linked_shipped_qty = 0

    for row in cur.fetchall():
        ord_qty = row[6]
        shp_qty = row[7]
        total_linked_order_qty += ord_qty
        total_linked_shipped_qty += shp_qty

        linked_orders.append({
            'order_no': row[0],
            'req_due': row[1],
            'final_due': row[2],
            'status': row[3],
            'order_id': row[4],
            'product_summary': row[5] or "",
            'total_qty': ord_qty,
            'shipped_qty': shp_qty,
            'remaining_qty': ord_qty - shp_qty
        })

    # 4. 연결된 납품 이력
    sql_deliveries = """
        SELECT d.invoice_no, d.ship_datetime, di.item_code, di.product_name, di.qty, di.serial_no
        FROM delivery_items di
        JOIN deliveries d ON di.delivery_id = d.id
        WHERE di.purchase_id = ?
        ORDER BY d.ship_datetime DESC, d.invoice_no
    """
    cur.execute(sql_deliveries, (purchase_id,))
    delivery_history = []
    total_delivered_qty_for_summary = 0
    
    for row in cur.fetchall():
        qty = row[4]
        total_delivered_qty_for_summary += qty
        delivery_history.append({
            'invoice_no': row[0],
            'ship_date': row[1],
            'item_code': row[2],
            'product_name': row[3],
            'qty': qty,
            'serial_no': row[5] or ''
        })
    
    # 5. 종합 요약
    phys_balance = total_ordered_qty - total_delivered_qty_for_summary
    
    return {
        'purchase_info': purchase_info,
        'purchase_items': purchase_items, 
        'linked_orders': linked_orders, 
        'delivery_history': delivery_history,
        'smart_data': smart_data, # [New]
        'summary': {
            'total_ordered_qty': total_ordered_qty,
            'total_delivered_qty': total_delivered_qty_for_summary,
            'balance': phys_balance,
            'total_linked_order_qty': total_linked_order_qty,
        }
    }


# ===== 매입 관리 (Suppliers, Tax Invoices, Payments) =====

def get_all_suppliers() -> list[dict]:
    """모든 공급처 정보를 반환합니다."""
    sql = "SELECT id, biz_no, name, ceo_name, contact, address FROM suppliers ORDER BY name ASC"
    rows = query_all(sql)
    return [
        {'id': row[0], 'biz_no': row[1], 'name': row[2], 'ceo_name': row[3], 'contact': row[4], 'address': row[5]} 
        for row in rows
    ]

def search_suppliers(term: str) -> list[dict]:
    """상호, 사업자번호, 대표자명으로 공급처를 검색합니다."""
    sql = """
        SELECT id, biz_no, name, ceo_name, biz_type, biz_item, contact, email, address 
        FROM suppliers 
        WHERE name LIKE ? OR biz_no LIKE ? OR ceo_name LIKE ?
        ORDER BY name ASC
    """
    pattern = f"%{term}%"
    rows = query_all(sql, (pattern, pattern, pattern))
    return [
        {
            'id': row[0], 'biz_no': row[1], 'name': row[2], 'ceo_name': row[3], 
            'biz_type': row[4], 'biz_item': row[5], 'contact': row[6], 
            'email': row[7], 'address': row[8]} 
        for row in rows
    ]

def get_supplier(supplier_id: int) -> dict:
    """ID로 공급처 상세 정보를 조회합니다."""
    sql = """
        SELECT id, biz_no, name, ceo_name, biz_type, biz_item, contact, email, address 
        FROM suppliers 
        WHERE id = ?
    """
    res = query_one(sql, (supplier_id,))
    if res:
        return {
            'id': res[0], 'biz_no': res[1], 'name': res[2], 'ceo_name': res[3], 
            'biz_type': res[4], 'biz_item': res[5], 'contact': res[6], 
            'email': res[7], 'address': res[8]
        }
    return None

def get_all_suppliers() -> list[dict]:
    """모든 공급처 목록을 반환합니다."""
    sql = "SELECT id, biz_no, name, ceo_name FROM suppliers ORDER BY name ASC"
    rows = query_all(sql)
    return [{'id': r[0], 'biz_no': r[1], 'name': r[2], 'ceo_name': r[3]} for r in rows]

def add_or_update_supplier(data: dict) -> int:
    """공급처 정보를 추가하거나 업데이트합니다."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO suppliers (biz_no, name, ceo_name, biz_type, biz_item, contact, email, address, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(name) DO UPDATE SET
                biz_no = excluded.biz_no,
                ceo_name = excluded.ceo_name,
                biz_type = excluded.biz_type,
                biz_item = excluded.biz_item,
                contact = excluded.contact,
                email = excluded.email,
                address = excluded.address,
                updated_at = datetime('now','localtime')
        """, (data.get('biz_no'), data['name'], data.get('ceo_name'), 
              data.get('biz_type'), data.get('biz_item'),
              data.get('contact'), data.get('email'), data.get('address')))
        # INSERT 또는 UPDATE 이후 확실하게 ID를 가져옴
        cur.execute("SELECT id FROM suppliers WHERE name = ?", (data['name'],))
        row = cur.fetchone()
        conn.commit()
        return row[0] if row else -1
    except Exception as e:
        print(f"add_or_update_supplier error: {e}")
        return -1
    finally:
        conn.close()

def add_purchase_tax_invoice(invoice_data: dict, purchase_ids: list[int] = None) -> int:
    """매입 세금계산서를 등록하고 관련 발주(PO)를 연결합니다."""
    # supplier_id가 0이거나 None이면 이름으로 조회 시도
    supplier_id = invoice_data.get('supplier_id')
    supplier_name = invoice_data.get('supplier_name')
    
    if (not supplier_id or supplier_id == 0) and supplier_name:
        res = query_one("SELECT id FROM suppliers WHERE name = ?", (supplier_name,))
        if res:
            supplier_id = res[0]
        else:
            # 공급자가 없으면 생성
            supplier_id = add_or_update_supplier({'name': supplier_name})
            
    if not supplier_id or supplier_id == -1:
        # 여전히 ID가 없으면 진행 불가
        print(f"Error: Could not resolve supplier_id for '{supplier_name}'")
        return -1
        
    invoice_data['supplier_id'] = supplier_id

    conn = get_conn()
    try:
        cur = conn.cursor()
        total = invoice_data.get('total_amount', 0)
        supply = invoice_data.get('supply_amount', 0)
        tax = invoice_data.get('tax_amount', 0)
        if supply == 0 and total > 0:
            supply = round(total / 1.1)
            tax = total - supply
        elif total == 0 and supply > 0:
            tax = round(supply * 0.1)
            total = supply + tax

        invoice_id = invoice_data.get('id')
        approval_number = invoice_data.get('approval_number')
        if approval_number == "":
            approval_number = None

        if invoice_id:
            cur.execute("""
                UPDATE purchase_tax_invoices SET
                    issue_date = ?, supplier_id = ?, total_amount = ?, 
                    supply_amount = ?, tax_amount = ?,
                    approval_number = ?, note = ?, updated_at = datetime('now','localtime')
                WHERE id = ?
            """, (invoice_data['issue_date'], invoice_data['supplier_id'], total, supply, tax,
                  approval_number, invoice_data.get('note'), invoice_id))
            if purchase_ids is not None:
                cur.execute("DELETE FROM purchase_invoice_links WHERE tax_invoice_id = ?", (invoice_id,))
                for pid in purchase_ids:
                    cur.execute("INSERT INTO purchase_invoice_links (tax_invoice_id, purchase_id) VALUES (?, ?)", (invoice_id, pid))
        else:
            cur.execute("""
                INSERT INTO purchase_tax_invoices (issue_date, supplier_id, total_amount, supply_amount, tax_amount, approval_number, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (invoice_data['issue_date'], invoice_data['supplier_id'], total, supply, tax,
                  approval_number, invoice_data.get('note')))
            invoice_id = cur.lastrowid
            if purchase_ids:
                for pid in purchase_ids:
                    cur.execute("INSERT INTO purchase_invoice_links (tax_invoice_id, purchase_id) VALUES (?, ?)", (invoice_id, pid))
        conn.commit()
        return invoice_id
    except Exception as e:
        print(f"add_purchase_tax_invoice error: {e}")
        conn.rollback()
        return -1
    finally:
        conn.close()

add_tax_invoice = add_purchase_tax_invoice


def get_purchase_tax_invoices(supplier_id: int = None, purchase_id: int = None) -> list[dict]:
    """조건에 맞는 매입 세금계산서 목록을 조회합니다."""
    sql = """
        SELECT inv.id, inv.issue_date, inv.supplier_id, s.name, inv.total_amount, 
               inv.supply_amount, inv.tax_amount,
               inv.approval_number, inv.status, inv.note,
               (SELECT GROUP_CONCAT(p.purchase_no, ', ') 
                FROM purchase_invoice_links l 
                JOIN purchases p ON l.purchase_id = p.id 
                WHERE l.tax_invoice_id = inv.id) as linked_pos,
               (SELECT COALESCE(SUM(amount), 0) FROM purchase_payments WHERE tax_invoice_id = inv.id) as paid_amount
        FROM purchase_tax_invoices inv
        JOIN suppliers s ON inv.supplier_id = s.id
    """
    params = []
    where_clauses = []
    
    if supplier_id:
        where_clauses.append("inv.supplier_id = ?")
        params.append(supplier_id)
    
    if purchase_id:
        where_clauses.append("inv.id IN (SELECT tax_invoice_id FROM purchase_invoice_links WHERE purchase_id = ?)")
        params.append(purchase_id)
        
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    
    sql += " ORDER BY inv.issue_date DESC"
    
    rows = query_all(sql, tuple(params))
    return [
        {
            'id': r[0], 'issue_date': r[1], 'supplier_id': r[2], 'supplier_name': r[3], 'total_amount': r[4],
            'supply_amount': r[5], 'tax_amount': r[6],
            'approval_number': r[7], 'status': r[8], 'note': r[9], 'linked_pos': r[10],
            'paid_amount': r[11], 'balance': r[4] - r[11]
        }
        for r in rows
    ]

# Alias
get_tax_invoices_for_purchase = lambda pid: get_purchase_tax_invoices(purchase_id=pid)

def add_purchase_payment(payment_data: dict) -> bool:
    """대금 지불 내역을 등록하고 세금계산서의 지불 상태를 자동 업데이트합니다."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        # 금액 보정
        total = payment_data.get('amount', 0)
        supply = payment_data.get('supply_amount', 0)
        tax = payment_data.get('tax_amount', 0)
        if total > 0 and supply == 0:
            supply = round(total / 1.1)
            tax = total - supply
        elif supply > 0 and total == 0:
            tax = round(supply * 0.1)
            total = supply + tax

        # 1. 지불 내역 삽입
        cur.execute("""
            INSERT INTO purchase_payments (tax_invoice_id, payment_date, amount, supply_amount, tax_amount, payment_method, note, purchase_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (payment_data['tax_invoice_id'], payment_data['payment_date'], 
              total, supply, tax, payment_data['payment_method'], payment_data.get('note'), payment_data.get('purchase_id')))
        
        # 2. 상태 업데이트
        _update_purchase_invoice_status(payment_data['tax_invoice_id'], cur)
        
        conn.commit()
        return True
    except Exception as e:
        print(f"add_purchase_payment error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_purchase_payments(tax_invoice_id: int, purchase_id: int = None) -> list[dict]:
    """특정 세금계산서(및 특정 발주)에 대한 지불 내역을 조회합니다."""
    if purchase_id is None:
        # 인보이스 상세 보기 등에서는 모든 지불 내역을 다 가져옴
        sql = """
            SELECT id, payment_date, amount, supply_amount, tax_amount, payment_method, note, purchase_id
            FROM purchase_payments
            WHERE tax_invoice_id = ?
            ORDER BY payment_date DESC
        """
        rows = query_all(sql, (tax_invoice_id,))
    else:
        # 특정 발주 건에 대한 지불만 필터링
        sql = """
            SELECT id, payment_date, amount, supply_amount, tax_amount, payment_method, note, purchase_id
            FROM purchase_payments
            WHERE tax_invoice_id = ? AND (purchase_id = ? OR purchase_id IS NULL)
            ORDER BY payment_date DESC
        """
        rows = query_all(sql, (tax_invoice_id, purchase_id))
        
    return [
        {
            'id': r[0], 'payment_date': r[1], 'amount': r[2],
            'supply_amount': r[3], 'tax_amount': r[4],
            'payment_method': r[5], 'note': r[6], 'purchase_id': r[7]
        }
        for r in rows
    ]

def delete_purchase_payment(payment_id: int) -> bool:
    """지불 내역을 삭제하고 세금계산서 상태를 자동 갱신합니다."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT tax_invoice_id FROM purchase_payments WHERE id = ?", (payment_id,))
        row = cur.fetchone()
        if not row:
            return False
        tax_invoice_id = row[0]
        
        cur.execute("DELETE FROM purchase_payments WHERE id = ?", (payment_id,))
        _update_purchase_invoice_status(tax_invoice_id, cur)
        conn.commit()
        return True
    except Exception as e:
        print(f"delete_purchase_payment error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# Alias 
add_payment = lambda pid, d, amt, meth, note, tax_invoice_id=None: add_purchase_payment({
    'tax_invoice_id': tax_invoice_id, 'payment_date': d, 'amount': amt, 'payment_method': meth, 'note': note
})

def _update_purchase_invoice_status(invoice_id: int, cursor):
    """지불 금액을 합산하여 세금계산서의 상태(미지불/부분지불/완료)를 자동 갱신합니다."""
    # 총액 조회
    cursor.execute("SELECT total_amount FROM purchase_tax_invoices WHERE id = ?", (invoice_id,))
    total = cursor.fetchone()[0]
    
    # 지불 합계 조회
    cursor.execute("SELECT SUM(amount) FROM purchase_payments WHERE tax_invoice_id = ?", (invoice_id,))
    paid = cursor.fetchone()[0] or 0
    
    if paid >= total:
        status = '지불완료'
    elif paid > 0:
        status = '부분지불'
    else:
        status = '미지불'
        
    cursor.execute("UPDATE purchase_tax_invoices SET status = ?, updated_at = datetime('now','localtime') WHERE id = ?", 
                   (status, invoice_id))

def get_purchase_payment_trend(year: int) -> list[dict]:
    """연도별 월간 매입 지불 현황을 집계합니다."""
    sql = """
        SELECT strftime('%m', payment_date) as month, SUM(amount) as total
        FROM purchase_payments
        WHERE strftime('%Y', payment_date) = ?
        GROUP BY month
        ORDER BY month ASC
    """
    rows = query_all(sql, (str(year),))
    return [{'month': r[0], 'total': r[1]} for r in rows]

def get_purchase_payment_status_for_po(purchase_id: int) -> dict:
    """특정 발주(PO) 건에 연결된 세금계산서 및 지불 현황 요약을 반환합니다."""
    sql = """
        SELECT 
            COUNT(inv.id) as invoice_count,
            SUM((
                SELECT COALESCE(SUM(supply_amount + tax_amount), 0) 
                FROM purchase_tax_invoice_items 
                WHERE tax_invoice_id = inv.id AND purchase_id = ?
            )) as total_invoiced,
            SUM((
                SELECT COALESCE(SUM(pay.amount), 0) 
                FROM purchase_payments pay 
                WHERE pay.tax_invoice_id = inv.id 
                  AND (pay.purchase_id = ? OR pay.purchase_id IS NULL)
            )) as total_paid
        FROM purchase_invoice_links link
        JOIN purchase_tax_invoices inv ON link.tax_invoice_id = inv.id
        WHERE link.purchase_id = ?
    """
    row = query_one(sql, (purchase_id, purchase_id, purchase_id))
    if not row or row[0] == 0:
        return {'invoice_count': 0, 'total_invoiced': 0, 'total_paid': 0, 'status': '미발행'}
    
    total_invoiced = row[1] or 0
    total_paid = row[2] or 0
    
    if total_paid >= total_invoiced:
        status = '지불완료'
    elif total_paid > 0:
        status = '부분지불'
    else:
        status = '미지불'
        
    return {
        'invoice_count': row[0],
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'status': status
    }

def get_available_purchases_for_tax() -> list[tuple]:
    """매입 세금계산서와 연결 가능한 발주(PO) 목록을 반환합니다."""
    sql = """
        SELECT id, purchase_no, purchase_dt, status, actual_amount
        FROM purchases
        WHERE status != '삭제'
/*        AND id NOT IN (SELECT purchase_id FROM purchase_invoice_links)  -- 이미 연결된 것은 제외할지 여부 (복수 연결 허용 시 주석) */
        ORDER BY purchase_dt DESC
    """
    return query_all(sql)

def delete_purchase_tax_invoice(invoice_id: int) -> bool:
    """세금계산서 및 관련 연결 정보를 삭제합니다."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM purchase_tax_invoices WHERE id = ?", (invoice_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"delete_purchase_tax_invoice error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_payments_for_purchase(purchase_id: int) -> list[dict]:
    """특정 발주와 관련된 모든 지불 내역을 조회합니다."""
    sql = """
        SELECT p.id, p.tax_invoice_id, p.payment_date, p.amount, p.supply_amount, p.tax_amount, p.payment_method, p.note
        FROM purchase_payments p
        JOIN purchase_invoice_links l ON p.tax_invoice_id = l.tax_invoice_id
        WHERE l.purchase_id = ?
        ORDER BY p.payment_date DESC
    """
    rows = query_all(sql, (purchase_id,))
    return [
        {
            'id': r[0], 'tax_invoice_id': r[1], 'payment_date': r[2], 
            'amount': r[3], 'supply_amount': r[4], 'tax_amount': r[5],
            'payment_method': r[6], 'note': r[7]
        }
        for r in rows
    ]

def delete_payment(payment_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.cursor()
        # 원본 invoice_id 찾기
        cur.execute("SELECT tax_invoice_id FROM purchase_payments WHERE id = ?", (payment_id,))
        res = cur.fetchone()
        if res:
            invoice_id = res[0]
            cur.execute("DELETE FROM purchase_payments WHERE id = ?", (payment_id,))
            _update_purchase_invoice_status(invoice_id, cur)
        conn.commit()
        return True
    except Exception as e:
        print(f"delete_payment error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def update_payment(payment_id, amount, method, note):
    conn = get_conn()
    try:
        cur = conn.cursor()
        # Find invoice_id
        cur.execute("SELECT tax_invoice_id FROM purchase_payments WHERE id = ?", (payment_id,))
        res = cur.fetchone()
        if res:
            invoice_id = res[0]
            cur.execute("""
                UPDATE purchase_payments SET 
                    amount = ?, 
                    supply_amount = ROUND(? / 1.1),
                    tax_amount = ? - ROUND(? / 1.1),
                    payment_method = ?, note = ?, updated_at = datetime('now','localtime')
                WHERE id = ?
            """, (amount, amount, amount, amount, method, note, payment_id))
            _update_purchase_invoice_status(invoice_id, cur)
        conn.commit()
    finally:
        conn.close()

# Missing functions required by UI
def link_tax_invoice_to_purchase(invoice_id, purchase_id):
    execute("INSERT OR IGNORE INTO purchase_invoice_links (tax_invoice_id, purchase_id) VALUES (?, ?)", (invoice_id, purchase_id))

def get_purchase_payment_summary(purchase_id):
    return get_purchase_payment_status_for_po(purchase_id)

def get_tax_invoice_items(invoice_id):
    """세금계산서의 상세 품목 리스트를 반환합니다. (현재 인보이스 내의 지불 상태 및 잔액 포함)"""
    sql = """
        SELECT id, item_name, spec, quantity, unit_price, supply_amount, tax_amount, purchase_id, purchase_no, note
        FROM purchase_tax_invoice_items
        WHERE tax_invoice_id = ?
        ORDER BY id
    """
    rows = query_all(sql, (invoice_id,))
    
    # 1. 해당 세금계산서의 총 지불액/청구액 확인
    total_paid_sql = "SELECT COALESCE(SUM(amount), 0) FROM purchase_payments WHERE tax_invoice_id = ?"
    total_invoice_paid = query_one(total_paid_sql, (invoice_id,))[0]

    total_amt_sql = "SELECT total_amount FROM purchase_tax_invoices WHERE id = ?"
    total_invoice_amt = query_one(total_amt_sql, (invoice_id,))[0]
    
    is_fully_paid = (total_invoice_paid >= total_invoice_amt and total_invoice_amt > 0)

    # 2. PO별 지불액 합계 미리 로드 (특정 품목 지불 시 purchase_id가 기록됨)
    pay_sql = """
        SELECT purchase_id, SUM(amount) as paid_sum 
        FROM purchase_payments 
        WHERE tax_invoice_id = ?
        GROUP BY purchase_id
    """
    pay_rows = query_all(pay_sql, (invoice_id,))
    po_paid_map = {r[0]: r[1] for r in pay_rows}

    items = []
    for r in rows:
        item_total = r[5] + r[6]
        item = {
            'id': r[0], 'item_name': r[1], 'spec': r[2], 'quantity': r[3],
            'unit_price': r[4], 'supply_amount': r[5], 'tax_amount': r[6],
            'purchase_id': r[7], 'purchase_no': r[8], 'note': r[9],
            'total': item_total
        }
        
        # 지불 상태 및 잔액 결정 (인보이스 전체 완납 시 우선 처리)
        if is_fully_paid:
            item['po_status'] = "지불완료"
            item['balance'] = 0
        else:
            # PO별 지불 항목 매칭
            po_paid = po_paid_map.get(item['purchase_id'], 0)
            if po_paid > 0:
                # 해당 PO의 이 인보이스 내 전체 합계 계산
                po_total_in_inv = sum(row[5] + row[6] for row in rows if row[7] == item['purchase_id'])
                
                if po_paid >= po_total_in_inv:
                    item['po_status'] = "지불완료"
                    item['balance'] = 0
                else:
                    item['po_status'] = "부분지불"
                    ratio = po_paid / po_total_in_inv
                    item['balance'] = max(0, item_total - round(item_total * ratio))
            else:
                item['po_status'] = "미지불"
                item['balance'] = item_total
            
        items.append(item)
    return items

def add_tax_invoice_item(invoice_id, item_name, spec, quantity, unit_price, purchase_no=None, purchase_id=None, purchase_item_id=None, note=None):
    """세금계산서에 품목을 추가하고 헤더의 총액을 업데이트합니다."""
    supply = quantity * unit_price
    tax = round(supply * 0.1)
    
    execute("""
        INSERT INTO purchase_tax_invoice_items (
            tax_invoice_id, item_name, spec, quantity, unit_price, 
            supply_amount, tax_amount, purchase_id, purchase_item_id, purchase_no, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (invoice_id, item_name, spec, quantity, unit_price, supply, tax, purchase_id, purchase_item_id, purchase_no, note))
    
    update_tax_invoice_total(invoice_id)
    
    if purchase_id:
        link_tax_invoice_to_purchase(invoice_id, purchase_id)

def update_purchase_tax_invoice_header(invoice_id, data):
    """세금계산서 헤더 정보(날짜, 공급자 등)를 업데이트합니다."""
    sql = """
        UPDATE purchase_tax_invoices 
        SET issue_date = ?, supplier_id = ?, approval_number = ?, note = ?, updated_at = datetime('now','localtime')
        WHERE id = ?
    """
    execute(sql, (data['issue_date'], data['supplier_id'], data.get('approval_number'), data.get('note', ""), invoice_id))

def clear_tax_invoice_items(invoice_id):
    """세금계산서의 모든 품목 및 발주 연결 정보를 삭제합니다 (수정 전 초기화용)."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM purchase_tax_invoice_items WHERE tax_invoice_id = ?", (invoice_id,))
        cur.execute("DELETE FROM purchase_invoice_links WHERE tax_invoice_id = ?", (invoice_id,))
        conn.commit()
    finally:
        conn.close()

def delete_tax_invoice_item(item_id):
    """현재 스키마에선 품목 ID가 없으므로 무시하거나 인보이스 전체 금액 초기화 시 사용"""
    pass

def update_tax_invoice_total(invoice_id):
    """세금계산서의 품목 합계를 계산하여 헤더 정보를 갱신하고 결제 상태를 업데이트합니다."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        # 품목 합계 계산
        cur.execute("SELECT SUM(supply_amount), SUM(tax_amount) FROM purchase_tax_invoice_items WHERE tax_invoice_id = ?", (invoice_id,))
        res = cur.fetchone()
        supply = res[0] or 0
        tax = res[1] or 0
        total = supply + tax
        
        # 헤더 업데이트
        cur.execute("""
            UPDATE purchase_tax_invoices 
            SET supply_amount = ?, tax_amount = ?, total_amount = ?, updated_at = datetime('now','localtime')
            WHERE id = ?
        """, (supply, tax, total, invoice_id))
        
        # 결제 상태 업데이트 (기존 로직 재사용)
        _update_purchase_invoice_status(invoice_id, cur)
        
        conn.commit()
    finally:
        conn.close()

def get_available_purchases_for_invoice():
    """인보이스 연결이 가능한 발주 목록 (get_available_purchases_for_tax와 동일)"""
    return get_available_purchases_for_tax()

def get_tax_invoice_detail(invoice_id):
    """세금계산서 상세 정보를 반환합니다. (공급자 명, 금액 일체 포함)"""
    sql = """
        SELECT inv.id, inv.issue_date, inv.supplier_id, s.name, inv.total_amount, 
               inv.supply_amount, inv.tax_amount, inv.approval_number, inv.note
        FROM purchase_tax_invoices inv
        JOIN suppliers s ON inv.supplier_id = s.id
        WHERE inv.id = ?
    """
    r = query_one(sql, (invoice_id,))
    if r:
        return {
            'id': r[0], 
            'issue_date': r[1], 
            'supplier_id': r[2], 
            'supplier_name': r[3],
            'total_amount': r[4], 
            'supply_amount': r[5], 
            'tax_amount': r[6],
            'approval_number': r[7], 
            'note': r[8],
            'items': get_tax_invoice_items(r[0]),
            'payments': get_purchase_payments(r[0]) # 지불 내역 추가
        }
    return None

def get_all_tax_invoices(start_date=None, end_date=None):
    """기간별 모든 세금계산서를 조회합니다."""
    sql = """
        SELECT inv.id, inv.issue_date, s.biz_no, s.name, s.ceo_name, 
               inv.supply_amount, inv.tax_amount, inv.total_amount, 
               (SELECT COUNT(*) FROM purchase_tax_invoice_items WHERE tax_invoice_id = inv.id) as item_count,
               inv.note,
               (SELECT COALESCE(SUM(amount), 0) FROM purchase_payments WHERE tax_invoice_id = inv.id) as paid_amount
        FROM purchase_tax_invoices inv
        JOIN suppliers s ON inv.supplier_id = s.id
    """
    params = []
    if start_date and end_date:
        sql += " WHERE inv.issue_date BETWEEN ? AND ?"
        params = [start_date, end_date]
    sql += " ORDER BY inv.issue_date DESC"
    return query_all(sql, tuple(params))

def delete_tax_invoice(invoice_id):
    return delete_purchase_tax_invoice(invoice_id)

def get_invoiced_item_ids_for_po(purchase_id):
    """특정 발주(PO)에서 이미 세금계산서가 발행된 품목 ID 목록을 반환합니다."""
    sql = "SELECT DISTINCT purchase_item_id FROM purchase_tax_invoice_items WHERE purchase_id = ? AND purchase_item_id IS NOT NULL"
    rows = query_all(sql, (purchase_id,))
    return [r[0] for r in rows]
