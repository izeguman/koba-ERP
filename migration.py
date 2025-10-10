# 기존 deliveries 테이블의 데이터를 새 구조로 이전
conn = get_conn()
cur = conn.cursor()

# 기존 데이터 백업
cur.execute("SELECT * FROM deliveries")
old_deliveries = cur.fetchall()

# 새 구조로 데이터 이전
for old_delivery in old_deliveries:
    # deliveries 테이블에 헤더만 저장
    # delivery_items 테이블에 품목 정보 저장
    pass

conn.commit()
conn.close()