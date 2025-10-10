# app/ui/purchase_widget.py
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QHeaderView
from PySide6.QtCore import Qt
from datetime import datetime
from ..db import (get_conn, get_available_orders, get_linked_orders,
                  get_orders_for_purchase_display, update_product_master_purchase_price,
                  query_all, create_purchase_with_items, get_purchase_with_items)
from .autocomplete_widgets import AutoCompleteLineEdit
from .money_lineedit import MoneyLineEdit


def format_money(val: float | None) -> str:
    if val is None:
        return ""
    try:
        return f"{val:,.0f}"
    except Exception:
        return str(val)


def parse_due_text(text: str) -> str | None:
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


def get_available_orders_for_purchase():
    """발주와 연결할 수 있는 주문 목록 (OA 발송됨, 청구 미완료)"""
    sql = """
        SELECT o.id, o.order_no, GROUP_CONCAT(oi.product_name, ' | ') as desc,
               SUM(oi.qty) as qty, COALESCE(o.final_due, o.req_due) as due_date
        FROM orders o
        LEFT JOIN order_items oi ON o.id = oi.order_id
        WHERE o.order_no IS NOT NULL 
        AND COALESCE(o.oa_sent, 0) = 1
        AND COALESCE(o.invoice_done, 0) = 0
        GROUP BY o.id
        ORDER BY o.order_no
    """
    return query_all(sql)

def is_purchase_completed(purchase_id: int) -> bool:
    """발주가 완료되었는지 확인"""
    conn = get_conn()
    cur = conn.cursor()

    # ✅ 먼저 완료 상태 체크
    cur.execute("SELECT status FROM purchases WHERE id = ?", (purchase_id,))
    result = cur.fetchone()
    if result and result[0] == '완료':
        conn.close()
        return True

    # 연결된 주문들이 모두 청구 완료되었는지 확인
    cur.execute("""
        SELECT COUNT(*) as total_orders,
               SUM(CASE WHEN COALESCE(o.invoice_done, 0) = 1 THEN 1 ELSE 0 END) as completed_orders
        FROM purchase_order_links pol
        JOIN orders o ON pol.order_id = o.id
        WHERE pol.purchase_id = ?
    """, (purchase_id,))

    result = cur.fetchone()
    # 연결된 주문이 하나도 없으면 이 조건은 무시
    if result and result[0] > 0:
        total_orders, completed_orders = result
        if completed_orders != total_orders:
            conn.close()
            return False

    # ✅ 수정된 SQL 쿼리: 발주량 = 생산량 = 납품량 확인
    cur.execute("""
        SELECT
            SUM(pi.qty) as order_qty,
            (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id) as produced_qty,
            (SELECT COALESCE(SUM(di.qty), 0)
             FROM delivery_items di
             JOIN delivery_purchase_links dpl ON di.delivery_id = dpl.delivery_id
             WHERE dpl.purchase_id = p.id) as delivered_qty
        FROM purchases p
        LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
        WHERE p.id = ?
        GROUP BY p.id
    """, (purchase_id,))

    result = cur.fetchone()
    conn.close()

    if not result:
        return False

    order_qty, produced_qty, delivered_qty = result
    order_qty = order_qty or 0
    produced_qty = produced_qty or 0
    delivered_qty = delivered_qty or 0

    # 발주량이 있고, 모든 수량이 일치할 때만 완료로 간주
    return order_qty > 0 and order_qty == produced_qty == delivered_qty


