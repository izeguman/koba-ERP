# app/ui/delivery_widget.py (전체 교체)
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import (QHeaderView, QTableWidgetItem, QMessageBox, QListWidgetItem,
                               QDialog, QVBoxLayout, QListWidget, QTableWidget,
                               QDialogButtonBox, QAbstractItemView, QTreeWidget, QTreeWidgetItem,
                               QFormLayout, QLineEdit, QCheckBox, QLabel)
from PySide6.QtCore import Qt, QSignalBlocker, QTimer, QSettings
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
    revert_repair_status_on_delivery_delete,
    get_product_master_by_code
)
from .utils import parse_datetime_text, apply_table_resize_policy
from ..db import is_purchase_completed, mark_products_as_delivered, unmark_products_as_delivered
from .autocomplete_widgets import AutoCompleteLineEdit
from ..logic.pallet_calculator import PalletCalculator


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
        self.table = QtWidgets.QTableWidget(0, 10) # 컬럼 1개 추가 (총 10개)
        self.table.setHorizontalHeaderLabels(
            ["발송일시", "인보이스번호", "총수량", "품목수", "제품명", "운송사", "2차포장", "연결 정보", "총 판매금액(엔)", "청구완료"]
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
        for col in range(10):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.table.setColumnWidth(0, 140);
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 70);
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 500);
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 150);
        self.table.setColumnWidth(7, 280)
        self.table.setColumnWidth(8, 120) # 판매금액
        self.table.setColumnWidth(9, 80)  # 청구완료

        if self.settings:
            self.restore_column_widths()
        header.sectionResized.connect(self.save_column_widths)
        header.sortIndicatorChanged.connect(self.on_sort_indicator_changed)
        header.setSortIndicatorShown(True)

        layout.addLayout(title_layout)
        layout.addWidget(self.table)
        apply_table_resize_policy(self.table)
        
        # ✅ [수정] 가로 스크롤바 활성화 (utils 정책 오버라이드)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.horizontalHeader().setStretchLastSection(False)

    def set_privacy_mode(self, enabled: bool):
        """재무 정보 숨기기 설정"""
        # 8번 컬럼: 총 판매금액
        
        if enabled:
            # 숨기기 전에 현재 폭을 메모리에 저장 (Settings 아님)
            # 이미 숨겨진 상태가 아닐 때만 저장해야 0으로 저장되는 것 방지
            if not self.table.isColumnHidden(8):
                self._temp_widths = [self.table.columnWidth(col) for col in range(self.table.columnCount())]
            
            self.table.setColumnHidden(8, True)
        else:
            # 보이기 전에 숨김 해제
            self.table.setColumnHidden(8, False)
            
            # 메모리에 저장된 폭이 있다면 복원
            if hasattr(self, '_temp_widths') and self._temp_widths:
                # 리사이즈 시그널을 차단하여 AdjacentColumnResizer 간섭 방지
                header = self.table.horizontalHeader()
                blocker = QSignalBlocker(header)
                try:
                    for col, width in enumerate(self._temp_widths):
                        if col < self.table.columnCount():
                            # 숨겨졌던 8번 컬럼이 0이면 안되므로 최소값 보정 (혹시 모를 안전장치)
                            if col == 8 and width < 50: width = 100
                            self.table.setColumnWidth(col, width)
                finally:
                    blocker.unblock()
                        
                # 복원 후 임시 변수 초기화 (선택사항, 유지해도 무방하나 안전하게)
                # self._temp_widths = None 

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
                    ) AS stock_info,
                    
                    -- ✅ [추가] 총 판매금액 (주문 연결된 건만 계산)
                    (SELECT SUM(di.qty * COALESCE(oi.unit_price_cents, 0)) / 100
                     FROM delivery_items di
                     LEFT JOIN order_items oi ON di.order_id = oi.order_id AND di.item_code = oi.item_code
                     WHERE di.delivery_id = d.id AND di.order_id IS NOT NULL
                    ) AS total_sales_amt

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
                    total_sales_amt # ✅ [추가] 총 판매금액
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
                
                # ✅ [추가] 총 판매금액 (8열)
                total_sales_amt = total_sales_amt or 0
                item_amt = QTableWidgetItem(f"{total_sales_amt:,}")
                item_amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_position, 8, item_amt)

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
                self.table.setCellWidget(row_position, 9, checkbox_widget) # 9열로 이동

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
        
        # menu.addAction("발주서 작성", self.open_add_order_dialog_from_context) # Not needed here
        menu.addAction("청구서 작성", self.create_invoice_document)
        menu.addSeparator()
        menu.addAction("납품 인보이스 작성 (일반)", lambda: self.create_commercial_invoice(is_repair=False))
        menu.addAction("납품 인보이스 작성 (수리품)", lambda: self.create_commercial_invoice(is_repair=True))
        menu.addSeparator()
        
        edit_action = menu.addAction("수정");
        edit_action.triggered.connect(self.edit_delivery)
        delete_action = menu.addAction("삭제");
        delete_action.triggered.connect(self.delete_delivery)
        
        menu.exec(self.table.viewport().mapToGlobal(position))


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

    def get_selected_products(self):
        """선택된 납품에 포함된 제품 목록을 반환합니다."""
        delivery_id = self.get_selected_delivery_id()
        if not delivery_id:
            return []

        try:
            conn = get_conn()
            cur = conn.cursor()
            # delivery_items 테이블에는 unit_price, is_repair_return 등이 없을 수 있으므로
            # products 및 order_items 테이블 조인/서브쿼리로 데이터 확보
            cur.execute("""
                SELECT 
                    di.item_code,
                    di.serial_no,
                    di.product_name,
                    di.manufacture_code,
                    di.qty,
                    (SELECT unit_price_cents FROM order_items oi WHERE oi.order_id = di.order_id AND oi.item_code = di.item_code LIMIT 1) as unit_price_cents,
                    (SELECT currency FROM order_items oi WHERE oi.order_id = di.order_id AND oi.item_code = di.item_code LIMIT 1) as currency,
                    (SELECT description FROM product_master pm WHERE pm.item_code = di.item_code ORDER BY pm.id DESC LIMIT 1) as description,
                    (SELECT status 
                     FROM product_repairs pr 
                     WHERE pr.product_id = (SELECT id FROM products WHERE serial_no = di.serial_no ORDER BY id DESC LIMIT 1) 
                     ORDER BY pr.id DESC LIMIT 1
                    ) as latest_repair_status,
                    
                    -- [수정] 박스 정보: Product Master 우선 사용 (최신 정보 반영) -> 없으면 Delivery Item 값 사용
                    COALESCE(
                        (SELECT items_per_box FROM product_master pm WHERE pm.item_code = di.item_code LIMIT 1),
                        NULLIF(di.items_per_box, 0), 1
                    ) as items_per_box,
                    
                    COALESCE(
                        (SELECT box_weight FROM product_master pm WHERE pm.item_code = di.item_code LIMIT 1),
                        NULLIF(di.box_weight, 0), 0.0
                    ) as box_weight,
                    
                    di.order_id,
                    (SELECT unit_price_jpy FROM product_master pm WHERE pm.item_code = di.item_code ORDER BY pm.id DESC LIMIT 1) as unit_price_jpy
                FROM delivery_items di
                WHERE di.delivery_id = ?
            """, (delivery_id,))
            
            products_data = []
            for row in cur.fetchall():
                # 수리품 여부 판단 (repair_status가 존재하면 수리품으로 간주)
                # 상태가 '접수', '수리중' 등이어도 납품 목록에 있다면 반송/출고 의도이므로 포함
                repair_status = row[8] or ""
                is_repair = bool(repair_status)
                
                # 시리얼 번호가 있으면 수량은 1로 고정
                qty = row[4]
                if row[1] and str(row[1]).strip():
                    qty = 1

                # 단가 계산 (cents 우선, 없으면 master jpy 사용)
                # cents는 100단위이므로 / 100, master price는 JPY 그대로 사용
                u_price_cents = row[5]
                u_price_jpy = row[12]
                
                if u_price_cents is not None:
                     unit_price = u_price_cents / 100.0
                elif u_price_jpy is not None:
                     # 사용자 DB에 마스터 단가도 센트 단위(x100)로 저장되어 있는 것으로 추정됨
                     unit_price = float(u_price_jpy) / 100.0
                else:
                     unit_price = 0.0

                products_data.append({
                    "item_code": row[0],
                    "serial_no": row[1],
                    "product_name": row[2],
                    "manufacturer_code": row[3],
                    "quantity": qty,
                    "unit_price": unit_price,
                    "currency": row[6] or 'JPY',
                    "description": row[7],
                    "latest_repair_status": repair_status,
                    "is_repair_return": is_repair,
                    "items_per_box": row[9] or 1,
                    "box_weight": row[10] or 0.0,
                    "order_id": row[11]
                })
            conn.close()
            return products_data
        except Exception as e:
            QMessageBox.critical(self, "오류", f"선택된 납품의 제품 정보를 불러오는 중 오류 발생:\n{e}")
            return []

    def create_commercial_invoice(self, is_repair=False):
        """납품 인보이스 생성 (Commercial Invoice)"""
        delivery_id = self.get_selected_delivery_id()
        if not delivery_id:
             QMessageBox.information(self, "알림", "인보이스를 작성할 납품을 선택해주세요.")
             return

        items = self.get_selected_products()
        if not items:
            return 

        # 필터링 제거: 사용자가 수리품 인보이스를 선택했든 일반 인보이스를 선택했든, 
        # 해당 납품 건에 포함된 '모든' 품목을 인보이스에 출력합니다.
        # 사용자가 알아서 구분하여 납품을 생성했다고 가정합니다.
        filtered_items = items


        try:
            # 포장/팔레트 정보 조회
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT invoice_no, secondary_packaging FROM deliveries WHERE id = ?", (delivery_id,))
            row = cur.fetchone()
            # ✅ [수정] DB에 저장된 인보이스 번호를 그대로 사용 (사용자 입력 제거)
            invoice_no = row[0] if row else ""
            secondary_packaging = row[1] if row else ""
            conn.close()

            if not invoice_no:
                 QMessageBox.warning(self, "알림", "선택된 납품에 인보이스 번호가 없습니다.")
                 return

            from .document_generator import generate_commercial_invoice
            import os

            # 생성 호출
            result_path = generate_commercial_invoice(
                filtered_items, 
                is_repair_return=is_repair, 
                secondary_packaging=secondary_packaging,
                manual_invoice_no=invoice_no
            )
            
            if str(result_path).startswith("인보이스 생성 실패"):
                QMessageBox.warning(self, "오류", result_path)
            else:
                # 성공 - 완료 다이얼로그
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("완료")
                msg_box.setText(f"인보이스가 생성되었습니다.\n{os.path.basename(result_path)}")
                
                open_folder_btn = msg_box.addButton("폴더 열기", QMessageBox.ActionRole)
                ok_btn = msg_box.addButton("확인", QMessageBox.AcceptRole)
                msg_box.setDefaultButton(ok_btn)
                
                msg_box.exec()
                
                if msg_box.clickedButton() == open_folder_btn:
                    folder = os.path.dirname(result_path)
                    os.startfile(folder)

        except Exception as e:
            QMessageBox.critical(self, "오류", f"상업 인보이스 생성 중 오류 발생:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def create_invoice_document(self):
        """청구서 작성 (엑셀 생성)"""
        delivery_id = self.get_selected_delivery_id()
        if not delivery_id:
            QMessageBox.information(self, "알림", "청구서를 작성할 납품을 선택해주세요.")
            return
            
        try:
            from .utils import resource_path
            from .document_generator import generate_invoice, get_next_invoice_serial, get_delivery_serial_rank
            import os
            from datetime import datetime
            
            # 1. 일련번호 추천값 조회
            today = datetime.now()
            ymd_full = today.strftime("%Y%m%d")
            suggested_serial = get_delivery_serial_rank(delivery_id)

            # 2. 사용자 입력
            serial, ok = QtWidgets.QInputDialog.getText(
                 self,
                 "청구서 작성",
                 f"청구서 일련번호를 입력하세요 (KI{ymd_full}-xxx)\n예: 001, 002...",
                 QtWidgets.QLineEdit.Normal,
                 suggested_serial
            )
            
            if not ok or not serial:
                 return
            
            template_path = resource_path("app/templete/ULVAC-PHI_Invoice_.xlsx")
            if not os.path.exists(template_path):
                 # Fallback
                 fallback = "ULVAC-PHI_Invoice_.xlsx"
                 if os.path.exists(fallback):
                     template_path = fallback
                 else:
                     QMessageBox.critical(self, "오류", f"템플릿 파일을 찾을 수 없습니다:\n{template_path}")
                     return

            generated_files = generate_invoice(delivery_id, template_path, invoice_serial=serial)
            
            if not generated_files:
                QMessageBox.information(self, "알림", "생성된 청구서가 없습니다.\n(연결된 주문이 없거나 품목이 없을 수 있습니다)")
                return
                
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setWindowTitle("완료")
            msg_box.setText(f"총 {len(generated_files)}개의 청구서 파일이 생성되었습니다.\n\n저장 경로: {os.path.dirname(generated_files[0])}")
            
            open_folder_btn = msg_box.addButton("폴더 열기", QtWidgets.QMessageBox.ActionRole)
            ok_btn = msg_box.addButton("확인", QtWidgets.QMessageBox.AcceptRole)
            
            msg_box.exec()
            
            if msg_box.clickedButton() == open_folder_btn:
                folder_path = os.path.dirname(generated_files[0])
                os.startfile(folder_path)

        except Exception as e:
             QMessageBox.critical(self, "오류", f"청구서 생성 중 오류 발생:\n{str(e)}")
             import traceback
             traceback.print_exc()

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

            # ✅ [추가] 주문 품목 단가 조회
            price_map = {}
            if self.order_id:
                try:
                    p_rows = query_all("SELECT item_code, unit_price_cents FROM order_items WHERE order_id = ?", (self.order_id,))
                    for ic, price in p_rows:
                        price_map[ic] = price
                except Exception as e:
                    print(f"단가 조회 실패: {e}")

            self.product_table.setRowCount(len(products))
            for row, product in enumerate(products):
                product_dict = dict(zip(['id', 'part_no', 'product_name', 'serial_no', 'manufacture_code'], product))
                
                # 단가 할당
                item_c = product_dict.get('part_no') # part_no가 item_code
                product_dict['unit_price'] = price_map.get(item_c, 0) / 100

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
            # 설정 값과 무관하게 항상 자동 생성 (사용자 요청)
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
            # if geometry:
            #     self.restoreGeometry(geometry)

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
        self.item_tree.setColumnWidth(0, 350)
        self.item_tree.setColumnWidth(1, 120)

        apply_table_resize_policy(self.item_tree)

        # ✅ [수정] 가로 스크롤바 활성화 (utils 정책 오버라이드)
        self.item_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.item_tree.header().setStretchLastSection(False)

        # ✅ [추가] 컬럼 폭 저장 및 복원
        if self.settings:
            self.restore_column_widths()
        
        self.item_tree.header().sectionResized.connect(self.save_column_widths)

        item_button_layout = QtWidgets.QHBoxLayout()
        self.btn_add_item = QtWidgets.QPushButton("+ 주문에서 품목 추가")
        self.btn_add_item.clicked.connect(self.open_add_order_dialog)

        self.btn_add_stock_item = QtWidgets.QPushButton("+ 재고/수리품 추가")
        self.btn_add_stock_item.clicked.connect(self.open_add_stock_dialog)

        item_button_layout.addWidget(self.btn_add_item)
        item_button_layout.addWidget(self.btn_add_stock_item)
        item_button_layout.addStretch()

        item_layout.addWidget(self.item_tree)

        # ✅ [추가] 팔레트 계산 버튼
        self.btn_pallet_calc = QtWidgets.QPushButton("📦 포장/팔레트 계산")
        self.btn_pallet_calc.setToolTip("선택한 품목의 포장 정보를 입력하고 팔레트 수량을 계산합니다.")
        self.btn_pallet_calc.clicked.connect(self.open_pallet_calc_dialog)
        item_button_layout.insertWidget(0, self.btn_pallet_calc) # 맨 앞에 추가
        
        item_layout.addLayout(item_button_layout)

        # ✅ [추가] 총 판매 가액 표시
        self.lbl_total_sales = QtWidgets.QLabel("총 판매가액: ¥0")
        self.lbl_total_sales.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_total_sales.setStyleSheet("font-size: 14px; font-weight: bold; color: #007bff; margin-right: 10px;")
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept_dialog)
        button_box.rejected.connect(self.reject)

        # 프라이버시 모드 적용 상태 확인 (설정에서)
        if self.settings:
             is_privacy = self.settings.value("view/privacy_mode", False, type=bool)
             self.set_privacy_mode(is_privacy)

        main_layout.addWidget(header_group)
        main_layout.addWidget(item_group, 1)
        main_layout.addWidget(self.lbl_total_sales) # 버튼 위에 추가
        main_layout.addWidget(button_box)

    def set_privacy_mode(self, enabled: bool):
        self.privacy_mode_enabled = enabled
        if enabled:
            self.lbl_total_sales.setText("총 판매가액: ****")
        else:
            self.update_all_counts()



    def open_pallet_calc_dialog(self):
        """선택한 항목에 대한 팔레트 계산 및 포장 정보 수정"""
        selected_items = self.item_tree.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "알림", "팔레트 계산을 수행할 품목을 선택해주세요.")
            return

        # 선택된 항목 중 '제품(Product)' 레벨인 것만 필터링
        target_items = []
        target_products_data = []
        
        for item in selected_items:
            data = item.data(0, Qt.UserRole)
            if data and 'product_name' in data: # 제품 노드
                target_items.append(item)
                target_products_data.append(data)
            elif data and data.get('type') == 'purchase':
                # 발주 노드 선택 시 하위 모든 제품 포함
                for i in range(item.childCount()):
                    child = item.child(i)
                    c_data = child.data(0, Qt.UserRole)
                    if c_data: 
                        target_items.append(child)
                        target_products_data.append(c_data)

        if not target_items:
            QMessageBox.information(self, "알림", "선택된 항목에 제품이 없습니다.")
            return

        # [수정] 혼적 허용: 선택된 모든 제품을 대상으로 함
        # 기존에는 동일 품목코드만 필터링했으나, 이제 여러 품목을 한 번에 넘김
        pass
        
        dialog = PalletCalculationDialog(self, tree_items=target_items, parent=self)
        if dialog.exec() == QDialog.Accepted:
            QMessageBox.information(self, "완료", "포장 정보가 저장되었습니다.")

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
        
        total_sales_amt = 0

        root = self.item_tree.invisibleRootItem()
        for i in range(root.childCount()):
            root_item = root.child(i)
            data = root_item.data(0, Qt.UserRole)
            if not data: continue
            
            item_type = data.get('type')

            if item_type == 'order':
                order_total_qty = 0
                for j in range(root_item.childCount()):
                    po_item = root_item.child(j)
                    po_data = po_item.data(0, Qt.UserRole)
                    
                    if not po_data or po_data.get('type') != 'purchase':
                         continue
                         
                    po_total_qty = po_item.childCount()
                    po_item.setText(0, f"  └ {po_data['purchase_text']} ({po_total_qty}개)")
                    order_total_qty += po_total_qty
                    
                    # 제품 단가 합산
                    for k in range(po_item.childCount()):
                        prod_item = po_item.child(k)
                        prod_data = prod_item.data(0, Qt.UserRole)
                        if prod_data:
                            total_sales_amt += (prod_data.get('unit_price') or 0)
                            
                root_item.setText(0, f"{data['order_text']} (총 {order_total_qty}개)")
                root_item.setFont(0, bold_font)
            
            elif item_type == 'stock_item':
                # 재고 품목 (개별)
                total_sales_amt += (data.get('unit_price') or 0)
                
        # 라벨 업데이트
        if getattr(self, 'privacy_mode_enabled', False):
            self.lbl_total_sales.setText("총 판매가액: ****")
        else:
            self.lbl_total_sales.setText(f"총 판매가액: ¥{int(total_sales_amt):,}")

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
                     ORDER BY r.receipt_date DESC, r.id DESC LIMIT 1) as latest_repair_status,

                    -- ✅ [추가] 단가 조회 (주문 연결 시)
                    (SELECT oi2.unit_price_cents / 100
                     FROM order_items oi2 
                     WHERE oi2.order_id = di.order_id AND oi2.item_code = di.item_code 
                     LIMIT 1
                    ) as unit_price,
                    
                    di.items_per_box, di.box_l, di.box_w, di.box_h, di.box_weight, di.max_layer,
                    di.pallet_type, di.loading_pattern, di.boxes_per_pallet

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
                'order_display_text', 'purchase_display_text', 'latest_repair_status', 'unit_price',
                'items_per_box', 'box_l', 'box_w', 'box_h', 'box_weight', 'max_layer',
                'pallet_type', 'loading_pattern', 'boxes_per_pallet'
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

                # 포장 정보 보정 (NULL -> 0 or 1)
                item_dict['items_per_box'] = item_dict.get('items_per_box') or 1
                item_dict['box_l'] = item_dict.get('box_l') or 0
                item_dict['box_w'] = item_dict.get('box_w') or 0
                item_dict['box_h'] = item_dict.get('box_h') or 0
                item_dict['box_weight'] = item_dict.get('box_weight') or 0.0
                item_dict['max_layer'] = item_dict.get('max_layer') or 0
                item_dict['boxes_per_pallet'] = item_dict.get('boxes_per_pallet') or 0

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

    def save_column_widths(self):
        """컬럼 폭 저장"""
        if not self.settings: return
        widths = []
        for i in range(self.item_tree.columnCount()):
            widths.append(self.item_tree.columnWidth(i))
        self.settings.setValue("delivery_dialog_tree/column_widths", widths)

    def restore_column_widths(self):
        """컬럼 폭 복원"""
        if not self.settings: return
        widths = self.settings.value("delivery_dialog_tree/column_widths")
        if widths:
            header = self.item_tree.header()
            blocker = QSignalBlocker(header)  # 리사이즈 시그널 차단
            try:
                for col, width in enumerate(widths):
                    if col < self.item_tree.columnCount():
                        self.item_tree.setColumnWidth(col, int(width))
            finally:
                blocker.unblock()

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
                            'purchase_id': purchase_id,
                            
                            # 포장 정보
                            'box_l': product_data.get('box_l', 0),
                            'box_w': product_data.get('box_w', 0),
                            'box_h': product_data.get('box_h', 0),
                            'items_per_box': product_data.get('items_per_box', 1),
                            'max_layer': product_data.get('max_layer', 0),
                            'box_weight': product_data.get('box_weight', 0.0),
                            
                            # 계산 결과
                            'pallet_type': product_data.get('pallet_type'),
                            'loading_pattern': product_data.get('loading_pattern'),
                            'boxes_per_pallet': product_data.get('boxes_per_pallet', 0)
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
                    'purchase_id': None,
                    
                    # 포장 정보
                    'box_l': product_data.get('box_l', 0),
                    'box_w': product_data.get('box_w', 0),
                    'box_h': product_data.get('box_h', 0),
                    'items_per_box': product_data.get('items_per_box', 1),
                    'max_layer': product_data.get('max_layer', 0),
                    'box_weight': product_data.get('box_weight', 0.0),
                    
                    # 계산 결과
                    'pallet_type': product_data.get('pallet_type'),
                    'loading_pattern': product_data.get('loading_pattern'),
                    'boxes_per_pallet': product_data.get('boxes_per_pallet', 0)
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
                        order_id, purchase_id,
                        box_l, box_w, box_h, items_per_box, max_layer, box_weight,
                        pallet_type, loading_pattern, boxes_per_pallet
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (delivery_id, item['item_code'], item['serial_no'], item['manufacture_code'],
                     item['product_name'],
                     item['qty'], item['order_id'], item['purchase_id'],
                     item['box_l'], item['box_w'], item['box_h'], 
                     item['items_per_box'], item['max_layer'], item['box_weight'],
                     item['pallet_type'], item['loading_pattern'], item['boxes_per_pallet'])
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
                  AND pr.consumed_by_product_id IS NULL
                  AND (
                      -- A. 어떤 납품 정보도 없는 순수 재고
                      pr.delivery_id IS NULL
                      OR 
                      -- B. 과거 납품되었으나 그 후에 리콜 접수된 제품 (재고로 간주)
                      (
                          EXISTS (
                              SELECT 1 FROM recall_items ri
                              JOIN recall_cases rc ON ri.recall_case_id = rc.id
                              JOIN deliveries d2 ON pr.delivery_id = d2.id
                              WHERE ri.product_id = pr.id 
                                AND rc.receipt_date > d2.ship_datetime
                                AND rc.status != '완료'
                          )
                          -- 단, 현재 수정 중인 납품서에 이미 들어있는 경우는 제외 (중복 방지)
                          AND (pr.delivery_id != ?)
                      )
                  )
                  -- C. 리콜 건 자체가 완료된 경우는 무조건 제외
                  AND NOT EXISTS (
                      SELECT 1 FROM recall_items ri2
                      JOIN recall_cases rc2 ON ri2.recall_case_id = rc2.id
                      WHERE ri2.product_id = pr.id AND rc2.status = '완료'
                  )
            """
            cur.execute(sql_products, (self.item_code, self.delivery_id or -1))
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
                        # 자체처리된 수리 건이 있어도 리콜 대상일 수 있으므로 continue 하지 않고 상태만 기록
                        status_text = "재고 (자체처리됨)"
                    elif latest_repair_status == '수리완료':
                        status_text = "✅ 수리완료 (출하대기)"
                        is_repaired = True
                    elif latest_repair_status == '재출고':
                        status_text = "✅ 재출고됨 (재고)"
                        is_repaired = True
                    elif latest_repair_status in ['접수', '수리중']:
                        status_text = f"⚠️ 수리중 ({latest_repair_status})"

                # --- [추가] 리콜 이력 확인 ---
                cur.execute("""
                    SELECT item_status FROM recall_items 
                    WHERE product_id = ? 
                    ORDER BY id DESC LIMIT 1
                """, (product_id,))
                recall = cur.fetchone()
                if recall:
                    recall_status = (recall[0] or "").strip()
                    if recall_status == '완료':
                        status_text = "✅ 리콜완료 (출하대기)"
                        is_repaired = True
                    elif recall_status in ['대기', '수리중']:
                        status_text = f"⚠️ 리콜중 ({recall_status})"

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

            # 4. (삭제) 이전에 현재 납품에 포함된 제품도 조회하여 추가하던 로직을 제거함
            # 이 창은 오직 '추가'할 수 있는 새로운 재고들만 보여줘야 함.
            # 이미 납품 수정 창의 목록에 있는 것은 표시할 필요가 없음.

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

# -----------------------------------------------------------------------------
# Pallet Calculation Dialog (다차종 혼적 지원)
# -----------------------------------------------------------------------------
class PalletCalculationDialog(QDialog):
    def __init__(self, delivery_widget, tree_items, parent=None):
        super().__init__(parent)
        self.delivery_widget = delivery_widget
        self.tree_items = tree_items 
        
        # 품목별 데이터 정리
        self.items_data = self._group_items(tree_items)

        self.setWindowTitle("팔레트 계산 (다차종 혼적 지원)")
        self.resize(1000, 700)
        
        self.setup_ui()
        self.load_initial_data()
        
        # [설정 로드] 컬럼 너비 복원
        self.load_settings()
        
    def _group_items(self, tree_items):
        grouped = {}
        for item in tree_items:
            data = item.data(0, Qt.UserRole)
            code = data.get('item_code') or data.get('part_no')
            if not code: continue
            
            if code not in grouped:
                # [수정] DB에서 약어 조회 (Rev 무관하게 최신 1건)
                abbr_name = None
                conn = get_conn()
                cur = conn.cursor()
                try:
                    # get_product_master_by_code는 Rev 가 일치해야 하므로,
                    # 여기서는 Rev 무관하게 약어를 가져오기 위해 직접 쿼리
                    cur.execute("SELECT abbreviation FROM product_master WHERE item_code = ? ORDER BY id DESC LIMIT 1", (code,))
                    res = cur.fetchone()
                    if res and res[0]:
                        abbr_name = res[0]
                except Exception as e:
                    print(f"Error fetching abbreviation for {code}: {e}")
                finally:
                    conn.close()

                original_name = data.get('product_name') or data.get('item_name') or data.get('description') or code
                final_name = abbr_name if abbr_name else original_name
                
                grouped[code] = {
                    'item_code': code,
                    'item_name': final_name,
                    'qty': 0,
                    'product_ids': [],
                    'tree_items': [],
                    'specs': {} 
                }
            grouped[code]['qty'] += 1
            grouped[code]['product_ids'].append(data.get('id'))
            grouped[code]['tree_items'].append(item)
            
            if not grouped[code]['specs'] and data.get('box_l'):
                 grouped[code]['specs'] = {
                     'box_l': data.get('box_l'),
                     'box_w': data.get('box_w'),
                     'box_h': data.get('box_h'),
                     'box_weight': data.get('box_weight'),
                     'items_per_box': data.get('items_per_box'),
                     'max_layer': data.get('max_layer')
                 }
                 
        return list(grouped.values())

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Summary
        total_qty = sum(item['qty'] for item in self.items_data)
        info_label = QLabel(f"선택된 품목: {len(self.items_data)}종 (총 {total_qty}개)")
        info_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(info_label)
        
        # Input Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["품목코드", "수량", "L (mm)", "W (mm)", "H (mm)", "무게 (kg)", "박스당 제품수량", "최대단수"])
        
        header = self.table.horizontalHeader()
        # 기본적으로 Stretch 사용하되, 특정 컬럼 너비 조정
        header.setSectionResizeMode(QHeaderView.Interactive)
        
        # 기본적으로 모든 컬럼을 Interactive(사용자 조절 가능)로 설정
        # 초기 폭은 내용을 기준으로 잡거나(ResizeToContents) 고정값 사용 후 Interactive 순서로 적용
        
        # 0: Code
        header.setSectionResizeMode(0, QHeaderView.Interactive) 
        
        # 1: Qty
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        
        # 2,3,4: L,W,H
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        
        # 5: Weight
        self.table.setColumnWidth(5, 70) 
        header.setSectionResizeMode(5, QHeaderView.Interactive)
        
        # 6: Items Per Box
        header.setSectionResizeMode(6, QHeaderView.Interactive)
        
        # 7: Max Layer
        self.table.setColumnWidth(7, 70)
        header.setSectionResizeMode(7, QHeaderView.Interactive)

        layout.addWidget(self.table)
        
        # Calc Button
        self.btn_calc = QtWidgets.QPushButton("계산하기 (혼적 적용)")
        self.btn_calc.clicked.connect(self.calculate)
        self.btn_calc.setStyleSheet("font-weight: bold; background-color: #e3f2fd; padding: 10px;")
        layout.addWidget(self.btn_calc)
        
        # Result Group
        result_group = QtWidgets.QGroupBox("계산 결과")
        result_layout = QFormLayout(result_group)
        
        self.lbl_pallet_type = QLabel("-")
        
        # [수정] 상세 리포트 표시를 위한 TextEdit
        self.txt_pattern = QtWidgets.QTextEdit()
        self.txt_pattern.setReadOnly(True)
        self.txt_pattern.setFixedHeight(200) # 높이 확보
        self.txt_pattern.setStyleSheet("background-color: #f9f9f9; font-family: Consolas, monospace;")
        
        self.lbl_total_pallet = QLabel("-")
        self.lbl_total_boxes = QLabel("-")
        
        result_layout.addRow("추천 팔레트:", self.lbl_pallet_type)
        result_layout.addRow("적재 내용:", self.txt_pattern)
        result_layout.addRow("총 박스 수:", self.lbl_total_boxes)
        result_layout.addRow("필요 팔레트:", self.lbl_total_pallet)
        
        result_layout.addRow("총 박스 수:", self.lbl_total_boxes)
        result_layout.addRow("필요 팔레트:", self.lbl_total_pallet)
        
        layout.addWidget(result_group)

        # [신규] 마스터 업데이트 옵션
        self.chk_update_master = QCheckBox("제품 마스터에 박스 정보(무게, 크기 등) 반영")
        self.chk_update_master.setChecked(True) # 기본값 체크
        layout.addWidget(self.chk_update_master)
        
        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("저장 및 적용")
        btns.accepted.connect(self.save_data)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def load_initial_data(self):
        self.table.setRowCount(len(self.items_data))
        conn = get_conn()
        cur = conn.cursor()
        
        for row, item in enumerate(self.items_data):
            code = item['item_code']
            qty = item['qty']
            specs = item['specs']
            
            if not specs.get('box_l'):
                cur.execute("SELECT items_per_box, box_l, box_w, box_h, box_weight, max_layer FROM product_master WHERE item_code = ? ORDER BY id DESC LIMIT 1", (code,))
                db_row = cur.fetchone()
                if db_row:
                    specs = {
                        'items_per_box': db_row[0] or 1,
                        'box_l': db_row[1] or 0,
                        'box_w': db_row[2] or 0,
                        'box_h': db_row[3] or 0,
                        'box_weight': db_row[4] or 0.0,
                        'max_layer': db_row[5] or 1
                    }
                else:
                    specs = {'items_per_box': 1, 'box_l': 0, 'box_w': 0, 'box_h': 0, 'box_weight': 0.0, 'max_layer': 1}
            
            item_code_item = QTableWidgetItem(code)
            item_code_item.setFlags(item_code_item.flags() ^ Qt.ItemIsEditable) 
            self.table.setItem(row, 0, item_code_item)
            
            qty_item = QTableWidgetItem(str(qty))
            qty_item.setFlags(qty_item.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, 1, qty_item)
            
            self.table.setItem(row, 2, QTableWidgetItem(str(specs.get('box_l', 0))))
            self.table.setItem(row, 3, QTableWidgetItem(str(specs.get('box_w', 0))))
            self.table.setItem(row, 4, QTableWidgetItem(str(specs.get('box_h', 0))))
            self.table.setItem(row, 5, QTableWidgetItem(str(specs.get('box_weight', 0))))
            self.table.setItem(row, 6, QTableWidgetItem(str(specs.get('items_per_box', 1))))
            self.table.setItem(row, 7, QTableWidgetItem(str(specs.get('max_layer', 1))))
            
        conn.close()
        QTimer.singleShot(100, self.calculate)

    def calculate(self):
        try:
            items_input = []
            for row in range(self.table.rowCount()):
                def get_val(col, default=0):
                    data = self.table.item(row, col)
                    if not data: return default
                    txt = data.text()
                    try: return int(float(txt))
                    except: return default
                    
                code = self.table.item(row, 0).text()
                qty = int(self.table.item(row, 1).text())
                
                # Retrieve Name from self.items_data (assuming stable order)
                original = self.items_data[row]
                name = original.get('item_name', code)
                
                box_l = get_val(2)
                box_w = get_val(3)
                box_h = get_val(4)
                weight = float(self.table.item(row, 5).text() or 0)
                per_box = get_val(6, 1)
                max_layer = get_val(7, 1)
                
                items_input.append({
                    'item_code': code,
                    'item_name': name,
                    'qty': qty,
                    'box_l': box_l,
                    'box_w': box_w,
                    'box_h': box_h,
                    'box_weight': weight,
                    'items_per_box': per_box,
                    'max_layer': max_layer
                })

            result = PalletCalculator.calculate_mixed(items_input)
            self.last_calc_result = result
            
            self.lbl_pallet_type.setText(result.get('pallet_type', '-'))
            
            # [수정] 상세 리포트 텍스트 사용
            detail_report = result.get('detailed_pattern_text') or result.get('pattern_str', '-')
            self.txt_pattern.setText(detail_report)
            
            self.lbl_total_boxes.setText(f"{result.get('total_boxes', 0)} 박스")
            self.lbl_total_pallet.setText(f"{result.get('total_pallets', 0)} PLT")
            self.lbl_total_pallet.setStyleSheet("color: blue; font-weight: bold; font-size: 16px;")

        except Exception as e:
            self.txt_pattern.setText(f"오류: {e}")
            import traceback
            traceback.print_exc()
            
    def save_data(self):
        if hasattr(self, 'last_calc_result') and self.last_calc_result:
            res = self.last_calc_result
            
            # 요약 저장용 텍스트 (DB용)
            summary_text = res.get('summary_text') or res.get('pattern_str', '')
            summary = summary_text
            
            current_text = self.delivery_widget.edt_secondary_packaging.text().strip()
            if summary not in current_text:
                if current_text:
                    new_text = f"{current_text} / {summary}"
                else:
                    new_text = summary
                self.delivery_widget.edt_secondary_packaging.setText(new_text)
            
            # [신규] 제품 마스터 업데이트 로직
            if self.chk_update_master.isChecked():
                self.update_product_master_specs()

        self.accept()

    def update_product_master_specs(self):
        """테이블에 입력된 값으로 product_master 테이블 업데이트"""
        from ..db import get_conn
        conn = get_conn()
        try:
            cur = conn.cursor()
            updated_count = 0
            
            for row in range(self.table.rowCount()):
                item_code = self.table.item(row, 0).text()
                
                # 입력값 가져오기 (calculate 함수와 동일한 로직)
                try:
                    box_l = int(float(self.table.item(row, 2).text() or 0))
                    box_w = int(float(self.table.item(row, 3).text() or 0))
                    box_h = int(float(self.table.item(row, 4).text() or 0))
                    box_weight = float(self.table.item(row, 5).text() or 0)
                    items_per_box = int(float(self.table.item(row, 6).text() or 1)) # 입수
                    max_layer = int(float(self.table.item(row, 7).text() or 1))
                except ValueError:
                    continue # 숫자가 아니면 스킵

                # 업데이트 쿼리 실행
                # box_l, box_w, box_h, box_weight, items_per_box, max_layer
                cur.execute("""
                    UPDATE product_master 
                    SET box_l=?, box_w=?, box_h=?, box_weight=?, items_per_box=?, max_layer=?, updated_at=datetime('now','localtime')
                    WHERE item_code=?
                """, (box_l, box_w, box_h, box_weight, items_per_box, max_layer, item_code))
                
                if cur.rowcount > 0:
                    updated_count += 1
            
            conn.commit()
            if updated_count > 0:
                print(f"[PalletCalc] {updated_count}개 품목의 마스터 정보가 업데이트되었습니다.")

        except Exception as e:
            conn.rollback()
            print(f"제품 마스터 업데이트 실패: {e}")

    def save_settings(self):
        settings = QSettings("Koba", "PalletCalc")
        # 컬럼 너비 저장
        for i in range(self.table.columnCount()):
            settings.setValue(f"col_width_{i}", self.table.columnWidth(i))
            
    def load_settings(self):
        settings = QSettings("Koba", "PalletCalc")
        for i in range(self.table.columnCount()):
            val = settings.value(f"col_width_{i}")
            if val:
                self.table.setColumnWidth(i, int(val))
                
    def done(self, r):
        # 다이얼로그 닫힐 때 설정 저장 (OK/Cancel 무관)
        self.save_settings()
        super().done(r)