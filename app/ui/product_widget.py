# app/ui/product_widget.py
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import (QHeaderView, QTreeWidget, QTreeWidgetItem,
                               QMessageBox, QGroupBox, QVBoxLayout, QFormLayout,
                               QLabel, QSpinBox, QListWidget, QListWidgetItem,
                               QPushButton, QDialog, QLineEdit, QDialogButtonBox)
from PySide6.QtCore import QLocale, Qt, QSignalBlocker
from PySide6.QtGui import QBrush, QColor
from datetime import datetime
import re

from .utils import parse_due_text
from ..db import (get_conn, query_all, is_purchase_completed, get_available_purchases,
                  get_bom_requirements, get_available_stock_for_bom, create_products,
                  assign_product_info_batch, reset_product_info_batch, get_repairs_for_product)
from .autocomplete_widgets import AutoCompleteLineEdit
from ..ui.repair_widget import RepairDialog


def get_next_serial_number(conn, part_no: str) -> str:
    """특정 품목의 다음 시리얼 번호를 생성합니다 (KT001 ~ KT999)"""
    cur = conn.cursor()
    cur.execute("""
                SELECT serial_no FROM products
                WHERE serial_no LIKE 'KT%'
                AND part_no = ?
                ORDER BY CAST(SUBSTR(serial_no, 3) AS INTEGER) DESC
                LIMIT 1
            """, (part_no,))
    result = cur.fetchone()
    if result and result[0]:
        last_serial = result[0]
        try:
            last_num = int(last_serial[2:])
            next_num = (last_num % 999) + 1
            return f"KT{next_num:03d}"
        except (ValueError, IndexError):
            return "KT001"
    else:
        return "KT001"


def get_purchase_info(purchase_id: int, item_code: str = None):
    """특정 발주의 상세 정보 반환 (품목코드로 필터링 가능)"""
    sql = """
        SELECT
            p.purchase_no,
            GROUP_CONCAT(pi.product_name, ' | ') as purchase_desc,
            SUM(pi.qty) as total_qty,
            AVG(pi.unit_price_cents) as avg_unit_price
        FROM purchases p
        LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
        WHERE p.id = ?
    """
    params = [purchase_id]

    if item_code:
        # ✅ [추가] 품목코드가 지정된 경우, 해당 품목의 수량만 합산
        sql += " AND pi.item_code = ?"
        params.append(item_code)

    sql += " GROUP BY p.id"
    result = query_all(sql, tuple(params))
    return result[0] if result else None


def get_produced_quantity(purchase_id: int, item_code: str = None):
    """특정 발주의 총 생산 수량 반환 (품목코드로 필터링 가능)"""
    sql = """
        SELECT COUNT(*) as total_produced
        FROM products
        WHERE purchase_id = ?
    """
    params = [purchase_id]

    if item_code:
        # ✅ [추가] 품목코드가 지정된 경우, 해당 품목의 생산 수량만 카운트
        sql += " AND part_no = ?"
        params.append(item_code)

    result = query_all(sql, tuple(params))
    return result[0][0] if result else 0


def parse_date_text(text: str) -> str | None:
    """텍스트로 들어온 날짜를 YYYY-MM-DD 로 정규화"""
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


'''def get_available_purchases():
    """
    '새 제품 추가'에서 연결할 수 있는 발주 목록을 반환합니다.
    - 모든 종류의 '완료' 상태를 종합적으로 판단하여 필터링합니다.
    """
    # 1. 필터링에 필요한 모든 정보를 DB에서 가져옵니다.
    sql = """
        SELECT
            p.id,
            p.purchase_no,
            GROUP_CONCAT(pi.product_name, ' | ') as purchase_desc,
            SUM(pi.qty) as ordered_qty,
            p.purchase_dt,
            (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id) as produced_qty
        FROM purchases p
        LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
        WHERE p.purchase_no IS NOT NULL
        GROUP BY p.id
        ORDER BY p.purchase_dt DESC
    """
    all_purchases = query_all(sql)

    # 2. Python 코드로 명확하게 필터링합니다.
    available_list = []
    for p_id, p_no, p_desc, ordered_qty, p_dt, produced_qty in all_purchases:

        # 조건 1: 시스템의 중앙 로직으로 '완료'된 발주인지 종합적으로 판단하여 제외
        if is_purchase_completed(p_id):
            continue

        # 조건 2: (안전장치) 발주 수량보다 생산 수량이 같거나 많으면 제외
        ordered_qty = ordered_qty or 0
        produced_qty = produced_qty or 0
        if ordered_qty <= produced_qty:
            continue

        # 위 조건들을 모두 통과한, 진짜 생산이 필요한 발주만 목록에 추가
        available_list.append((p_id, p_no, p_desc, ordered_qty, p_dt))

    return available_list'''


