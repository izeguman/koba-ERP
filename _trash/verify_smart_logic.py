
import sqlite3
import os
from collections import defaultdict

def test_smart_logic():
    test_db_path = "test_smart_logic.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        
    conn = sqlite3.connect(test_db_path)
    
    # Define schema locally to avoid import issues
    schema = """
    CREATE TABLE purchases (id INTEGER PRIMARY KEY, purchase_no TEXT, purchase_dt TEXT, status TEXT, actual_amount INT);
    CREATE TABLE purchase_items (id INTEGER PRIMARY KEY, purchase_id INT, item_code TEXT, product_name TEXT, qty INT, unit_price_cents INT, currency TEXT, rev TEXT);
    CREATE TABLE orders (id INTEGER PRIMARY KEY, order_no TEXT, order_dt TEXT);
    CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INT, item_code TEXT, product_name TEXT, qty INT);
    CREATE TABLE purchase_order_links (id INTEGER PRIMARY KEY, purchase_id INT, order_id INT);
    """
    conn.executescript(schema)
    
    # Helper to insert
    def mk_purch(pid, pno, dt, item, qty):
        conn.execute("INSERT INTO purchases (id, purchase_no, purchase_dt) VALUES (?, ?, ?)", (pid, pno, dt))
        conn.execute("INSERT INTO purchase_items (purchase_id, item_code, product_name, qty) VALUES (?, ?, ?, ?)", (pid, item, "TestItem", qty))

    def mk_order(oid, ono, dt, item, qty):
        conn.execute("INSERT INTO orders (id, order_no, order_dt) VALUES (?, ?, ?)", (oid, ono, dt))
        conn.execute("INSERT INTO order_items (order_id, item_code, product_name, qty) VALUES (?, ?, ?, ?)", (oid, item, "TestItem", qty))
        
    def link(pid, oid):
        conn.execute("INSERT INTO purchase_order_links (purchase_id, order_id) VALUES (?, ?)", (pid, oid))

    # --- SCENARIO SETUP ---
    ITEM = "ITEM-001"
    
    # 1. Order A (10개) - Day 1
    mk_order(1, "Order-A", "2025-01-01", ITEM, 10)
    
    # 2. Purchase a (15개) - Day 2
    mk_purch(100, "Purch-a", "2025-01-02", ITEM, 15)
    link(100, 1) # Link a -> A
    
    # 3. Order B (7개) - Day 3
    mk_order(2, "Order-B", "2025-01-03", ITEM, 7)
    link(100, 2) # Link a -> B
    
    # 4. Purchase c (10개) - Day 4
    mk_purch(101, "Purch-c", "2025-01-04", ITEM, 10)
    link(101, 2) # Link c -> B
    
    conn.commit()
    
    # --- RUN LOGIC ---
    cur = conn.cursor()
    
    # 1. Load Purchases
    cur.execute("SELECT p.id, p.purchase_no, p.purchase_dt, pi.item_code, pi.qty FROM purchases p JOIN purchase_items pi ON p.id=pi.purchase_id ORDER BY p.purchase_dt, p.id")
    purchases = {}
    for pid, pno, pdt, code, qty in cur.fetchall():
        if pid not in purchases: purchases[pid] = {'id': pid, 'no': pno, 'dt': pdt, 'stock': {}}
        purchases[pid]['stock'][code] = qty
        
    # 2. Load Orders
    cur.execute("SELECT o.id, o.order_no, o.order_dt FROM orders o ORDER BY o.order_dt, o.id")
    orders_list = cur.fetchall()
    
    cur.execute("SELECT order_id, item_code, qty FROM order_items")
    order_items_map = {}
    for oid, code, qty in cur.fetchall():
        if oid not in order_items_map: order_items_map[oid] = []
        order_items_map[oid].append({'code': code, 'qty': qty})
        
    # 3. Load Links
    cur.execute("SELECT order_id, purchase_id FROM purchase_order_links")
    links_map = {}
    for oid, pid in cur.fetchall():
        if oid not in links_map: links_map[oid] = set()
        links_map[oid].add(pid)
        
    # 4. FIFO SIMULATION
    sorted_p_list = sorted(purchases.values(), key=lambda x: (x['dt'], x['id']))
    allocation_log = []
    
    for oid, ono, odt in orders_list:
        items = order_items_map.get(oid, [])
        linked_pids = links_map.get(oid, set())
        
        candidates = [p for p in sorted_p_list if p['id'] in linked_pids]
        
        for item in items:
            needed = item['qty']
            code = item['code']
            
            for p in candidates:
                if needed <= 0: break
                stock = p['stock'].get(code, 0)
                if stock > 0:
                    take = min(stock, needed)
                    p['stock'][code] -= take
                    needed -= take
                    allocation_log.append({'oid': oid, 'pid': p['id'], 'qty': take, 'code': code})
                    
    # --- CHECK RESULTS ---
    print("=== Simulation Results ===")
    
    p_a = purchases[100]
    rem_a = p_a['stock'][ITEM]
    contrib_a = sum(x['qty'] for x in allocation_log if x['pid'] == 100)
    print(f"Purch-a (Orig 15): Rem={rem_a}, Contrib={contrib_a}")
    
    p_c = purchases[101]
    rem_c = p_c['stock'][ITEM]
    contrib_c = sum(x['qty'] for x in allocation_log if x['pid'] == 101)
    print(f"Purch-c (Orig 10): Rem={rem_c}, Contrib={contrib_c}")
    
    assert rem_a == 0
    assert contrib_a == 15
    assert rem_c == 8
    assert contrib_c == 2
    
    print("\nSUCCESS: Matches User Scenario!")
    
    conn.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

if __name__ == "__main__":
    test_smart_logic()
