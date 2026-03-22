# app/ui/autocomplete_widgets.py

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import QCompleter, QHeaderView, QMessageBox, QLineEdit
from PySide6.QtCore import Qt, QStringListModel, QTimer
from PySide6.QtGui import QBrush, QColor

from ..db import (
    get_conn, get_order_with_items, create_order_with_items,
    update_order_with_items, add_or_update_product_master,
    get_available_purchases, query_all, calculate_fifo_allocation_margins
)
from .money_lineedit import MoneyLineEdit
from .utils import parse_due_text, apply_table_resize_policy


class AutoCompleteLineEdit(QtWidgets.QLineEdit):
    """자동완성 기능이 있는 LineEdit - 클릭 시 전체 목록 표시"""
    product_selected = QtCore.Signal(dict)

    def __init__(self, parent=None, type_filter=None):
        super().__init__(parent)
        self.all_products = []
        self.product_data = {}
        # ✅ 기본값 개선: 완제품, 모듈, 부품, 레거시 타입 포함
        if type_filter is None:
             self.type_filter = ['PRODUCT', 'MODULE', 'SELLABLE', 'PART', 'SUB_COMPONENT']
        else:
             self.type_filter = type_filter
             
        self.setup_completer()
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.update_completions)
        self.textChanged.connect(self.on_text_changed)
        
        # 초기 데이터 로드
        self.load_data()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if hasattr(self, 'completer') and self.completer:
             if not self.text():
                self.completer.setCompletionPrefix("")
                self.completer.complete()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if hasattr(self, 'completer') and self.completer:
            if not self.text():
                self.completer.setCompletionPrefix("")
                self.completer.complete()

    def set_type_filter(self, type_filter):
        """필터 설정 및 데이터 재로드"""
        self.type_filter = type_filter
        self.load_data()  # 갱신

    def setup_completer(self):
        """자동완성 초기화"""
        self.completer = QtWidgets.QCompleter(self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        
        # ✅ 시그널 연결 (이게 누락되어 있었음)
        self.completer.activated.connect(self.handle_completion)
        
        # ✅ 중요: QLineEdit의 기본 completer 동작(자동 채우기)을 끄고 커스텀 핸들링 사용
        self.setCompleter(None) 
        self.completer.setWidget(self)

    def _get_extended_filter(self):
        """✅ 필터 확장: 한글 및 다양한 표기법 포함"""
        if not self.type_filter:
            return []
            
        extended = list(self.type_filter)
        # 대소문자 무시하고 비교하기 위해 변환
        upper_filter = [str(x).upper() for x in self.type_filter]
        
        if 'PART' in upper_filter:
            extended.extend(['부품', '자재', 'Part'])
        if 'PRODUCT' in upper_filter:
            extended.extend(['제품', '완제품', 'Product'])
        if 'MODULE' in upper_filter:
            extended.extend(['모듈', 'Module'])
        if 'SELLABLE' in upper_filter:
            extended.extend(['판매가능', 'Sellable'])
            
        return list(set(extended))

    def load_data(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            
            sql = "SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description FROM product_master WHERE is_active = 1"
            params = []
            
            # ✅ 타입 필터링 적용 (확장된 필터 사용)
            extended_filter = self._get_extended_filter()
            if extended_filter:
                placeholders = ', '.join('?' for _ in extended_filter)
                sql += f" AND UPPER(item_type) IN ({placeholders})"
                # 필터 값들도 대문자로 변환하여 매칭 (한글은 그대로 유지됨)
                params.extend([str(t).upper() for t in extended_filter])
                
            sql += " ORDER BY item_code"
            
            cur.execute(sql, tuple(params))
            self.all_products = cur.fetchall()
            conn.close()

            if self.all_products:
                completions = []
                self.product_data = {}
                for product in self.all_products:
                    product_id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description = product
                    display_text = f"{item_code} - {product_name}"
                    if rev: display_text = f"{item_code} (Rev {rev}) - {product_name}"
                    completions.append(display_text)
                    self.product_data[display_text] = {
                        'item_code': item_code, 'rev': rev, 'product_name': product_name,
                        'unit_price_jpy': unit_price_jpy,
                        'purchase_price_krw': purchase_price_krw
                    }
                model = QStringListModel(completions)
                self.completer.setModel(model)
                current_text = self.text().strip()
                if current_text:
                    self.completer.setCompletionPrefix(current_text)
            else:
                 self.completer.setModel(QStringListModel([]))

        except Exception as e:
            print(f"제품 목록 로드 오류: {e}")

    def on_text_changed(self, text):
        """텍스트 변경 시 타이머 시작"""
        if len(text) >= 2:
            self.search_timer.start(300)

    def update_completions(self):
        text = self.text().strip()
        if len(text) < 2: return
        try:
            conn = get_conn()
            cur = conn.cursor()
            
            sql = "SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw FROM product_master WHERE is_active = 1 AND (item_code LIKE ? OR product_name LIKE ?)"
            params = [f"%{text}%", f"%{text}%"]
            
            # ✅ 타입 필터링 적용 (확장된 필터 사용)
            extended_filter = self._get_extended_filter()
            if extended_filter:
                placeholders = ', '.join('?' for _ in extended_filter)
                sql += f" AND UPPER(item_type) IN ({placeholders})"
                params.extend([str(t).upper() for t in extended_filter])
                
            sql += " ORDER BY item_code, rev LIMIT 10"
            
            cur.execute(sql, tuple(params))
            products = cur.fetchall()
            conn.close()
            completions = []
            self.product_data = {}
            for product in products:
                product_id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw = product
                display_text = f"{item_code} - {product_name}"
                if rev: display_text = f"{item_code} (Rev {rev}) - {product_name}"
                completions.append(display_text)
                self.product_data[display_text] = {'item_code': item_code, 'rev': rev, 'product_name': product_name,
                                                   'unit_price_jpy': unit_price_jpy,
                                                   'purchase_price_krw': purchase_price_krw}
            model = QStringListModel(completions)
            self.completer.setModel(model)

            if completions:
                self.completer.setCompletionPrefix(text)
                self.completer.complete()

        except Exception as e:
            print(f"자동완성 검색 오류: {e}")

    def handle_completion(self, text):
        if hasattr(self, 'product_data') and text in self.product_data:
            product_info = self.product_data[text]
            self.completer.popup().hide()
            self.blockSignals(True)
            self.setText(product_info['item_code'])
            self.blockSignals(False)
            self.setCursorPosition(len(self.text()))
            self.product_selected.emit(product_info)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            if self.completer.popup().isVisible():
                current_index = self.completer.popup().currentIndex()
                if current_index.isValid():
                    text = self.completer.completionModel().data(current_index)
                    self.handle_completion(text)
                    event.ignore()
                    return
        super().keyPressEvent(event)


class ProductOrderDialog(QtWidgets.QDialog):
    """주문 추가/수정 다이얼로그"""

    def __init__(self, parent=None, is_edit=False, order_id=None, settings=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.order_id = order_id
        # items 리스트가 딕셔너리를 담고 있으므로 초기화 방식 유지
        self.items = []
        self.settings = settings
        self.setup_ui()

        # 초기화 시 로드
        self.load_available_purchases()

        if is_edit and order_id:
            self.load_order_data()

    def setup_ui(self):
        title = "주문 수정" if self.is_edit else "새 주문 추가"
        self.setWindowTitle(title)
        self.setMinimumWidth(800)
        self.setMinimumHeight(800)

        self.setStyleSheet("""
            QLineEdit, QSpinBox, QComboBox {
                min-height: 13px;
                padding: 2px 5px;
                font-size: 12px;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(15)

        # --- 1. 주문 정보 그룹 ---
        header_group = QtWidgets.QGroupBox("주문 정보")
        header_form = QtWidgets.QFormLayout(header_group)
        header_form.setContentsMargins(15, 15, 15, 15)
        header_form.setVerticalSpacing(4)
        header_form.setLabelAlignment(Qt.AlignRight)

        self.edt_recv_dt = QtWidgets.QLineEdit()
        self.edt_order_dt = QtWidgets.QLineEdit()
        self.edt_order_no = QtWidgets.QLineEdit()
        self.edt_req_due = QtWidgets.QLineEdit()
        self.edt_req_due.setPlaceholderText("예: 2025-09-03")

        header_form.addRow("접수일:", self.edt_recv_dt)
        header_form.addRow("주문일:", self.edt_order_dt)
        header_form.addRow("주문번호*:", self.edt_order_no)
        header_form.addRow("최초 납기일*:", self.edt_req_due)

        # --- 2. 품목 정보 그룹 ---
        item_group = QtWidgets.QGroupBox("품목 정보")
        item_layout = QtWidgets.QVBoxLayout(item_group)
        item_layout.setContentsMargins(15, 15, 15, 15)
        item_layout.setSpacing(10)

        input_form = QtWidgets.QFormLayout()
        input_form.setVerticalSpacing(8)
        input_form.setLabelAlignment(Qt.AlignRight)

        # ✅ 기본 필터: 완제품/모듈/부품/레거시
        self.edt_item_code = AutoCompleteLineEdit(type_filter=['PRODUCT', 'MODULE', 'SELLABLE', 'PART', 'SUB_COMPONENT'])
        self.edt_item_code.product_selected.connect(self.on_product_selected)

        self.edt_rev = QtWidgets.QLineEdit()
        self.edt_product_name = QtWidgets.QLineEdit()
        self.sp_qty = QtWidgets.QSpinBox()
        self.sp_qty.setRange(1, 1_000_000)
        self.sp_qty.setGroupSeparatorShown(True)
        self.edt_unit_price = MoneyLineEdit()

        self.cb_update_master = QtWidgets.QCheckBox("제품 마스터에 판매단가 자동 업데이트")
        self.cb_update_master.setChecked(True)

        btn_add_item = QtWidgets.QPushButton("품목 추가")
        btn_add_item.clicked.connect(self.add_item)
        btn_add_item.setCursor(Qt.PointingHandCursor)
        btn_add_item.setStyleSheet("""
            QPushButton {
                padding: 5px 15px; 
                font-weight: bold; 
                font-size: 13px;
                background-color: #f0f0f0;
                border: 1px solid #888;
                border-radius: 4px;
                min-height: 18px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        
        is_privacy = False
        if self.settings and self.settings.value("view/privacy_mode", False, type=bool):
            is_privacy = True

        input_form.addRow("품목코드*:", self.edt_item_code)
        input_form.addRow("Rev:", self.edt_rev)
        input_form.addRow("제품명*:", self.edt_product_name)
        input_form.addRow("수량:", self.sp_qty)
        
        if not is_privacy:
            input_form.addRow("단가(엔):", self.edt_unit_price)
            input_form.addRow("", self.cb_update_master)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_add_item)

        item_layout.addLayout(input_form)
        item_layout.addLayout(btn_layout)

        # 품목 테이블
        self.item_table = QtWidgets.QTableWidget(0, 6)
        self.item_table.setHorizontalHeaderLabels(["품목코드", "Rev", "제품명", "수량", "단가(엔)", "금액(엔)"])
        header = self.item_table.horizontalHeader()
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        self.item_table.setColumnWidth(0, 120);
        self.item_table.setColumnWidth(1, 60)
        self.item_table.setColumnWidth(2, 300);
        self.item_table.setColumnWidth(3, 80)
        self.item_table.setColumnWidth(4, 100);
        self.item_table.setColumnWidth(5, 100)
        self.item_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.item_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.item_table.customContextMenuRequested.connect(self.show_item_context_menu)
        self.item_table.setMinimumHeight(140)
        
        apply_table_resize_policy(self.item_table)
        
        # ✅ [수정] 가로 스크롤바 활성화 (utils 정책 오버라이드)
        self.item_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.item_table.horizontalHeader().setStretchLastSection(False)

        if is_privacy:
            self.item_table.setColumnHidden(4, True)
            self.item_table.setColumnHidden(5, True)

        item_layout.addWidget(self.item_table)



        total_layout = QtWidgets.QHBoxLayout()
        total_layout.addStretch()
        
        if not is_privacy:
            total_layout.addWidget(QtWidgets.QLabel("총 주문금액:"))
            self.lbl_total_amount = QtWidgets.QLabel("0")
            self.lbl_total_amount.setStyleSheet("font-weight: bold; font-size: 14px; color: #0066cc;")
            total_layout.addWidget(self.lbl_total_amount);
            total_layout.addWidget(QtWidgets.QLabel("엔"))
        else:
            self.lbl_total_amount = QtWidgets.QLabel("0")
            self.lbl_total_amount.setVisible(False)
            
        item_layout.addLayout(total_layout)

        # --- 3. 발주 연결 그룹 ---
        purchase_group = QtWidgets.QGroupBox("연결할 발주 (재고가 있는 기존 발주)")
        purchase_layout = QtWidgets.QVBoxLayout(purchase_group)
        purchase_layout.setContentsMargins(15, 15, 15, 15)

        purchase_label = QtWidgets.QLabel("이 주문을 연결할 기존 발주를 선택하세요 (복수 선택 가능):")
        purchase_label.setStyleSheet("font-weight: bold; color: #0066cc;")

        # ✅ [추가] 미완료 발주만 보기 체크박스
        self.cb_show_incomplete_only = QtWidgets.QCheckBox("미완료 발주만 보기 (체크 해제 시 완료된 발주도 표시)")
        self.cb_show_incomplete_only.setChecked(True)
        self.cb_show_incomplete_only.toggled.connect(self.load_available_purchases)

        self.purchase_list = QtWidgets.QListWidget()
        self.purchase_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.purchase_list.setMinimumHeight(120)

        purchase_layout.addWidget(purchase_label)
        purchase_layout.addWidget(self.cb_show_incomplete_only)  # ✅ 추가
        purchase_layout.addWidget(self.purchase_list)

        main_layout.addWidget(header_group)
        main_layout.addWidget(item_group)
        main_layout.addWidget(purchase_group)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept_dialog)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    def on_product_selected(self, product_info):
        self.edt_rev.setText(product_info['rev'] or "")
        self.edt_product_name.setText(product_info['product_name'])
        if product_info['unit_price_jpy']:
            self.edt_unit_price.set_value(product_info['unit_price_jpy'] // 100)

    def add_item(self):
        item_code = self.edt_item_code.text().strip()
        product_name = self.edt_product_name.text().strip()
        if not item_code or not product_name:
            QMessageBox.warning(self, "입력 오류", "품목코드와 제품명은 필수입니다.")
            return

        rev = self.edt_rev.text().strip() or None
        qty = self.sp_qty.value()
        unit_price_cents = self.edt_unit_price.get_value() * 100

        if self.cb_update_master.isChecked():
            status = add_or_update_product_master(
                item_code=item_code,
                rev=rev,
                product_name=product_name,
                unit_price_jpy=unit_price_cents
            )
            if status == 'DUPLICATE_INACTIVE':
                rev_str = f"(Rev: {rev})" if rev else ""
                QMessageBox.warning(
                    self, "중복 오류",
                    f"품목코드: {item_code} {rev_str}\n\n"
                    "판매하지 않는 품목입니다.\n"
                    "품목 관리 탭에서 '판매 중'으로 변경 후 다시 시도해주세요."
                )
                return

        item = {
            'item_code': item_code, 'rev': rev, 'product_name': product_name,
            'qty': qty, 'unit_price_cents': unit_price_cents, 'currency': 'JPY'
        }
        self.items.append(item)

        row = self.item_table.rowCount()
        self.item_table.insertRow(row)
        self.item_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item['item_code']))
        self.item_table.setItem(row, 1, QtWidgets.QTableWidgetItem(item['rev'] or ""))
        self.item_table.setItem(row, 2, QtWidgets.QTableWidgetItem(item['product_name']))
        self.item_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{item['qty']:,}"))
        unit_price = item['unit_price_cents'] // 100
        self.item_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{unit_price:,}"))
        self.item_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{item['qty'] * unit_price:,}"))

        self.update_total_amount()
        self.edt_item_code.clear()
        self.edt_rev.clear()
        self.edt_product_name.clear()
        self.sp_qty.setValue(1)
        self.edt_unit_price.set_value(0)

        self.load_available_purchases()

    def show_item_context_menu(self, position):
        if self.item_table.itemAt(position) is None: return
        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("삭제")
        delete_action.triggered.connect(self.delete_selected_item)
        menu.exec_(self.item_table.mapToGlobal(position))

    def delete_selected_item(self):
        row = self.item_table.currentRow()
        if row >= 0:
            self.items.pop(row)
            self.item_table.removeRow(row)
            self.update_total_amount()
            self.load_available_purchases()

    def update_total_amount(self):
        total = sum(item['qty'] * (item['unit_price_cents'] // 100) for item in self.items)
        self.lbl_total_amount.setText(f"{total:,}")

    def load_order_data(self):
        self.items.clear()
        self.item_table.setRowCount(0)
        order = get_order_with_items(self.order_id)
        if not order: return
        header = order['header']
        self.edt_order_no.setText(header[1] or "")
        self.edt_recv_dt.setText(header[3] or "")
        self.edt_order_dt.setText(header[4] or "")
        self.edt_req_due.setText(header[5] or "")

        for i, item_data in enumerate(order['items']):
            item_id, item_code, rev, product_name, qty, unit_price_cents, currency = item_data
            item = {'id': item_id, 'item_code': item_code, 'rev': rev, 'product_name': product_name, 'qty': qty,
                    'unit_price_cents': unit_price_cents, 'currency': currency}
            self.items.append(item)
            row = self.item_table.rowCount()
            self.item_table.insertRow(row)
            unit_price = unit_price_cents // 100
            
            # ID 저장을 위해 첫 번째 컬럼에 UserRole 설정
            code_item = QtWidgets.QTableWidgetItem(item_code or "")
            code_item.setData(Qt.UserRole, item_id)
            self.item_table.setItem(row, 0, code_item)
            self.item_table.setItem(row, 1, QtWidgets.QTableWidgetItem(rev or ""))
            self.item_table.setItem(row, 2, QtWidgets.QTableWidgetItem(product_name))
            self.item_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{qty:,}"))
            self.item_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{unit_price:,}"))
            self.item_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{item['qty'] * unit_price:,}"))

        self.update_total_amount()
        self.load_available_purchases()

    def accept_dialog(self):
        order_no = self.edt_order_no.text().strip()
        if not order_no or not self.items:
            # ✅ [수정] 항목 없을 때 경고 메시지가 빈값인 문제 수정
            QMessageBox.warning(self, "입력 오류", "주문번호와 최소 1개 이상의 품목은 필수입니다.")
            return
        req_due = parse_due_text(self.edt_req_due.text())
        if not req_due:
            QMessageBox.warning(self, "입력 오류", "최초 납기일은 필수입니다.")
            return

        try:
            order_data = {'order_no': order_no, 'recv_dt': parse_due_text(self.edt_recv_dt.text()),
                          'order_dt': parse_due_text(self.edt_order_dt.text()), 'req_due': req_due,
                          'final_due': req_due}

            shipment_data_to_save = None
            selected_purchase_ids = [item.data(Qt.UserRole) for item in self.purchase_list.selectedItems()]

            if self.is_edit:
                # 테이블에서 현재 편집된 아이템들의 ID 정보 등을 최신화하여 수집
                updated_items = []
                for row in range(self.item_table.rowCount()):
                    # load_order_data에서 첫 번째 컬럼(0)에 ID를 UserRole로 저장했음
                    item_id = self.item_table.item(row, 0).data(Qt.UserRole)
                    
                    # self.items 리스트와 순서가 같다고 가정하지만, 안전하게 테이블 값으로 재구성하거나 매핑
                    # 여기서는 self.items가 add_item/delete_item으로 동기화된다고 보고 ID만 주입
                    if row < len(self.items):
                        item_data = self.items[row].copy() # 기존 데이터 복사
                        if item_id:
                            item_data['id'] = item_id
                        updated_items.append(item_data)
                
                # 기존 로직: DELETE order_shipments... (이건 유지할지 여부는 update_order_with_items 변경에 따라 다름)
                # update_order_with_items가 items ID를 기반으로 UPDATE를 수행하므로
                # order_shipments가 CASCADE로 삭제되지 않게 하려면 order_items의 ID가 유지되어야 함.
                # DB의 update_order_with_items 수정으로 order_items가 유지되므로 order_shipments도 유지됨.
                # 단, 여기서 명시적으로 shipment를 삭제하는 로직이 있다면 주의 필요.
                
                # 기존 코드:
                # cur.execute("DELETE FROM order_shipments WHERE order_item_id IN (SELECT id FROM order_items WHERE order_id = ?)", (self.order_id,))
                # 이 코드는 "모든 납기 일정을 초기화"하는 것으로 보임.
                # 납기 변경 이력이 사라지는 주 원인이 바로 아래의 DELETE 문일 수도 있음!
                # 하지만 사용자가 "이력이 사라진다"고 한 것은 order_items가 재생성되면서 cascade delete되는 것 때문일 가능성이 큼.
                # 아래 DELETE 문이 실행되면 납기 일정은 날아가지만, shipment_change_history는 order_item_id에 종속적이므로
                # order_item_id가 유지된다면 history도 유지될 가능성이 있음 (history 테이블 정의 확인 필요).
                # shipment_date_changes 테이블은 order_item_id를 참조하고 ON DELETE CASCADE임.
                
                # 따라서, order_items를 UPDATE하면 ID가 유지되고 -> history도 유지됨.
                # 그러나 아래의 DELETE order_shipments는 '현재 일정'을 지우는 것임.
                # 만약 shipment_date_changes가 order_shipments와는 독립적으로 order_item_id에만 연결되어 있다면 
                # 아래 구문은 history에 영향을 주지 않음.
                
                # 다만, update_order_with_items 내부에서 shipment_data_to_save가 None이면 납기 정보를 건드리지 않아야 하는데,
                # 현재 코드는 shipment_data가 있으면 save_shipments_for_order_item을 호출함.
                
                # 결론: 아래의 DELETE 문은 제거해야 함. 
                # 왜냐하면 사용자가 납기 정보를 수정하지 않았는데 납기 정보가 초기화되면 안 되기 때문.
                # 또는 납기 정보가 수정된 경우에만 처리해야 함.
                # (현재 다이얼로그에는 납기 상세 편집 기능이 없음 - 최초 납기일만 있음)
                
                # 안전을 위해 DB 연결 부분 제거하고 update 함수 호출만 수행
                
                update_order_with_items(self.order_id, order_data, updated_items, shipment_data_to_save,
                                        selected_purchase_ids)
            else:
                create_order_with_items(order_data, self.items, shipment_data_to_save, selected_purchase_ids)

            QMessageBox.information(self, "완료", f"주문 '{order_no}'이 저장되었습니다.")

            try:
                from .outlook_sync import OutlookSyncWorker
                self.sync_worker = OutlookSyncWorker(future_only=True)
                self.sync_worker.sync_finished.connect(lambda msg: print(f">> 자동 동기화 완료: {msg}"))
                self.sync_worker.start()
            except Exception as e:
                print(f">> 자동 동기화 실패: {e}")

            self.accept()

        except Exception as e:
            if "UNIQUE constraint failed: orders.order_no" in str(e):
                QtWidgets.QMessageBox.critical(
                    self, "중복 오류",
                    f"주문번호 '{order_no}'는 이미 존재합니다.\n"
                    "다른 주문번호를 사용해주세요."
                )
            else:
                QtWidgets.QMessageBox.critical(self, "오류", f"주문 저장 중 오류가 발생했습니다:\n{str(e)}")

            import traceback
            traceback.print_exc()

    def load_available_purchases(self):
        """
        연결 가능한 발주 목록 로드
        """
        current_item_codes = set()
        for row in range(self.item_table.rowCount()):
            code_item = self.item_table.item(row, 0)
            if code_item and code_item.text():
                current_item_codes.add(code_item.text().strip())

        previously_selected_ids = {item.data(Qt.UserRole) for item in self.purchase_list.selectedItems()}
        self.purchase_list.clear()

        if not current_item_codes:
            no_item = QtWidgets.QListWidgetItem("주문 품목을 먼저 추가하세요.")
            no_item.setFlags(no_item.flags() & ~QtCore.Qt.ItemIsSelectable)
            self.purchase_list.addItem(no_item)
            return

        all_purchases_dict = {}
        linked_purchase_ids = set()

        try:
            # 기본 발주 목록 로드 (get_available_purchases 내부에서 FIFO 여유분(dict) 계산됨)
            available_purchases = get_available_purchases()

            completed_purchases = []
            
            # ✅ [수정] "미완료만 보기"가 해제되어 있거나, 수정 모드일 때만 완료된 발주를 가져옴 (필요시)
            # 하지만 여기서 '수정 모드' 여부보다 체크박스가 더 중요함.
            # 체크박스가 해제되면 완료된 것도 다 가져와야 함.
            
            should_load_completed = not self.cb_show_incomplete_only.isChecked()

            if should_load_completed:
                # 이미 available_purchases에 있는 건 제외하고 가져와야 함
                available_ids = {p[0] for p in available_purchases}
                not_in_clause = ""
                params = []
                if available_ids:
                    placeholders = ', '.join('?' for _ in available_ids)
                    not_in_clause = f"WHERE p.id NOT IN ({placeholders})"
                    params.extend(list(available_ids))

                base_sql = """
                            SELECT 
                                p.id, 
                                p.purchase_no, 
                                (SELECT GROUP_CONCAT(pi.product_name, ' | ') FROM purchase_items pi WHERE pi.purchase_id = p.id) as p_desc,
                                (SELECT SUM(pi.qty) FROM purchase_items pi WHERE pi.purchase_id = p.id) as total_qty,
                                p.purchase_dt,
                                0 as stock_qty, 0 as allocation_margin, 0 as produced_qty, NULL as first_serial,
                                COALESCE(p.status, '발주')
                            FROM purchases p
                        """
                completed_purchases = query_all(f"{base_sql} {not_in_clause}", tuple(params))

            all_possible_purchases = available_purchases + completed_purchases

            purchase_items_map = {}
            for p_id, item_code in query_all("SELECT purchase_id, item_code FROM purchase_items", ()):
                if p_id not in purchase_items_map:
                    purchase_items_map[p_id] = set()
                purchase_items_map[p_id].add(item_code)

            if self.is_edit and self.order_id:
                linked_ids_result = query_all(
                    "SELECT p.id FROM purchases p JOIN purchase_order_links pol ON p.id = pol.purchase_id WHERE pol.order_id = ?",
                    (self.order_id,)
                )
                linked_purchase_ids.update(row[0] for row in linked_ids_result)

            for (p_id, p_no, p_desc, ordered_qty, p_dt, stock_qty, allocation_margin_raw, produced_qty,
                 first_available_serial, *rest) in all_possible_purchases:

                items_in_this_purchase = purchase_items_map.get(p_id, set())
                intersection = current_item_codes.intersection(items_in_this_purchase)
                
                # 교집합이 없으면 스킵 (단, 이미 연결된 건 제외)
                if not intersection:
                    if p_id not in linked_purchase_ids:
                        continue
                
                status = rest[0] if rest else "미완료"
                display_text = ""
                item_color = None

                # ✅ [수정] 해당 품목에 대한 여유분 계산
                # allocation_margin_raw는 이제 {item_code: qty} 딕셔너리임 (get_available_purchases 수정됨)
                margins_dict = allocation_margin_raw if isinstance(allocation_margin_raw, dict) else {}
                
                # 교집합 품목들의 여유분 합계
                relevant_margin = sum(margins_dict.get(code, 0) for code in intersection)

                # 여유분이 0 이하면 표시 안 함 (단, 이미 연결된 건 제외)
                # (중요: 사용자는 재고가 없는 발주가 나오는 것을 혼란스러워했음)
                # ✅ [수정] 체크박스가 해제되어 있으면 여유분이 없어도 표시해야 함
                if self.cb_show_incomplete_only.isChecked():
                    if relevant_margin <= 0 and p_id not in linked_purchase_ids:
                        continue
                else:
                    # 전체 보기 모드: 여유분이 없어도 품목만 맞으면 표시
                    # (위의 intersection check는 이미 통과했음)
                    pass

                if status == '완료':
                    tag = "[완료]"
                    if p_id in linked_purchase_ids:
                        tag = "[연결됨/완료]"
                    display_text = f"{tag} [{p_dt}] {p_no} - {p_desc or 'N/A'}"
                    item_color = QColor("#888888")
                else:
                    if stock_qty <= 0 and produced_qty == 0:
                        stock_str = "미생산"
                    else:
                        serial_str = ""
                        if stock_qty > 0 and first_available_serial:
                            serial_str = f" (S/N: {first_available_serial}~)"
                        stock_str = f"재고: {stock_qty}개{serial_str}"
                    
                    # ✅ 여유분 표시 개선: "할당 여유: 7개"
                    margin_info = f"{relevant_margin}개"
                    
                    margin_str = f"할당 여유: {margin_info}"
                    order_str = f"총 발주: {ordered_qty}개"

                    display_text = f"[{p_dt}] {p_no} - ({order_str} / {stock_str} / {margin_str}) - {p_desc}"

                item = QtWidgets.QListWidgetItem(display_text)
                item.setData(Qt.UserRole, p_id)
                if item_color:
                    item.setForeground(QBrush(item_color))

                self.purchase_list.addItem(item)
                if p_id in linked_purchase_ids or p_id in previously_selected_ids:
                    item.setSelected(True)

        except Exception as e:
            print(f"발주 목록 로드 오류: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self.restore_column_widths)

    def done(self, result):
        """다이얼로그가 닫힐 때(OK, Cancel, X 등) 항상 호출됨"""
        self.save_column_widths()
        super().done(result)

    def save_column_widths(self):
        """테이블 컬럼 폭 저장"""
        if not self.settings: return
        widths = []
        for col in range(self.item_table.columnCount()):
            widths.append(self.item_table.columnWidth(col))
        self.settings.setValue("order_dialog_item_table/column_widths", widths)

    def restore_column_widths(self):
        """테이블 컬럼 폭 복원"""
        if not self.settings: return
        widths = self.settings.value("order_dialog_item_table/column_widths")
        if widths:
            # 리사이저 간섭 방지
            self.item_table.horizontalHeader().blockSignals(True)
            try:
                for col, width in enumerate(widths):
                    if col < self.item_table.columnCount():
                        self.item_table.setColumnWidth(col, int(width))
            finally:
                self.item_table.horizontalHeader().blockSignals(False)