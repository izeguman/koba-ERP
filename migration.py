import sqlite3
import pandas as pd

# DB 파일 경로 (프로젝트 루트에 있다고 가정)
DB_PATH = "production.db"


def run_fix():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("--- 🛠️ 긴급 데이터 복구 및 진단 시작 ---")

    # 1. 타겟 설정 (문제가 된 발주와 주문)
    TARGET_PURCHASE_NO = 'TO2505-007'
    TARGET_ORDER_NO = '4502632255'

    # ID 조회
    cur.execute("SELECT id FROM purchases WHERE purchase_no = ?", (TARGET_PURCHASE_NO,))
    p_row = cur.fetchone()
    if not p_row:
        print(f"❌ 발주 {TARGET_PURCHASE_NO}를 찾을 수 없습니다.")
        return
    p_id = p_row[0]

    cur.execute("SELECT id FROM orders WHERE order_no = ?", (TARGET_ORDER_NO,))
    o_row = cur.fetchone()
    if not o_row:
        print(f"❌ 주문 {TARGET_ORDER_NO}를 찾을 수 없습니다.")
        return
    o_id = o_row[0]

    print(f"✅ 타겟 확인: 발주 ID {p_id} / 주문 ID {o_id}")

    # ---------------------------------------------------------
    # 2. [데이터 정제] 소모된 제품이 예약을 잡고 있는지 확인 및 강제 해제
    # ---------------------------------------------------------
    print("\n[1단계: 데이터 정제]")
    cur.execute("""
        SELECT id, serial_no, reserved_order_id 
        FROM products 
        WHERE consumed_by_product_id IS NOT NULL 
          AND reserved_order_id IS NOT NULL
    """)
    ghosts = cur.fetchall()

    if ghosts:
        print(f"⚠️ '소모되었는데 예약된' 유령 데이터 {len(ghosts)}건 발견! 강제 초기화합니다.")
        for g in ghosts:
            print(f"   - Product ID {g[0]} (S/N: {g[1]}) : 예약 {g[2]} -> NULL로 해제")

        cur.execute("""
            UPDATE products 
            SET reserved_order_id = NULL 
            WHERE consumed_by_product_id IS NOT NULL
        """)
        conn.commit()
        print("   -> ✅ 정제 완료.")
    else:
        print("   -> ✅ 소모된 제품 데이터는 깨끗합니다.")

    # ---------------------------------------------------------
    # 3. [상태 진단] 왜 할당이 안 되는지 수치 확인
    # ---------------------------------------------------------
    print("\n[2단계: 할당 조건 정밀 진단]")

    # A. 총 필요 수량
    cur.execute("""
        SELECT SUM(qty) FROM order_items 
        WHERE order_id = ? 
          AND item_code IN (SELECT item_code FROM purchase_items WHERE purchase_id = ?)
    """, (o_id, p_id))
    total_req = cur.fetchone()[0] or 0
    print(f"   A. 주문 총 필요량: {total_req}개")

    # B. 현재 예약된 수량 (소모품 제외 조건 포함)
    cur.execute("""
        SELECT COUNT(*) FROM products 
        WHERE reserved_order_id = ? 
          AND delivery_id IS NULL 
          AND consumed_by_product_id IS NULL
    """, (o_id,))
    reserved_qty = cur.fetchone()[0]
    print(f"   B. 현재 유효 예약량: {reserved_qty}개")

    # C. 납품된 수량
    cur.execute("""
        SELECT COALESCE(SUM(di.qty), 0)
        FROM delivery_items di
        WHERE di.order_id = ?
          AND di.item_code IN (SELECT item_code FROM purchase_items WHERE purchase_id = ?)
    """, (o_id, p_id))
    delivered_qty = cur.fetchone()[0]
    print(f"   C. 기 납품 수량: {delivered_qty}개")

    needed_qty = total_req - reserved_qty - delivered_qty
    print(f"   ▶ 계산된 부족 수량: {needed_qty}개 ({total_req} - {reserved_qty} - {delivered_qty})")

    # ---------------------------------------------------------
    # 4. [할당 시도] 가용 재고 확인 및 강제 할당
    # ---------------------------------------------------------
    if needed_qty > 0:
        print("\n[3단계: 재고 확인 및 할당]")

        # 가용 재고 조회
        cur.execute("""
            SELECT id, serial_no FROM products 
            WHERE purchase_id = ? 
              AND delivery_id IS NULL 
              AND consumed_by_product_id IS NULL
              AND reserved_order_id IS NULL
            ORDER BY id ASC
        """, (p_id,))
        free_stock = cur.fetchall()

        print(f"   - 현재 가용(자유) 재고: {len(free_stock)}개")

        if free_stock:
            target_prod = free_stock[0]
            print(f"   - 타겟 재고 발견: ID {target_prod[0]} (S/N: {target_prod[1]})")

            print("   🔄 강제 할당 실행 중...")
            cur.execute("""
                UPDATE products 
                SET reserved_order_id = ? 
                WHERE id = ?
            """, (o_id, target_prod[0]))
            conn.commit()
            print(f"   ✅ 할당 성공! (Product {target_prod[0]} -> Order {o_id})")
        else:
            print("   ❌ 할당할 자유 재고가 없습니다! (이미 다 예약되었거나 소모됨)")
    else:
        print("\n✅ 이미 필요한 수량이 모두 충족되어 있어 할당할 필요가 없습니다.")

    conn.close()


if __name__ == "__main__":
    run_fix()