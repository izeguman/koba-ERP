# app/ui/autocomplete_widgets.py
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QCompleter, QHeaderView
from PySide6.QtCore import Qt, QStringListModel, QTimer
from ..db import search_product_master, add_or_update_product_master, get_conn, get_all_product_master
from .money_lineedit import MoneyLineEdit


def parse_due_text(text: str) -> str | None:
    """날짜 파싱 함수"""
    from datetime import datetime
    s = (text or "").strip()
    if not s:
        return None
    fmts = [
        "%Y-%m-%d", "%Y/%m/%d",
        "%y-%m-%d", "%y/%m/%d",
        "%d-%b-%y", "%d-%b-%Y",
        "%d/%m/%Y", "%m/%d/%Y",
    ]
    for f in fmts:
        try:
            dt = datetime.strptime(s, f)
            if dt.year < 2000:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


class AutoCompleteLineEdit(QtWidgets.QLineEdit):
    """자동완성 기능이 있는 LineEdit - 포커스 시 자동으로 전체 목록 표시"""

    product_selected = QtCore.Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_products = []  # 전체 제품 목록
        self.product_data = {}  # 제품 데이터
        self.setup_completer()

        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.update_completions)

        self.textChanged.connect(self.on_text_changed)

    def setup_completer(self):
        """자동완성 설정"""
        self.completer = QCompleter(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setMaxVisibleItems(10)

        self.completer.activated.connect(self.handle_completion)
        self.setCompleter(None)
        self.completer.setWidget(self)

    def focusInEvent(self, event):
        """포커스를 받으면 전체 제품 목록 표시 (단종 제품 제외)"""
        super().focusInEvent(event)

        # ✅ is_active = 1인 제품만 로드
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description
                FROM product_master 
                WHERE is_active = 1
                ORDER BY item_code
            """)
            self.all_products = cur.fetchall()
            conn.close()

            if self.all_products:
                completions = []
                self.product_data = {}

                for product in self.all_products:
                    product_id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description = product

                    display_text = f"{item_code} - {product_name}"
                    if rev:
                        display_text = f"{item_code} (Rev {rev}) - {product_name}"

                    completions.append(display_text)
                    self.product_data[display_text] = {
                        'item_code': item_code,
                        'rev': rev,
                        'product_name': product_name,
                        'unit_price_jpy': unit_price_jpy,
                        'purchase_price_krw': purchase_price_krw
                    }

                model = QStringListModel(completions)
                self.completer.setModel(model)

                # 현재 텍스트가 있으면 필터링, 없으면 전체 표시
                current_text = self.text().strip()
                if current_text:
                    self.completer.setCompletionPrefix(current_text)
                else:
                    self.completer.setCompletionPrefix("")

                popup = self.completer.popup()
                popup.setCurrentIndex(self.completer.completionModel().index(0, 0))

                cr = self.cursorRect()
                cr.setWidth(self.completer.popup().sizeHintForColumn(0) +
                            self.completer.popup().verticalScrollBar().sizeHint().width())
                self.completer.complete(cr)
        except Exception as e:
            print(f"제품 목록 로드 오류: {e}")

    def on_text_changed(self, text):
        """텍스트 변경 시 검색 타이머 시작"""
        if len(text) >= 2:
            self.search_timer.start(300)
        else:
            self.search_timer.stop()

    def update_completions(self):
        """자동완성 목록 업데이트 (단종 제품 제외)"""
        text = self.text().strip()
        if len(text) < 2:
            return

        try:
            # ✅ is_active = 1인 제품만 검색
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw
                FROM product_master 
                WHERE is_active = 1 
                AND (item_code LIKE ? OR product_name LIKE ?)
                ORDER BY item_code, rev
                LIMIT 10
            """, (f"%{text}%", f"%{text}%"))
            products = cur.fetchall()
            conn.close()

            completions = []
            self.product_data = {}

            for product in products:
                product_id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw = product

                display_text = f"{item_code} - {product_name}"
                if rev:
                    display_text = f"{item_code} (Rev {rev}) - {product_name}"

                completions.append(display_text)

                self.product_data[display_text] = {
                    'item_code': item_code,
                    'rev': rev,
                    'product_name': product_name,
                    'unit_price_jpy': unit_price_jpy,
                    'purchase_price_krw': purchase_price_krw
                }

            model = QStringListModel(completions)
            self.completer.setModel(model)

            if completions:
                self.completer.setCompletionPrefix(text)
                popup = self.completer.popup()
                popup.setCurrentIndex(self.completer.completionModel().index(0, 0))

                cr = self.cursorRect()
                cr.setWidth(self.completer.popup().sizeHintForColumn(0) +
                            self.completer.popup().verticalScrollBar().sizeHint().width())
                self.completer.complete(cr)

        except Exception as e:
            print(f"자동완성 검색 오류: {e}")

    def handle_completion(self, text):
        """완성 선택 처리"""
        if hasattr(self, 'product_data') and text in self.product_data:
            product_info = self.product_data[text]

            self.completer.popup().hide()

            self.blockSignals(True)
            self.setText(product_info['item_code'])
            self.blockSignals(False)

            self.setCursorPosition(len(product_info['item_code']))

            self.product_selected.emit(product_info)

    def keyPressEvent(self, event):
        """키 입력 이벤트 처리"""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            if self.completer.popup().isVisible():
                current_index = self.completer.popup().currentIndex()
                if current_index.isValid():
                    text = self.completer.completionModel().data(current_index)
                    self.handle_completion(text)
                    return

        super().keyPressEvent(event)


