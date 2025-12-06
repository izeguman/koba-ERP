# app/ui/delivery_widget.py (전체 교체)
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import (QHeaderView, QTableWidgetItem, QMessageBox, QListWidgetItem,
                               QDialog, QVBoxLayout, QListWidget, QTableWidget,
                               QDialogButtonBox, QAbstractItemView, QTreeWidget, QTreeWidgetItem,
                               QFormLayout, QLineEdit, QCheckBox, QLabel)
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QBrush, QColor, QFont

from datetime import datetime
from collections import defaultdict

from ..db import (
    query_all, get_conn, get_delivery_with_items,
    check_and_update_order_completion, get_linked_purchase_ids_from_orders,
    get_available_purchases, get_next_delivery_number, query_one,
    is_purchase_completed,

    # 납품 처리 관련 함수
    mark_products_as_delivered,
    unmark_products_as_delivered,

    # 수리 이력 업데이트 관련 함수 (revert 추가됨)
    update_repair_redelivery_status,
    update_repair_status_on_delivery,
    revert_repair_status_on_delivery_delete
)
from .utils import parse_datetime_text, apply_table_resize_policy
from ..db import is_purchase_completed, mark_products_as_delivered, unmark_products_as_delivered
from .autocomplete_widgets import AutoCompleteLineEdit


def get_available_orders_for_purchase(delivery_id_to_include=None):
    """
    발주와 연결할 수 있는 주문 목록을 반환합니다.
    1. (delivery_id_to_include=None, '새 납품'): OA 발송됨, 청구 미완료된 모든 주문
    2. (delivery_id_to_include=ID, '납품 수정'): *모든* 주문
    """
    sql = """
        SELECT
            o.id,
            o.order_no,
            GROUP_CONCAT(oi.product_name, ' | ') as order_desc,
            SUM(oi.qty) as total_ordered_qty,
            COALESCE(
                (SELECT MAX(s.due_date) 
                 FROM order_shipments s 
                 JOIN order_items oi_s ON s.order_item_id = oi_s.id 
                 WHERE oi_s.order_id = o.id), 
                o.final_due, 
                o.req_due
            ) as due_date
        FROM orders o
        LEFT JOIN order_items oi ON o.id = oi.order_id
    """

    params = []
    where_conditions = []

    # 기본 조건 (항상 적용)
    where_conditions.append("o.order_no IS NOT NULL")

    if delivery_id_to_include is None:
        # '새 납품' (New Delivery) 모드: 완료되지 않은 (invoice_done=0) + OA 발송된 건만
        where_conditions.append("COALESCE(o.oa_sent, 0) = 1")
        where_conditions.append("COALESCE(o.invoice_done, 0) = 0")
    else:
        # '납품 수정' (Edit Delivery) 모드: 모든 주문 표시 (필터 없음)
        pass

    sql += f" WHERE {' AND '.join(where_conditions)}"
    sql += " GROUP BY o.id ORDER BY due_date ASC, o.order_no ASC"

    return query_all(sql, tuple(params))