class PurchaseWidget(QtWidgets.QWidget):
    """✅ 발주 목록을 표시하는 위젯"""
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.show_all = False
        self.setup_ui()
        self.load_purchase_list()

    def setup_ui(self):
        """✅ 발주 목록 UI 구성"""
        layout = QtWidgets.QVBoxLayout(self)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("발주 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        # 필터 버튼
        self.btn_show_all = QtWidgets.QPushButton("미완료만")
        self.btn_show_all.setCheckable(True)
        self.btn_show_all.setChecked(False)
        self.btn_show_all.toggled.connect(self.toggle_show_all)

        self.btn_new_purchase = QtWidgets.QPushButton("새 발주")
        self.btn_refresh_purchase = QtWidgets.QPushButton("새로고침")

        self.btn_new_purchase.clicked.connect(self.add_purchase)
        self.btn_refresh_purchase.clicked.connect(self.load_purchase_list)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.btn_new_purchase)
        title_layout.addWidget(self.btn_refresh_purchase)
        title_layout.addWidget(self.btn_show_all)

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["발주일", "발주번호", "품목수", "발주내용", "발주금액(원)", "연결주문", "완료여부"]
        )
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.setShowGrid(True)

        self.table.itemDoubleClicked.connect(self.edit_purchase)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 300)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 150)
        self.table.setColumnWidth(6, 80)  # 완료여부 컬럼

        if self.settings:
            self.restore_column_widths()

        header.sectionResized.connect(self.save_column_widths)

        layout.addLayout(title_layout)
        layout.addWidget(self.table)

        self.purchase_data = []

    def toggle_show_all(self, checked: bool):
        self.show_all = checked
        self.btn_show_all.setText("전체보기" if checked else "미완료만")
        self.load_purchase_list()

    def save_column_widths(self):
        if not self.settings:
            return
        widths = []
        for col in range(self.table.columnCount()):
            widths.append(self.table.columnWidth(col))
        self.settings.setValue("purchase_table/column_widths", widths)

    def restore_column_widths(self):
        if not self.settings:
            return
        widths = self.settings.value("purchase_table/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < self.table.columnCount():
                    self.table.setColumnWidth(col, int(width))

    def show_context_menu(self, position):
        if self.table.itemAt(position) is None:
            return

        menu = QtWidgets.QMenu(self)

        edit_action = menu.addAction("수정")
        edit_action.triggered.connect(self.edit_purchase)

        delete_action = menu.addAction("삭제")
        delete_action.triggered.connect(self.delete_purchase)

        menu.exec_(self.table.mapToGlobal(position))

    def update_completed_status(self, purchase_id: int, state: int):
        """✅ 완료여부 상태 업데이트"""
        is_completed = (state == QtCore.Qt.CheckState.Checked.value)
        new_status = "완료" if is_completed else "발주"

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE purchases 
                SET status = ?, updated_at = datetime('now','localtime') 
                WHERE id = ?
            """, (new_status, purchase_id))
            conn.commit()

            # 미완료만 보기 모드에서 완료로 변경하면 목록에서 제거
            if not self.show_all and is_completed:
                self.load_purchase_list()
                QtWidgets.QMessageBox.information(
                    self, "알림",
                    f"발주가 '{new_status}' 상태로 변경되었습니다.\n(미완료 목록에서 제거됨)"
                )

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"상태 업데이트 중 오류:\n{str(e)}")
        finally:
            conn.close()

    # app/ui/purchase_widget.py의 load_purchase_list() 메서드 수정

    def load_purchase_list(self):
        """발주 목록 로드"""
        try:
            conn = get_conn()
            cur = conn.cursor()

            sql = """
                SELECT 
                    p.id,
                    p.purchase_dt,
                    p.purchase_no,
                    p.status,
                    COUNT(pi.id) as item_count,
                    GROUP_CONCAT(pi.product_name, ' | ') as product_names,
                    CASE 
                        WHEN p.actual_amount > 0 THEN p.actual_amount / 100.0
                        ELSE SUM(pi.qty * pi.unit_price_cents) / 100.0
                    END as amount_krw
                FROM purchases p
                LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
                GROUP BY p.id
                ORDER BY p.purchase_dt DESC, p.purchase_no
            """

            cur.execute(sql)
            rows = cur.fetchall()

            if not self.show_all:
                filtered_rows = []
                for row in rows:
                    purchase_id = row[0]
                    # ✅ 완료 상태도 제외
                    if row[3] != '완료' and not is_purchase_completed(purchase_id):
                        filtered_rows.append(row)
                rows = filtered_rows

            self.purchase_data = rows
            self.table.setRowCount(len(rows))
            self.table.setSortingEnabled(False)

            for r, row in enumerate(rows):
                (purchase_id, purchase_dt, purchase_no, status, item_count,
                 product_names, amount_krw) = row

                item_0 = QtWidgets.QTableWidgetItem("" if purchase_dt is None else str(purchase_dt))
                item_0.setData(Qt.UserRole, purchase_id)
                self.table.setItem(r, 0, item_0)

                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(purchase_no or "")))
                self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(f"{item_count}개"))

                if product_names:
                    display_names = product_names if len(product_names) < 80 else product_names[:77] + "..."
                    self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(display_names))
                else:
                    self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(""))

                self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(format_money(amount_krw)))

                order_nos = get_orders_for_purchase_display(purchase_id)
                self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(order_nos or ""))

                # ✅ 완료여부 체크박스 추가 (자동 완료 판단 포함)
                completed_checkbox = QtWidgets.QCheckBox()

                # ✅ status가 '완료'이거나 자동으로 완료된 경우 체크
                is_manually_completed = (status == '완료')
                is_auto_completed = is_purchase_completed(purchase_id)
                completed_checkbox.setChecked(is_manually_completed or is_auto_completed)

                completed_checkbox.setStyleSheet("QCheckBox { margin-left: 20px; }")
                completed_checkbox.stateChanged.connect(
                    lambda state, pid=purchase_id: self.update_completed_status(pid, state)
                )

                checkbox_widget = QtWidgets.QWidget()
                checkbox_layout = QtWidgets.QHBoxLayout(checkbox_widget)
                checkbox_layout.addWidget(completed_checkbox)
                checkbox_layout.setAlignment(Qt.AlignCenter)
                checkbox_layout.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(r, 6, checkbox_widget)

                # ✅ 완료된 항목은 회색으로 표시
                if is_manually_completed or is_auto_completed:
                    from PySide6.QtGui import QBrush, QColor
                    for col in range(6):  # 0~5번 컬럼 (체크박스는 제외)
                        if self.table.item(r, col):
                            self.table.item(r, col).setForeground(QBrush(QColor("#888888")))

            self.table.setSortingEnabled(True)
            for i in range(self.table.rowCount()):
                self.table.setRowHeight(i, 25)

            conn.close()

        except Exception as e:
            print(f"발주 목록 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.purchase_data = []
            self.table.setRowCount(0)

    def get_selected_purchase(self):
        """선택된 발주 가져오기"""
        current_row = self.table.currentRow()
        if current_row < 0:
            return None

        item = self.table.item(current_row, 0)
        if not item:
            return None

        purchase_id = item.data(Qt.UserRole)
        if not purchase_id:
            return None

        for row in self.purchase_data:
            if row[0] == purchase_id:
                return row

        return None

    def add_purchase(self):
        """새 발주 추가"""
        dialog = PurchaseDialog(self, is_edit=False)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_purchase_list()

    def edit_purchase(self):
        """발주 수정"""
        purchase_data = self.get_selected_purchase()
        if not purchase_data:
            QtWidgets.QMessageBox.information(self, "알림", "수정할 발주를 선택해주세요.")
            return

        purchase_id = purchase_data[0]
        dialog = PurchaseDialog(self, is_edit=True, purchase_id=purchase_id)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_purchase_list()

    def delete_purchase(self):
        """발주 삭제"""
        purchase_data = self.get_selected_purchase()
        if not purchase_data:
            QtWidgets.QMessageBox.information(self, "알림", "삭제할 발주를 선택해주세요.")
            return

        (purchase_id, purchase_dt, purchase_no, status, item_count,
         product_names, amount_krw) = purchase_data

        reply = QtWidgets.QMessageBox.question(
            self,
            "발주 삭제",
            f"정말로 다음 발주를 삭제하시겠습니까?\n\n"
            f"발주번호: {purchase_no}\n"
            f"품목 수: {item_count}개\n"
            f"금액: {format_money(amount_krw)}원\n"
            f"발주일: {purchase_dt}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM purchases WHERE id=?", (purchase_id,))
            conn.commit()
            conn.close()

            self.load_purchase_list()
            QtWidgets.QMessageBox.information(self, "완료", f"발주 '{purchase_no}'이 삭제되었습니다.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"발주 삭제 중 오류가 발생했습니다:\n{str(e)}")


class PurchaseDialog(QtWidgets.QDialog):
    """✅ 발주 입력 다이얼로그 (여러 품목 지원)"""

    def __init__(self, parent=None, is_edit=False, purchase_id=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.purchase_id = purchase_id
        self.items = []
        self.setup_ui()

        if is_edit and purchase_id:
            self.load_purchase_data()

    def setup_ui(self):
        title = "발주 수정" if self.is_edit else "새 발주 추가"
        self.setWindowTitle(title)
        self.setMinimumWidth(900)
        self.setMinimumHeight(700)

        main_layout = QtWidgets.QVBoxLayout(self)

        # 발주 헤더 정보
        header_group = QtWidgets.QGroupBox("발주 정보")
        header_form = QtWidgets.QFormLayout(header_group)

        self.edt_purchase_dt = QtWidgets.QLineEdit()
        self.edt_purchase_dt.setPlaceholderText("예: 2025-08-27 / 2025/8/27")

        self.edt_purchase_no = QtWidgets.QLineEdit()

        header_form.addRow("발주일", self.edt_purchase_dt)
        header_form.addRow("발주번호*", self.edt_purchase_no)

        # 품목 입력 영역
        item_group = QtWidgets.QGroupBox("품목 정보")
        item_layout = QtWidgets.QVBoxLayout(item_group)

        input_form = QtWidgets.QFormLayout()

        self.edt_item_code = AutoCompleteLineEdit()
        self.edt_item_code.setPlaceholderText("품목코드 입력 또는 검색")
        self.edt_item_code.product_selected.connect(self.on_product_selected)

        self.edt_rev = QtWidgets.QLineEdit()

        self.edt_purchase_desc = QtWidgets.QLineEdit()
        self.edt_purchase_desc.setMinimumWidth(400)

        self.sp_qty = QtWidgets.QSpinBox()
        self.sp_qty.setRange(1, 1_000_000)
        self.sp_qty.setValue(1)
        self.sp_qty.setGroupSeparatorShown(True)

        self.edt_unit_price = MoneyLineEdit(max_value=1_000_000_000)
        self.edt_unit_price.setPlaceholderText("예: 482040")
        self.edt_unit_price.setMinimumWidth(200)

        self.cb_update_master = QtWidgets.QCheckBox("제품 마스터에 발주단가 업데이트")
        self.cb_update_master.setChecked(True)

        btn_add_item = QtWidgets.QPushButton("품목 추가")
        btn_add_item.clicked.connect(self.add_item)

        input_form.addRow("품목코드", self.edt_item_code)
        input_form.addRow("Rev", self.edt_rev)
        input_form.addRow("발주내용*", self.edt_purchase_desc)
        input_form.addRow("수량", self.sp_qty)
        input_form.addRow("단가(원)", self.edt_unit_price)
        input_form.addRow("", self.cb_update_master)
        input_form.addRow("", btn_add_item)

        item_layout.addLayout(input_form)

        # 품목 리스트 테이블
        self.item_table = QtWidgets.QTableWidget(0, 6)
        self.item_table.setHorizontalHeaderLabels(
            ["품목코드", "Rev", "발주내용", "수량", "단가(원)", "금액(원)"]
        )
        self.item_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.item_table.setMaximumHeight(200)
        self.item_table.itemDoubleClicked.connect(self.edit_item)
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
        self.item_table.setColumnWidth(5, 120)

        item_layout.addWidget(self.item_table)

        # ✅ 이 금액 표시 및 직접 입력
        total_layout = QtWidgets.QHBoxLayout()
        total_layout.addStretch()

        total_layout.addWidget(QtWidgets.QLabel("이 발주금액:"))

        # ✅ 계산된 금액 표시 (읽기 전용)
        self.lbl_calculated_amount = QtWidgets.QLabel("0")
        self.lbl_calculated_amount.setStyleSheet("font-weight: bold; font-size: 14px; color: #666;")
        total_layout.addWidget(self.lbl_calculated_amount)
        total_layout.addWidget(QtWidgets.QLabel("원"))

        total_layout.addSpacing(20)

        # ✅ 실제 발주금액 입력
        total_layout.addWidget(QtWidgets.QLabel("→ 실제 발주금액:"))
        self.edt_total_amount = MoneyLineEdit(max_value=10_000_000_000)
        self.edt_total_amount.setPlaceholderText("직접 입력 (선택)")
        self.edt_total_amount.setMinimumWidth(150)
        self.edt_total_amount.setStyleSheet("background-color: #fffacd;")  # 노란 배경
        total_layout.addWidget(self.edt_total_amount)
        total_layout.addWidget(QtWidgets.QLabel("원"))

        item_layout.addLayout(total_layout)

        # ✅ 안내 메시지
        note_label = QtWidgets.QLabel(
            "※ 실제 발주금액을 입력하지 않으면 품목별 단가 × 수량의 합계가 사용됩니다."
        )
        note_label.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        note_label.setAlignment(Qt.AlignRight)
        item_layout.addWidget(note_label)

        # 연결할 주문
        order_group = QtWidgets.QGroupBox("연결할 주문번호 (OA 발송됨, 청구 미완료)")
        order_layout = QtWidgets.QVBoxLayout(order_group)

        self.order_list = QtWidgets.QListWidget()
        self.order_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.order_list.setMaximumHeight(120)
        self.order_list.setStyleSheet("""
            QListWidget::item:selected {
                background-color: #0078d4;
                color: white;
                border: 1px solid #005a9e;
            }
            QListWidget::item:hover {
                background-color: #e6f3ff;
                border: 1px solid #0078d4;
            }
        """)

        self.load_available_orders()
        order_layout.addWidget(self.order_list)

        # 버튼
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept_dialog)
        btns.rejected.connect(self.reject)

        main_layout.addWidget(header_group)
        main_layout.addWidget(item_group)
        main_layout.addWidget(order_group)
        main_layout.addWidget(btns)

    def on_product_selected(self, product_info):
        """제품 선택 시 정보 자동 입력"""
        self.edt_rev.setText(product_info['rev'] or "")
        self.edt_purchase_desc.setText(product_info['product_name'])

        if product_info['purchase_price_krw']:
            self.edt_unit_price.set_value(product_info['purchase_price_krw'] // 100)

    def add_item(self):
        """품목 추가"""
        purchase_desc = self.edt_purchase_desc.text().strip()

        if not purchase_desc:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "발주내용은 필수입니다.")
            return

        item_code = self.edt_item_code.text().strip() or None
        rev = self.edt_rev.text().strip() or None
        qty = self.sp_qty.value()
        unit_price = self.edt_unit_price.get_value()

        item = {
            'item_code': item_code,
            'rev': rev,
            'product_name': purchase_desc,
            'qty': qty,
            'unit_price_cents': unit_price * 100,
            'currency': 'KRW'
        }
        self.items.append(item)

        row = self.item_table.rowCount()
        self.item_table.insertRow(row)

        self.item_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item_code or ""))
        self.item_table.setItem(row, 1, QtWidgets.QTableWidgetItem(rev or ""))
        self.item_table.setItem(row, 2, QtWidgets.QTableWidgetItem(purchase_desc))
        self.item_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{qty:,}"))
        self.item_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{unit_price:,}"))
        self.item_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{qty * unit_price:,}"))

        self.edt_item_code.clear()
        self.edt_rev.clear()
        self.edt_purchase_desc.clear()
        self.sp_qty.setValue(1)
        self.edt_unit_price.set_value(0)

        self.update_total_amount()

    def edit_item(self):
        """선택된 품목 수정"""
        row = self.item_table.currentRow()
        if row < 0 or row >= len(self.items):
            return

        # 현재 품목 데이터 가져오기
        current_item = self.items[row]

        # 수정 다이얼로그 생성
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("품목 수정")
        dialog.setMinimumWidth(600)

        form = QtWidgets.QFormLayout(dialog)

        # 품목코드
        edt_item_code = AutoCompleteLineEdit()
        edt_item_code.setText(current_item.get('item_code') or "")

        # Rev
        edt_rev = QtWidgets.QLineEdit()
        edt_rev.setText(current_item.get('rev') or "")

        # 발주내용
        edt_purchase_desc = QtWidgets.QLineEdit()
        edt_purchase_desc.setText(current_item['product_name'])
        edt_purchase_desc.setMinimumWidth(400)

        # 수량
        sp_qty = QtWidgets.QSpinBox()
        sp_qty.setRange(1, 1_000_000)
        sp_qty.setValue(current_item['qty'])
        sp_qty.setGroupSeparatorShown(True)

        # 단가
        edt_unit_price = MoneyLineEdit(max_value=1_000_000_000)
        edt_unit_price.set_value(current_item['unit_price_cents'] // 100)
        edt_unit_price.setMinimumWidth(200)

        form.addRow("품목코드", edt_item_code)
        form.addRow("Rev", edt_rev)
        form.addRow("발주내용*", edt_purchase_desc)
        form.addRow("수량", sp_qty)
        form.addRow("단가(원)", edt_unit_price)

        # 버튼
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        form.addRow(btns)

        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return

        # 수정된 데이터 저장
        purchase_desc = edt_purchase_desc.text().strip()
        if not purchase_desc:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "발주내용은 필수입니다.")
            return

        item_code = edt_item_code.text().strip() or None
        rev = edt_rev.text().strip() or None
        qty = sp_qty.value()
        unit_price = edt_unit_price.get_value()

        # items 리스트 업데이트
        self.items[row] = {
            'item_code': item_code,
            'rev': rev,
            'product_name': purchase_desc,
            'qty': qty,
            'unit_price_cents': unit_price * 100,
            'currency': 'KRW'
        }

        # 테이블 업데이트
        self.item_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item_code or ""))
        self.item_table.setItem(row, 1, QtWidgets.QTableWidgetItem(rev or ""))
        self.item_table.setItem(row, 2, QtWidgets.QTableWidgetItem(purchase_desc))
        self.item_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{qty:,}"))
        self.item_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{unit_price:,}"))
        self.item_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{qty * unit_price:,}"))

        self.update_total_amount()

    def show_item_context_menu(self, position):
        """품목 우클릭 메뉴"""
        if self.item_table.itemAt(position) is None:
            return

        menu = QtWidgets.QMenu(self)
        edit_action = menu.addAction("수정")
        edit_action.triggered.connect(self.edit_item)
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
        """이 금액 업데이트 (계산된 금액 표시)"""
        total = sum(item['qty'] * (item['unit_price_cents'] // 100) for item in self.items)
        self.lbl_calculated_amount.setText(f"{total:,}")

        # ✅ 실제 발주금액이 비어있으면 계산된 금액으로 자동 설정
        if self.edt_total_amount.get_value() == 0:
            self.edt_total_amount.set_value(total)

    def load_available_orders(self):
        """연결 가능한 주문 목록 로드"""
        orders = get_available_orders_for_purchase()
        for order_id, order_no, order_desc, qty, req_due in orders:
            display_text = f"{order_no} - {order_desc} (수량: {qty}, 납기: {req_due})"
            item = QtWidgets.QListWidgetItem(display_text)
            item.setData(Qt.UserRole, order_id)
            self.order_list.addItem(item)

    def load_purchase_data(self):
        """기존 발주 데이터 로드"""
        purchase = get_purchase_with_items(self.purchase_id)
        if not purchase:
            return

        header = purchase['header']
        self.edt_purchase_no.setText(header[1] or "")
        self.edt_purchase_dt.setText(header[2] or "")

        for item_data in purchase['items']:
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

        linked_orders = get_linked_orders(self.purchase_id)
        linked_order_ids = [order[0] for order in linked_orders]

        for i in range(self.order_list.count()):
            item = self.order_list.item(i)
            order_id = item.data(Qt.UserRole)
            if order_id in linked_order_ids:
                item.setSelected(True)

        self.update_total_amount()

        # ✅ 기존 발주의 실제 금액 로드
        if header[4] and header[4] > 0:  # actual_amount가 있으면
            self.edt_total_amount.set_value(header[4] // 100)  # 센트 → 원
        else:
            # actual_amount가 없으면 계산된 금액 사용
            total = sum(item['qty'] * (item['unit_price_cents'] // 100) for item in self.items)
            self.edt_total_amount.set_value(total)

    def accept_dialog(self):
        """발주 저장"""
        purchase_no = self.edt_purchase_no.text().strip()

        if not purchase_no:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "발주번호는 필수입니다.")
            return

        if not self.items:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "최소 1개 이상의 품목을 추가해야 합니다.")
            return

        purchase_dt_raw = self.edt_purchase_dt.text().strip()
        purchase_dt = parse_due_text(purchase_dt_raw) if purchase_dt_raw else None

        if purchase_dt_raw and not purchase_dt:
            QtWidgets.QMessageBox.warning(self, "발주일", "발주일 형식이 올바르지 않습니다.")
            return

        selected_order_ids = []
        for i in range(self.order_list.count()):
            item = self.order_list.item(i)
            if item.isSelected():
                selected_order_ids.append(item.data(Qt.UserRole))

        # ✅ 실제 발주금액 가져오기
        actual_total = self.edt_total_amount.get_value()
        calculated_total = sum(item['qty'] * (item['unit_price_cents'] // 100) for item in self.items)

        # ✅ 금액 차이가 있으면 확인
        if actual_total != calculated_total and actual_total > 0:
            reply = QtWidgets.QMessageBox.question(
                self,
                "발주금액 확인",
                f"품목 금액 합계: {calculated_total:,}원\n"
                f"실제 발주금액: {actual_total:,}원\n"
                f"차이: {actual_total - calculated_total:,}원\n\n"
                f"실제 발주금액({actual_total:,}원)으로 저장하시겠습니까?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return

        try:
            if self.cb_update_master.isChecked():
                for item in self.items:
                    if item['item_code']:
                        update_product_master_purchase_price(
                            item_code=item['item_code'],
                            rev=item.get('rev'),
                            product_name=item['product_name'],
                            purchase_price_krw=item['unit_price_cents']
                        )

            # ✅ 수정 (라인 836 근처)
            purchase_data = {
                'purchase_no': purchase_no,
                'purchase_dt': purchase_dt,
                'status': '발주',
                'actual_amount': (actual_total if actual_total > 0 else calculated_total) * 100  # ✅ 센트 단위로!
            }

            if self.is_edit:
                # ✅ 발주 수정 구현
                conn = get_conn()
                try:
                    cur = conn.cursor()

                    # 헤더 업데이트
                    # ✅ 수정된 코드
                    cur.execute("""
                        UPDATE purchases SET
                            purchase_no = ?,
                            purchase_dt = ?,
                            actual_amount = ?,
                            status = ?,
                            updated_at = datetime('now','localtime')
                        WHERE id = ?
                    """, (purchase_no, purchase_dt,
                          (actual_total if actual_total > 0 else calculated_total) * 100,  # ✅ 센트 단위로
                          '발주', self.purchase_id))

                    # 기존 품목 삭제 후 재등록
                    cur.execute("DELETE FROM purchase_items WHERE purchase_id = ?", (self.purchase_id,))

                    for item in self.items:
                        cur.execute("""
                            INSERT INTO purchase_items (
                                purchase_id, item_code, rev, product_name,
                                qty, unit_price_cents, currency
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            self.purchase_id,
                            item.get('item_code'),
                            item.get('rev'),
                            item['product_name'],
                            item['qty'],
                            item['unit_price_cents'],
                            item.get('currency', 'KRW')
                        ))

                    # 기존 주문 연결 삭제
                    cur.execute("DELETE FROM purchase_order_links WHERE purchase_id = ?", (self.purchase_id,))

                    # 새로운 주문 연결 추가
                    for order_id in selected_order_ids:
                        cur.execute("""
                            INSERT INTO purchase_order_links (purchase_id, order_id)
                            VALUES (?, ?)
                        """, (self.purchase_id, order_id))

                    conn.commit()

                    QtWidgets.QMessageBox.information(
                        self, "완료",
                        f"발주 '{purchase_no}'이 수정되었습니다.\n"
                        f"품목 수: {len(self.items)}개\n"
                        f"발주금액: {actual_total if actual_total > 0 else calculated_total:,}원"
                    )

                except Exception as e:
                    conn.rollback()
                    QtWidgets.QMessageBox.critical(
                        self, "오류",
                        f"발주 수정 중 오류가 발생했습니다:\n{str(e)}"
                    )
                    import traceback
                    traceback.print_exc()
                    return
                finally:
                    conn.close()

            else:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM purchases WHERE purchase_no=?", (purchase_no,))
                if cur.fetchone():
                    reply = QtWidgets.QMessageBox.question(
                        self, "발주번호 중복",
                        f"발주번호 '{purchase_no}'가 이미 존재합니다.\n계속 진행하시겠습니까?",
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                        QtWidgets.QMessageBox.No
                    )
                    if reply != QtWidgets.QMessageBox.Yes:
                        conn.close()
                        return
                conn.close()

                create_purchase_with_items(purchase_data, self.items, selected_order_ids)

                # ✅ 저장 완료 메시지에 실제 금액 표시
                QtWidgets.QMessageBox.information(
                    self, "완료",
                    f"새 발주가 추가되었습니다.\n"
                    f"품목 수: {len(self.items)}개\n"
                    f"발주금액: {actual_total if actual_total > 0 else calculated_total:,}원"
                )

            self.accept()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"발주 저장 중 오류가 발생했습니다:\n{str(e)}")
            import traceback
            traceback.print_exc()