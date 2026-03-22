
import os

file_path = 'app/db.py'

correct_function_code = '''
def get_purchase_report_data(purchase_id: int) -> dict:
    """
    발주 상세 리포트용 데이터를 조회합니다.
    - 발주 기본 정보 (purchases)
    - 발주 품목 (purchase_items)
    - 연결된 주문 (orders)
    - 연결된 납품 (deliveries)
    - 집계: 총 발주량, 총 납품량, 잔량
    """
    conn = get_conn()
    cur = conn.cursor()

    # 1. 발주 기본 정보
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
        'actual_amount': p_row[4]
    }

    # 2. 발주 품목 정보
    sql_items = """
        SELECT item_code, product_name, qty, unit_price_cents, currency, rev
        FROM purchase_items
        WHERE purchase_id = ?
        ORDER BY item_code
    """
    cur.execute(sql_items, (purchase_id,))
    purchase_items = []
    total_ordered_qty = 0
    
    for row in cur.fetchall():
        qty = row[2]
        total_ordered_qty += qty
        purchase_items.append({
            'item_code': row[0],
            'product_name': row[1],
            'qty': qty,
            'unit_price': row[3] / 100.0 if row[3] else 0,
            'currency': row[4],
            'rev': row[5] or ''
        })

    # 3. 연결된 주문 정보 (purchase_order_links)
    sql_orders = """
        SELECT o.order_no, o.req_due, o.final_due, o.status, pol.order_id
        FROM purchase_order_links pol
        JOIN orders o ON pol.order_id = o.id
        WHERE pol.purchase_id = ?
        ORDER BY o.order_no
    """
    cur.execute(sql_orders, (purchase_id,))
    linked_orders = []
    for row in cur.fetchall():
        linked_orders.append({
            'order_no': row[0],
            'req_due': row[1],
            'final_due': row[2],
            'status': row[3],
            'order_id': row[4]
        })

    # 4. 연결된 납품 정보 (delivery_items 기준)
    # 해당 발주의 발주서 번호를 참조하고 있는 납품 내역을 찾습니다.
    # delivery_items 테이블에 purchase_id가 기록되어 있어야 합니다.
    sql_deliveries = """
        SELECT d.invoice_no, d.ship_datetime, di.item_code, di.product_name, di.qty, di.serial_no
        FROM delivery_items di
        JOIN deliveries d ON di.delivery_id = d.id
        WHERE di.purchase_id = ?
        ORDER BY d.ship_datetime DESC, d.invoice_no
    """
    cur.execute(sql_deliveries, (purchase_id,))
    delivery_history = []
    total_delivered_qty = 0
    
    for row in cur.fetchall():
        qty = row[4]
        total_delivered_qty += qty
        delivery_history.append({
            'invoice_no': row[0],
            'ship_date': row[1],
            'item_code': row[2],
            'product_name': row[3],
            'qty': qty,
            'serial_no': row[5] or ''
        })
    
    # 5. 종합 요약
    balance = total_ordered_qty - total_delivered_qty
    
    return {
        'purchase_info': purchase_info,
        'purchase_items': purchase_items,
        'linked_orders': linked_orders,
        'delivery_history': delivery_history,
        'summary': {
            'total_ordered_qty': total_ordered_qty,
            'total_delivered_qty': total_delivered_qty,
            'balance': balance
        }
    }
'''

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    start_index = -1
    for i, line in enumerate(lines):
        if line.strip() == "def get_purchase_report_data(purchase_id: int) -> dict:":
            start_index = i
            break
            
    if start_index != -1:
        new_lines = lines[:start_index]
        new_lines.append(correct_function_code)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print("Successfully repaired app/db.py")
    else:
        print("Could not find the function definition in app/db.py")

except Exception as e:
    print(f"Error repairing file: {e}")
