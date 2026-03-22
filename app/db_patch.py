
def get_all_product_master():
    """모든 제품 마스터 데이터 조회"""
    sql = "SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, created_at, updated_at, is_active, item_type FROM product_master ORDER BY item_code ASC"
    return query_all(sql)


def add_or_update_product_master(item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, item_type='PRODUCT', is_active=1):
    """제품 마스터 추가 또는 업데이트 (중복 시)"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        
        # Check existence
        cur.execute("SELECT id, is_active FROM product_master WHERE item_code = ? AND (rev IS ? OR rev = ?)", (item_code, rev, rev))
        existing = cur.fetchone()
        
        if existing:
            p_id, current_active = existing
            # If it exists but we are trying to add it, maybe we just update it?
            # Usage in widget says: if result == 'DUPLICATE_INACTIVE': ...
            
            if current_active == 0 and is_active == 1:
                # User might want to reactivate
                return 'DUPLICATE_INACTIVE'
            
            # Update existing
            cur.execute("""
                UPDATE product_master 
                SET product_name=?, unit_price_jpy=?, purchase_price_krw=?, description=?, item_type=?, is_active=?, updated_at=datetime('now','localtime')
                WHERE id=?
            """, (product_name, unit_price_jpy, purchase_price_krw, description, item_type, is_active, p_id))
            conn.commit()
            return 'UPDATED'
        else:
            cur.execute("""
                INSERT INTO product_master (item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, item_type, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, item_type, is_active))
            conn.commit()
            return 'INSERTED'
            
    except Exception as e:
        print(f"add_or_update_product_master error: {e}")
        return 'ERROR'
    finally:
        conn.close()


def update_product_master(product_id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, item_type):
    """제품 마스터 정보 수정"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE product_master 
            SET item_code=?, rev=?, product_name=?, unit_price_jpy=?, purchase_price_krw=?, description=?, item_type=?, updated_at=datetime('now','localtime')
            WHERE id=?
        """, (item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, item_type, product_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"update_product_master error: {e}")
        return False
    finally:
        conn.close()


def delete_product_master(product_id):
    """제품 마스터 삭제"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM product_master WHERE id=?", (product_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"delete_product_master error: {e}")
        return False
    finally:
        conn.close()


def search_product_master(keyword):
    """제품 검색 (코드 또는 이름)"""
    sql = """
        SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, created_at, updated_at, is_active, item_type 
        FROM product_master 
        WHERE item_code LIKE ? OR product_name LIKE ?
        ORDER BY item_code ASC
    """
    param = f"%{keyword}%"
    return query_all(sql, (param, param))
