import sqlite3
try:
    conn = sqlite3.connect('production_system.db')
    cursor = conn.cursor()
    cursor.execute('SELECT item_code, unit_price_cents FROM purchase_items LIMIT 5')
    print('Purchase Items (unit_price_cents):', cursor.fetchall())
    cursor.execute('SELECT item_code, unit_price_jpy FROM product_master LIMIT 5')
    print('Product Master (unit_price_jpy):', cursor.fetchall())
    conn.close()
except Exception as e:
    print(e)
