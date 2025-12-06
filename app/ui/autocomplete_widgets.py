# app/ui/autocomplete_widgets.py

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import QCompleter, QHeaderView, QMessageBox, QLineEdit
from PySide6.QtCore import Qt, QStringListModel, QTimer
from PySide6.QtGui import QBrush, QColor

# ✅ [수정] calculate_fifo_allocation_margins 임포트 추가
from ..db import (
    get_conn, get_order_with_items, create_order_with_items,
    update_order_with_items, add_or_update_product_master,
    get_available_purchases, query_all, calculate_fifo_allocation_margins
)
from .money_lineedit import MoneyLineEdit
from .utils import parse_due_text
from .outlook_sysnc import sync_outlook_tasks


class AutoCompleteLineEdit(QtWidgets.QLineEdit):
    # ... (기존 코드와 동일, 변경 없음) ...
    """자동완성 기능이 있는 LineEdit - 클릭 시 전체 목록 표시"""
    product_selected = QtCore.Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_products = []
        self.product_data = {}
        self.setup_completer()
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.update_completions)
        self.textChanged.connect(self.on_text_changed)

    def setup_completer(self):
        self.completer = QCompleter(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setMaxVisibleItems(10)
        self.completer.activated.connect(self.handle_completion)
        self.setCompleter(None)
        self.completer.setWidget(self)
        popup = self.completer.popup()
        popup.setStyleSheet("QListView::item:selected { background-color: #0078d4; color: white; }")

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.load_data()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.completer:
            self.completer.complete()

    def load_data(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description FROM product_master WHERE is_active = 1 ORDER BY item_code")
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
                self.completer.setCompletionPrefix(current_text)

        except Exception as e:
            print(f"제품 목록 로드 오류: {e}")

    def on_text_changed(self, text):
        if len(text) >= 2:
            self.search_timer.start(300)
        else:
            self.search_timer.stop()

    def update_completions(self):
        text = self.text().strip()
        if len(text) < 2: return
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw FROM product_master WHERE is_active = 1 AND (item_code LIKE ? OR product_name LIKE ?) ORDER BY item_code, rev LIMIT 10",
                (f"%{text}%", f"%{text}%"))
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
from .utils import parse_due_text


class AutoCompleteLineEdit(QtWidgets.QLineEdit):
    """자동완성 기능이 있는 LineEdit - 클릭 시 전체 목록 표시"""
    product_selected = QtCore.Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_products = []
        self.product_data = {}
        self.setup_completer()
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.update_completions)
        self.textChanged.connect(self.on_text_changed)

    def setup_completer(self):
        self.completer = QCompleter(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setMaxVisibleItems(10)
        self.completer.activated.connect(self.handle_completion)
        self.setCompleter(None)
        self.completer.setWidget(self)
        popup = self.completer.popup()
        popup.setStyleSheet("QListView::item:selected { background-color: #0078d4; color: white; }")

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.load_data()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.completer:
            self.completer.complete()

    def load_data(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description FROM product_master WHERE is_active = 1 ORDER BY item_code")
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
                self.completer.setCompletionPrefix(current_text)

        except Exception as e:
            print(f"제품 목록 로드 오류: {e}")

    def on_text_changed(self, text):
        if len(text) >= 2:
            self.search_timer.start(300)
        else:
            self.search_timer.stop()

    def update_completions(self):
        text = self.text().strip()
        if len(text) < 2: return
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw FROM product_master WHERE is_active = 1 AND (item_code LIKE ? OR product_name LIKE ?) ORDER BY item_code, rev LIMIT 10",
                (f"%{text}%", f"%{text}%"))
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

    def __init__(self, parent=None, is_edit=False, order_id=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.order_id = order_id
        self.items = []
        self.setup_ui()

        # 초기화 시 로드
        self.load_available_purchases()

        if is_edit and order_id:
            self.load_order_data()

    def setup_ui(self):
        title = "주문 수정" if self.is_edit else "새 주문 추가"
        self.setWindowTitle(title)
        # ✅ [수정] 다이얼로그 기본 크기 대폭 확대 (겹침 방지)
        self.setMinimumWidth(800)
        self.setMinimumHeight(800)

        # ✅ [수정] 입력창 스타일 및 그룹박스 스타일 개선
        self.setStyleSheet("""
            QLineEdit, QSpinBox, QComboBox {
                min-height: 13px;  /* 입력창 높이 적절히 조정 */
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
        main_layout.setSpacing(15)  # 그룹박스 간 간격 확보

        # --- 1. 주문 정보 그룹 ---
        header_group = QtWidgets.QGroupBox("주문 정보")
        # ✅ [수정] 폼 레이아웃 간격을 좁힘 (너무 넓지 않게)
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
        input_form.setVerticalSpacing(8)  # 입력창 상하 간격
        input_form.setLabelAlignment(Qt.AlignRight)

        self.edt_item_code = AutoCompleteLineEdit()
        self.edt_item_code.product_selected.connect(self.on_product_selected)
        self.edt_rev = QtWidgets.QLineEdit()
        self.edt_product_name = QtWidgets.QLineEdit()
        self.sp_qty = QtWidgets.QSpinBox()
        self.sp_qty.setRange(1, 1_000_000)
        self.sp_qty.setGroupSeparatorShown(True)
        self.edt_unit_price = MoneyLineEdit()

        self.cb_update_master = QtWidgets.QCheckBox("제품 마스터에 판매단가 자동 업데이트")
        self.cb_update_master.setChecked(True)

        # ✅ [수정] 버튼 스타일 개선 (높이를 키우고, 배경색 추가)
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
                min-height: 18px; /* 높이 충분히 확보 */
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)

        input_form.addRow("품목코드*:", self.edt_item_code)
        input_form.addRow("Rev:", self.edt_rev)
        input_form.addRow("제품명*:", self.edt_product_name)
        input_form.addRow("수량:", self.sp_qty)
        input_form.addRow("단가(엔):", self.edt_unit_price)
        input_form.addRow("", self.cb_update_master)

        # 버튼을 담을 레이아웃 (오른쪽 정렬)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_add_item)

        item_layout.addLayout(input_form)
        item_layout.addLayout(btn_layout)  # 버튼 추가

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
        self.item_table.setMinimumHeight(140)  # 테이블 최소 높이

        item_layout.addWidget(self.item_table)

        # 총액 표시
        total_layout = QtWidgets.QHBoxLayout()
        total_layout.addStretch()
        total_layout.addWidget(QtWidgets.QLabel("총 주문금액:"))
        self.lbl_total_amount = QtWidgets.QLabel("0")
        self.lbl_total_amount.setStyleSheet("font-weight: bold; font-size: 14px; color: #0066cc;")
        total_layout.addWidget(self.lbl_total_amount);
        total_layout.addWidget(QtWidgets.QLabel("엔"))
        item_layout.addLayout(total_layout)

        # --- 3. 발주 연결 그룹 ---
        purchase_group = QtWidgets.QGroupBox("연결할 발주 (재고가 있는 기존 발주)")
        purchase_layout = QtWidgets.QVBoxLayout(purchase_group)
        purchase_layout.setContentsMargins(15, 15, 15, 15)

        purchase_label = QtWidgets.QLabel("이 주문을 연결할 기존 발주를 선택하세요 (복수 선택 가능):")
        purchase_label.setStyleSheet("font-weight: bold; color: #0066cc;")
        self.purchase_list = QtWidgets.QListWidget()
        self.purchase_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.purchase_list.setMinimumHeight(120)  # 리스트 최소 높이

        purchase_layout.addWidget(purchase_label)
        purchase_layout.addWidget(self.purchase_list)

        # --- 4. 메인 레이아웃 조립 ---
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
                    "이미 '단종' 처리된 품목입니다.\n"
                    "품목 관리 탭에서 '생산 가능'으로 변경 후 다시 시도해주세요."
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
            _, item_code, rev, product_name, qty, unit_price_cents, currency = item_data
            item = {'item_code': item_code, 'rev': rev, 'product_name': product_name, 'qty': qty,
                    'unit_price_cents': unit_price_cents, 'currency': currency}
            self.items.append(item)
            row = self.item_table.rowCount()
            self.item_table.insertRow(row)
            unit_price = unit_price_cents // 100
            self.item_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item_code or ""))
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
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM order_shipments WHERE order_item_id IN (SELECT id FROM order_items WHERE order_id = ?)",
                    (self.order_id,))
                conn.commit()
                conn.close()
                update_order_with_items(self.order_id, order_data, self.items, shipment_data_to_save,
                                        selected_purchase_ids)
            else:
                create_order_with_items(order_data, self.items, shipment_data_to_save, selected_purchase_ids)

            QMessageBox.information(self, "완료", f"주문 '{order_no}'이 저장되었습니다.")

            try:
                # ✅ [수정] 백그라운드 스레드에서 Outlook 동기화 실행 (미래 일정만)
                from .outlook_sysnc import OutlookSyncWorker
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
        ✅ [수정] FIFO 계산 로직 적용 (db.calculate_fifo_allocation_margins 활용)
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
            # ✅ [수정] FIFO 할당 여유 계산 (전체)
            fifo_margins = calculate_fifo_allocation_margins()

            # 기본 발주 목록 로드
            available_purchases = get_available_purchases()

            completed_purchases = []
            if self.is_edit:
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
                if not current_item_codes.intersection(items_in_this_purchase):
                    if p_id not in linked_purchase_ids:
                        continue

                status = rest[0] if rest else "미완료"
                display_text = ""
                item_color = None

                # ✅ [수정] FIFO 계산된 할당 여유분 사용
                allocation_margin = fifo_margins.get(p_id, 0)

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

                    margin_str = f"할당 여유: {allocation_margin}개"
                    order_str = f"총 발주: {ordered_qty}개"

                    display_text = f"[{p_dt}] {p_no} - ({order_str} / {stock_str} / {margin_str}) - {p_desc}"

                    if stock_qty < allocation_margin:
                        item_color = QColor("#dc3545")

                all_purchases_dict[p_id] = (display_text, p_id, item_color)

            if not all_purchases_dict:
                no_item = QtWidgets.QListWidgetItem("연결 가능한 발주 없음 (품목 일치 건 없음)")
                no_item.setFlags(no_item.flags() & ~QtCore.Qt.ItemIsSelectable)
                self.purchase_list.addItem(no_item)
                return

            sorted_items = sorted(all_purchases_dict.values(), key=lambda x: x[0].split(']')[0], reverse=True)

            for display_text, p_id, item_color in sorted_items:
                item = QtWidgets.QListWidgetItem(display_text)
                item.setData(Qt.UserRole, p_id)
                if item_color:
                    item.setForeground(QBrush(item_color))
                self.purchase_list.addItem(item)

                if p_id in previously_selected_ids or p_id in linked_purchase_ids:
                    item.setSelected(True)

        except Exception as e:
            print(f"연결 가능한 발주 목록 로딩 중 오류: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "오류", f"발주 목록 로드 중 오류:\n{e}")