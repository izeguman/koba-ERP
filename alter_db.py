from app.db import get_conn

def alter():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE purchase_payments ADD COLUMN purchase_id INTEGER REFERENCES purchases(id)")
        print("Column purchase_id added successfully.")
    except Exception as e:
        print("Error or already exists:", e)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    alter()
