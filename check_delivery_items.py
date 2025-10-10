# check_delivery_items.py
# KI20220728-01 납품의 품목을 상세히 확인합니다

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import get_conn


def check_delivery_items():
    """KI20220728-01 납품의 품목 상세 확인"""

    conn = get_conn()
    cur = conn.cursor()

    invoice_no = 'KI20220728-01'

    print("=" * 80)
    print(f"납품 품목 상세 확인: {invoice_no}")
    print("=" * 80)

    # 1. 납품 ID 찾기
    cur.execute("SELECT id FROM deliveries WHERE invoice_no = ?", (invoice_no,))
    result = cur.fetchone()

    if not result:
        print(f"❌ {invoice_no} 납품을 찾을 수 없습니다!")
        conn.close()
        return

    delivery_id = result[0]
    print(f"Delivery ID: {delivery_id}\n")

    # 2. delivery_items 조회
    print("=" * 80)
    print("delivery_items 테이블 데이터 (원본)")
    print("=" * 80)
    cur.execute("""
        SELECT id, item_code, serial_no, manufacture_code, product_name, qty
        FROM delivery_items
        WHERE delivery_id = ?
        ORDER BY id
    """, (delivery_id,))

    items = cur.fetchall()
    print(f"총 {len(items)}개 품목:\n")

    for item in items:
        item_id, item_code, serial_no, manufacture_code, product_name, qty = item
        print(f"[{item_id}] item_code: {item_code}")
        print(f"     serial_no: {serial_no}")
        print(f"     manufacture_code: {manufacture_code}")
        print(f"     product_name: {product_name}")
        print(f"     qty: {qty}")
        print()

    # 3. 시리얼 번호 그룹화 로직 시뮬레이션
    print("=" * 80)
    print("시리얼 번호 그룹화 로직 시뮬레이션")
    print("=" * 80)

    import re
    items_from_db = sorted(items, key=lambda x: (x[1] or "", x[2] or ""))
    all_serials_in_delivery = {item[2] for item in items_from_db if item[2]}

    print(f"모든 시리얼 번호: {all_serials_in_delivery}\n")

    processed_serials = set()
    display_items = []

    for item_data in items_from_db:
        item_id, item_code, serial_no, manufacture_code, product_name, qty = item_data

        print(f"처리 중: serial_no={serial_no}, item_code={item_code}")

        if serial_no and serial_no in processed_serials:
            print(f"  → 이미 처리됨 (건너뜀)\n")
            continue

        match = re.search(r'(\D+)(\d+)$', serial_no) if serial_no else None

        if match:
            prefix, start_num_str = match.groups()
            start_num, num_width = int(start_num_str), len(start_num_str)

            print(f"  → 시리얼 패턴 발견: prefix='{prefix}', start_num={start_num}")

            count = 1
            processed_serials.add(serial_no)

            # 연속된 시리얼 찾기
            while True:
                next_serial = f"{prefix}{start_num + count:0{num_width}d}"
                if next_serial in all_serials_in_delivery:
                    print(f"  → 연속 시리얼 발견: {next_serial}")
                    count += 1
                    processed_serials.add(next_serial)
                else:
                    break

            print(f"  → 그룹 크기: {count}개\n")

            new_item_data = list(item_data)
            new_item_data[5] = count  # qty 업데이트
            display_items.append(tuple(new_item_data))
        else:
            print(f"  → 시리얼 패턴 없음, 그대로 추가\n")
            display_items.append(item_data)

    print("=" * 80)
    print("최종 표시될 품목 (그룹화 후)")
    print("=" * 80)
    print(f"총 {len(display_items)}개 표시:\n")

    for idx, item_data in enumerate(display_items, 1):
        item_id, item_code, serial_no, manufacture_code, product_name, qty = item_data
        print(f"{idx}. item_code: {item_code}")
        print(f"   serial_no: {serial_no}")
        print(f"   product_name: {product_name}")
        print(f"   qty: {qty}")
        print()

    # 4. 문제 진단
    print("=" * 80)
    print("문제 진단")
    print("=" * 80)

    if len(items) != len(display_items):
        print(f"⚠️  원본 품목 {len(items)}개가 {len(display_items)}개로 그룹화되었습니다!")
        print(f"   시리얼 번호 그룹화 로직이 잘못 작동했을 수 있습니다.")
    else:
        print(f"✅ 원본 품목과 표시 품목 개수가 동일합니다.")

    # 5. 제품명이 다른데 그룹화되었는지 확인
    for i, item1 in enumerate(items):
        for j, item2 in enumerate(items):
            if i >= j:
                continue

            # 시리얼 번호가 연속인지 확인
            serial1, serial2 = item1[2], item2[2]
            if not serial1 or not serial2:
                continue

            match1 = re.search(r'(\D+)(\d+)$', serial1)
            match2 = re.search(r'(\D+)(\d+)$', serial2)

            if match1 and match2:
                prefix1, num1 = match1.groups()
                prefix2, num2 = match2.groups()

                if prefix1 == prefix2 and abs(int(num1) - int(num2)) == 1:
                    # 연속된 시리얼인데 제품명이 다름!
                    if item1[4] != item2[4]:  # product_name
                        print(f"\n❌ 문제 발견!")
                        print(f"   {serial1} ({item1[4][:30]}...)")
                        print(f"   {serial2} ({item2[4][:30]}...)")
                        print(f"   → 제품명이 다른데 시리얼 번호가 연속입니다!")
                        print(f"   → 이 두 품목이 잘못 그룹화되었을 가능성이 높습니다.")

    conn.close()
    print("\n" + "=" * 80)


if __name__ == "__main__":
    check_delivery_items()