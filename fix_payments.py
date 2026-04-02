from app.db import get_conn

def fix():
    conn = get_conn()
    cur = conn.cursor()
    # Find payments that match a PO's exact amount but have no purchase_id
    cur.execute("""
        UPDATE purchase_payments
        SET purchase_id = (
            SELECT pii.purchase_id
            FROM purchase_tax_invoice_items pii
            WHERE pii.tax_invoice_id = purchase_payments.tax_invoice_id
            GROUP BY pii.purchase_id
            HAVING SUM(pii.supply_amount + pii.tax_amount) = purchase_payments.amount
        )
        WHERE purchase_id IS NULL AND amount > 0
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    fix()
