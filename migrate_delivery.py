# migrate_delivery_data.py
# 구 방식(deliveries.order_id/purchase_id)에서 신규 방식(링크 테이블)으로 데이터 마이그레이션

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import get_conn


def migrate_delivery_data():
    """구 방식의 납품 데이터를 신규 방식으로 마이그레이션"""

    print("=" * 80)
    print("납품 데이터 마이그레이션 시작")
    print("=" * 80)
    print("구 방식: deliveries.order_id, deliveries.purchase_id")
    print("신규 방식: delivery_order_links, delivery_purchase_links")
    print("=" * 80)

    conn = get_conn()
    cur = conn.cursor()

    try:
        # 1. 마이그레이션이 필요한 납품 찾기
        cur.execute("""
            SELECT id, invoice_no, order_id, purchase_id
            FROM deliveries
            WHERE order_id IS NOT NULL OR purchase_id IS NOT NULL
            ORDER BY id
        """)

        deliveries_to_migrate = cur.fetchall()

        if not deliveries_to_migrate:
            print("\n✅ 마이그레이션이 필요한 데이터가 없습니다!")
            conn.close()
            return

        print(f"\n📋 마이그레이션 대상: {len(deliveries_to_migrate)}개 납품\n")

        migrated_count = 0

        for delivery in deliveries_to_migrate:
            delivery_id, invoice_no, old_order_id, old_purchase_id = delivery

            print(f"[{delivery_id}] {invoice_no}")
            print(f"  기존: order_id={old_order_id}, purchase_id={old_purchase_id}")

            # 2. delivery_order_links에 이미 데이터가 있는지 확인
            if old_order_id:
                cur.execute("""
                    SELECT COUNT(*) FROM delivery_order_links 
                    WHERE delivery_id = ? AND order_id = ?
                """, (delivery_id, old_order_id))

                order_link_exists = cur.fetchone()[0] > 0

                if not order_link_exists:
                    # 링크가 없으면 생성
                    cur.execute("""
                        INSERT INTO delivery_order_links (delivery_id, order_id)
                        VALUES (?, ?)
                    """, (delivery_id, old_order_id))
                    print(f"  ✅ order_id={old_order_id}를 delivery_order_links에 추가")
                else:
                    print(f"  ℹ️  order_id={old_order_id}는 이미 delivery_order_links에 있음")

            # 3. delivery_purchase_links에 이미 데이터가 있는지 확인
            if old_purchase_id:
                cur.execute("""
                    SELECT COUNT(*) FROM delivery_purchase_links 
                    WHERE delivery_id = ? AND purchase_id = ?
                """, (delivery_id, old_purchase_id))

                purchase_link_exists = cur.fetchone()[0] > 0

                if not purchase_link_exists:
                    # 링크가 없으면 생성
                    cur.execute("""
                        INSERT INTO delivery_purchase_links (delivery_id, purchase_id)
                        VALUES (?, ?)
                    """, (delivery_id, old_purchase_id))
                    print(f"  ✅ purchase_id={old_purchase_id}를 delivery_purchase_links에 추가")
                else:
                    print(f"  ℹ️  purchase_id={old_purchase_id}는 이미 delivery_purchase_links에 있음")

            # 4. 구 컬럼을 NULL로 설정
            cur.execute("""
                UPDATE deliveries 
                SET order_id = NULL, purchase_id = NULL
                WHERE id = ?
            """, (delivery_id,))
            print(f"  ✅ deliveries.order_id, purchase_id를 NULL로 설정\n")

            migrated_count += 1

        # 커밋
        conn.commit()

        print("=" * 80)
        print(f"✅ 마이그레이션 완료: {migrated_count}개 납품 처리됨")
        print("=" * 80)

        # 5. 마이그레이션 결과 확인
        print("\n검증 중...")

        cur.execute("""
            SELECT COUNT(*) FROM deliveries 
            WHERE order_id IS NOT NULL OR purchase_id IS NOT NULL
        """)
        remaining = cur.fetchone()[0]

        if remaining > 0:
            print(f"⚠️  경고: 아직 {remaining}개의 납품이 구 방식을 사용 중입니다!")
        else:
            print("✅ 모든 납품이 신규 방식으로 마이그레이션되었습니다!")

        # 링크 테이블 통계
        cur.execute("SELECT COUNT(*) FROM delivery_order_links")
        order_links_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM delivery_purchase_links")
        purchase_links_count = cur.fetchone()[0]

        print(f"\n📊 최종 통계:")
        print(f"  - delivery_order_links: {order_links_count}개 연결")
        print(f"  - delivery_purchase_links: {purchase_links_count}개 연결")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

    finally:
        conn.close()

    print("\n" + "=" * 80)
    print("마이그레이션 완료!")
    print("=" * 80)


if __name__ == "__main__":
    # 사용자에게 확인
    print("\n⚠️  경고: 이 작업은 데이터베이스를 수정합니다!")
    print("계속하려면 'yes'를 입력하세요: ", end="")

    response = input().strip().lower()

    if response == 'yes':
        migrate_delivery_data()
    else:
        print("\n취소되었습니다.")