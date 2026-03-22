from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QFrame, QGridLayout, QWidget, QApplication
)
from PySide6.QtGui import QColor, QFont, QClipboard
from PySide6.QtCore import Qt
from ..db import get_purchase_report_data

class PurchaseReportDialog(QDialog):
    """
    발주 건에 대한 상세 리포트를 보여주는 다이얼로그 (PySide6 위젯 기반)
    주요 목적: 협력업체와 잔량(Balance) 교차 검증
    """
    def __init__(self, purchase_id, parent=None):
        super().__init__(parent)
        self.purchase_id = purchase_id
        self.setWindowTitle(f"발주 상세 리포트 - Purchase ID: {purchase_id}")
        self.resize(1000, 800)
        
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(20)
        self.layout.setContentsMargins(20, 20, 20, 20)
        
        # 데이터 로드
        self.data = get_purchase_report_data(self.purchase_id)
        
        if not self.data:
            self.layout.addWidget(QLabel("<h2>데이터를 찾을 수 없습니다.</h2>"))
            return

        # 1. 상단 기본 정보 (Header)
        self.init_header_ui()

        # 2. 수량 요약 (Summary Cards)
        self.init_summary_ui()

        # 3. 탭 위젯 (상세 데이터)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        self.init_purchase_items_tab()
        self.init_delivery_history_tab()
        self.init_linked_orders_tab()
        self.init_consumption_tab()

        # 4. 하단 버튼
        btn_layout = QHBoxLayout()
        self.btn_copy = QPushButton("클립보드에 복사(요약)")
        self.btn_copy.clicked.connect(self.copy_summary_to_clipboard)
        btn_layout.addWidget(self.btn_copy)
        
        btn_layout.addStretch()
        
        self.btn_close = QPushButton("닫기")
        self.btn_close.clicked.connect(self.accept)
        self.btn_close.setFixedWidth(100)
        btn_layout.addWidget(self.btn_close)
        
        self.layout.addLayout(btn_layout)

        # [New] 컬럼 폭 복원
        self.load_column_widths()

    def closeEvent(self, event):
        self.save_column_widths()
        super().closeEvent(event)

    def accept(self):
        self.save_column_widths()
        super().accept()

    def reject(self):
        self.save_column_widths()
        super().reject()

    def init_header_ui(self):
        info = self.data['purchase_info']
        
        # [New] 테이블 형태의 헤더 (QFrame + Grid + Borders)
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            .QFrame { 
                background-color: #f9f9f9; 
                border: 1px solid #ccc; 
            }
            QLabel {
                padding: 8px;
                border: 1px solid #ddd;
                font-size: 14px;
            }
            QLabel[class="header"] {
                background-color: #e0e0e0;
                font-weight: bold;
                color: #333;
            }
            QLabel[class="value"] {
                background-color: white;
                color: #000;
            }
        """)
        
        layout = QGridLayout(header_frame)
        layout.setSpacing(0) # 셀 간격 없앰 (border 연결)
        layout.setContentsMargins(0, 0, 0, 0)
        
        items = [
            ("발주번호", info['purchase_no']),
            ("발주일자", info['purchase_dt']),
            ("상태", info['status']),
            ("실발주액", f"{info['actual_amount']:,.0f} KRW")
        ]

        # 4개의 컬럼 (Label, Value, Label, Value...) -> 2줄로 배치? 아니면 1줄?
        # 사용자 요청: "표처럼 칸좀 만들어주라" -> 1줄이 깔끔할듯.
        
        for i, (label, value) in enumerate(items):
            lbl_title = QLabel(label)
            lbl_title.setProperty("class", "header")
            lbl_title.setAlignment(Qt.AlignCenter)
            
            lbl_value = QLabel(value)
            lbl_value.setProperty("class", "value")
            lbl_value.setAlignment(Qt.AlignCenter)
            
            layout.addWidget(lbl_title, 0, i * 2)
            layout.addWidget(lbl_value, 0, i * 2 + 1)
            
            # 비율 조정 (Header는 좁게, Value는 넓게)
            layout.setColumnStretch(i * 2, 1)
            layout.setColumnStretch(i * 2 + 1, 2)

        self.layout.addWidget(header_frame)

    def init_summary_ui(self):
        summary = self.data['summary']
        smart_data = self.data.get('smart_data', {})
        my_surplus = smart_data.get('my_surplus', {})
        my_allocs = smart_data.get('my_allocations', [])
        other_allocs = smart_data.get('other_allocations', [])
        
        # [New] 소모 수량
        my_consumption = smart_data.get('my_consumption', {}) # {code: qty}

        # [New] 품목별 과부족 현황 (Per-Item Status)
        purchase_items = self.data['purchase_items']
        
        container = QFrame()
        container.setStyleSheet("background-color: #f0f0f0; border-radius: 8px; padding: 5px;") # Padding 10->5
        v_layout = QVBoxLayout(container)
        v_layout.setSpacing(2) # Spacing 5->2
        v_layout.setContentsMargins(5, 5, 5, 5) # Layout margin added
        
        # 타이틀
        lbl_main = QLabel("📊 스마트 수량 검증 (Smart Allocation)")
        lbl_main.setStyleSheet("font-size: 13px; font-weight: bold; color: #333; margin-bottom: 2px;") # 14->13px, Margin 5->2
        v_layout.addWidget(lbl_main)

        # 품목별 카드 생성
        for item in purchase_items:
            item_code = item['item_code']
            p_qty = item['qty'] # 발주 수량
            
            # 1. 내 할당량 합계 (얼마나 기여했나)
            my_contrib_qty = sum(log['qty'] for log in my_allocs if log['item_code'] == item_code)
            
            # 2. 타 발주 기여량 합계 (얼마나 도움 받았나)
            other_contrib_qty = sum(log['qty'] for log in other_allocs if log['item_code'] == item_code)
            
            # 3. 소모량 (Consumption)
            consumed_qty = my_consumption.get(item_code, 0)
            
            # 4. 진정한 잔여량 (FIFO 시뮬레이션 결과)
            true_surplus = item.get('true_surplus', 0)

            # 5. 내가 타 발주(주문)를 지원한 수량 (제3의 사용처)
            # 총발주 - (내주문할당 + 소모) - 남은거 = 사라진거(누군가 씀)
            given_support_qty = p_qty - (my_contrib_qty + consumed_qty + true_surplus)
            if given_support_qty < 0: given_support_qty = 0 # Safety

            # 상태 판단
            if true_surplus > 0:
                status_html = f"<span style='color:green; font-weight:bold;'>여유 (+{true_surplus:,})</span>"
                status_desc = f"주문 할당 및 부품 소모 후 남은 수량: {true_surplus:,}개"
                bg_color = "#e8f5e9"
            else:
                if other_contrib_qty > 0:
                    status_html = f"<span style='color:blue; font-weight:bold;'>완료 (지원 받음)</span>"
                    status_desc = f"본 발주 재고 소진됨. 부족분 {other_contrib_qty:,}개는 <b>타 발주로부터 지원 받음</b>."
                    if consumed_qty > 0:
                         status_desc += f"<br>• (참고) 선행 부품 소진: {consumed_qty:,}개"
                    bg_color = "#e3f2fd"
                elif given_support_qty > 0:
                    status_html = f"<span style='color:blue; font-weight:bold;'>완료 (타 발주 지원함)</span>"
                    status_desc = f"본 발주 재고 소진됨. {given_support_qty:,}개는 <b>타 발주의 부족분을 지원하기 위해 사용</b>."
                    bg_color = "#e3f2fd"
                else:
                    req_qty = item.get('linked_req_qty', 0)
                    deficit = req_qty - my_contrib_qty
                    if deficit > 0:
                        status_html = f"<span style='color:red; font-weight:bold;'>부족 (-{deficit:,})</span>"
                        status_desc = f"재고 소진. 추가 발주 필요 ({deficit:,}개 부족)"
                        if consumed_qty > 0:
                            status_desc += f"<br>• 부품 소진 이슈: {consumed_qty:,}개 소모로 부족 발생"
                        bg_color = "#ffebee" 
                    else:
                        status_html = f"<span style='color:blue; font-weight:bold;'>딱 맞음 (Balanced)</span>"
                        status_desc = "발주 수량이 주문 및 소모량과 정확히 일치하여 소진됨."
                        if consumed_qty > 0:
                             status_desc += f"<br>• 부품 소진: {consumed_qty:,}개 포함"
                        bg_color = "#e3f2fd"

            # UI 카드 구성
            item_card = QFrame()
            item_card.setStyleSheet(f"""
                .QFrame {{ 
                    background-color: {bg_color}; 
                    border: 1px solid #bbb; 
                    border-radius: 6px; 
                }}
            """)
            card_layout = QVBoxLayout(item_card)
            card_layout.setContentsMargins(8, 4, 8, 4) 
            card_layout.setSpacing(0) 
            
            # 헤더
            top_layout = QHBoxLayout()
            lbl_name = QLabel(f"{item['product_name']} ({item_code})")
            lbl_name.setStyleSheet("font-weight: bold; font-size: 12px;") 
            lbl_status = QLabel(status_html)
            lbl_status.setTextFormat(Qt.RichText)
            
            top_layout.addWidget(lbl_name)
            top_layout.addStretch()
            top_layout.addWidget(lbl_status)
            card_layout.addLayout(top_layout)
            
            # 내용
            lbl_desc = QLabel(f"• {status_desc}")
            lbl_desc.setStyleSheet("color: #555;") 
            lbl_desc.setTextFormat(Qt.RichText)
            card_layout.addWidget(lbl_desc)
            
            # 상세 수치 (수식 명확화)
            used_qty = my_contrib_qty + consumed_qty
            
            # 텍스트 조합
            parts = [f"발주: {p_qty}"]
            
            usage_str = f"사용: {used_qty}(할당{my_contrib_qty}+소진{consumed_qty})"
            if given_support_qty > 0:
                usage_str += f"+지원함{given_support_qty}"
            parts.append(usage_str)
            
            if true_surplus > 0:
                parts.append(f"잔여: {true_surplus}")
            
            if other_contrib_qty > 0:
                parts.append(f"<b>지원받음: {other_contrib_qty}</b>")
                
            detail_text = " | ".join(parts)
            
            lbl_detail = QLabel(detail_text)
            lbl_detail.setStyleSheet("color: #777; font-size: 11px;")
            card_layout.addWidget(lbl_detail)
            
            v_layout.addWidget(item_card)
        
        self.layout.addWidget(container)

    def init_purchase_items_tab(self):
        items = self.data['purchase_items']
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "품목코드", "품명", "수량(Ord)", "기납품(Rcv)", "잔량(Bal)", "단가", "통화"
        ])
        table.setRowCount(len(items))
        
        for r, item in enumerate(items):
            bal = item['balance']
            bal_brush = QColor("red") if bal > 0 else QColor("green")
            
            self.set_item(table, r, 0, item['item_code'])
            self.set_item(table, r, 1, item['product_name'], align=Qt.AlignLeft | Qt.AlignVCenter) # [Fix] 왼쪽 정렬
            self.set_item_num(table, r, 2, item['qty'])
            self.set_item_num(table, r, 3, item['delivered_qty'], color=QColor("blue"))
            self.set_item_num(table, r, 4, bal, color=bal_brush, bold=True)
            self.set_item_num(table, r, 5, item['unit_price'])
            self.set_item(table, r, 6, item['currency'])

        # [New] 컬럼 리사이즈 (Interactive) + 품명 컬럼 초기 너비 설정 (Stretch 제거)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive) 
        # header.setSectionResizeMode(1, QHeaderView.Stretch) # Stretch 제거
        table.setColumnWidth(1, 300) # 초기 너비 300
        
        self.tabs.addTab(table, "1. 발주 품목 상세")
        self.table_items = table # 저장용 참조
        
        self.tabs.addTab(table, "1. 발주 품목 상세")

    def init_delivery_history_tab(self):
        deliveries = self.data['delivery_history']
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            "발송일자", "송장번호", "품목", "입고수량", "S/N"
        ])
        table.setRowCount(len(deliveries))
        
        for r, d in enumerate(deliveries):
            self.set_item(table, r, 0, d['ship_date'])
            self.set_item(table, r, 1, d['invoice_no'])
            self.set_item(table, r, 2, f"({d['item_code']}) {d['product_name']}", align=Qt.AlignLeft | Qt.AlignVCenter) # [Fix] 왼쪽 정렬
            self.set_item_num(table, r, 3, d['qty'])
            self.set_item(table, r, 4, d['serial_no'])

        # [New] 컬럼 리사이즈
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # header.setSectionResizeMode(2, QHeaderView.Stretch) # Stretch 제거
        table.setColumnWidth(2, 300)
        
        self.tabs.addTab(table, "2. 연결된 납품 이력")
        self.table_delivery = table
        
        self.tabs.addTab(table, "2. 연결된 납품 이력")

    def init_linked_orders_tab(self):
        orders = self.data['linked_orders']
        
        # [New] Smart Data에서 할당량 맵핑
        smart_data = self.data.get('smart_data', {})
        my_allocs = smart_data.get('my_allocations', [])
        alloc_map = {}
        for a in my_allocs:
            oid = a['oid']
            alloc_map[oid] = alloc_map.get(oid, 0) + a['qty']

        table = QTableWidget()
        # [New] 주문수량, 기납품, 잔량, [New] 본발주할당
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            "주문번호", "주문내용", "요청납기", "최종납기", "주문수량", "납품수량", "잔량", "본발주할당"
        ])
        table.setRowCount(len(orders))
        
        for r, o in enumerate(orders):
            self.set_item(table, r, 0, o['order_no'])
            self.set_item(table, r, 1, o['product_summary'], align=Qt.AlignLeft | Qt.AlignVCenter)
            self.set_item(table, r, 2, o['req_due'])
            self.set_item(table, r, 3, o['final_due'])
            
            total = o.get('total_qty', 0)
            shipped = o.get('shipped_qty', 0)
            rem = o.get('remaining_qty', 0)
            
            # [New] 내 할당량
            my_alloc_qty = alloc_map.get(o['order_id'], 0)
            
            self.set_item_num(table, r, 4, total)
            self.set_item_num(table, r, 5, shipped, color=QColor("blue"))
            self.set_item_num(table, r, 6, rem, color=QColor("red") if rem > 0 else QColor("green"))
            self.set_item_num(table, r, 7, my_alloc_qty, bold=True, color=QColor("purple"))

        # [New] 컬럼 리사이즈
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # header.setSectionResizeMode(1, QHeaderView.Stretch) # Stretch 제거
        table.setColumnWidth(1, 400) # 내용이 기니까 더 넓게

        self.tabs.addTab(table, "3. 연결된 주문 정보")
        self.table_orders = table
        
        self.tabs.addTab(table, "3. 연결된 주문 정보")

    def init_consumption_tab(self):
        # [New] 부품 소진 내역 탭
        smart_data = self.data.get('smart_data', {})
        details = smart_data.get('consumption_details', [])
        
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            "부품코드", "상위 제품 (Parent)", "상위 S/N", "소진 수량", "관련 주문"
        ])
        table.setRowCount(len(details))
        
        if not details:
            # 데이터 없음
            table.setRowCount(1)
            self.set_item(table, 0, 0, "No Data")
            self.set_item(table, 0, 1, "부품으로 소진된 내역이 없습니다.")
            table.setSpan(0, 1, 1, 4)
        else:
            for r, d in enumerate(details):
                self.set_item(table, r, 0, d['item_code'])
                self.set_item(table, r, 1, d['parent_name'], align=Qt.AlignLeft | Qt.AlignVCenter)
                self.set_item(table, r, 2, d['parent_serial'])
                self.set_item_num(table, r, 3, d['qty'], color=QColor("red"))
                self.set_item(table, r, 4, d['order_no'] or "-")
        
        # [New] 컬럼 리사이즈
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # header.setSectionResizeMode(1, QHeaderView.Stretch)
        table.setColumnWidth(1, 250)
        
        self.tabs.addTab(table, "4. 부품 소진 내역 (Component Usage)")
        self.table_consumption = table
        
        self.tabs.addTab(table, "4. 부품 소진 내역 (Component Usage)")

    # --- Helper Methods ---
    def set_item(self, table, row, col, text, align=Qt.AlignCenter, color=None, bold=False):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(align)
        if color:
            item.setForeground(color)
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        table.setItem(row, col, item)

    def set_item_num(self, table, row, col, value, align=Qt.AlignCenter, color=None, bold=False):
        text = f"{value:,.0f}" if isinstance(value, (int, float)) else str(value)
        self.set_item(table, row, col, text, align, color, bold)

    def copy_summary_to_clipboard(self):
        summary = self.data['summary']
        text = f"""[발주 상세 리포트 요약]
