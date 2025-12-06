# migrate_delivery_items.py
import sqlite3
import os
from contextlib import contextmanager

# --- 설정 ---
# db.py 파일이 app 폴더 안에 있다고 가정합니다.
# 이 스크립트는 app 폴더의 부모 폴더(프로젝트 루트)에서 실행해야 합니다.
DB_PATH = os.path.join('app', 'db', 'production.db')


# ---

@contextmanager
def get_conn():
    """DB 연결 컨텍스트 매니저"""
    if not os.path.exists(DB_PATH):
        print(f"오류: 데이터베이스 파일을 찾을 수 없습니다. 경로: {DB_PATH}")
        print("이 스크립트를 프로젝트 루트 폴더에서 실행했는지 확인하세요.")
        raise FileNotFoundError(f"Database not found at {DB_PATH}")

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        print(f"데이터베이스 연결 오류: {e}")
    finally:
        if conn:
            conn.close()


def find_linked_order_id(conn, delivery_id, item_code):
    """
    납품 ID와 품목 코드를 기반으로 연결된 주문 ID를 찾습니다.
    (delivery_order_links -> order_items)
    """
    cur = conn.cursor()
    # 1. 이 납품에 연결된 모든 주문 ID를 예전 링크 테이블에서 찾음
    cur.execute("SELECT order_id FROM delivery_order_links WHERE delivery_id = ?", (delivery_id,))
    linked_order_ids = [row['order_id'] for row in cur.fetchall()]

    if not linked_order_ids:
        return None

    # 2. 그 주문들 중에서 이 품목 코드를 포함하는 주문을 찾음
    placeholders = ', '.join('?' for _ in linked_order_ids)
    cur.execute(f"""
        SELECT order_id 
        FROM order_items 
        WHERE order_id IN ({placeholders}) AND item_code = ?
        LIMIT 1
    """, (*linked_order_ids, item_code))

    result = cur.fetchone()
    return result['order_id'] if result else None


def find_linked_purchase_id(conn, delivery_id, item_code):
    """
    납품 ID와 품목 코드를 기반으로 연결된 발주 ID를 찾습니다.
    (delivery_purchase_links -> purchase_items)
    """
    cur = conn.cursor()
    # 1. 이 납품에 연결된 모든 발주 ID를 예전 링크 테이블에서 찾음
    cur.execute("SELECT purchase_id FROM delivery_purchase_links WHERE delivery_id = ?", (delivery_id,))
    linked_purchase_ids = [row['purchase_id'] for row in cur.fetchall()]

    if not linked_purchase_ids:
        return None

    # 2. 그 발주들 중에서 이 품목 코드를 포함하는 발주를 찾음
    placeholders = ', '.join('?' for _ in linked_purchase_ids)
    cur.execute(f"""
        SELECT purchase_id 
        FROM purchase_items 
        WHERE purchase_id IN ({placeholders}) AND item_code = ?
        LIMIT 1
    """, (*linked_purchase_ids, item_code))

    result = cur.fetchone()
    return result['purchase_id'] if result else None


def run_migration():
    """메인 마이그레이션 실행 함수"""
    print("데이터 복원 스크립트를 시작합니다...")
    print(f"데이터베이스 경로: {DB_PATH}\n")

    updated_order_count = 0
    updated_purchase_count = 0
    failed_items = []

    try:
        with get_conn() as conn:
            cur = conn.cursor()

            # 1. 대상 항목 조회 (order_id 또는 purchase_id가 NULL인 항목)
            cur.execute("""
                SELECT id, delivery_id, item_code, serial_no, order_id, purchase_id 
                FROM delivery_items 
                WHERE order_id IS NULL OR purchase_id IS NULL
            """)
            items_to_fix = cur.fetchall()

            if not items_to_fix:
                print("👍 모든 납품 품목 데이터가 이미 올바른 형식을 가지고 있습니다. 복원할 데이터가 없습니다.")
                return

            print(f"총 {len(items_to_fix)}개의 납품 품목에서 order_id 또는 purchase_id가 비어있습니다. 복원을 시도합니다...")

            update_cursor = conn.cursor()

            for item in items_to_fix:
                item_id = item['id']
                delivery_id = item['delivery_id']
                item_code = item['item_code']

                new_order_id = item['order_id']
                new_purchase_id = item['purchase_id']

                is_updated = False

                # 2. Order ID 복원 시도
                if item['order_id'] is None:
                    found_order_id = find_linked_order_id(conn, delivery_id, item_code)
                    if found_order_id:
                        new_order_id = found_order_id
                        update_cursor.execute("UPDATE delivery_items SET order_id = ? WHERE id = ?",
                                              (new_order_id, item_id))
                        updated_order_count += 1
                        is_updated = True

                # 3. Purchase ID 복원 시도
                if item['purchase_id'] is None:
                    found_purchase_id = find_linked_purchase_id(conn, delivery_id, item_code)
                    if found_purchase_id:
                        new_purchase_id = found_purchase_id
                        update_cursor.execute("UPDATE delivery_items SET purchase_id = ? WHERE id = ?",
                                              (new_purchase_id, item_id))
                        updated_purchase_count += 1
                        is_updated = True

                if is_updated:
                    print(
                        f"  [성공] 품목 ID: {item_id} (S/N: {item['serial_no']}) -> (Order: {new_order_id}, Purchase: {new_purchase_id})")
                else:
                    failed_items.append(item)
                    print(f"  [실패] 품목 ID: {item_id} (S/N: {item['serial_no']}) -> 연결된 주문/발주를 찾을 수 없습니다.")

            # 4. 변경 사항 최종 저장
            conn.commit()

            print("\n--- 복원 완료 ---")
            print(f"✅ Order ID 업데이트: {updated_order_count}건")
            print(f"✅ Purchase ID 업데이트: {updated_purchase_count}건")

            if failed_items:
                print(f"⚠️ 총 {len(failed_items)}건의 품목 ID는 복원에 실패했습니다 (데이터 불일치).")

    except sqlite3.Error as e:
        print(f"\n[치명적 오류] 마이그레이션 중단: {e}")
        print("데이터베이스가 변경되지 않았습니다.")
    except FileNotFoundError:
        # get_conn에서 이미 메시지를 출력했으므로 여기선 종료만 함
        pass


if __name__ == "__main__":
    # 실행 전 중요 안내
    print("=" * 60)
    print(" KOBATECH DB 데이터 복원 스크립트")
    print("=" * 60)
    print("이 스크립트는 'delivery_items' 테이블의 비어있는(NULL) 'order_id'")
    print("와 'purchase_id' 컬럼을 예전 연결 데이터를 기반으로 채웁니다.")
    print("\n[중요] 실행 전 'production.db' 파일을 반드시 백업하세요!\n")

    answer = input("계속 진행하시겠습니까? (y/n): ")

    if answer.lower() == 'y':
        run_migration()
    else:
        print("작업을 취소했습니다.")