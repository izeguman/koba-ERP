import os
import sys
from datetime import datetime

# 현재 디렉토리를 sys.path에 추가하여 app 패키지를 임포트할 수 있도록 함
sys.path.append(os.getcwd())

try:
    from app.db import query_all
    
    print("--- 2026 Revenue Research ---")

    # 1. 실제 매출 (deliveries 기준)
    sql_actual = """
        SELECT SUM((di.qty * oi.unit_price_cents / 100.0) * (COALESCE(er.rate, 900.0) / 100.0))
        FROM deliveries d
        JOIN delivery_items di ON d.id = di.delivery_id
        JOIN order_items oi ON di.order_id = oi.order_id AND di.item_code = oi.item_code
        LEFT JOIN exchange_rates er 
               ON er.year = CAST(strftime('%Y', d.ship_datetime) AS INTEGER)
              AND er.month = CAST(strftime('%m', d.ship_datetime) AS INTEGER)
        WHERE strftime('%Y', d.ship_datetime) = '2026'
          AND d.invoice_done = 1
    """
    actual_res = query_all(sql_actual)
    actual_val = actual_res[0][0] if actual_res and actual_res[0][0] else 0
    print(f"Actual 2026 Revenue: {actual_val:,.0f}")

    # 2. 보정된 예상 매출 (Shipments + 필터링된 Order Items)
    sql_expected_fixed = """
        WITH item_prices AS (
            SELECT 
                oi.id as order_item_id,
                oi.qty as total_qty,
                (oi.unit_price_cents / 100.0) as price_cents,
                o.final_due as order_due
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
        ),
        shipment_expected AS (
            -- 2-1. 납품 일정이 있는 항목들의 2026년분 합계
            SELECT 
                SUM((s.ship_qty * (oi.unit_price_cents / 100.0)) * (COALESCE(er.rate, 900.0) / 100.0)) as val
            FROM order_shipments s
            JOIN order_items oi ON s.order_item_id = oi.id
            LEFT JOIN exchange_rates er 
                   ON er.year = CAST(strftime('%Y', s.due_date) AS INTEGER)
                  AND er.month = CAST(strftime('%m', s.due_date) AS INTEGER)
            WHERE strftime('%Y', s.due_date) = '2026'
        ),
        order_only_expected AS (
            -- 2-2. 납품 일정이 아예 없는 항목들 중 주문 기한이 2026년인 항목 합계
            SELECT 
                SUM((oi.qty * (oi.unit_price_cents / 100.0)) * (COALESCE(er.rate, 900.0) / 100.0)) as val
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            LEFT JOIN exchange_rates er 
                   ON er.year = CAST(strftime('%Y', o.final_due) AS INTEGER)
                  AND er.month = CAST(strftime('%m', o.final_due) AS INTEGER)
            WHERE strftime('%Y', o.final_due) = '2026'
              AND NOT EXISTS (SELECT 1 FROM order_shipments s WHERE s.order_item_id = oi.id)
        )
        SELECT (COALESCE((SELECT val FROM shipment_expected), 0) + COALESCE((SELECT val FROM order_only_expected), 0))
    """
    expected_res = query_all(sql_expected_fixed)
    expected_val = expected_res[0][0] if expected_res and expected_res[0][0] else 0
    print(f"Fixed Expected 2026 Revenue (Shipments + Fallback): {expected_val:,.0f}")

    # 3. 누락된 링크 조사
    # 모든 주문 아이템 수량 vs shipment 일점 수량 합계 확인
    sql_missing_shipments = """
        SELECT oi.order_id, oi.item_code, oi.qty as order_qty, 
               (SELECT SUM(s.ship_qty) FROM order_shipments s WHERE s.order_item_id = oi.id) as shipment_qty_sum
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE strftime('%Y', o.final_due) = '2026'
          AND (shipment_qty_sum IS NULL OR shipment_qty_sum < oi.qty)
    """
    missing_ship = query_all(sql_missing_shipments)
    print(f"Order Items with missing or incomplete shipments in 2026: {len(missing_ship)}")
    if missing_ship:
        print("Example (order_id, item, order_qty, ship_sum):", missing_ship[:5])

    # 4. 일자 불일치 조사 (2025년 예정이었으나 2026년 출하된 건)
    sql_drift = """
        SELECT SUM((di.qty * oi.unit_price_cents / 100.0) * (COALESCE(er.rate, 900.0) / 100.0))
        FROM deliveries d
        JOIN delivery_items di ON d.id = di.delivery_id
        JOIN order_items oi ON di.order_id = oi.order_id AND di.item_code = oi.item_code
        JOIN orders o ON di.order_id = o.id
        LEFT JOIN exchange_rates er 
               ON er.year = CAST(strftime('%Y', d.ship_datetime) AS INTEGER)
              AND er.month = CAST(strftime('%m', d.ship_datetime) AS INTEGER)
        WHERE strftime('%Y', d.ship_datetime) = '2026'
          AND strftime('%Y', o.final_due) < '2026'
          AND d.invoice_done = 1
    """
    drift_res = query_all(sql_drift)
    drift_val = drift_res[0][0] if drift_res and drift_res[0][0] else 0
    print(f"Revenue from orders scheduled before 2026 but delivered in 2026: {drift_val:,.0f}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