발주번호: {self.data['purchase_info']['purchase_no']}
--------------------------
총 발주 수량: {summary['total_ordered_qty']:,}
총 납품 수량: {summary['total_delivered_qty']:,}
미납 잔량: {summary['balance']:,}
납품 예정 수량: {summary.get('total_linked_remaining_qty', 0):,}
--------------------------
"""
        QApplication.clipboard().setText(text)

    # [New] Settings save/load
    def save_column_widths(self):
        from PySide6.QtCore import QSettings
        # 메인 윈도우와 동일한 설정 키 사용 (레지스트리/설정파일 공유)
        settings = QSettings("KOBATECH", "ProductionManagement")
        
        def save_state(table, name):
             if table:
                 settings.setValue(f"PurchaseReportDialog/{name}_headerState", table.horizontalHeader().saveState())
        
        save_state(getattr(self, 'table_items', None), "table_items")
        save_state(getattr(self, 'table_delivery', None), "table_delivery")
        save_state(getattr(self, 'table_orders', None), "table_orders")
        save_state(getattr(self, 'table_consumption', None), "table_consumption")
        settings.sync() 

    def load_column_widths(self):
        from PySide6.QtCore import QSettings
        settings = QSettings("KOBATECH", "ProductionManagement")
        
        def load_state(table, name):
            if table:
                val = settings.value(f"PurchaseReportDialog/{name}_headerState")
                if val:
                    table.horizontalHeader().restoreState(val)
        
        load_state(getattr(self, 'table_items', None), "table_items")
        load_state(getattr(self, 'table_delivery', None), "table_delivery")
        load_state(getattr(self, 'table_orders', None), "table_orders")
        load_state(getattr(self, 'table_consumption', None), "table_consumption")