class DeliveryWidget(QtWidgets.QWidget):
    """납품 목록을 표시하는 위젯"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.delivery_data = []
        self.active_delivery_dialogs = []  # 모달리스 다이얼로그 추적용

        if self.settings:
            self.show_completed = self.settings.value("filters/delivery_show_all", False, type=bool)
        else:
            self.show_completed = False

        self.setup_ui()

        self.current_sort_column = self.settings.value("delivery_table/sort_column", 0, type=int)
        sort_order_val = self.settings.value("delivery_table/sort_order", Qt.DescendingOrder)
        self.current_sort_order = Qt.SortOrder(sort_order_val)
        self.load_delivery_list()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("납품 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        self.btn_show_completed = QtWidgets.QPushButton("미완료만")
        self.btn_show_completed.setCheckable(True)
        self.btn_show_completed.setChecked(self.show_completed)
        self.btn_show_completed.toggled.connect(self.toggle_show_completed)
        btn_new = QtWidgets.QPushButton("새 납품")
        self.btn_refresh = QtWidgets.QPushButton("새로고침")
        btn_new.clicked.connect(self.add_delivery)
        self.btn_refresh.clicked.connect(self.load_delivery_list)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(btn_new)
        title_layout.addWidget(self.btn_refresh)
        title_layout.addWidget(self.btn_show_completed)
        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["발송일시", "인보이스번호", "총수량", "품목수", "제품명", "운송사", "2차포장", "연결 정보", "청구완료"]
        )
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.itemDoubleClicked.connect(self.edit_delivery)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        header = self.table.horizontalHeader()
        for col in range(9):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.table.setColumnWidth(0, 140);
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 70);
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 500);
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 150);
        self.table.setColumnWidth(7, 280)
        self.table.setColumnWidth(8, 80)

        if self.settings:
            self.restore_column_widths()
        header.sectionResized.connect(self.save_column_widths)
        header.sortIndicatorChanged.connect(self.on_sort_indicator_changed)
        header.setSortIndicatorShown(True)

        layout.addLayout(title_layout)
        layout.addWidget(self.table)
        apply_table_resize_policy(self.table)

    def toggle_show_completed(self, checked):
        self.show_completed = checked
        self.btn_show_completed.setText("전체보기" if checked else "미완료만")
        self.load_delivery_list()

    def save_column_widths(self):
        if not self.settings: return
        widths = [self.table.columnWidth(col) for col in range(self.table.columnCount())]
        self.settings.setValue("delivery_main_table/column_widths", widths)

    def restore_column_widths(self):
        if not self.settings: return
        widths = self.settings.value("delivery_main_table/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < self.table.columnCount():
                    self.table.setColumnWidth(col, int(width))

    def refresh_product_list(self):
        try:
            main_window = self.window()
            if hasattr(main_window, 'product_production_widget'):
                main_window.product_production_widget.load_product_list()
        except Exception as e:
            print(f"제품 생산 목록 새로고침 실패: {e}")

    def load_delivery_list(self, delivery_id_to_select=None):
        try:
            comp_fg = self.settings.value("colors/delivery_completed_fg", "#000000")
            comp_bg = self.settings.value("colors/delivery_completed_bg", "#FFE082")
            incomp_fg = self.settings.value("colors/delivery_incomplete_fg", "#000000")
            incomp_bg = self.settings.value("colors/delivery_incomplete_bg", "#FFFFFF")

            # 납품 리스트 조회용 SQL
            sql = """
                SELECT 
                    d.id,
                    d.invoice_no,
                    d.ship_datetime,
                    d.carrier,
                    d.secondary_packaging,

                    -- 주문번호
                    (SELECT GROUP_CONCAT(DISTINCT o2.order_no)
                     FROM delivery_order_links dol2
                     JOIN orders o2 ON dol2.order_id = o2.id
                     WHERE dol2.delivery_id = d.id
                    ) AS order_nos,

                    -- 발주번호
                    (SELECT GROUP_CONCAT(DISTINCT p2.purchase_no)
                     FROM delivery_purchase_links dpl2
                     JOIN purchases p2 ON dpl2.purchase_id = p2.id
                     WHERE dpl2.delivery_id = d.id
                    ) AS purchase_nos,

                    d.invoice_done AS is_completed,

                    -- 총수량
                    (SELECT COALESCE(SUM(qty), 0)
                     FROM delivery_items di
                     WHERE di.delivery_id = d.id
                    ) AS total_qty,

                    -- 품목수
                    (SELECT COUNT(DISTINCT di.product_name)
                     FROM delivery_items di
                     WHERE di.delivery_id = d.id
                    ) AS item_count,

                    -- [수정됨] 제품명: 서브쿼리를 이용해 DISTINCT와 구분자(' | ') 충돌 해결
                    (SELECT GROUP_CONCAT(p_name, ' | ')
                     FROM (
                         SELECT DISTINCT product_name as p_name
                         FROM delivery_items
                         WHERE delivery_id = d.id
                     )
                    ) AS product_names,

                    -- 재고 정보 (변경 없음)
                    (SELECT GROUP_CONCAT(di.serial_no || ' | ' || COALESCE(di.manufacture_code, '') || ' | ' || di.product_name, ', ')
                     FROM delivery_items di
                     WHERE di.delivery_id = d.id AND di.order_id IS NULL
                    ) AS stock_info

                FROM deliveries d
            """

            order_clause = self.get_delivery_order_clause()
            sql += f" ORDER BY {order_clause}"

            self.delivery_data = query_all(sql)

            self.table.setSortingEnabled(False)
            self.table.setRowCount(0)

            for row_data in self.delivery_data:
                (
                    delivery_id,
                    invoice_no,
                    ship_datetime,
                    carrier,
                    secondary_packaging,
                    order_nos,
                    purchase_nos,
                    is_completed,
                    total_qty,
                    item_count,
                    product_names,
                    stock_info,  # ✅ [추가] SQL에서 받아온 재고 정보
                ) = row_data

                if is_completed and not self.show_completed:
                    continue

                row_position = self.table.rowCount()
                self.table.insertRow(row_position)

                item = QTableWidgetItem(ship_datetime or "")
                item.setData(Qt.UserRole, delivery_id)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_position, 0, item)

                item = QTableWidgetItem(invoice_no or "")
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_position, 1, item)

                item = QTableWidgetItem(str(total_qty))
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_position, 2, item)

                item = QTableWidgetItem(f"{item_count}종")
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_position, 3, item)

                if product_names:
                    unique_names = list(dict.fromkeys(product_names.split(" | ")))
                    unique_names_str = " | ".join(unique_names)
                    display_names = (
                        unique_names_str
                        if len(unique_names_str) < 80
                        else unique_names_str[:77] + "..."
                    )
                    item = QTableWidgetItem(display_names)
                else:
                    item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.table.setItem(row_position, 4, item)

                item = QTableWidgetItem(carrier or "")
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.table.setItem(row_position, 5, item)

                item = QTableWidgetItem(secondary_packaging or "")
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.table.setItem(row_position, 6, item)

                connection_info = []
                if order_nos: connection_info.append(f"주문:{order_nos}")
                if purchase_nos: connection_info.append(f"발주:{purchase_nos}")

                # ✅ [수정] 주문/발주 정보가 없는데 재고 정보가 있다면 표시
                if not order_nos and not purchase_nos and stock_info:
                    # 너무 길어질 수 있으니 적당히 자르거나 포맷팅
                    if len(stock_info) > 50:
                        connection_info.append(f"[개별출고] {stock_info[:47]}...")
                    else:
                        connection_info.append(f"[개별출고] {stock_info}")
                elif not order_nos and not purchase_nos:
                    connection_info.append("-")  # 아무 정보도 없는 경우

                item = QTableWidgetItem(" / ".join(connection_info))

                # 툴팁에 전체 정보 표시 (재고 정보가 잘렸을 경우를 대비)
                if stock_info:
                    item.setToolTip(stock_info.replace(", ", "\n"))

                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.table.setItem(row_position, 7, item)

                checkbox = QtWidgets.QCheckBox()
                checkbox.setChecked(bool(is_completed))
                checkbox.setStyleSheet("QCheckBox { margin-left: 20px; }")
                checkbox.stateChanged.connect(
                    lambda state, did=delivery_id: self.update_invoice_status(did, state)
                )

                checkbox_widget = QtWidgets.QWidget()
                checkbox_layout = QtWidgets.QHBoxLayout(checkbox_widget)
                checkbox_layout.addWidget(checkbox)
                checkbox_layout.setAlignment(Qt.AlignCenter)
                checkbox_layout.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(row_position, 8, checkbox_widget)

                fg_color = QColor(comp_fg if is_completed else incomp_fg)
                bg_color = QColor(comp_bg if is_completed else incomp_bg)

                for col in range(self.table.columnCount()):
                    item = self.table.item(row_position, col)
                    if item:
                        item.setForeground(QBrush(fg_color))
                        item.setBackground(QBrush(bg_color))

            with QSignalBlocker(self.table.horizontalHeader()):
                self.table.horizontalHeader().setSortIndicator(
                    self.current_sort_column, self.current_sort_order
                )

            self.table.setSortingEnabled(True)

            for i in range(self.table.rowCount()):
                self.table.setRowHeight(i, 25)

            if delivery_id_to_select:
                found_row = -1
                for r in range(self.table.rowCount()):
                    item = self.table.item(r, 0)
                    if item and item.data(Qt.UserRole) == delivery_id_to_select:
                        found_row = r
                        break
                if found_row != -1:
                    self.table.selectRow(found_row)
                    self.table.scrollToItem(
                        self.table.item(found_row, 0),
                        QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter
                    )

        except Exception as e:
            print(f"납품 목록 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.delivery_data = []
            self.table.setRowCount(0)

    def get_delivery_order_clause(self):
        column_names = ["d.ship_datetime", "d.invoice_no", "total_qty", "item_count", "product_names", "d.carrier",
                        "d.secondary_packaging", "order_nos"]
        if 0 <= self.current_sort_column < len(column_names):
            column = column_names[self.current_sort_column]
            direction = "DESC" if self.current_sort_order == Qt.DescendingOrder else "ASC"
        else:
            column = "d.ship_datetime";
            direction = "DESC"
        return f"{column} {direction}, d.invoice_no {direction}"

    def update_invoice_status(self, delivery_id: int, state: int):
        invoice_done = 1 if state == QtCore.Qt.CheckState.Checked.value else 0
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("UPDATE deliveries SET invoice_done=?, updated_at=datetime('now','localtime') WHERE id=?",
                        (invoice_done, delivery_id))

            cur.execute("SELECT DISTINCT order_id FROM delivery_items WHERE delivery_id = ? AND order_id IS NOT NULL",
                        (delivery_id,))

            linked_order_ids = [row[0] for row in cur.fetchall()]
            for order_id in linked_order_ids:
                check_and_update_order_completion(order_id, conn)
            conn.commit();
            conn.close()
            main_window = self.window()
            if hasattr(main_window, 'refresh_order_purchase_delivery'):
                main_window.refresh_order_purchase_delivery()
                main_window.product_production_widget.load_product_list()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"청구 상태 업데이트 중 오류:\n{str(e)}");
            self.load_delivery_list()

    def on_sort_indicator_changed(self, column_index, order):
        if self.current_sort_column == column_index and self.current_sort_order == order: return
        self.current_sort_column = column_index;
        self.current_sort_order = order
        self.settings.setValue("delivery_table/sort_column", self.current_sort_column)
        self.settings.setValue("delivery_table/sort_order", self.current_sort_order)
        self.load_delivery_list()

    def get_selected_delivery_id(self):
        current_row = self.table.currentRow()
        if current_row < 0: return None
        item = self.table.item(current_row, 0)
        return item.data(Qt.UserRole) if item else None

    def add_delivery(self):
        """새 납품 추가 (모달리스)"""
        dialog = DeliveryDialog(self, settings=self.settings)
        dialog.accepted.connect(self.load_delivery_list)
        dialog.finished.connect(lambda: self.cleanup_delivery_dialog(dialog))
        dialog.show()
        self.active_delivery_dialogs.append(dialog)

    def cleanup_delivery_dialog(self, dialog):
        if dialog in self.active_delivery_dialogs:
            self.active_delivery_dialogs.remove(dialog)

    def edit_delivery(self):
        """납품 수정 (모달리스)"""
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.information(self, "알림", "수정할 납품을 선택해주세요.");
            return
        delivery_id = self.table.item(selected_row, 0).data(Qt.UserRole)

        # 이미 열려있는지 확인
        for dlg in self.active_delivery_dialogs:
            if getattr(dlg, 'delivery_id', None) == delivery_id:
                dlg.raise_()
                dlg.activateWindow()
                return

        dialog = DeliveryDialog(self, is_edit=True, delivery_id=delivery_id, settings=self.settings)
        dialog.accepted.connect(lambda: self.load_delivery_list(delivery_id_to_select=delivery_id))
        dialog.finished.connect(lambda: self.cleanup_delivery_dialog(dialog))
        dialog.show()
        self.active_delivery_dialogs.append(dialog)

    def show_context_menu(self, position):
        if self.table.itemAt(position) is None: return
        menu = QtWidgets.QMenu(self)
        edit_action = menu.addAction("수정");
        edit_action.triggered.connect(self.edit_delivery)
        delete_action = menu.addAction("삭제");
        delete_action.triggered.connect(self.delete_delivery)
        menu.exec_(self.table.mapToGlobal(position))


    def delete_delivery(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.information(self, "알림", "삭제할 납품을 선택해주세요.");
            return
        delivery_id = self.table.item(selected_row, 0).data(Qt.UserRole)
        invoice_no = self.table.item(selected_row, 1).text()

        reply = QMessageBox.question(self, "납품 삭제",
                                     f"정말로 납품 '{invoice_no}'을(를) 삭제하시겠습니까?\n\n"
                                     "※ 연관된 제품의 '재출고' 상태가 '수리완료'로 원복됩니다.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                # ✅ [추가] 삭제 전 수리 상태 원복 (재출고 -> 수리완료)
                revert_repair_status_on_delivery_delete(delivery_id)

                conn = get_conn()
                # 기존 납품 취소 로직
                unmark_products_as_delivered(delivery_id, conn)

                cur = conn.cursor();
                cur.execute("DELETE FROM deliveries WHERE id = ?", (delivery_id,));
                conn.commit();
                conn.close()

                self.load_delivery_list()
                QMessageBox.information(self, "완료", f"납품 '{invoice_no}'이(가) 삭제되었습니다.")

            except Exception as e:
                QMessageBox.critical(self, "오류", f"삭제 중 오류가 발생했습니다:\n{e}")


# [신규] 주문 -> 발주 -> 제품을 선택하는 다이얼로그
class AddProductsFromPurchaseDialog(QDialog):
    def __init__(self, order_id, order_text, delivery_id, parent=None):
        super().__init__(parent)
        self.order_id = order_id
        self.order_text = order_text
        self.delivery_id = delivery_id
        self.selected_products = []

        self.setWindowTitle(f"주문에서 품목 추가: {self.order_text}")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)

        purchase_group = QtWidgets.QGroupBox("1. 연결된 발주 선택")
        purchase_layout = QVBoxLayout(purchase_group)
        self.purchase_list = QListWidget()
        self.purchase_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.purchase_list.itemSelectionChanged.connect(self.on_purchase_selected)
        purchase_layout.addWidget(self.purchase_list)

        product_group = QtWidgets.QGroupBox("2. 납품할 제품 선택 (체크박스로 다중 선택)")
        product_layout = QVBoxLayout(product_group)

        self.chk_select_all = QtWidgets.QCheckBox("전체 선택 / 해제")
        self.chk_select_all.toggled.connect(self.select_all_products)
        product_layout.addWidget(self.chk_select_all)

        self.product_table = QTableWidget(0, 5)
        self.product_table.setHorizontalHeaderLabels(["", "S/N", "품목명", "품목코드", "제조코드"])
        self.product_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.product_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.product_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        self.product_table.setColumnWidth(1, 100)
        self.product_table.setColumnWidth(3, 120)
        self.product_table.setColumnWidth(4, 80)
        product_layout.addWidget(self.product_table)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept_dialog)
        button_box.rejected.connect(self.reject)

        layout.addWidget(purchase_group, 1)
        layout.addWidget(product_group, 2)
        layout.addWidget(button_box)

        self.load_purchases()

    def select_all_products(self, checked):
        """테이블의 모든 제품 체크박스 상태를 변경합니다."""
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self.product_table.rowCount()):
            item = self.product_table.item(row, 0)
            if item:
                item.setCheckState(state)

    def load_purchases(self):
        """
        이 주문에 연결할 수 있는 발주 목록 로드
        1. (Item Match) 이 주문의 품목과 일치하는 *모든* 발주
        2. (Linked) 'purchase_order_links'에 명시적으로 연결된 발주
        3. (Existing) 'delivery_items'에 이미 포함된 발주
        """
        self.purchase_list.clear()
        try:
            order_item_codes = set()
            try:
                rows = query_all("SELECT DISTINCT item_code FROM order_items WHERE order_id = ?", (self.order_id,))
                order_item_codes.update(row[0] for row in rows if row[0])
            except Exception as e:
                print(f"Failed to get item codes: {e}")

            if not order_item_codes:
                self.purchase_list.addItem("이 주문에 품목이 없거나 품목코드가 없습니다.")
                self.purchase_list.setEnabled(False)
                return

            purchase_items_map = {}
            try:
                for p_id, item_code in query_all("SELECT purchase_id, item_code FROM purchase_items", ()):
                    if p_id not in purchase_items_map:
                        purchase_items_map[p_id] = set()
                    purchase_items_map[p_id].add(item_code)
            except Exception as e:
                print(f"Failed to build map: {e}")

            matching_po_ids = set()
            for po_id, item_codes in purchase_items_map.items():
                if order_item_codes.intersection(item_codes):
                    matching_po_ids.add(po_id)

            linked_purchase_ids = get_linked_purchase_ids_from_orders([self.order_id])
            existing_purchase_ids = set()
            if self.delivery_id:
                rows = query_all("""
                    SELECT DISTINCT di.purchase_id
                    FROM delivery_items di
                    WHERE di.delivery_id = ? AND di.order_id = ? AND di.purchase_id IS NOT NULL
                """, (self.delivery_id, self.order_id))
                existing_purchase_ids.update(row[0] for row in rows)

            all_relevant_po_ids = matching_po_ids.union(linked_purchase_ids).union(existing_purchase_ids)

            if not all_relevant_po_ids:
                self.purchase_list.addItem("이 주문의 품목과 일치하는 발주가 없습니다.")
                self.purchase_list.setEnabled(False)
                return

            available_purchases_map = {}
            for (p_id, p_no, p_desc, ordered_qty, p_dt,
                 stock_qty, allocation_margin, produced_qty, first_available_serial) in get_available_purchases():

                if stock_qty <= 0 and produced_qty == 0:
                    stock_str = "미생산"
                else:
                    serial_str = f" (S/N: {first_available_serial}~)" if stock_qty > 0 and first_available_serial else ""
                    stock_str = f"재고: {stock_qty}개{serial_str}"

                available_purchases_map[p_id] = f"({stock_str} / 여유: {allocation_margin}개)"

            placeholders = ', '.join('?' for _ in all_relevant_po_ids)
            all_po_details = query_all(f"""
                SELECT 
                    p.id, 
                    p.purchase_no, 
                    (SELECT GROUP_CONCAT(pi.product_name, ' | ') 
                     FROM purchase_items pi WHERE pi.purchase_id = p.id) as p_desc
                FROM purchases p
                WHERE p.id IN ({placeholders})
            """, tuple(all_relevant_po_ids))

            purchases_to_load = {}

            for p_id, p_no, p_desc in all_po_details:
                stock_info = available_purchases_map.get(p_id)
                tag_parts = []

                if p_id in existing_purchase_ids:
                    tag_parts.append("기존 연결")
                elif p_id in linked_purchase_ids:
                    tag_parts.append("주문 연결")

                if stock_info:
                    tag_parts.append(stock_info)
                else:
                    tag_parts.append("[완료]")

                tag = " / ".join(tag_parts)
                display_text = f"{p_no} - ({tag}) - {p_desc or 'N/A'}"
                purchases_to_load[p_id] = (display_text, p_id)

            sorted_purchases = sorted(purchases_to_load.values(), key=lambda x: x[0], reverse=True)
            for display_text, p_id in sorted_purchases:
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, p_id)
                self.purchase_list.addItem(item)

        except Exception as e:
            print(f"연결된 발주 로드 오류: {e}")
            import traceback
            traceback.print_exc()
            self.purchase_list.addItem("로드 오류")

    def on_purchase_selected(self):
        selected_items = self.purchase_list.selectedItems()
        if not selected_items:
            self.product_table.setRowCount(0)
            return

        self.chk_select_all.setChecked(False)
        purchase_id = selected_items[0].data(Qt.UserRole)
        self.load_products(purchase_id)

    def load_products(self, purchase_id):
        self.product_table.setRowCount(0)
        if not purchase_id: return

        try:
            conn = get_conn()
            cur = conn.cursor()

            sql = """
                SELECT id, part_no, product_name, serial_no, manufacture_code
                FROM products
                WHERE (delivery_id IS NULL OR delivery_id = ?)
                  AND consumed_by_product_id IS NULL
                  AND purchase_id = ?
                ORDER BY serial_no ASC
            """
            current_delivery_id = self.delivery_id if self.delivery_id else -1
            cur.execute(sql, (current_delivery_id, purchase_id))
            products = cur.fetchall()
            conn.close()

            self.product_table.setRowCount(len(products))
            for row, product in enumerate(products):
                product_dict = dict(zip(['id', 'part_no', 'product_name', 'serial_no', 'manufacture_code'], product))

                chk_item = QTableWidgetItem()
                chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chk_item.setCheckState(Qt.Unchecked)
                chk_item.setData(Qt.UserRole, product_dict)
                self.product_table.setItem(row, 0, chk_item)

                self.product_table.setItem(row, 1, QTableWidgetItem(product_dict['serial_no']))
                self.product_table.setItem(row, 2, QTableWidgetItem(product_dict['product_name']))
                self.product_table.setItem(row, 3, QTableWidgetItem(product_dict['part_no']))
                self.product_table.setItem(row, 4, QTableWidgetItem(product_dict['manufacture_code']))

        except Exception as e:
            print(f"제품 로드 중 오류: {e}")

    def accept_dialog(self):
        selected_purchase_items = self.purchase_list.selectedItems()
        if not selected_purchase_items:
            QMessageBox.warning(self, "선택 오류", "발주를 먼저 선택해야 합니다.")
            return

        purchase_id = selected_purchase_items[0].data(Qt.UserRole)
        purchase_text = selected_purchase_items[0].text()

        for row in range(self.product_table.rowCount()):
            chk_item = self.product_table.item(row, 0)
            if chk_item.checkState() == Qt.Checked:
                product_data = chk_item.data(Qt.UserRole)
                product_data['order_id'] = self.order_id
                product_data['purchase_id'] = purchase_id
                product_data['order_text'] = self.order_text
                product_data['purchase_text'] = purchase_text
                product_data['qty'] = 1
                self.selected_products.append(product_data)

        if not self.selected_products:
            QMessageBox.warning(self, "선택 오류", "최소 1개 이상의 제품을 체크해야 합니다.")
            return

        self.accept()


class DeliveryDialog(QDialog):
    def __init__(self, parent=None, is_edit=False, delivery_id=None, repair_info=None, settings=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.delivery_id = delivery_id
        self.repair_info = repair_info
        self.is_repair_delivery = (repair_info is not None)
        self.settings = settings

        self.setup_ui()

        if not self.is_edit and not self.is_repair_delivery:
            use_auto_num = self.settings.value("auto_numbering/enable_delivery_no", False, type=bool)
            if use_auto_num:
                try:
                    today = datetime.now()
                    next_no = get_next_delivery_number(today.year, today.month, today.day)
                    self.edt_invoice_no.setText(next_no)
                    self.edt_invoice_no.setStyleSheet("background-color: #fffacd;")
                except Exception as e:
                    print(f"추천 납품번호 생성 실패: {e}")

        if self.is_edit and self.delivery_id:
            self.load_delivery_data()

        if self.is_repair_delivery:
            QMessageBox.warning(self, "알림", "수리품 재출고 기능은 이 UI에서 아직 지원되지 않습니다.")
            QtCore.QTimer.singleShot(0, self.reject)

        if self.settings:
            geometry = self.settings.value("delivery_dialog/geometry")
            if geometry:
                self.restoreGeometry(geometry)

    def setup_ui(self):
        title = "납품 수정" if self.is_edit else "새 납품 추가"
        self.setWindowTitle(title)
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)

        main_layout = QVBoxLayout(self)

        header_group = QtWidgets.QGroupBox("납품 기본 정보")
        header_form = QtWidgets.QFormLayout(header_group)
        self.edt_invoice_no = QtWidgets.QLineEdit();
        self.edt_invoice_no.setPlaceholderText("인보이스번호 (필수)")
        self.edt_ship_datetime = QtWidgets.QLineEdit();
        self.edt_ship_datetime.setPlaceholderText("예: 2025-08-27 14:30 / 2025-08-27")
        self.edt_carrier = QtWidgets.QLineEdit();
        self.edt_carrier.setPlaceholderText("운송사")

        if not self.is_edit:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(
                    "SELECT carrier FROM deliveries WHERE carrier IS NOT NULL AND carrier != '' ORDER BY id DESC LIMIT 1")
                result = cur.fetchone()
                if result and result[0]:
                    self.edt_carrier.setText(result[0])
                    self.edt_carrier.setStyleSheet("background-color: #fffacd;")
                conn.close()
            except Exception as e:
                print(f"마지막 운송사 조회 오류: {e}")

        self.edt_secondary_packaging = QtWidgets.QLineEdit();
        self.edt_secondary_packaging.setPlaceholderText("2차 포장 정보")
        header_form.addRow("인보이스번호*", self.edt_invoice_no)
        header_form.addRow("발송일시", self.edt_ship_datetime)
        header_form.addRow("운송사", self.edt_carrier)
        header_form.addRow("2차 포장 정보", self.edt_secondary_packaging)

        item_group = QtWidgets.QGroupBox("납품 품목")
        item_layout = QVBoxLayout(item_group)

        self.item_tree = QTreeWidget()
        self.item_tree.setColumnCount(2)
        self.item_tree.setHeaderLabels(["S/N (또는 주문/발주)", "품목코드"])
        self.item_tree.setAlternatingRowColors(True)
        self.item_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.item_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.item_tree.customContextMenuRequested.connect(self.show_tree_context_menu)

        header = self.item_tree.header()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        self.item_tree.setColumnWidth(0, 350)
        self.item_tree.setColumnWidth(1, 120)

        self.restore_column_widths()
        header.sectionResized.connect(self.save_column_widths)

        item_button_layout = QtWidgets.QHBoxLayout()
        self.btn_add_item = QtWidgets.QPushButton("+ 주문에서 품목 추가")
        self.btn_add_item.clicked.connect(self.open_add_order_dialog)

        self.btn_add_stock_item = QtWidgets.QPushButton("+ 재고/수리품 추가")
        self.btn_add_stock_item.clicked.connect(self.open_add_stock_dialog)

        item_button_layout.addWidget(self.btn_add_item)
        item_button_layout.addWidget(self.btn_add_stock_item)
        item_button_layout.addStretch()

        item_layout.addWidget(self.item_tree)
        item_layout.addLayout(item_button_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept_dialog)
        button_box.rejected.connect(self.reject)

        main_layout.addWidget(header_group)
        main_layout.addWidget(item_group, 1)
        main_layout.addWidget(button_box)

    def save_column_widths(self):
        """QTreeWidget의 컬럼 폭을 저장합니다."""
        if not self.settings: return
        header = self.item_tree.header()
        widths = [header.sectionSize(i) for i in range(header.count())]
        self.settings.setValue("delivery_dialog/tree_column_widths", widths)

    def restore_column_widths(self):
        """QTreeWidget의 컬럼 폭을 복원합니다."""
        if not self.settings: return
        widths = self.settings.value("delivery_dialog/tree_column_widths")
        if widths:
            header = self.item_tree.header()
            for i, width in enumerate(widths):
                if i < header.count():
                    header.resizeSection(i, int(width))

    def closeEvent(self, event):
        """창을 닫을 때 현재 지오메트리(크기 및 위치)를 저장합니다."""
        if self.settings:
            self.settings.setValue("delivery_dialog/geometry", self.saveGeometry())
        super().closeEvent(event)

    def show_tree_context_menu(self, position):
        selected_items = self.item_tree.selectedItems()
        if not selected_items:
            return

        menu = QtWidgets.QMenu(self)

        # ✅ [수정] 선택된 아이템이 '주문(order)' 타입인지 확인
        item = selected_items[0]
        data = item.data(0, Qt.UserRole)

        item_level = -1
        if item.parent() is None:
            item_level = 0
        elif item.parent().parent() is None:
            item_level = 1
        else:
            item_level = 2

        # ✅ 타입이 'order'인 경우에만 '발주/제품 추가' 메뉴 표시
        if item_level == 0 and data and data.get('type') == 'order':
            add_action = menu.addAction("이 주문에 발주/제품 추가...")
            add_action.triggered.connect(self.add_products_to_selected_order)

        delete_action = menu.addAction("선택 항목 삭제")
        delete_action.triggered.connect(self.delete_selected_tree_items)

        menu.exec_(self.item_tree.mapToGlobal(position))

    def delete_selected_tree_items(self):
        selected_items = self.item_tree.selectedItems()
        if not selected_items: return

        reply = QMessageBox.question(self, "삭제 확인",
                                     f"{len(selected_items)}개 항목(및 하위 항목)을 삭제하시겠습니까?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.No: return

        root = self.item_tree.invisibleRootItem()
        for item in selected_items:
            (item.parent() or root).removeChild(item)

        self.update_all_counts()

    def open_add_order_dialog(self):
        available_orders = get_available_orders_for_purchase(self.delivery_id if self.is_edit else None)

        if not available_orders:
            QMessageBox.information(self, "알림", "납품 가능한 (OA가 발송된) 주문이 없습니다.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("납품할 주문 선택 (헤더를 클릭하여 정렬)")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout(dialog)

        table_widget = QTableWidget()
        table_widget.setColumnCount(4)
        table_widget.setHorizontalHeaderLabels(["주문번호", "제품명", "수량", "납기일"])

        table_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table_widget.setSortingEnabled(True)
        table_widget.setAlternatingRowColors(True)
        table_widget.verticalHeader().setVisible(False)

        table_widget.setRowCount(len(available_orders))

        for row, (o_id, o_no, o_desc, qty, req_due) in enumerate(available_orders):
            summary_text = f"{o_no} - {o_desc or 'N/A'}"
            item_no = QTableWidgetItem(o_no)
            item_no.setData(Qt.UserRole, {'id': o_id, 'text': summary_text})

            item_desc = QTableWidgetItem(o_desc or "N/A")

            item_qty = QTableWidgetItem()
            item_qty.setData(Qt.DisplayRole, qty or 0)
            item_qty.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            item_due = QTableWidgetItem(req_due or "N/A")
            item_due.setTextAlignment(Qt.AlignCenter)

            table_widget.setItem(row, 0, item_no)
            table_widget.setItem(row, 1, item_desc)
            table_widget.setItem(row, 2, item_qty)
            table_widget.setItem(row, 3, item_due)

        table_widget.setColumnWidth(0, 120)
        table_widget.setColumnWidth(1, 400)
        table_widget.setColumnWidth(2, 80)
        table_widget.setColumnWidth(3, 100)
        table_widget.horizontalHeader().setStretchLastSection(True)
        table_widget.sortByColumn(3, Qt.AscendingOrder)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        layout.addWidget(table_widget)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            selected_rows = set(item.row() for item in table_widget.selectedItems())
            selected_orders = []

            for row in selected_rows:
                item = table_widget.item(row, 0)
                if item:
                    selected_orders.append(item.data(Qt.UserRole))

            for order_data in selected_orders:
                self.add_order_to_tree(order_data['id'], order_data['text'])

    def add_order_to_tree(self, order_id, order_text, expand=True):
        for i in range(self.item_tree.topLevelItemCount()):
            item = self.item_tree.topLevelItem(i)
            data = item.data(0, Qt.UserRole)
            if data and data.get('type') == 'order' and data.get('order_id') == order_id:
                if expand: self.item_tree.expandItem(item)
                return item

        item = QTreeWidgetItem([order_text, ""])
        item.setData(0, Qt.UserRole, {'type': 'order', 'order_id': order_id, 'order_text': order_text})
        font = item.font(0);
        font.setBold(True);
        item.setFont(0, font)
        item.setBackground(0, QBrush(QColor("#e9f5ff")))
        self.item_tree.addTopLevelItem(item)
        if expand: self.item_tree.expandItem(item)
        return item

    def add_purchase_to_tree(self, order_item, purchase_id, purchase_text, expand=True):
        for i in range(order_item.childCount()):
            item = order_item.child(i)
            if item.data(0, Qt.UserRole).get('purchase_id') == purchase_id:
                if expand: self.item_tree.expandItem(item)
                return item

        item = QTreeWidgetItem([f"  └ {purchase_text}", ""])
        item.setData(0, Qt.UserRole, {'type': 'purchase', 'purchase_id': purchase_id, 'purchase_text': purchase_text})
        item.setBackground(0, QBrush(QColor("#f4f4f4")))
        order_item.addChild(item)
        if expand: self.item_tree.expandItem(item)
        return item

    def add_product_to_tree(self, purchase_item, product_data):
        new_item_code = product_data.get('item_code') or product_data.get('part_no')
        new_serial_no = product_data.get('serial_no')
        new_mfg_code = product_data.get('manufacture_code', '')

        for i in range(purchase_item.childCount()):
            item = purchase_item.child(i)
            existing_data = item.data(0, Qt.UserRole)
            if not existing_data: continue

            existing_item_code = existing_data.get('item_code')
            existing_serial_no = existing_data.get('serial_no')
            existing_mfg_code = existing_data.get('manufacture_code', '')

            if (existing_item_code == new_item_code and
                    existing_serial_no == new_serial_no and
                    existing_mfg_code == new_mfg_code):
                return

        product_name = product_data.get('product_name', '')
        product_data['item_code'] = new_item_code
        product_data['product_name'] = product_name
        product_data['manufacture_code'] = new_mfg_code

        display_text = f"    └ {new_serial_no} | {new_mfg_code}"

        item = QTreeWidgetItem([display_text, new_item_code or ""])
        item.setData(0, Qt.UserRole, product_data)
        purchase_item.addChild(item)

    def add_products_to_selected_order(self):
        selected_item = self.item_tree.currentItem()
        # ✅ [수정] 선택된 항목이 '주문'인지 확인
        if not selected_item:
            QMessageBox.warning(self, "알림", "항목을 선택하세요.")
            return

        order_data = selected_item.data(0, Qt.UserRole)
        if not order_data or order_data.get('type') != 'order':
            QMessageBox.warning(self, "알림", "주문(최상위 항목)을 선택하세요.")
            return

        order_id = order_data['order_id']
        order_text = order_data['order_text']

        dialog = AddProductsFromPurchaseDialog(order_id, order_text, self.delivery_id, self)
        if dialog.exec() == QDialog.Accepted:
            products = dialog.selected_products
            if not products: return

            po_groups = defaultdict(list)
            for prod in products:
                po_groups[prod['purchase_id']].append(prod)

            for purchase_id, product_list in po_groups.items():
                if not product_list: continue
                purchase_text = product_list[0]['purchase_text']
                po_item = self.add_purchase_to_tree(selected_item, purchase_id, purchase_text)
                for product_data in product_list:
                    self.add_product_to_tree(po_item, product_data)

            self.update_all_counts()

    def update_all_counts(self):
        bold_font = QFont();
        bold_font.setBold(True)

        root = self.item_tree.invisibleRootItem()
        for i in range(root.childCount()):
            order_item = root.child(i)
            data = order_item.data(0, Qt.UserRole)

            # ✅ [수정] 'order' 타입일 때만 처리 (재고품목은 건너뜀)
            if not data or data.get('type') != 'order':
                continue

            order_total_qty = 0

            for j in range(order_item.childCount()):
                po_item = order_item.child(j)
                po_data = po_item.data(0, Qt.UserRole)

                # 발주 항목인지 확인 (혹시 모를 방어코드)
                if not po_data or po_data.get('type') != 'purchase':
                    continue

                po_total_qty = po_item.childCount()
                po_item.setText(0, f"  └ {po_data['purchase_text']} ({po_total_qty}개)")
                order_total_qty += po_total_qty

            order_item.setText(0, f"{data['order_text']} (총 {order_total_qty}개)")
            order_item.setFont(0, bold_font)

    def load_delivery_data(self):
        if not self.delivery_id: return
        try:
            conn = get_conn()
            cur = conn.cursor()

            cur.execute(
                "SELECT invoice_no, ship_datetime, carrier, secondary_packaging FROM deliveries WHERE id = ?",
                (self.delivery_id,))
            header = cur.fetchone()
            if not header:
                QMessageBox.warning(self, "오류", "납품 정보를 찾을 수 없습니다.");
                self.reject();
                return

            self.edt_invoice_no.setText(header[0] or "")
            self.edt_ship_datetime.setText(header[1] or "")
            self.edt_carrier.setText(header[2] or "")
            self.edt_secondary_packaging.setText(header[3] or "")

            self.item_tree.clear()

            # ✅ [수정] 수리 상태까지 포함한 쿼리 (StockItem 표시용)
            cur.execute("""
                SELECT 
                    di.serial_no, di.manufacture_code as di_mfg_code, di.qty, 
                    di.order_id, di.purchase_id,
                    di.item_code as di_item_code, di.product_name as di_product_name,

                    pr.part_no as pr_item_code,
                    pr.product_name as pr_product_name,
                    pr.manufacture_code as pr_mfg_code,

                    (SELECT o.order_no || ' - ' || GROUP_CONCAT(oi.product_name, ' | ') 
                     FROM orders o 
                     LEFT JOIN order_items oi ON o.id = oi.order_id 
                     WHERE o.id = di.order_id 
                     GROUP BY o.id) as order_display_text,

                    (SELECT p.purchase_no || ' - ' || GROUP_CONCAT(pi.product_name, ' | ') 
                     FROM purchases p 
                     LEFT JOIN purchase_items pi ON p.id = pi.purchase_id 
                     WHERE p.id = di.purchase_id 
                     GROUP BY p.id) as purchase_display_text,

                    -- [추가] 수리 상태 조회 (StockItem용)
                    (SELECT r.status FROM product_repairs r 
                     WHERE r.product_id = pr.id 
                     ORDER BY r.receipt_date DESC, r.id DESC LIMIT 1) as latest_repair_status

                FROM delivery_items di
                LEFT JOIN products pr 
                   ON di.purchase_id = pr.purchase_id
                  AND di.serial_no = pr.serial_no
                  AND di.item_code = pr.part_no
                  AND COALESCE(di.manufacture_code, '') = COALESCE(pr.manufacture_code, '')
                WHERE di.delivery_id = ?
            """, (self.delivery_id,))

            items_with_parents = cur.fetchall()
            conn.close()

            order_item_map = {}
            purchase_item_map_compound = {}

            item_keys = [
                'serial_no', 'di_mfg_code', 'qty', 'order_id', 'purchase_id',
                'di_item_code', 'di_product_name', 'pr_item_code', 'pr_product_name', 'pr_mfg_code',
                'order_display_text', 'purchase_display_text', 'latest_repair_status'
            ]

            for item_row in items_with_parents:
                item_dict = dict(zip(item_keys, item_row))

                order_id = item_dict['order_id']
                purchase_id = item_dict['purchase_id']

                # 공통 데이터 정리
                item_dict['manufacture_code'] = item_dict.get('di_mfg_code') or item_dict.get('pr_mfg_code') or ''
                item_dict['item_code'] = item_dict.get('pr_item_code') or item_dict.get('di_item_code')
                item_dict['product_name'] = item_dict.get('pr_product_name') or item_dict.get(
                    'di_product_name') or 'N/A'

                # ✅ [수정] 주문/발주 정보가 없는 경우 (재고 품목)
                if not order_id or not purchase_id:
                    self.add_stock_item_to_tree(item_dict)
                    continue

                # --- 주문(Order) 아이템 ---
                order_item = order_item_map.get(order_id)
                if not order_item:
                    order_text = item_dict.get('order_display_text') or f"주문 ID {order_id}"
                    order_item = self.add_order_to_tree(order_id, order_text, expand=True)
                    order_item_map[order_id] = order_item

                # --- 발주(Purchase) 아이템 ---
                po_key = (order_id, purchase_id)
                po_item = purchase_item_map_compound.get(po_key)
                if not po_item:
                    purchase_text = item_dict.get('purchase_display_text') or f"발주 ID {purchase_id}"
                    po_item = self.add_purchase_to_tree(order_item, purchase_id, purchase_text, expand=True)
                    purchase_item_map_compound[po_key] = po_item

                # --- 제품(S/N) 아이템 ---
                self.add_product_to_tree(po_item, item_dict)

            self.update_all_counts()

        except Exception as e:
            QMessageBox.critical(self, "데이터 로드 오류", f"납품 데이터 로드 중 오류 발생:\n{e}")
            import traceback;
            traceback.print_exc()
            self.reject()

    def accept_dialog(self):
        invoice_no = self.edt_invoice_no.text().strip()
        if not invoice_no:
            QMessageBox.warning(self, "입력 오류", "인보이스번호는 필수입니다.");
            return

        duplicate = query_one("SELECT id FROM deliveries WHERE invoice_no = ? AND id != ?",
                              (invoice_no, self.delivery_id or -1))
        if duplicate:
            QMessageBox.warning(self, "중복 오류", f"인보이스 번호 '{invoice_no}'는 이미 존재합니다.");
            return

        ship_datetime_raw = self.edt_ship_datetime.text().strip()
        ship_datetime = parse_datetime_text(ship_datetime_raw) if ship_datetime_raw else None
        if ship_datetime_raw and not ship_datetime:
            QMessageBox.warning(self, "날짜 형식 오류", "발송일시 형식이 올바르지 않습니다.");
            return

        carrier = self.edt_carrier.text().strip();
        secondary_packaging = self.edt_secondary_packaging.text().strip()
        delivery_type = '수리' if self.is_repair_delivery else '일반'

        final_items = []
        unique_order_ids = set()
        unique_purchase_ids = set()

        repair_products_to_update = []

        root = self.item_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            data = item.data(0, Qt.UserRole)
            if not data: continue

            item_type = data.get('type')

            if item_type == 'order':
                order_id = data['order_id']
                unique_order_ids.add(order_id)

                for j in range(item.childCount()):
                    po_item = item.child(j)
                    purchase_id = po_item.data(0, Qt.UserRole)['purchase_id']
                    unique_purchase_ids.add(purchase_id)

                    for k in range(po_item.childCount()):
                        prod_item = po_item.child(k)
                        product_data = prod_item.data(0, Qt.UserRole)
                        final_items.append({
                            'item_code': product_data.get('item_code'),
                            'serial_no': product_data['serial_no'],
                            'manufacture_code': product_data.get('manufacture_code', ''),
                            'product_name': product_data.get('product_name'),
                            'qty': 1,
                            'order_id': order_id,
                            'purchase_id': purchase_id
                        })

            elif item_type == 'stock_item':
                product_data = data
                # DB에서 가져온 값에 공백이 있을 수 있으므로 strip() 추가
                status_chk = (product_data.get('latest_repair_status') or "").strip()

                # ✅ '수리완료' 문자열이 포함되어 있는지 확인 (안전하게)
                if '수리완료' in status_chk:
                    repair_products_to_update.append(product_data.get('product_id'))

                final_items.append({
                    'item_code': product_data.get('item_code'),
                    'serial_no': product_data['serial_no'],
                    'manufacture_code': product_data.get('manufacture_code', ''),
                    'product_name': product_data.get('product_name'),
                    'qty': 1,
                    'order_id': None,
                    'purchase_id': None
                })

        if not final_items:
            QMessageBox.warning(self, "입력 오류", "최소 1개 이상의 유효한 품목이 필요합니다.");
            return

        from ..db import mark_products_as_delivered, unmark_products_as_delivered, update_repair_redelivery_status
        conn = get_conn()
        try:
            cur = conn.cursor()
            delivery_id = self.delivery_id

            if self.is_edit:
                unmark_products_as_delivered(delivery_id, conn)
                cur.execute(
                    "UPDATE deliveries SET invoice_no=?, ship_datetime=?, carrier=?, secondary_packaging=?, delivery_type=?, updated_at=datetime('now','localtime') WHERE id=?",
                    (invoice_no, ship_datetime, carrier, secondary_packaging, delivery_type, delivery_id))
            else:
                cur.execute(
                    "INSERT INTO deliveries (invoice_no, ship_datetime, carrier, secondary_packaging, delivery_type) VALUES (?, ?, ?, ?, ?)",
                    (invoice_no, ship_datetime, carrier, secondary_packaging, delivery_type))
                delivery_id = cur.lastrowid

            cur.execute("DELETE FROM delivery_items WHERE delivery_id = ?", (delivery_id,))
            cur.execute("DELETE FROM delivery_order_links WHERE delivery_id = ?", (delivery_id,))
            cur.execute("DELETE FROM delivery_purchase_links WHERE delivery_id = ?", (delivery_id,))

            for item in final_items:
                cur.execute(
                    """INSERT INTO delivery_items (
                        delivery_id, item_code, serial_no, manufacture_code, product_name, qty,
                        order_id, purchase_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (delivery_id, item['item_code'], item['serial_no'], item['manufacture_code'],
                     item['product_name'],
                     item['qty'], item['order_id'], item['purchase_id'])
                )

            for order_id in unique_order_ids:
                cur.execute("INSERT INTO delivery_order_links (delivery_id, order_id) VALUES (?, ?)",
                            (delivery_id, order_id))

            for purchase_id in unique_purchase_ids:
                cur.execute("INSERT INTO delivery_purchase_links (delivery_id, purchase_id) VALUES (?, ?)",
                            (delivery_id, purchase_id))

            mark_products_as_delivered(delivery_id, conn)

            if self.is_repair_delivery:
                update_repair_redelivery_status(self.repair_info['repair_id'], invoice_no)

            conn.commit()
            # 수리 이력 별도 업데이트
            for p_id in repair_products_to_update:
                if p_id:
                    update_repair_status_on_delivery(p_id, invoice_no)

            action = "수정" if self.is_edit else "등록"
            QMessageBox.information(self, "완료", f"납품 '{invoice_no}'이 {action}되었습니다.")

            try:
                main_window = self.parent().window()
                if hasattr(main_window, 'refresh_order_purchase_delivery'):
                    main_window.refresh_order_purchase_delivery()
                if hasattr(main_window, 'product_production_widget'):
                    main_window.product_production_widget.load_product_list()
            except Exception as e:
                print(f"메인 윈도우 자동 새로고침 실패: {e}")

            self.accept()
        except Exception as e:
            if conn: conn.rollback()
            QMessageBox.critical(self, "오류", f"납품 저장 중 오류가 발생했습니다:\n{str(e)}")
            import traceback;
            traceback.print_exc()
        finally:
            if conn: conn.close()

    def open_add_stock_dialog(self):
        """(새 함수) 1. 품목 검색창 열기"""
        dialog = StockItemSearchDialog(self)
        if dialog.exec() == QDialog.Accepted:
            item_code = dialog.selected_item_code
            product_name = dialog.selected_product_name
            if item_code:
                self.open_stock_picker_dialog(item_code, product_name)

    def open_stock_picker_dialog(self, item_code, product_name):
        """(새 함수) 2. S/N 선택창 열기"""

        existing_serials = set()
        if self.is_edit:
            root = self.item_tree.invisibleRootItem()
            for i in range(root.childCount()):
                item = root.child(i)
                data = item.data(0, Qt.UserRole)
                if data and data.get('type') == 'stock_item' and data.get('item_code') == item_code:
                    existing_serials.add(data.get('serial_no'))

        dialog = StockSerialPickerDialog(self, item_code, product_name, self.delivery_id, self.is_edit,
                                         existing_serials)
        if dialog.exec() == QDialog.Accepted:
            selected_products = dialog.get_selected_products()

            for product_data in selected_products:
                self.add_stock_item_to_tree(product_data)
            self.update_all_counts()

    def add_stock_item_to_tree(self, product_data):
        """(새 함수) S/N(재고/수리품)을 트리의 최상위 항목으로 추가"""

        serial_no = product_data.get('serial_no', 'N/A')
        item_code = product_data.get('item_code', 'N/A')
        product_name = product_data.get('product_name', 'N/A')
        mfg_code = product_data.get('manufacture_code', '')
        latest_repair_status = product_data.get('latest_repair_status')

        root = self.item_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            data = item.data(0, Qt.UserRole)
            if data and data.get('type') == 'stock_item' and data.get('serial_no') == serial_no:
                return

        display_name = f"{product_name}"
        if latest_repair_status == '수리완료':
            display_name += " (수리완료)"

        item = QTreeWidgetItem([f"{serial_no} | {mfg_code} | {product_name}", item_code])
        item.setToolTip(0, display_name)

        product_data['type'] = 'stock_item'
        item.setData(0, Qt.UserRole, product_data)

        if latest_repair_status == '수리완료':
            repair_bg = QColor("#E8F5E9")
            item.setBackground(0, QBrush(repair_bg))
            item.setBackground(1, QBrush(repair_bg))

        root.addChild(item)
        return item


class StockItemSearchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("재고/수리품 추가 (1/2단계: 품목 검색)")
        self.setMinimumWidth(500)

        self.selected_item_code = None
        self.selected_product_name = None

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.info_label = QLabel("납품할 S/N의 품목을 검색하여 선택하세요:")
        self.search_box = AutoCompleteLineEdit()
        self.search_box.product_selected.connect(self.on_product_selected)

        form.addRow(self.info_label)
        form.addRow("품목 검색:", self.search_box)

        self.selected_label = QLabel("선택된 품목: (없음)")
        self.selected_label.setStyleSheet("font-weight: bold; color: #0066cc;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(self.selected_label)
        layout.addWidget(buttons)

    def on_product_selected(self, product_info):
        self.selected_item_code = product_info.get('item_code')
        self.selected_product_name = product_info.get('product_name')

        self.selected_label.setText(f"선택된 품목: {self.selected_item_code} - {self.selected_product_name}")
        self.ok_button.setEnabled(True)


class StockSerialPickerDialog(QDialog):
    def __init__(self, parent, item_code, product_name, delivery_id, is_edit, existing_serials=None):
        super().__init__(parent)
        self.item_code = item_code
        self.delivery_id = delivery_id
        self.is_edit = is_edit
        self.existing_serials = existing_serials or set()

        self.setWindowTitle(f"재고/수리품 추가 (2/2단계: S/N 선택)")
        self.setMinimumSize(800, 600)

        layout = QVBoxLayout(self)
        self.info_label = QLabel(f"<b>{product_name} ({item_code})</b>의 S/N 목록")
        layout.addWidget(self.info_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "S/N", "제조코드", "발주번호", "상태"])

        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 120)

        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.load_available_serials()

    def load_available_serials(self):
        """
        재고 S/N 목록을 로드합니다. (수리 상태 확인 로직 개선판)
        SQL 서브쿼리 대신 Python에서 직접 이력을 확인하여 정확도 향상
        """
        self.table.setRowCount(0)
        all_products_map = {}

        try:
            conn = get_conn()
            cur = conn.cursor()

            # 1. 해당 품목코드(part_no)를 가진 '재고 상태(납품X, 소모X)'인 모든 제품 조회
            #    (이 단계에서는 수리 상태를 가져오지 않음)
            sql_products = """
                SELECT 
                    pr.id, pr.serial_no, pr.manufacture_code, p.purchase_no, pr.product_name
                FROM products pr
                LEFT JOIN purchases p ON pr.purchase_id = p.id
                WHERE pr.part_no = ?
                  AND pr.delivery_id IS NULL
                  AND pr.consumed_by_product_id IS NULL
            """
            cur.execute(sql_products, (self.item_code,))
            products = cur.fetchall()

            for (product_id, serial_no, mfg_code, po_no, name) in products:

                # 2. [핵심 수정] 각 제품별로 '모든' 수리 이력을 조회하여 Python에서 직접 최신 상태 판단
                cur.execute("""
                    SELECT status, receipt_date, id 
                    FROM product_repairs 
                    WHERE product_id = ? 
                    ORDER BY receipt_date DESC, id DESC
                """, (product_id,))

                repairs = cur.fetchall()

                # 기본 상태
                status_text = "재고 (신품/조립)"
                latest_repair_status = None
                is_repaired = False

                # 수리 이력이 있다면 최신 기록 분석
                if repairs:
                    # 가장 최신 기록 (ORDER BY로 정렬했으므로 첫 번째)
                    raw_status = repairs[0][0]
                    latest_repair_status = (raw_status or "").strip()

                    if latest_repair_status == '자체처리':
                        continue

                    if latest_repair_status == '수리완료':
                        status_text = "✅ 수리완료 (출하대기)"
                        is_repaired = True
                    elif latest_repair_status == '재출고':
                        # 재출고된 건이 왜 재고에 있는지? (반품 후 재입고 시나리오 등)
                        status_text = "✅ 재출고됨 (재고)"
                        is_repaired = True
                    elif latest_repair_status in ['접수', '수리중']:
                        status_text = f"⚠️ 수리중 ({latest_repair_status})"

                # 3. 맵에 저장
                all_products_map[product_id] = {
                    'product_id': product_id,
                    'serial_no': serial_no,
                    'manufacture_code': mfg_code,
                    'purchase_no': po_no,
                    'product_name': name,
                    'item_code': self.item_code,
                    'status_text': status_text,
                    'latest_repair_status': latest_repair_status,
                    'is_repaired': is_repaired,
                    'checked': (serial_no in self.existing_serials)
                }

            # 4. (수정 모드일 때) 현재 납품에 포함된 제품도 조회하여 추가
            if self.is_edit and self.delivery_id:
                sql_existing = """
                    SELECT 
                        pr.id, pr.serial_no, pr.manufacture_code, p.purchase_no, pr.product_name
                    FROM products pr
                    LEFT JOIN purchases p ON pr.purchase_id = p.id
                    WHERE pr.part_no = ? AND pr.delivery_id = ?
                """
                cur.execute(sql_existing, (self.item_code, self.delivery_id))
                existing_rows = cur.fetchall()

                for (product_id, serial_no, mfg_code, po_no, name) in existing_rows:
                    if product_id not in all_products_map:
                        # 기존 제품에 대해서도 수리 상태 재확인
                        cur.execute("""
                            SELECT status FROM product_repairs 
                            WHERE product_id = ? ORDER BY receipt_date DESC, id DESC LIMIT 1
                        """, (product_id,))
                        res = cur.fetchone()
                        r_stat = (res[0] or "").strip() if res else None

                        is_rep = (r_stat in ['수리완료', '자체처리', '재출고'])

                        all_products_map[product_id] = {
                            'product_id': product_id, 'serial_no': serial_no, 'manufacture_code': mfg_code,
                            'purchase_no': po_no, 'product_name': name, 'item_code': self.item_code,
                            'status_text': f"현재 납품 포함 (S/N: {serial_no})",
                            'latest_repair_status': r_stat,
                            'is_repaired': is_rep,
                            'checked': True
                        }

            conn.close()

            # 테이블 표시 (S/N 순 정렬)
            self.table.setRowCount(len(all_products_map))
            sorted_products = sorted(all_products_map.values(), key=lambda x: x['serial_no'])

            for row, prod_data in enumerate(sorted_products):
                chk_item = QTableWidgetItem()
                chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chk_item.setCheckState(Qt.Checked if prod_data['checked'] else Qt.Unchecked)
                chk_item.setData(Qt.UserRole, prod_data)

                item_sn = QTableWidgetItem(prod_data['serial_no'])
                item_mfg = QTableWidgetItem(prod_data['manufacture_code'])
                item_po = QTableWidgetItem(prod_data['purchase_no'])
                item_status = QTableWidgetItem(prod_data['status_text'])

                # 수리완료/자체처리 건은 녹색 배경
                if prod_data.get('is_repaired'):
                    bg_color = QColor("#E8F5E9")  # 연한 녹색
                    for item in (chk_item, item_sn, item_mfg, item_po, item_status):
                        item.setBackground(QBrush(bg_color))

                # 수리중 건은 옅은 주황색 배경 (시각적 구분 강화)
                elif '수리중' in prod_data['status_text']:
                    bg_color = QColor("#FFF3E0")  # 연한 주황색
                    for item in (chk_item, item_sn, item_mfg, item_po, item_status):
                        item.setBackground(QBrush(bg_color))

                self.table.setItem(row, 0, chk_item)
                self.table.setItem(row, 1, item_sn)
                self.table.setItem(row, 2, item_mfg)
                self.table.setItem(row, 3, item_po)
                self.table.setItem(row, 4, item_status)

        except Exception as e:
            print(f"S/N 로드 오류: {e}")
            import traceback
            traceback.print_exc()

    def get_selected_products(self):
        products = []
        for row in range(self.table.rowCount()):
            chk_item = self.table.item(row, 0)
            if chk_item.checkState() == Qt.Checked:
                products.append(chk_item.data(Qt.UserRole))
        return products