class ProductOrderDialog(QtWidgets.QDialog):
    """제품 마스터 정보를 활용한 주문 입력 다이얼로그 (여러 품목 지원)"""

    def __init__(self, parent=None, is_edit=False, order_id=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.order_id = order_id
        self.items = []  # 품목 리스트
        self.setup_ui()

        if is_edit and order_id:
            self.load_order_data()

    def setup_ui(self):
        title = "주문 수정" if self.is_edit else "새 주문 추가"
        self.setWindowTitle(title)
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)

        main_layout = QtWidgets.QVBoxLayout(self)

        # ========== 주문 헤더 정보 ==========
        header_group = QtWidgets.QGroupBox("주문 정보")
        header_form = QtWidgets.QFormLayout(header_group)

        self.edt_recv_dt = QtWidgets.QLineEdit()
        self.edt_recv_dt.setPlaceholderText("예: 2025-08-27 / 2025/8/27")

        self.edt_order_dt = QtWidgets.QLineEdit()
        self.edt_order_dt.setPlaceholderText("예: 2025-08-27 / 2025/8/27")

        self.edt_order_no = QtWidgets.QLineEdit()

        self.edt_req_due = QtWidgets.QLineEdit()
        self.edt_req_due.setPlaceholderText("예: 2025-09-03 / 2025/9/3")

        header_form.addRow("접수일", self.edt_recv_dt)
        header_form.addRow("주문일", self.edt_order_dt)
        header_form.addRow("주문번호*", self.edt_order_no)
        header_form.addRow("납기일", self.edt_req_due)

        # ========== 품목 입력 영역 ==========
        item_group = QtWidgets.QGroupBox("품목 정보")
        item_layout = QtWidgets.QVBoxLayout(item_group)

        # 품목 입력 폼
        input_form = QtWidgets.QFormLayout()

        self.edt_item_code = AutoCompleteLineEdit()
        self.edt_item_code.setPlaceholderText("품목코드 입력 또는 검색")
        self.edt_item_code.product_selected.connect(self.on_product_selected)

        self.edt_rev = QtWidgets.QLineEdit()

        self.edt_product_name = QtWidgets.QLineEdit()
        self.edt_product_name.setMinimumWidth(400)

        self.sp_qty = QtWidgets.QSpinBox()
        self.sp_qty.setRange(1, 1_000_000)
        self.sp_qty.setValue(1)
        self.sp_qty.setGroupSeparatorShown(True)

        self.edt_unit_price = MoneyLineEdit(max_value=1_000_000_000)
        self.edt_unit_price.setPlaceholderText("예: 405000")
        self.edt_unit_price.setMinimumWidth(200)

        # ✨ 제품 마스터 업데이트 체크박스 추가
        self.cb_update_master = QtWidgets.QCheckBox("제품 마스터에 판매단가 자동 업데이트")
        self.cb_update_master.setChecked(True)  # 기본값: 체크

        btn_add_item = QtWidgets.QPushButton("품목 추가")
        btn_add_item.clicked.connect(self.add_item)

        input_form.addRow("품목코드*", self.edt_item_code)
        input_form.addRow("Rev", self.edt_rev)
        input_form.addRow("제품명*", self.edt_product_name)
        input_form.addRow("수량", self.sp_qty)
        input_form.addRow("단가(엔)", self.edt_unit_price)
        input_form.addRow("", self.cb_update_master)  # ✨ 체크박스 추가
        input_form.addRow("", btn_add_item)

        item_layout.addLayout(input_form)

        # 품목 리스트 테이블
        self.item_table = QtWidgets.QTableWidget(0, 6)
        self.item_table.setHorizontalHeaderLabels(
            ["품목코드", "Rev", "제품명", "수량", "단가(엔)", "금액(엔)"]
        )
        self.item_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.item_table.setMaximumHeight(200)
        self.item_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.item_table.customContextMenuRequested.connect(self.show_item_context_menu)

        header = self.item_table.horizontalHeader()
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.item_table.setColumnWidth(0, 120)
        self.item_table.setColumnWidth(1, 60)
        self.item_table.setColumnWidth(2, 300)
        self.item_table.setColumnWidth(3, 80)
        self.item_table.setColumnWidth(4, 100)
        self.item_table.setColumnWidth(5, 100)

        item_layout.addWidget(self.item_table)

        # 총 금액 표시
        total_layout = QtWidgets.QHBoxLayout()
        total_layout.addStretch()
        total_layout.addWidget(QtWidgets.QLabel("총 주문금액:"))
        self.lbl_total_amount = QtWidgets.QLabel("0")
        self.lbl_total_amount.setStyleSheet("font-weight: bold; font-size: 14px; color: #0066cc;")
        total_layout.addWidget(self.lbl_total_amount)
        total_layout.addWidget(QtWidgets.QLabel("엔"))

        item_layout.addLayout(total_layout)

        # ========== 버튼 ==========
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept_dialog)
        btns.rejected.connect(self.reject)

        # 레이아웃 구성
        main_layout.addWidget(header_group)
        main_layout.addWidget(item_group)
        main_layout.addWidget(btns)

    def on_product_selected(self, product_info):
        """제품 선택 시 정보 자동 입력"""
        self.edt_rev.setText(product_info['rev'] or "")
        self.edt_product_name.setText(product_info['product_name'])

        if product_info['unit_price_jpy']:
            self.edt_unit_price.set_value(product_info['unit_price_jpy'] // 100)

    def add_item(self):
        """품목 추가"""
        item_code = self.edt_item_code.text().strip()
        product_name = self.edt_product_name.text().strip()

        if not item_code or not product_name:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "품목코드와 제품명은 필수입니다.")
            return

        rev = self.edt_rev.text().strip() or None
        qty = self.sp_qty.value()
        unit_price = self.edt_unit_price.get_value()

        # 품목 데이터 저장
        item = {
            'item_code': item_code,
            'rev': rev,
            'product_name': product_name,
            'qty': qty,
            'unit_price_cents': unit_price * 100,
            'currency': 'JPY'
        }
        self.items.append(item)

        # 테이블에 추가
        row = self.item_table.rowCount()
        self.item_table.insertRow(row)

        self.item_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item_code))
        self.item_table.setItem(row, 1, QtWidgets.QTableWidgetItem(rev or ""))
        self.item_table.setItem(row, 2, QtWidgets.QTableWidgetItem(product_name))
        self.item_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{qty:,}"))
        self.item_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{unit_price:,}"))
        self.item_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{qty * unit_price:,}"))

        # 입력 필드 초기화
        self.edt_item_code.clear()
        self.edt_rev.clear()
        self.edt_product_name.clear()
        self.sp_qty.setValue(1)
        self.edt_unit_price.set_value(0)

        self.update_total_amount()

    def show_item_context_menu(self, position):
        """품목 우클릭 메뉴"""
        if self.item_table.itemAt(position) is None:
            return

        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("삭제")
        delete_action.triggered.connect(self.delete_selected_item)
        menu.exec_(self.item_table.mapToGlobal(position))

    def delete_selected_item(self):
        """선택된 품목 삭제"""
        row = self.item_table.currentRow()
        if row >= 0:
            self.items.pop(row)
            self.item_table.removeRow(row)
            self.update_total_amount()

    def update_total_amount(self):
        """총 금액 업데이트"""
        total = sum(item['qty'] * (item['unit_price_cents'] // 100) for item in self.items)
        self.lbl_total_amount.setText(f"{total:,}")

    def load_order_data(self):
        """기존 주문 데이터 로드 (수정 모드)"""
        from ..db import get_order_with_items

        order = get_order_with_items(self.order_id)
        if not order:
            return

        header = order['header']
        # header: (id, order_no, customer_id, recv_dt, order_dt, req_due, final_due, oa_sent, invoice_done, status)

        self.edt_order_no.setText(header[1] or "")
        self.edt_recv_dt.setText(header[3] or "")
        self.edt_order_dt.setText(header[4] or "")
        self.edt_req_due.setText(header[5] or "")

        # 품목 로드
        for item_data in order['items']:
            # item_data: (id, item_code, rev, product_name, qty, unit_price_cents, currency)
            item = {
                'item_code': item_data[1],
                'rev': item_data[2],
                'product_name': item_data[3],
                'qty': item_data[4],
                'unit_price_cents': item_data[5],
                'currency': item_data[6]
            }
            self.items.append(item)

            row = self.item_table.rowCount()
            self.item_table.insertRow(row)

            unit_price = item_data[5] // 100
            self.item_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item_data[1] or ""))
            self.item_table.setItem(row, 1, QtWidgets.QTableWidgetItem(item_data[2] or ""))
            self.item_table.setItem(row, 2, QtWidgets.QTableWidgetItem(item_data[3]))
            self.item_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{item_data[4]:,}"))
            self.item_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{unit_price:,}"))
            self.item_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{item_data[4] * unit_price:,}"))

        self.update_total_amount()

    def accept_dialog(self):
        """주문 저장"""
        order_no = self.edt_order_no.text().strip()

        if not order_no:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "주문번호는 필수입니다.")
            return

        if not self.items:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "최소 1개 이상의 품목을 추가해야 합니다.")
            return

        recv_dt_raw = self.edt_recv_dt.text().strip()
        recv_dt = parse_due_text(recv_dt_raw) if recv_dt_raw else None

        order_dt_raw = self.edt_order_dt.text().strip()
        order_dt = parse_due_text(order_dt_raw) if order_dt_raw else None

        req_due_raw = self.edt_req_due.text().strip()
        req_due = parse_due_text(req_due_raw) if req_due_raw else None

        if recv_dt_raw and not recv_dt:
            QtWidgets.QMessageBox.warning(self, "접수일", "접수일 형식이 올바르지 않습니다.")
            return

        if order_dt_raw and not order_dt:
            QtWidgets.QMessageBox.warning(self, "주문일", "주문일 형식이 올바르지 않습니다.")
            return

        if req_due_raw and not req_due:
            QtWidgets.QMessageBox.warning(self, "납기일", "납기일 형식이 올바르지 않습니다.")
            return

        try:
            from ..db import create_order_with_items, update_order_with_items, get_conn, add_or_update_product_master

            # ✨ 제품 마스터에 자동 추가/업데이트 (체크박스 확인)
            if self.cb_update_master.isChecked():
                for item in self.items:
                    if item.get('item_code'):  # 품목코드가 있는 경우만
                        try:
                            add_or_update_product_master(
                                item_code=item['item_code'],
                                rev=item.get('rev'),
                                product_name=item['product_name'],
                                unit_price_jpy=item['unit_price_cents'],  # 이미 cents 단위
                                purchase_price_krw=None,  # 주문에서는 판매단가만 업데이트
                                description=None
                            )
                        except Exception as e:
                            print(f"제품 마스터 업데이트 중 오류 (무시): {e}")

            order_data = {
                'order_no': order_no,
                'recv_dt': recv_dt,
                'order_dt': order_dt,
                'req_due': req_due,
                'final_due': req_due,
                'oa_sent': 0,
                'invoice_done': 0
            }

            if self.is_edit:
                update_order_with_items(self.order_id, order_data, self.items)
                QtWidgets.QMessageBox.information(self, "완료", "주문이 수정되었습니다.")
            else:
                # 주문번호 중복 체크
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM orders WHERE order_no=?", (order_no,))
                if cur.fetchone():
                    reply = QtWidgets.QMessageBox.question(
                        self, "주문번호 중복",
                        f"주문번호 '{order_no}'가 이미 존재합니다.\n계속 진행하시겠습니까?",
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                        QtWidgets.QMessageBox.No
                    )
                    if reply != QtWidgets.QMessageBox.Yes:
                        conn.close()
                        return
                conn.close()

                create_order_with_items(order_data, self.items)
                QtWidgets.QMessageBox.information(self, "완료",
                                                  f"새 주문이 추가되었습니다.\n품목 수: {len(self.items)}개\n\n"
                                                  f"※ 제품 마스터에도 자동 등록되었습니다.")

            self.accept()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"주문 저장 중 오류가 발생했습니다:\n{str(e)}")
            import traceback
            traceback.print_exc()