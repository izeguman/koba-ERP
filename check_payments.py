import sys
import os
import sqlite3

sys.path.append(os.getcwd())

from app.db import get_conn

def check():
    conn = get_conn()
    cur = conn.cursor()
    
    # 1. Find Invoice ID
    print("Finding Invoice ID...")
    cur.execute("SELECT id, total_amount FROM tax_invoices WHERE total_amount = 139968323")
    row = cur.fetchone()
    if not row:
        print("Invoice not found!")
        return
    
    invoice_id = row[0]
    print(f"Invoice ID: {invoice_id}")
    
    # 2. Find Linked Purchases via TaxInvoiceItems
    print("Finding Linked Purchase IDs...")
    cur.execute("SELECT DISTINCT purchase_id FROM tax_invoice_items WHERE tax_invoice_id = ?", (invoice_id,))
    purchase_ids = [r[0] for r in cur.fetchall() if r[0] is not None]
    print(f"Linked Purchase IDs: {purchase_ids}")
    
    if not purchase_ids:
        print("No linked purchases found.")
        return

    # 3. Check Payments for these Purchases
    print("Checking Payments...")
    p_ids_str = ','.join(map(str, purchase_ids))
    sql = f"SELECT id, amount, tax_invoice_id, purchase_id FROM payments WHERE purchase_id IN ({p_ids_str})"
    cur.execute(sql)
    payments = cur.fetchall()
    
    print("\n[Payments Found]")
    for p in payments:
        pid, amt, tax_inv_id, purch_id = p
        status = "LINKED" if tax_inv_id == invoice_id else "UNLINKED"
        print(f"Payment ID: {pid}, Amount: {amt}, Purchase ID: {purch_id}, TaxInvoiceID: {tax_inv_id} -> {status}")

    conn.close()

if __name__ == "__main__":
    import traceback
    try:
        check()
    except Exception as e:
        print(f"Error during check: {e}")
        traceback.print_exc()
    except SyntaxError as e:
        print(f"Syntax Error: {e}")
        traceback.print_exc()
    except ImportError as e:
        print(f"Import Error: {e}")
        traceback.print_exc()
