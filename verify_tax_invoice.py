# verify_tax_invoice.py
import sys
import os
import sqlite3

# 현재 디렉토리를 sys.path에 추가
sys.path.append(os.getcwd())

from app.db import init_db, get_conn, add_tax_invoice, add_payment, get_tax_invoice_payment_status

def verify():
    # 1. DB 초기화 (스키마 마이그레이션 적용)
    print("Initialize DB...")
    init_db()
    
    # 2. 테스트용 세금계산서 생성
    print("Creating Test Tax Invoice...")
    conn = get_conn()
    cur = conn.cursor()
    # 기존 데이터에 영향 없도록 임의의 과거 날짜 사용
    cur.execute("""
        INSERT INTO tax_invoices (issue_date, supplier_name, total_amount, note, approval_number)
        VALUES ('2020-01-01', 'TEST_SUPPLIER', 10000, 'TEST_INVOICE', 'TEST-1234')
    """)
    invoice_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    print(f"Tax Invoice ID: {invoice_id}, Amount: 10,000")
    
    # 3. 초기 상태 확인
    status = get_tax_invoice_payment_status(invoice_id)
    print(f"Initial Status: {status['status']} (Expected: 미결)")
    
    # 4. 부분 결제 추가 (5,000원)
    print("Adding Partial Payment (5,000)...")
    # 임의의 purchase_id 1 사용 (없으면 에러날 수 있으므로 체크)
    # 테스트를 위해 임시 Purchase 생성
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO purchases (id, purchase_no, purchase_dt, status) VALUES (99999, 'TEST-PO', '2020-01-01', '완료')")
    conn.commit()
    conn.close()
    
    add_payment(99999, '2020-01-01', 5000, '기타', 'Partial Payment', tax_invoice_id=invoice_id)
    
    status = get_tax_invoice_payment_status(invoice_id)
    print(f"Partial Status: {status['status']} (Expected: 부분)")
    
    # 5. 잔금 결제 추가 (5,000원)
    print("Adding Remaining Payment (5,000)...")
    add_payment(99999, '2020-01-01', 5000, '기타', 'Remaining Payment', tax_invoice_id=invoice_id)
    
    status = get_tax_invoice_payment_status(invoice_id)
    print(f"Final Status: {status['status']} (Expected: 완료)")
    
    # 6. 정리 (테스트 데이터 삭제)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM payments WHERE purchase_id = 99999")
    cur.execute("DELETE FROM tax_invoices WHERE id = ?", (invoice_id,))
    cur.execute("DELETE FROM purchases WHERE id = 99999")
    conn.commit()
    conn.close()
    print("Cleaned up test data.")

if __name__ == "__main__":
    import traceback
    with open("verify_log.txt", "w", encoding="utf-8") as f:
        try:
            # Redirect stdout/stderr
            sys.stdout = f
            sys.stderr = f
            verify()
            print("\nVerification Successful!")
        except Exception as e:
            print(f"\nVerification Failed: {e}")
            traceback.print_exc()