class ProductWidget(QtWidgets.QWidget):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.expanded_state = {}

        # ✅ 저장된 설정 불러오기
        if self.settings:
            self.show_all_products = self.settings.value("filters/product_show_all", False, type=bool)
        else:
            self.show_all_products = False

        self.setup_ui()

        # ✅ 저장된 정렬 상태 불러오기 (기본값: 5-발주번호, 1-내림차순)
        self.current_sort_column = self.settings.value("product_tree/sort_column", 5, type=int)
        sort_order_val = self.settings.value("product_tree/sort_order", Qt.DescendingOrder)
        self.current_sort_order = Qt.SortOrder(sort_order_val)

        self.load_product_list()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("제품 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        self.btn_new_product = QtWidgets.QPushButton("새 제품")
        self.btn_refresh_product = QtWidgets.QPushButton("새로고침")

        # ✅ 추가: 미납품/전체보기 토글 버튼
        self.btn_show_all_products = QtWidgets.QPushButton("전체보기" if self.show_all_products else "미납품만")
        self.btn_show_all_products.setCheckable(True)
        self.btn_show_all_products.setChecked(self.show_all_products)   # ✅ 저장된 값으로 설정
        self.btn_show_all_products.toggled.connect(self.toggle_show_all)

        self.btn_new_product.clicked.connect(self.add_product)
        self.btn_refresh_product.clicked.connect(self.load_product_list)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.btn_new_product)
        title_layout.addWidget(self.btn_refresh_product)
        title_layout.addWidget(self.btn_show_all_products)  # ✅ 추가: 버튼 레이아웃에 추가

        self.tree = QTreeWidget()
        self.tree.setStyleSheet("""
                    QTreeView {
                        font-size: 10pt; /* 전체 폰트 크기를 10pt로 설정 */
                    }
                    QTreeView::item {
                        min-height: 25px; /* 각 항목의 최소 높이를 25px로 설정하여 줄 간격 확보 */
                    }
                    QTreeView::item:hover:!selected {
                        background: transparent;
                        border: none;
                        outline: none;
                    }
                """)
        self.tree.setHeaderLabels(
            ["제조일자", "품목코드", "제품명", "시리얼번호", "제조코드", "발주번호", "납품상태"]
        )
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tree.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.setAnimated(True)

        self.tree.setUniformRowHeights(True)

        self.tree.itemDoubleClicked.connect(self.edit_product)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        self.tree.itemExpanded.connect(self.on_item_expanded)
        self.tree.itemCollapsed.connect(self.on_item_collapsed)

        header = self.tree.header()
        # ✅ [추가] 시그널 연결 및 화살표 강제 표시
        header.sortIndicatorChanged.connect(self.on_header_sort_changed)
        header.setSortIndicatorShown(True)
        for col in range(self.tree.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.tree.setColumnWidth(0, 100)    # 제조일자
        self.tree.setColumnWidth(1, 120)    # 품목코드
        self.tree.setColumnWidth(2, 600)    # 제품명
        self.tree.setColumnWidth(3, 300)    # 시리얼번호
        self.tree.setColumnWidth(4, 100)    # 제조코드
        self.tree.setColumnWidth(5, 120)    # 발주번호
        self.tree.setColumnWidth(6, 100)    # 납품상태

        if self.settings:
            self.restore_column_widths()
            self.restore_expanded_state()

        header.sectionResized.connect(self.save_column_widths)

        layout.addLayout(title_layout)
        layout.addWidget(self.tree)

        self.product_data = {}

    # ✅ 추가: 버튼 클릭 시 호출될 함수
    def toggle_show_all(self, checked: bool):
        """미납품/전체 보기 토글"""
        self.show_all_products = checked
        self.btn_show_all_products.setText("전체보기" if checked else "미납품만")
        self.load_product_list()

    def on_item_expanded(self, item):
        key = item.data(0, Qt.UserRole)
        if key:
            self.expanded_state[key] = True
            self.save_expanded_state()

    def on_item_collapsed(self, item):
        key = item.data(0, Qt.UserRole)
        if key:
            self.expanded_state[key] = False
            self.save_expanded_state()

    def save_expanded_state(self):
        if self.settings:
            self.settings.setValue("product_tree/expanded_state", self.expanded_state)

    def restore_expanded_state(self):
        if self.settings:
            saved_state = self.settings.value("product_tree/expanded_state")
            if saved_state:
                self.expanded_state = saved_state

    def save_column_widths(self):
        if not self.settings:
            return
        widths = []
        for col in range(self.tree.columnCount()):
            widths.append(self.tree.columnWidth(col))
        self.settings.setValue("product_table/column_widths", widths)

    def restore_column_widths(self):
        if not self.settings:
            return
        widths = self.settings.value("product_table/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < self.tree.columnCount():
                    self.tree.setColumnWidth(col, int(width))

    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        # 다중 선택 확인
        selected_items = self.tree.selectedItems()
        child_items = [i for i in selected_items if i.parent()]  # 자식 노드만

        menu = QtWidgets.QMenu(self)

        # ✅ [추가] 미확정(S/N 없음) 제품이 포함되어 있는지 확인
        unassigned_items = []
        for i in child_items:
            p_id = i.data(0, Qt.UserRole + 1)
            # S/N 컬럼(3번) 텍스트 확인
            sn_text = i.text(3)
            if "미확정" in sn_text or not sn_text:
                unassigned_items.append((p_id, i.text(1)))  # id, part_no

        if unassigned_items:
            assign_action = menu.addAction(f"시리얼 번호 부여 (확정) - {len(unassigned_items)}개")
            # part_no가 모두 같은지 확인 (다르면 불가)
            part_nos = {x[1] for x in unassigned_items}
            if len(part_nos) == 1:
                p_ids = [x[0] for x in unassigned_items]
                part_no = list(part_nos)[0]
                assign_action.triggered.connect(lambda: self.open_assign_dialog(p_ids, part_no))
            else:
                assign_action.setEnabled(False)
                assign_action.setText("시리얼 부여 (품목이 서로 다름)")

            menu.addSeparator()

        # 2. ✅ [신규] 확정된 제품 -> 시리얼 삭제(초기화) 메뉴
        assigned_items = []
        for i in child_items:
            p_id = i.data(0, Qt.UserRole + 1)
            sn_text = i.text(3)
            status_text = i.text(6)  # 납품상태 컬럼

            # 조건: S/N이 있고(미확정 아님) + 납품/소모/자체처리가 아닌 '재고' 상태여야 함
            is_assigned = (sn_text and "미확정" not in sn_text)
            is_stock = ("미납품" in status_text or "수리완료(재고)" in status_text)

            if is_assigned and is_stock:
                assigned_items.append(p_id)

        if assigned_items:
            reset_action = menu.addAction(f"시리얼 번호 삭제 (미확정으로 변경) - {len(assigned_items)}개")
            reset_action.triggered.connect(lambda: self.reset_serial_numbers(assigned_items))
            menu.addSeparator()

        # 개별 제품(자식 노드)을 클릭했을 때만 메뉴 표시
        if item and item.parent():
            edit_action = menu.addAction("수정")
            edit_action.triggered.connect(self.edit_product)

            # ✅ 수리 이력 관리 메뉴 추가
            menu.addSeparator()
            repair_action = menu.addAction("수리 이력 관리")
            repair_action.triggered.connect(self.open_repair_history)
            menu.addSeparator()

            delete_action = menu.addAction("삭제")
            delete_action.triggered.connect(self.delete_product)

        # 여러 개 선택 시 일괄 삭제 메뉴
        selected_items = self.tree.selectedItems()
        child_items = [item for item in selected_items if item.parent()]
        if len(child_items) > 1:
            if not menu.isEmpty():
                menu.addSeparator()
            delete_multiple_action = menu.addAction(f"선택한 {len(child_items)}개 삭제")
            delete_multiple_action.triggered.connect(self.delete_multiple_products)

        # ✅ [추가] 맨 아래에 시스템 관리용 메뉴 추가
        if not menu.isEmpty():
            menu.addSeparator()

        recalc_action = menu.addAction("🔄 재고-주문 할당 전체 재계산 (FIFO)")
        recalc_action.triggered.connect(self.run_recalculation)

        menu.exec_(self.tree.mapToGlobal(position))

        if not menu.isEmpty():
            menu.exec_(self.tree.mapToGlobal(position))

    # ✅ [추가] 재계산 실행 함수
    def run_recalculation(self):
        from ..db import recalculate_all_allocations

        reply = QMessageBox.question(
            self, "재고 재계산",
            "모든 미납품 재고의 주문 할당을 초기화하고,\n"
            "현재 미완료 주문의 납기일 순서(FIFO)대로 다시 할당합니다.\n\n"
            "계속 하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if recalculate_all_allocations():
                self.load_product_list()
                QMessageBox.information(self, "완료", "재고 할당이 재계산되었습니다.")
            else:
                QMessageBox.critical(self, "오류", "재계산 중 오류가 발생했습니다.")

    def reset_serial_numbers(self, product_ids):
        """(새 함수) 선택된 제품의 S/N 정보를 초기화합니다."""
        reply = QMessageBox.question(
            self, "시리얼 번호 삭제",
            f"선택한 {len(product_ids)}개 제품의 시리얼 번호와 제조일자 정보를 삭제하시겠습니까?\n\n"
            "삭제 후에는 '미확정 재고' 상태로 변경되어,\n"
            "나중에 다시 일괄 부여할 수 있습니다.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                reset_product_info_batch(product_ids)
                self.load_product_list()  # 목록 새로고침
                QMessageBox.information(self, "완료", "시리얼 번호가 삭제(초기화)되었습니다.")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"초기화 실패: {e}")

    def open_assign_dialog(self, product_ids, part_no):
        """S/N 부여 다이얼로그 실행"""
        dialog = AssignProductInfoDialog(self, product_ids, part_no)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            data = dialog.get_data()
            try:
                assign_product_info_batch(
                    product_ids,
                    data['date'],
                    data['code'],
                    data['start_sn']
                )
                self.load_product_list()
                QMessageBox.information(self, "완료", "제품 정보가 확정되었습니다.")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"저장 실패: {e}")

    def add_product_from_inventory(self, purchase_id, item_code, product_name, next_serial_no=None): # ✅ [수정]
        """(새 함수) 재고 현황 탭에서 호출하여 새 제품 추가 창을 엽니다."""
        prefill_data = {
            'purchase_id': purchase_id,
            'item_code': item_code,
            'product_name': product_name,
            'serial_no': next_serial_no # ✅ [추가]
        }
        # prefill_data를 전달하여 다이얼로그 생성
        dialog = ProductDialog(self, is_edit=False, prefill_data=prefill_data)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_product_list()


    def open_repair_history(self):
        product_data = self.get_selected_product()
        if not product_data:
            QtWidgets.QMessageBox.warning(self, "알림", "제품을 선택해주세요.")
            return

        product_id = product_data[0]
        serial_no = product_data[4]

        # 수리 이력 조회 및 새 수리 접수를 위한 다이얼로그
        # 별도의 '수리 이력' 창 대신, 바로 '수리 접수/수정' 창을 여는 방식으로 단순화
        # 가장 최근 수리 건을 바로 수정하거나, 없으면 새로 생성하도록 유도

        repairs = get_repairs_for_product(product_id)
        if repairs:
            # 가장 최근 수리 건 ID
            latest_repair_id = repairs[0][0]
            dialog = RepairDialog(self, repair_id=latest_repair_id, product_id=product_id, serial_no=serial_no)
            dialog.setWindowTitle(f"수리 이력 수정/조회 - {product_data[4]}")
        else:
            # 수리 이력이 없으면 새 접수 창 열기
            dialog = RepairDialog(self, product_id=product_id, serial_no=serial_no)
            dialog.setWindowTitle(f"새 수리 접수 - {product_data[4]}")

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            # 수리 관리 탭이 있다면 새로고침
            main_window = self.window()
            if hasattr(main_window, 'repair_widget'):
                main_window.repair_widget.load_repair_list()

    def load_product_list(self):
        try:
            from PySide6.QtGui import QBrush, QColor

            # 1. 색상 설정 (기존과 동일)
            comp_fg = QColor(self.settings.value("colors/product_completed_fg", "#888888"))
            comp_bg = QColor(self.settings.value("colors/product_completed_bg", "#F5F5F5"))
            incomp_fg = QColor(self.settings.value("colors/product_incomplete_fg", "#000000"))
            incomp_bg = QColor(self.settings.value("colors/product_incomplete_bg", "#FFFFFF"))
            repair_fg = QColor(self.settings.value("colors/product_repaired_fg", "#006633"))
            repair_bg = QColor(self.settings.value("colors/product_repaired_bg", "#E8F5E9"))

            conn = get_conn()
            cur = conn.cursor()

            # ✅ [수정] 14번째 컬럼: (TRIM 사용, = '수리완료'는 Python에서 처리)
            sql = """
                SELECT
                  pr.id,
                  pr.manufacture_date,
                  pr.part_no,
                  pr.product_name,
                  pr.serial_no,
                  pr.manufacture_code,
                  p.purchase_no,
                  pr.purchase_id,
                  CASE WHEN pr.delivery_id IS NOT NULL THEN 1 ELSE 0 END as is_delivered,
                  pr.delivered_at,
                  d.invoice_no as delivery_invoice,
                  pr.consumed_by_product_id,
                  EXISTS (SELECT 1 FROM products p_sub 
                          WHERE p_sub.consumed_by_product_id = pr.id) as is_assembly,
                  
                  -- ✅ [추가] 예약된 주문 번호 조회
                  (SELECT order_no FROM orders WHERE id = pr.reserved_order_id) as reserved_order_no,

                  (SELECT TRIM(r.status) FROM product_repairs r 
                   WHERE r.product_id = pr.id 
                   ORDER BY r.receipt_date DESC, r.id DESC LIMIT 1) as latest_repair_status

                FROM products pr
                LEFT JOIN purchases p ON pr.purchase_id = p.id
                LEFT JOIN deliveries d ON pr.delivery_id = d.id
            """

            order_clause = self.get_product_order_clause()
            sql += f" ORDER BY {order_clause}"

            cur.execute(sql)
            rows = cur.fetchall()

            # (그룹화)
            grouped_data = {}
            for row in rows:
                # ✅ [수정 1] 여기에도 reserved_order_no를 추가해야 합니다.
                (product_id, manufacture_date, part_no, product_name, serial_no, manufacture_code,
                 purchase_no, purchase_id, is_delivered, delivered_at, delivery_invoice,
                 consumed_by_product_id, is_assembly, reserved_order_no, latest_repair_status) = row

                key = (part_no or "미지정", purchase_no or "미지정")
                if key not in grouped_data: grouped_data[key] = []
                grouped_data[key].append(row)
            self.product_data = grouped_data
            self.tree.clear()

            # (필터링)
            data_to_display = {}
            if self.show_all_products:
                data_to_display = self.product_data
            else:
                for key, products in self.product_data.items():
                    purchase_id = products[0][7] if products else None
                    is_completed_for_filter = False
                    if purchase_id:
                        is_completed_for_filter = is_purchase_completed(purchase_id)
                    else:
                        delivered_count = sum(1 for p in products if p[8])
                        consumed_count = sum(1 for p in products if p[11] is not None)
                        total_count = len(products)
                        is_completed_for_filter = (
                                                              delivered_count + consumed_count == total_count) and total_count > 0

                    # ✅ [추가] '수리완료' 재고가 있으면 '미완료' 필터에서도 항상 표시
                    if not is_completed_for_filter:
                        # 4단계에서 추가한 '수리완료' 재고 표시 로직
                        for p in products:
                            status = p[13]  # latest_repair_status
                            is_delivered = p[8]
                            is_consumed = p[11] is not None
                            if status and '수리완료' in status and not is_delivered and not is_consumed:
                                is_completed_for_filter = False  # (미완료 목록에 포함)
                                break  # 하나라도 있으면 통과

                    if not is_completed_for_filter:
                        data_to_display[key] = products

            # (트리 생성 - 부모)
            for (part_no, purchase_no), products in data_to_display.items():
                serial_numbers = [p[4] for p in products if p[4]];
                serial_range = "시리얼 없음"
                if serial_numbers:
                    serial_numbers.sort();
                    serial_range = f"{serial_numbers[0]} ~ {serial_numbers[-1]}"
                delivered_count = sum(1 for p in products if p[8])
                consumed_count = sum(1 for p in products if p[11] is not None)
                total_count = len(products)
                delivery_status = f"{delivered_count + consumed_count}/{total_count}"
                if consumed_count > 0: delivery_status += f" (소모 {consumed_count}개)"
                purchase_id = products[0][7] if products else None
                is_complete = False
                if purchase_id:
                    conn_inner = get_conn();
                    cur_inner = conn_inner.cursor()
                    cur_inner.execute("SELECT status FROM purchases WHERE id = ?", (purchase_id,))
                    result = cur_inner.fetchone();
                    conn_inner.close()
                    if result and result[0] == '완료': is_complete = True
                if not is_complete:
                    is_complete = (delivered_count + consumed_count == total_count) and total_count > 0
                parent_item = QTreeWidgetItem(self.tree)
                parent_item.setText(0, products[0][1] or "");
                parent_item.setText(1, part_no)
                parent_item.setText(2, products[0][3] or "");
                parent_item.setText(3, f"{serial_range} ({total_count}개)")
                parent_item.setText(4, products[0][5] or "");
                parent_item.setText(5, purchase_no)
                parent_item.setText(6, delivery_status)
                p_fg = comp_fg if is_complete else incomp_fg;
                p_bg = comp_bg if is_complete else incomp_bg
                bold_font = parent_item.font(0);
                bold_font.setBold(True)
                for col in range(self.tree.columnCount()):
                    parent_item.setForeground(col, QBrush(p_fg));
                    parent_item.setBackground(col, QBrush(p_bg));
                    parent_item.setFont(col, bold_font)
                parent_key = f"{part_no}|{purchase_no}";
                parent_item.setData(0, Qt.UserRole, parent_key)

                # (트리 생성 - 자식)
                for product in products:
                    # ✅ [수정] reserved_order_no 변수 추가 (15개 항목 언패킹)
                    (product_id, manufacture_date, part_no, product_name, serial_no, manufacture_code,
                     purchase_no, purchase_id, is_delivered, delivered_at, delivery_invoice,
                     consumed_by_product_id, is_assembly, reserved_order_no, latest_repair_status) = product

                    is_consumed = (consumed_by_product_id is not None)

                    # ✅ [추가] 자체처리 여부 판단 (공백 제거 안전장치 포함)
                    is_self_handled = (latest_repair_status and '자체처리' in latest_repair_status)

                    # ✅ [추가] 재출고 여부 판단
                    is_redelivered = (latest_repair_status and '재출고' in latest_repair_status)

                    child_item = QTreeWidgetItem(parent_item)
                    child_item.setText(0, manufacture_date or "");
                    child_item.setText(1, part_no or "")

                    display_name = product_name or ""

                    # ✅ [수정] 제품명 옆 상태 표시 로직 (재출고 추가)
                    if latest_repair_status:
                        if '수리완료' in latest_repair_status:
                            display_name += " (수리완료)"
                        elif '자체처리' in latest_repair_status:
                            display_name += " (자체처리)"
                        elif '재출고' in latest_repair_status:
                            # 사용자 요청대로 표시
                            display_name += " (수리완료: 재출고)"
                        else:
                            display_name += f" (수리중: {latest_repair_status})"

                    # ✅ [수정] S/N 및 제조코드 표시
                    if serial_no:
                        child_item.setText(3, serial_no)
                        child_item.setText(4, manufacture_code or "")
                    else:
                        # S/N이 없으면 '미확정' 표시 및 강조
                        child_item.setText(3, "(미확정 재고)")
                        child_item.setText(4, "-")
                        # 폰트 색상 변경 (예: 파란색)
                        child_item.setForeground(3, QBrush(QColor("#0066cc")))

                    if is_assembly:
                        display_name += " (조립품)"

                    child_item.setText(2, display_name)
                    # ✅ [수정] S/N이 없으면 '미확정' 표시 및 파란색 강조
                    if serial_no:
                        child_item.setText(3, serial_no)
                        child_item.setText(4, manufacture_code or "")
                    else:
                        child_item.setText(3, "(미확정 재고)")
                        child_item.setText(4, "-")
                        child_item.setForeground(3, QBrush(QColor("#0066cc")))  # 파란색

                    child_item.setText(5, purchase_no or "")

                    # ✅ [수정] 납품상태 컬럼 처리 (재출고 추가)
                    if is_delivered:
                        status_text = "납품됨"
                        if delivery_invoice: status_text += f" ({delivery_invoice})"
                        child_item.setText(6, status_text)
                    elif is_consumed:
                        status_text = "소모됨 (조립)"
                        child_item.setText(6, status_text)
                    elif is_self_handled:
                        child_item.setText(6, "자체처리 완료")
                    elif is_redelivered:
                        # 재출고도 납품 완료된 것으로 표시
                        child_item.setText(6, "재출고 완료")
                    else:
                        status_text = "미납품"
                        if latest_repair_status and '수리완료' in latest_repair_status:
                            status_text = "수리완료(재고)"

                        # ✅ [추가] 예약 정보 표시
                        if reserved_order_no:
                            status_text += f" [예약: {reserved_order_no}]"
                        else:
                            status_text += " [자유재고]"

                        child_item.setText(6, status_text)

                        # ✅ [추가] 예약된 재고는 텍스트 색상을 보라색 등으로 표시
                    if reserved_order_no and not is_delivered:
                        child_item.setForeground(6, QBrush(QColor("#6f42c1")))  # 보라색

                    # ✅ [수정] 색상 처리 (재출고도 완료 색상 적용)
                    # 납품됨 / 소모됨 / 자체처리 / 재출고 -> 모두 완료 색상
                    is_complete = is_delivered or is_consumed or is_self_handled or is_redelivered

                    c_fg = comp_fg;
                    c_bg = comp_bg

                    if is_complete:
                        c_fg, c_bg = comp_fg, comp_bg
                    elif latest_repair_status and '수리완료' in latest_repair_status:
                        c_fg, c_bg = repair_fg, repair_bg
                    else:
                        c_fg, c_bg = incomp_fg, incomp_bg

                    for col in range(self.tree.columnCount()):
                        child_item.setForeground(col, QBrush(c_fg));
                        child_item.setBackground(col, QBrush(c_bg))
                    child_item.setData(0, Qt.UserRole + 1, product_id)

                # (펼침 상태 복원)
                if parent_key in self.expanded_state:
                    parent_item.setExpanded(self.expanded_state[parent_key])
                else:
                    if any(p[8] == 0 for p in products):
                        parent_item.setExpanded(True)
                    else:
                        parent_item.setExpanded(False)

            # (정렬 기능 활성화)
            self.tree.setSortingEnabled(True)
            with QSignalBlocker(self.tree.header()):
                self.tree.header().setSortIndicator(self.current_sort_column, self.current_sort_order)

        except Exception as e:
            print(f"제품 목록 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.product_data = {}
            self.tree.clear()

    def get_product_order_clause(self):
        """(새 함수) 제품 생산 트리의 정렬 기준을 SQL ORDER BY 절로 변환"""
        # ["제조일자", "품목코드", "제품명", "시리얼번호", "제조코드", "발주번호", "납품상태"]
        column_names = [
            "pr.manufacture_date",  # 0
            "pr.part_no",  # 1
            "pr.product_name",  # 2
            "pr.serial_no",  # 3
            "pr.manufacture_code",  # 4
            "p.purchase_no",  # 5
            "is_delivered"  # 6
        ]

        if 0 <= self.current_sort_column < len(column_names):
            column = column_names[self.current_sort_column]
            # QTreeWidget은 그룹(부모) 정렬이 아닌 개별 항목(자식) 기준으로 정렬해야 함
            direction = "DESC" if self.current_sort_order == Qt.DescendingOrder else "ASC"
        else:  # 기본값
            column = "p.purchase_no"
            direction = "DESC"

        # 2차, 3차 정렬 기준
        return f"{column} {direction}, pr.part_no ASC, pr.serial_no ASC"

    def on_header_sort_changed(self, column_index, order):
        """(새 함수) 제품 생산 트리 헤더의 정렬 표시기가 변경될 때 호출됩니다."""

        # 1. 현재 상태와 동일하면 (load_due_list에 의한 프로그래밍 방식 호출), 무시
        if self.current_sort_column == column_index and self.current_sort_order == order:
            return

        # 2. 사용자 클릭에 의한 변경이므로, 새 정렬 상태를 저장
        self.current_sort_column = column_index
        self.current_sort_order = order

        # 3. 새 정렬 상태를 QSettings에 저장
        self.settings.setValue("product_tree/sort_column", self.current_sort_column)
        self.settings.setValue("product_tree/sort_order", self.current_sort_order)

        # 4. SQL 정렬을 다시 적용하기 위해 목록 새로고침
        self.load_product_list()


    def get_selected_product(self):
        current_item = self.tree.currentItem()
        if not current_item or not current_item.parent():
            return None

        product_id = current_item.data(0, Qt.UserRole + 1)
        if not product_id:
            return None

        try:
            conn = get_conn()
            cur = conn.cursor()
            sql = """
                SELECT
                  pr.id,
                  pr.manufacture_date,
                  pr.part_no,
                  pr.product_name,
                  pr.serial_no,
                  pr.manufacture_code,
                  p.purchase_no,
                  pr.purchase_id,
                  CASE WHEN pr.delivery_id IS NOT NULL THEN 1 ELSE 0 END as is_delivered,
                  pr.delivered_at,
                  d.invoice_no as delivery_invoice,
                  pr.consumed_by_product_id,
                  EXISTS (SELECT 1 FROM products p_sub WHERE p_sub.consumed_by_product_id = pr.id) as is_assembly /* [추가] */
                FROM products pr
                LEFT JOIN purchases p ON pr.purchase_id = p.id
                LEFT JOIN deliveries d ON pr.delivery_id = d.id
                WHERE pr.id = ?
            """
            cur.execute(sql, (product_id,))
            return cur.fetchone()
        except Exception as e:
            print(f"제품 정보 조회 오류: {e}")
            return None

    def add_product(self):
        dialog = ProductDialog(self, is_edit=False)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_product_list()

    def edit_product(self):
        """제품 수정 (다중 선택 지원)"""
        selected_items = self.tree.selectedItems()

        child_items = [item for item in selected_items if item.parent()]

        if not child_items:
            QtWidgets.QMessageBox.information(self, "알림", "수정할 제품을 선택해주세요.")
            return

        if len(child_items) == 1:
            product_id = child_items[0].data(0, Qt.UserRole + 1)
            if not product_id:
                return

            try:
                conn = get_conn()
                cur = conn.cursor()
                sql = """
                    SELECT
                      pr.id,
                      pr.manufacture_date,
                      pr.part_no,
                      pr.product_name,
                      pr.serial_no,
                      pr.manufacture_code,
                      p.purchase_no,
                      pr.purchase_id,
                      CASE WHEN pr.delivery_id IS NOT NULL THEN 1 ELSE 0 END as is_delivered,
                      pr.delivered_at,
                      d.invoice_no as delivery_invoice,
                      pr.consumed_by_product_id,
                      EXISTS (SELECT 1 FROM products p_sub WHERE p_sub.consumed_by_product_id = pr.id) as is_assembly /* [추가] */
                    FROM products pr
                    LEFT JOIN purchases p ON pr.purchase_id = p.id
                    LEFT JOIN deliveries d ON pr.delivery_id = d.id
                    WHERE pr.id = ?
                """
                cur.execute(sql, (product_id,))
                product_data = cur.fetchone()
                conn.close()

                if product_data:
                    dialog = ProductDialog(self, is_edit=True, product_data=product_data)
                    if dialog.exec() == QtWidgets.QDialog.Accepted:
                        self.load_product_list()
            except Exception as e:
                print(f"제품 정보 조회 오류: {e}")
                return

        else:
            self.edit_multiple_products(child_items)

    def edit_multiple_products(self, child_items):
        """여러 제품 일괄 수정"""
        product_ids = []
        for item in child_items:
            product_id = item.data(0, Qt.UserRole + 1)
            if product_id:
                product_ids.append(product_id)

        if not product_ids:
            return

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"제품 일괄 수정 ({len(product_ids)}개)")
        dialog.setMinimumWidth(600)

        form = QtWidgets.QFormLayout(dialog)

        info_label = QtWidgets.QLabel(f"선택된 {len(product_ids)}개 제품의 공통 속성을 수정합니다.")
        info_label.setStyleSheet("font-weight: bold; color: #0066cc;")
        form.addRow(info_label)

        form.addRow(QtWidgets.QLabel(""))

        cb_update_date = QtWidgets.QCheckBox("제조일자 변경")
        edt_manufacture_date = QtWidgets.QLineEdit()
        edt_manufacture_date.setPlaceholderText("예: 2025-08-27")
        edt_manufacture_date.setEnabled(False)
        cb_update_date.toggled.connect(edt_manufacture_date.setEnabled)

        form.addRow(cb_update_date, edt_manufacture_date)

        cb_update_code = QtWidgets.QCheckBox("제조코드 변경")
        edt_manufacture_code = QtWidgets.QLineEdit()
        edt_manufacture_code.setPlaceholderText("예: 2534 (제조일자 입력 시 자동 생성)")
        edt_manufacture_code.setEnabled(False)

        def auto_generate_manufacture_code():
            if cb_update_code.isChecked():
                return
            date_text = edt_manufacture_date.text().strip()
            if not date_text:
                return
            parsed_date = parse_date_text(date_text)
            if parsed_date:
                try:
                    date_obj = datetime.strptime(parsed_date, "%Y-%m-%d")
                    year_code = str(date_obj.year)[-2:]
                    iso_year, iso_week, iso_weekday = date_obj.isocalendar()
                    if iso_year != date_obj.year:
                        year_code = str(iso_year)[-2:]
                    week_code = f"{iso_week:02d}"
                    manufacture_code = year_code + week_code
                    edt_manufacture_code.setText(manufacture_code)
                    edt_manufacture_code.setStyleSheet("background-color: #fffacd;")
                    edt_manufacture_code.setToolTip(f"✓ 자동 생성됨 (수동 변경하려면 '제조코드 변경' 체크)")
                except Exception as e:
                    print(f"제조코드 자동 생성 오류: {e}")

        def on_code_checkbox_toggled(checked):
            edt_manufacture_code.setEnabled(checked)
            if checked:
                edt_manufacture_code.setStyleSheet("")
                edt_manufacture_code.setToolTip("수동 입력 모드")
            else:
                auto_generate_manufacture_code()

        cb_update_code.toggled.connect(on_code_checkbox_toggled)
        edt_manufacture_date.textChanged.connect(auto_generate_manufacture_code)

        form.addRow(cb_update_code, edt_manufacture_code)

        cb_update_purchase = QtWidgets.QCheckBox("발주번호 연결 변경")
        purchase_combo = QtWidgets.QComboBox()
        purchase_combo.addItem("연결 해제", None)

        try:
            purchases = get_available_purchases()
            for purchase_id, purchase_no, purchase_desc, qty, purchase_dt in purchases:
                display_text = f"{purchase_no} - {purchase_desc} (수량: {qty}, 발주일: {purchase_dt})"
                purchase_combo.addItem(display_text, purchase_id)
        except Exception as e:
            print(f"발주 목록 로드 실패: {e}")

        purchase_combo.setEnabled(False)
        cb_update_purchase.toggled.connect(purchase_combo.setEnabled)

        form.addRow(cb_update_purchase, purchase_combo)

        form.addRow(QtWidgets.QLabel(""))

        preview_label = QtWidgets.QLabel("수정할 제품 목록:")
        preview_label.setStyleSheet("font-weight: bold;")
        form.addRow(preview_label)

        preview_text = QtWidgets.QTextEdit()
        preview_text.setMaximumHeight(150)
        preview_text.setReadOnly(True)

        try:
            conn = get_conn()
            cur = conn.cursor()
            preview_lines = []
            for i, product_id in enumerate(product_ids[:10], 1):
                cur.execute("""
                    SELECT part_no, product_name, serial_no, manufacture_date
                    FROM products WHERE id = ?
                """, (product_id,))
                result = cur.fetchone()
                if result:
                    part_no, product_name, serial_no, manufacture_date = result
                    preview_lines.append(f"{i}. {part_no} - {serial_no} ({manufacture_date})")
            if len(product_ids) > 10:
                preview_lines.append(f"... 외 {len(product_ids) - 10}개")
            preview_text.setPlainText("\n".join(preview_lines))
            conn.close()
        except Exception as e:
            preview_text.setPlainText(f"미리보기 로드 실패: {e}")

        form.addRow(preview_text)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        form.addRow(btns)

        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return

        try:
            conn = get_conn()
            cur = conn.cursor()
            updated_count = 0
            for product_id in product_ids:
                updates = []
                params = []
                if cb_update_date.isChecked():
                    date_text = edt_manufacture_date.text().strip()
                    parsed_date = parse_date_text(date_text) if date_text else None
                    if parsed_date:
                        updates.append("manufacture_date = ?")
                        params.append(parsed_date)
                        if not cb_update_code.isChecked():
                            code_text = edt_manufacture_code.text().strip()
                            if code_text:
                                updates.append("manufacture_code = ?")
                                params.append(code_text)
                if cb_update_code.isChecked():
                    code_text = edt_manufacture_code.text().strip()
                    if code_text:
                        updates.append("manufacture_code = ?")
                        params.append(code_text)
                if cb_update_purchase.isChecked():
                    purchase_id = purchase_combo.currentData()
                    updates.append("purchase_id = ?")
                    params.append(purchase_id)
                if updates:
                    sql = f"UPDATE products SET {', '.join(updates)} WHERE id = ?"
                    params.append(product_id)
                    cur.execute(sql, tuple(params))
                    updated_count += 1
            conn.commit()
            conn.close()
            self.load_product_list()
            QtWidgets.QMessageBox.information(
                self, "완료",
                f"총 {updated_count}개 제품이 수정되었습니다."
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "오류",
                f"제품 일괄 수정 중 오류가 발생했습니다:\n{str(e)}"
            )

    def delete_product(self):
        product_data = self.get_selected_product()
        if not product_data:
            QtWidgets.QMessageBox.information(self, "알림", "삭제할 제품을 선택해주세요.")
            return

        product_id, manufacture_date, part_no, product_name, serial_no, manufacture_code, \
            purchase_no, purchase_id, is_delivered, delivered_at, delivery_invoice, \
            consumed_by_product_id, is_assembly = product_data  # ✅ 13개 항목

        reply = QtWidgets.QMessageBox.question(
            self,
            "제품 삭제",
            f"정말로 다음 제품을 삭제하시겠습니까?\n\n"
            f"품목코드: {part_no}\n"
            f"제품명: {product_name}\n"
            f"시리얼번호: {serial_no}\n"
            f"제조일자: {manufacture_date}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            conn = get_conn()
            cur = conn.cursor()

            # [추가] 1. 이 제품(부모)에 연결된 부품(자식)들의 재고를 복구
            cur.execute("UPDATE products SET consumed_by_product_id = NULL WHERE consumed_by_product_id = ?",
                        (product_id,))

            # 2. 부모 제품 삭제 (기존 로직)
            cur.execute("DELETE FROM products WHERE id=?", (product_id,))
            conn.commit()
            conn.close()
            self.load_product_list()
            QtWidgets.QMessageBox.information(
                self, "완료",
                f"품목코드: {part_no}\n제품명: {product_name}\n시리얼번호: '{serial_no}'\n삭제되었습니다."
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"제품 삭제 중 오류가 발생했습니다:\n{str(e)}")

    def delete_multiple_products(self):
        selected_items = self.tree.selectedItems()
        child_items = [item for item in selected_items if item.parent()]

        if not child_items:
            QtWidgets.QMessageBox.information(self, "알림", "삭제할 제품을 선택해주세요.")
            return

        product_ids = []
        for item in child_items:
            product_id = item.data(0, Qt.UserRole + 1)
            if product_id:
                product_ids.append(product_id)

        if not product_ids:
            return

        product_count = len(product_ids)
        preview_count = min(5, product_count)
        preview_text = ""
        for i, product_id in enumerate(product_ids[:preview_count]):
            item = child_items[i]
            part_no = item.text(1)
            serial_no = item.text(3)
            preview_text += f"  • {part_no} - '{serial_no}'\n"
        if product_count > preview_count:
            preview_text += f"  ... 외 {product_count - preview_count}개"

        reply = QtWidgets.QMessageBox.question(
            self,
            "제품 일괄 삭제",
            f"정말로 선택한 {product_count}개의 제품을 삭제하시겠습니까?\n\n"
            f"{preview_text}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            conn = get_conn()
            cur = conn.cursor()
            deleted_count = 0
            for product_id in product_ids:
                # [추가] 1. 부품 재고 복구 (연결 해제)
                cur.execute("UPDATE products SET consumed_by_product_id = NULL WHERE consumed_by_product_id = ?",
                            (product_id,))

                # 2. 부모 제품 삭제
                cur.execute("DELETE FROM products WHERE id=?", (product_id,))
                deleted_count += 1
            conn.commit()
            conn.close()
            self.load_product_list()
            QtWidgets.QMessageBox.information(
                self, "완료",
                f"총 {deleted_count}개의 제품이 삭제되었습니다."
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"제품 삭제 중 오류가 발생했습니다:\n{str(e)}")


class ProductDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, is_edit=False, product_data=None, prefill_data=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.product_data = product_data
        self.prefill_data = prefill_data  # ✅ [추가]
        self.current_product_info = None

        self.bom_requirements = []  # ✅ [추가] 이 제품에 필요한 BOM 요구사항
        self.bom_stock = {}  # ✅ [추가] 필요한 부품들의 현재 재고
        self.bom_widgets = {}  # ✅ [추가] 동적으로 생성된 BOM 위젯들

        self.setup_ui()

        if is_edit and product_data:
            self.load_product_data()

        if self.prefill_data:  # ✅ [추가]
            self.apply_prefill_data()

    def setup_ui(self):
        title = "제품 수정" if self.is_edit else "새 제품 추가"
        self.setWindowTitle(title)
        self.setMinimumWidth(700)

        form = QtWidgets.QFormLayout(self)

        self.edt_manufacture_date = QtWidgets.QLineEdit()
        self.edt_manufacture_date.setPlaceholderText("예: 2025-08-27 / 2025/8/27")

        self.edt_manufacture_date.textChanged.connect(self.on_manufacture_date_changed)

        self.edt_item_code = AutoCompleteLineEdit()
        self.edt_item_code.setPlaceholderText("품목코드 입력 또는 검색")
        self.edt_item_code.product_selected.connect(self.on_product_selected)

        self.edt_product_name = QtWidgets.QLineEdit()
        self.edt_product_name.setMinimumWidth(400)

        self.edt_serial_no = QtWidgets.QLineEdit()
        self.edt_serial_no.setPlaceholderText("비워두면 자동 생성 (KT001~KT999)")

        # [추가] 사용자가 직접 S/N을 수정하면 강조(노란색) 제거
        self.edt_serial_no.textChanged.connect(lambda: self.edt_serial_no.setStyleSheet(""))

        self.edt_manufacture_code = QtWidgets.QLineEdit()
        self.edt_manufacture_code.setPlaceholderText("예: 2534 (YY주차) - 제조일자 입력 시 자동 생성")

        self.sp_production_qty = QtWidgets.QSpinBox()
        self.sp_production_qty.setRange(1, 1_000_000)
        self.sp_production_qty.setValue(1)
        self.sp_production_qty.setGroupSeparatorShown(True)

        qty_note = QtWidgets.QLabel("※ 생산수량만큼 개별 제품이 생성되며, 시리얼번호(KT001~KT999)가 자동 할당됩니다.")
        qty_note.setStyleSheet("color: #666; font-size: 10px;")
        qty_note.setWordWrap(True)

        # ✅ [수정] 신규 모드일 때는 날짜/S/N 입력란 숨김 처리
        if self.is_edit:
            form.addRow("제조일자", self.edt_manufacture_date)

        form.addRow("품목코드*", self.edt_item_code)
        form.addRow("제품명*", self.edt_product_name)

        if self.is_edit:
            form.addRow("시리얼번호", self.edt_serial_no)
            form.addRow("제조코드", self.edt_manufacture_code)

        if not self.is_edit:
            form.addRow("생산수량", self.sp_production_qty)
            # 안내 문구 추가
            info_lbl = QLabel("※ 신규 생산 시 S/N은 부여되지 않습니다. (나중에 우클릭으로 확정)")
            info_lbl.setStyleSheet("color: #666; font-size: 11px;")
            form.addRow("", info_lbl)

        # ✅ [추가 시작] 생산 방식 선택 (BOM이 있을 때만 보임)
        self.production_mode_group = QtWidgets.QGroupBox("생산 방식")
        mode_layout = QtWidgets.QHBoxLayout(self.production_mode_group)
        self.radio_simple = QtWidgets.QRadioButton("단순 생산 (재고 소모 없음)")
        self.radio_assembly = QtWidgets.QRadioButton("조립 생산 (BOM 부품 재고 소모)")
        self.radio_simple.setChecked(True)
        mode_layout.addWidget(self.radio_simple)
        mode_layout.addWidget(self.radio_assembly)
        self.production_mode_group.setVisible(False)  # 기본값은 숨김

        # 라디오 버튼 클릭 시 UI 변경
        self.radio_simple.toggled.connect(self.on_production_mode_changed)

        form.addRow(self.production_mode_group)
        # ✅ [추가 끝]

        # ✅ [추가 시작] BOM 부품 선택 그룹
        self.bom_group = QtWidgets.QGroupBox("BOM 부품 선택 (조립)")
        self.bom_layout = QtWidgets.QVBoxLayout(self.bom_group)
        self.bom_group.setVisible(False)  # 기본값은 숨김
        form.addRow(self.bom_group)
        # ✅ [추가 끝]

        form.addRow(QtWidgets.QLabel(""))
        purchase_label = QtWidgets.QLabel("연결할 발주:")
        purchase_label.setStyleSheet("font-weight: bold;")
        form.addRow(purchase_label)

        self.purchase_combo = QtWidgets.QComboBox()
        self.purchase_combo.addItem("선택 안함", None)
        self.load_available_purchases()
        self.purchase_combo.currentIndexChanged.connect(self.on_purchase_selected)

        self.lbl_purchase_info = QtWidgets.QLabel("")
        self.lbl_purchase_info.setStyleSheet("color: #666; font-size: 11px;")
        self.lbl_purchase_info.setWordWrap(True)

        form.addRow("발주번호:", self.purchase_combo)
        form.addRow("", self.lbl_purchase_info)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept_dialog)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def on_product_selected(self, product_info):
        """품목 마스터에서 제품 선택 시 (조립품인지 확인)"""
        self.current_product_info = product_info
        self.edt_product_name.setText(product_info['product_name'])

        # ✅ [추가 시작] 다음 추천 시리얼 번호 자동 조회
        item_code = product_info.get('item_code')
        if item_code and not self.is_edit:  # 수정 모드가 아닐 때만
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("""
                            SELECT serial_no FROM products
                            WHERE serial_no LIKE 'KT%' AND part_no = ?
                            AND consumed_by_product_id IS NULL
                            ORDER BY CAST(SUBSTR(serial_no, 3) AS INTEGER) DESC LIMIT 1
                        """, (item_code,))
                result = cur.fetchone()
                conn.close()

                if result and result[0]:
                    last_num = int(result[0][2:])
                    next_num = (last_num % 999) + 1
                else:
                    next_num = 1

                next_serial_no = f"KT{next_num:03d}"

                self.edt_serial_no.setText(next_serial_no)
                self.edt_serial_no.setPlaceholderText(f"추천 S/N: {next_serial_no}. (비워두면 자동 생성)")
                self.edt_serial_no.setStyleSheet("background-color: #fffacd;")  # 강조

            except Exception as e:
                print(f"다음 시리얼 번호 조회 오류: {e}")
                self.edt_serial_no.setText("")
                self.edt_serial_no.setStyleSheet("")  # 스타일 초기화
        # ✅ [추가 끝]

        if self.is_edit:  # 수정 모드에서는 BOM 로드 안 함
            return

        # 1. BOM 요구사항 확인
        self.bom_requirements = get_bom_requirements(product_info['item_code'])

        # 2. BOM 요구사항이 없으면 (단순 생산품)
        if not self.bom_requirements:
            self.bom_group.setVisible(False)
            self.sp_production_qty.setEnabled(True)  # 다중 생산 가능
            self.sp_production_qty.setValue(1)
            # (S/N 자동 생성 로직은 '재고 현황'에서 넘어올 때만 필요하므로, 여기서는 삭제)
            return

        # 3. BOM 요구사항이 있으면 (조립품)
        # ✅ [수정] BOM 그룹 대신 '생산 방식 선택' 라디오 버튼을 표시
        self.production_mode_group.setVisible(True)

        # ✅ [수정] '단순 생산'을 기본값으로 설정
        self.radio_simple.setChecked(True)

        # ✅ [수정] 조립 UI(bom_group)는 숨기고, 수량 입력은 활성화 (단순 생산이 기본이므로)
        self.bom_group.setVisible(False)
        self.sp_production_qty.setEnabled(True)
        self.sp_production_qty.setValue(1)

        # 4. 필요한 부품들의 현재 재고 조회
        child_codes = [req['child_code'] for req in self.bom_requirements]
        self.bom_stock = get_available_stock_for_bom(child_codes)

        # 5. BOM UI 동적 생성
        self.build_bom_ui()

    def on_production_mode_changed(self):
        """(새 함수) 생산 방식 라디오 버튼 클릭 시 UI 상태 변경"""
        is_assembly = self.radio_assembly.isChecked()

        # 1. BOM 그룹 (부품 선택)
        self.bom_group.setVisible(is_assembly)

        # 2. 생산 수량
        self.sp_production_qty.setEnabled(not is_assembly)  # 조립은 1개, 단순생산은 N개
        if is_assembly:
            self.sp_production_qty.setValue(1)

        # 3. ✅ [수정] "연결할 발주" (조립 시에도 활성화)
        # self.purchase_combo.setEnabled(not is_assembly) # ⬅️ [제거]
        self.lbl_purchase_info.setEnabled(True) # ⬅️ [수정] 항상 활성화
        if is_assembly:
            # self.purchase_combo.setCurrentIndex(0) # ⬅️ [제거]
            self.lbl_purchase_info.setText("조립품을 연결할 발주서를 선택하세요.\n(소모되는 부품과는 별개입니다)")
            self.lbl_purchase_info.setStyleSheet("color: #0066cc; font-size: 11px;")
        else:
            # 단순 생산 시, 발주 정보 다시 로드 (on_purchase_selected가 트리거됨)
            self.on_purchase_selected()

    def build_bom_ui(self):
        """(새 함수) 조회된 BOM 요구사항과 재고를 바탕으로 UI를 동적 생성"""

        # 1. 기존 위젯 삭제 및 레이아웃 비우기
        for widget in self.bom_widgets.values():
            widget.deleteLater()
        self.bom_widgets = {}

        while self.bom_layout.count():
            item = self.bom_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            layout = item.layout()  # ⬅︎ [추가] 레이아웃도 삭제
            if layout:
                # [추가] 레이아웃 내 위젯들도 삭제
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                layout.deleteLater()

        # 2. ✅ [수정] 수직 레이아웃(v_layout)을 다시 추가
        v_layout = QtWidgets.QVBoxLayout()
        self.bom_layout.addLayout(v_layout)

        for req in self.bom_requirements:
            child_code = req['child_code']
            qty_req = req['qty_req']
            name = req['name']

            stock_list = self.bom_stock.get(child_code, [])

            # ✅ [수정] 'label_text' 변수 정의
            label_text = f"<b>{name} ({child_code})</b> - 필요 수량: {qty_req}개"

            # 재고가 없는 경우
            if not stock_list:
                label_text += " <font color='red'>(재고 없음!)</" "font>"
                v_layout.addWidget(QLabel(label_text))
                continue

            # ✅ [추가] 품목 유형(item_type) 확인 (첫 번째 재고 아이템 기준)
            item_type = stock_list[0].get('item_type', 'SELLABLE')

            if item_type == 'SELLABLE':
                label_text += " <font color='#0066cc'>(판매/조립품: S/N 뒷번호 사용 권장)</font>"
            else:
                label_text += " <font color='#666'>(순수 하위 부품: S/N 앞번호 사용 권장)</font>"

            v_layout.addWidget(QLabel(label_text))  # ✅ 라벨 위젯 추가

            # 재고가 있는 경우 (QListWidget으로 변경)
            list_widget = QtWidgets.QListWidget()
            list_widget.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

            # ✅ [수정] 리스트 높이를 동적으로 설정 (최대 6줄)
            row_height = 25  # 항목당 예상 높이
            # 재고 리스트의 길이와 6줄 중 작은 값을 택함 (최소 2줄 높이 보장)
            list_height = max(2 * row_height, min(len(stock_list) * row_height, 6 * row_height))
            list_widget.setStyleSheet(f"min-height: {list_height}px; max-height: {list_height}px;")

            for stock_item in stock_list:
                # {product_id, serial_no, name}
                list_item = QtWidgets.QListWidgetItem(f"{stock_item['serial_no']} - {stock_item['name']}")
                list_item.setData(Qt.UserRole, stock_item['product_id'])
                list_widget.addItem(list_item)

            v_layout.addWidget(list_widget)  # ✅ QVBoxLayout에 추가
            self.bom_widgets[child_code] = list_widget

        v_layout.addStretch()  # 남는 공간 확보

    def on_manufacture_date_changed(self):
        date_text = self.edt_manufacture_date.text().strip()
        if not date_text:
            return

        parsed_date = parse_date_text(date_text)
        if parsed_date:
            try:
                date_obj = datetime.strptime(parsed_date, "%Y-%m-%d")
                year_code = str(date_obj.year)[-2:]
                iso_year, iso_week, iso_weekday = date_obj.isocalendar()

                if iso_year != date_obj.year:
                    year_code = str(iso_year)[-2:]

                week_code = f"{iso_week:02d}"
                manufacture_code = year_code + week_code
                self.edt_manufacture_code.setText(manufacture_code)
            except Exception as e:
                print(f"제조코드 생성 오류: {e}")
                self.edt_manufacture_code.setText("")

    def on_purchase_selected(self):
        purchase_id = self.purchase_combo.currentData()
        if purchase_id:
            try:
                # ✅ [추가] 현재 폼에 입력된 품목코드 가져오기
                # (재고 현황에서 넘어온 경우, 이 필드는 채워져 있음)
                item_code_filter = self.edt_item_code.text().strip() or None

                # ✅ [수정] 헬퍼 함수 호출 시 품목코드 전달
                purchase_info = get_purchase_info(purchase_id, item_code=item_code_filter)

                if purchase_info:
                    purchase_no, purchase_desc, total_qty, unit_price_cents = purchase_info

                    # ✅ [수정] 헬퍼 함수 호출 시 품목코드 전달
                    produced_qty = get_produced_quantity(purchase_id, item_code=item_code_filter)
                    remaining_qty = total_qty - produced_qty

                    info_text = f"발주내용: {purchase_desc}\n"
                    info_text += f"총 발주량: {total_qty}개\n"
                    info_text += f"기 생산량: {produced_qty}개\n"
                    info_text += f"미생산량: {remaining_qty}개"

                    if remaining_qty <= 0:
                        info_text += " (⚠️ 이미 모든 수량이 생산됨)"
                        self.lbl_purchase_info.setStyleSheet("color: #d63384; font-size: 11px;")
                    elif remaining_qty < total_qty * 0.2:
                        info_text += " (⚠️ 생산 완료 임박)"
                        self.lbl_purchase_info.setStyleSheet("color: #fd7e14; font-size: 11px;")
                    else:
                        self.lbl_purchase_info.setStyleSheet("color: #198754; font-size: 11px;")

                    self.lbl_purchase_info.setText(info_text)

                    if not self.is_edit and remaining_qty > 0:
                        self.sp_production_qty.setValue(remaining_qty)
                    elif not self.is_edit:
                        self.sp_production_qty.setValue(1)
            except Exception as e:
                print(f"발주 정보 로드 오류: {e}")
                self.lbl_purchase_info.setText("발주 정보를 불러올 수 없습니다.")
                self.lbl_purchase_info.setStyleSheet("color: #dc3545; font-size: 11px;")
        else:
            self.lbl_purchase_info.setText("")
            if not self.is_edit:
                self.sp_production_qty.setValue(1)

    def load_available_purchases(self):
        try:
            purchases = get_available_purchases()

            # ✅ [수정] 9개 항목 언패킹
            for purchase_id, purchase_no, purchase_desc, ordered_qty, purchase_dt, stock_qty, allocation_margin, produced_qty, first_available_serial in purchases:

                # "미생산" 텍스트 표시
                if stock_qty <= 0 and produced_qty == 0:
                    stock_str = "미생산"
                else:
                    serial_str = ""
                    if stock_qty > 0 and first_available_serial:
                        serial_str = f" (S/N: {first_available_serial}~)"
                    stock_str = f"재고: {stock_qty}개{serial_str}"

                margin_str = f"할당 여유: {allocation_margin}개"
                order_str = f"총 발주: {ordered_qty}개"

                # (총 발주 / 재고 + S/N / 할당 여유) 순서로 표시
                display_text = f"{purchase_no} - ({order_str} / {stock_str} / {margin_str}) - {purchase_desc}"

                self.purchase_combo.addItem(display_text, purchase_id)

                # ✅ 빨간색 글씨 적용
                if stock_qty < allocation_margin:
                    # 콤보박스의 마지막 아이템(방금 추가한 아이템)의 인덱스를 가져옴
                    last_index = self.purchase_combo.count() - 1
                    self.purchase_combo.setItemData(last_index, QBrush(QColor("#dc3545")), Qt.ForegroundRole)

        except Exception as e:
            print(f"발주 목록 로드 실패: {e}")
            import traceback
            traceback.print_exc()

    def load_product_data(self):
        if not self.product_data:
            return

        product_id, manufacture_date, part_no, product_name, serial_no, manufacture_code, \
            purchase_no, purchase_id, is_delivered, delivered_at, delivery_invoice, \
            consumed_by_product_id, is_assembly = self.product_data  # ✅ 13개 항목

        self.edt_manufacture_date.setText(manufacture_date or "")
        self.edt_item_code.setText(part_no or "")
        self.edt_product_name.setText(product_name or "")
        self.edt_serial_no.setText(serial_no or "")
        self.edt_manufacture_code.setText(manufacture_code or "")

        if purchase_id:
            for i in range(self.purchase_combo.count()):
                if self.purchase_combo.itemData(i) == purchase_id:
                    self.purchase_combo.setCurrentIndex(i)
                    break

    def accept_dialog(self):
        item_code = self.edt_item_code.text().strip()
        product_name = self.edt_product_name.text().strip()

        # 필수 입력값 검증 (선택 사항)
        if not item_code or not product_name:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "품목코드와 제품명은 필수입니다.")
            return

        # ✅ [수정] 신규 생성 시에는 날짜/S/N/코드를 무조건 None으로 설정
        if not self.is_edit:
            manufacture_date = None
            manufacture_code = None
            # serial_no는 create_products 함수 내부에서 자동으로 NULL 처리됨
        else:
            # 수정 모드일 때만 입력값 가져오기
            manufacture_date_raw = self.edt_manufacture_date.text().strip()
            manufacture_date = parse_due_text(manufacture_date_raw) if manufacture_date_raw else None

            if manufacture_date_raw and not manufacture_date:
                QMessageBox.warning(self, "제조일자", "제조일자 형식이 올바르지 않습니다.")
                return

        manufacture_code = self.edt_manufacture_code.text().strip() or None
        # ✅ [수정] 생산 방식에 따라 purchase_id 분기
        is_assembly = self.production_mode_group.isVisible() and self.radio_assembly.isChecked()

        purchase_id = self.purchase_combo.currentData()  # 단순 생산은 선택된 발주 ID

        if is_assembly:
            # purchase_id = None  # 조립 생산은 발주 ID를 NULL로 저장
            production_qty = 1  # 조립은 1개
        else:

            production_qty = self.sp_production_qty.value()

        product_data = {
            'manufacture_date': manufacture_date,
            'part_no': item_code,
            'product_name': product_name,
            'manufacture_code': manufacture_code,
            'purchase_id': purchase_id  # ✅ 수정된 purchase_id
        }

        try:
            if self.is_edit:
                # --- [수정 모드] ---
                product_id = self.product_data[0]
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE products
                    SET manufacture_date=?, part_no=?, product_name=?, serial_no=?, manufacture_code=?, purchase_id=?
                    WHERE id=?
                """, (manufacture_date, item_code, product_name,
                      self.edt_serial_no.text().strip() or None,  # 수정 시 S/N 수동 입력
                      manufacture_code, purchase_id, product_id))
                conn.commit()
                conn.close()
                self.accept()
                return

            # --- [신규 생성 모드] ---
            consumed_items_ids = []

            # 2. (분기) 조립 생산인가? (✅ 라디오 버튼이 선택되었는가?)
            if self.production_mode_group.isVisible() and self.radio_assembly.isChecked():
                production_qty = 1  # 조립은 1개만

                # ✅ [추가] 조립 모드인데 BOM 요구사항이 없으면 오류
                if not self.bom_requirements:
                    QMessageBox.critical(self, "조립 오류", "이 제품은 조립용 BOM이 등록되지 않았습니다.")
                    return

                # 2-1. 소모될 부품 ID 수집 및 수량 검증
                for req in self.bom_requirements:
                    child_code = req['child_code']
                    qty_req = req['qty_req']

                    if child_code not in self.bom_widgets:
                        QMessageBox.critical(self, "조립 오류", f"필요한 부품 '{child_code}'의 재고가 없습니다.")
                        return

                    list_widget = self.bom_widgets[child_code]
                    selected_items = list_widget.selectedItems()

                    # ✅ [수정] 선택된 항목이 없으면 더 명확한 오류 메시지
                    if len(selected_items) == 0:
                        QMessageBox.critical(
                            self, "부품 미선택",
                            f"'{child_code}' 부품을 선택해주세요.\n\n"
                            f"재고 목록에서 사용할 제품을 클릭하여 선택하세요.\n"
                            f"(필요 수량: {qty_req}개)"
                        )
                        return

                    if len(selected_items) != qty_req:
                        QMessageBox.warning(self, "수량 오류",
                                            f"'{child_code}'의 필요 수량({qty_req}개)과\n"
                                            f"선택한 재고 수량({len(selected_items)}개)이 일치하지 않습니다."
                                            )
                        return

                    for item in selected_items:
                        consumed_items_ids.append(item.data(Qt.UserRole))

                # ✅ [추가] 최종 검증: consumed_items_ids가 비어있으면 안 됨
                if not consumed_items_ids:
                    QMessageBox.critical(
                        self, "조립 오류",
                        "조립에 필요한 부품이 선택되지 않았습니다.\n"
                        "각 부품의 재고 목록에서 사용할 제품을 선택해주세요."
                    )
                    return

            # 3. (분기) 단순 생산인가?
            else:
                # (consumed_items_ids는 빈 리스트로 전달됨)
                pass

            # 4. DB 저장 (db.py의 중앙 함수 호출)
            create_products(product_data, production_qty, consumed_items_ids)

            if consumed_items_ids:
                QMessageBox.information(self, "조립 완료", f"조립품 1개가 생성되었습니다.\n(부품 {len(consumed_items_ids)}개 소모)")
            else:
                QMessageBox.information(
                    self, "완료",
                    f"제품 {production_qty}개가 생성되었습니다.\n시리얼 번호는 별도로 할당하기 바랍니다."
                )
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "오류", f"제품 저장 중 오류가 발생했습니다:\n{str(e)}")
            import traceback;
            traceback.print_exc()

    def apply_prefill_data(self):
        """(새 함수) 재고 현황에서 전달받은 데이터로 폼을 미리 채웁니다."""
        if not self.prefill_data:
            return

        item_code = self.prefill_data.get('item_code')
        product_name = self.prefill_data.get('product_name')
        purchase_id = self.prefill_data.get('purchase_id')
        serial_no = self.prefill_data.get('serial_no')

        if item_code:
            self.edt_item_code.setText(item_code)
            self.edt_item_code.setReadOnly(True)  # 품목코드 변경 방지
            self.edt_item_code.setStyleSheet("background-color: #f0f0f0;")

        # ✅ [추가 시작]
        if serial_no:
            self.edt_serial_no.setText(serial_no)
            self.edt_serial_no.setPlaceholderText(f"추천 S/N: {serial_no}. (비워두면 자동 생성)")
            self.edt_serial_no.setStyleSheet("background-color: #fffacd;")  # 강조
        # ✅ [추가 끝]

        if product_name:
            self.edt_product_name.setText(product_name)
            self.edt_product_name.setReadOnly(True)  # 제품명 변경 방지
            self.edt_product_name.setStyleSheet("background-color: #f0f0f0;")

        if purchase_id:
            # 콤보박스에서 일치하는 발주 ID를 찾아 선택
            for i in range(self.purchase_combo.count()):
                if self.purchase_combo.itemData(i) == purchase_id:
                    self.purchase_combo.setCurrentIndex(i)
                    break
            self.purchase_combo.setEnabled(False)  # 발주번호 변경 방지

        # 제조일자 필드에 포커스
        self.edt_manufacture_date.setFocus()


# ✅ 시리얼 번호 부여 팝업
class AssignProductInfoDialog(QDialog):
    def __init__(self, parent, product_ids, part_no):
        super().__init__(parent)
        self.product_ids = product_ids
        self.part_no = part_no
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle(f"제품 출하 확정 ({len(self.product_ids)}개)")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.edt_date = QLineEdit()
        self.edt_date.setPlaceholderText(datetime.now().strftime("%Y-%m-%d"))
        self.edt_date.setText(datetime.now().strftime("%Y-%m-%d"))
        self.edt_date.textChanged.connect(self.update_code)

        self.edt_code = QLineEdit()
        self.edt_code.setPlaceholderText("자동 생성됨")

        self.sp_start_sn = QSpinBox()
        self.sp_start_sn.setRange(1, 999)
        self.sp_start_sn.setPrefix("KT")
        self.sp_start_sn.setDisplayIntegerBase(10)

        # 다음 S/N 자동 추천
        next_sn_str = get_next_serial_number(get_conn(), self.part_no)
        try:
            next_num = int(next_sn_str.replace("KT", ""))
            self.sp_start_sn.setValue(next_num)
        except:
            self.sp_start_sn.setValue(1)

        form.addRow("제조일자:", self.edt_date)
        form.addRow("제조코드:", self.edt_code)
        form.addRow("시작 S/N:", self.sp_start_sn)

        layout.addLayout(form)

        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet("color: #0066cc; font-size: 11px;")
        layout.addWidget(self.lbl_preview)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.update_code()  # 초기 실행
        self.sp_start_sn.valueChanged.connect(self.update_preview)

    def update_code(self):
        date_text = self.edt_date.text().strip()
        if not date_text: return
        parsed = parse_due_text(date_text)
        if parsed:
            try:
                dt = datetime.strptime(parsed, "%Y-%m-%d")
                year_code = str(dt.year)[-2:]
                iso_year, iso_week, _ = dt.isocalendar()
                if iso_year != dt.year: year_code = str(iso_year)[-2:]
                self.edt_code.setText(f"{year_code}{iso_week:02d}")
            except:
                pass
        self.update_preview()

    def update_preview(self):
        count = len(self.product_ids)
        start = self.sp_start_sn.value()
        end = start + count - 1
        # 999 넘어가는 경우 처리 (단순 표시용)
        end_disp = ((end - 1) % 999) + 1
        self.lbl_preview.setText(f"예상 S/N: KT{start:03d} ~ KT{end_disp:03d} (총 {count}개 부여)")

    def get_data(self):
        return {
            'date': parse_due_text(self.edt_date.text()),
            'code': self.edt_code.text(),
            'start_sn': self.sp_start_sn.value()
        }