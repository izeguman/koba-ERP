# check_db.py
from app.db import get_conn

conn = get_conn()
cur = conn.cursor()

# TO2503-002 발주의 납품 내역 확인
sql = """
SELECT d.id, d.invoice_no, d.qty, d.ship_datetime, p.purchase_no
FROM deliveries d
LEFT JOIN purchases p ON d.purchase_id = p.id
WHERE p.purchase_no = 'TO2503-002'
"""

cur.execute(sql)
rows = cur.fetchall()

print("TO2503-002 발주의 납품 내역:")
print("-" * 80)
for row in rows:
    delivery_id, invoice_no, qty, ship_datetime, purchase_no = row
    print(f"납품ID: {delivery_id}, 인보이스: {invoice_no}, 수량: {qty}, 발송일시: {ship_datetime}")

print(f"\n총 납품 수량: {sum(row[2] for row in rows)}개")
print(f"납품 건수: {len(rows)}건")

conn.close()