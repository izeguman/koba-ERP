# app/ui/purchase_widget.py
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QHeaderView
from PySide6.QtCore import Qt, QSignalBlocker, QSettings
from datetime import datetime
from ..db import (get_conn,
                  get_linked_orders, get_orders_for_purchase_display,
                  update_product_master_purchase_price, query_all,
                  create_purchase_with_items, get_purchase_with_items,
                  get_next_purchase_number, update_purchase_with_items)
from .autocomplete_widgets import AutoCompleteLineEdit
from .money_lineedit import MoneyLineEdit
from .utils import parse_due_text, apply_table_resize_policy
from ..db import is_purchase_completed, calculate_fifo_allocation_margins


def format_money(val: float | None) -> str:
    if val is None:
        return ""
    try:
        return f"{val:,.0f}"
    except Exception:
        return str(val)


def get_available_orders_for_purchase(purchase_id_to_include=None):
    """
    발주와 연결할 수 있는 주문 목록을 반환합니다.
    1. (기본) OA 발송됨, 청구 미완료된 모든 주문
    2. (수정 시) + 현재 발주에 이미 연결된 주문 (청구 완료 여부와 상관없이)
    """
    sql = """
        SELECT
            o.id,
            o.order_no,
            GROUP_CONCAT(oi.product_name, ' | ') as order_desc,
            SUM(oi.qty) as total_ordered_qty,

            /* [수정] 분할 납기를 포함한 '진짜' 최종 납기일 조회 */
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

    # --- [수정] WHERE 절 로직 (괄호 오류 수정) ---
    # 1. 기본 조건 (미청구 + OA 발송)
    where_clause = """
        WHERE (
            o.order_no IS NOT NULL
            AND COALESCE(o.oa_sent, 0) = 1
            AND COALESCE(o.invoice_done, 0) = 0
        )
    """
    params = []

    if purchase_id_to_include:
        # 2. 수정 모드일 때 (OR 조건 추가)
        where_clause += """
            OR (
                o.id IN (SELECT order_id FROM purchase_order_links WHERE purchase_id = ?)
            )
        """
        params.append(purchase_id_to_include)

    # 3. SQL 조합
    sql += where_clause
    sql += " GROUP BY o.id ORDER BY due_date ASC, o.order_no ASC"

    return query_all(sql, tuple(params))


class PurchaseWidget(QtWidgets.QWidget):
    """✅ 발주 목록을 표시하는 위젯"""
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.active_purchase_dialogs = []  # 모달리스 다이얼로그 추적용

        # ✅ 저장된 설정 불러오기
        if self.settings:
            self.show_all = self.settings.value("filters/purchases_show_all", False, type=bool)
        else:
            self.show_all = False

        self.setup_ui()

        # ✅ 저장된 정렬 상태 불러오기 (기본값: 0-발주일, 1-내림차순)
        self.current_sort_column = self.settings.value("purchase_table/sort_column", 0, type=int)
        # QSettings는 Qt Enum을 직접 처리할 수 있으므로 type=int를 제거합니다.
        sort_order_val = self.settings.value("purchase_table/sort_order", Qt.DescendingOrder)
        self.current_sort_order = Qt.SortOrder(sort_order_val)

        self.load_purchase_list()


    def setup_ui(self):
        """✅ 발주 목록 UI 구성"""
        layout = QtWidgets.QVBoxLayout(self)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("발주 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        self.btn_show_all = QtWidgets.QPushButton("미완료만")
        self.btn_show_all.setCheckable(True)
        self.btn_show_all.setChecked(self.show_all)  # ✅ 저장된 값으로 설정
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

        # ✅ 컬럼 개수 7개 -> 8개로 변경
        self.table = QtWidgets.QTableWidget(0, 8)
        # ✅ 헤더에 '총수량' 추가
        self.table.setHorizontalHeaderLabels(
            ["발주일", "발주번호", "총수량", "품목수", "발주내용", "발주금액(원)", "연결주문", "완료여부"]
        )
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False) # ✅ [수정] Qt 기본 정렬 비활성화

        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.setShowGrid(True)

        self.table.itemDoubleClicked.connect(self.edit_purchase)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        # ✅ 컬럼 폭 설정 수정 (총수량 추가 및 인덱스 조정)
        self.table.setColumnWidth(0, 90)  # 발주일
        self.table.setColumnWidth(1, 80)  # 발주번호
        self.table.setColumnWidth(2, 70)  # 총수량 (새로 추가)
        self.table.setColumnWidth(3, 70)  # 품목수
        self.table.setColumnWidth(4, 600)  # 발주내용
        self.table.setColumnWidth(5, 120)  # 발주금액(원)
        self.table.setColumnWidth(6, 350)  # 연결주문
        self.table.setColumnWidth(7, 80)  # 완료여부

        if self.settings:
            self.restore_column_widths()

        header.sectionResized.connect(self.save_column_widths)
        # ✅ [추가] 헤더 클릭 시 SQL 정렬을 수행하도록 시그널 연결
        header.sortIndicatorChanged.connect(self.on_sort_indicator_changed)
        # ✅ [추가] 정렬 화살표를 항상 표시하도록 설정
        header.setSortIndicatorShown(True)

        layout.addLayout(title_layout)
        layout.addWidget(self.table)

        apply_table_resize_policy(self.table)

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


    def load_purchase_list(self):
        """발주 목록 로드"""
        try:
            from PySide6.QtGui import QBrush, QColor

            # ✅ 1. 설정에서 발주 관련 사용자 지정 색상 불러오기
            comp_fg = self.settings.value("colors/purchase_completed_fg", "#000000")
            comp_bg = self.settings.value("colors/purchase_completed_bg", "#BBDEFB")
            incomp_fg = self.settings.value("colors/purchase_incomplete_fg", "#000000")
            incomp_bg = self.settings.value("colors/purchase_incomplete_bg", "#FFFFFF")

            conn = get_conn()
            cur = conn.cursor()

            # ✅ [수정] 툴팁에 표시할 상세 정보(생산량, 납품량, 소모량, 할당량, S/N)를 함께 조회하도록 쿼리 확장
            sql = """
                SELECT 
                    p.id,
                    p.purchase_dt,
                    p.purchase_no,
                    p.status,
                    SUM(pi.qty) as total_qty,
                    COUNT(pi.id) as item_count,
                    GROUP_CONCAT(pi.product_name, ' | ') as product_names,
                    CASE 
                        WHEN p.actual_amount > 0 THEN p.actual_amount / 100.0
                        ELSE SUM(pi.qty * pi.unit_price_cents) / 100.0
                    END as amount_krw,

                    -- [추가] 재고 및 할당 여유 계산을 위한 서브쿼리
                    (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id) as produced_qty,
                    (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id AND pr.delivery_id IS NOT NULL) as delivered_qty,
                    (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id AND pr.consumed_by_product_id IS NOT NULL) as consumed_qty,

                    -- 연결된 주문의 할당량 (이 발주에 포함된 품목만 집계)
                    (SELECT COALESCE(SUM(oi.qty), 0)
                     FROM order_items oi
                     JOIN purchase_order_links pol ON oi.order_id = pol.order_id
                     WHERE pol.purchase_id = p.id
                     AND oi.item_code IN (SELECT pi_sub.item_code FROM purchase_items pi_sub WHERE pi_sub.purchase_id = p.id)
                    ) as linked_order_qty,

                    -- 가장 빠른 재고 S/N
                    (SELECT pr.serial_no FROM products pr
                     WHERE pr.purchase_id = p.id AND pr.delivery_id IS NULL AND pr.consumed_by_product_id IS NULL
                     ORDER BY pr.serial_no ASC
                     LIMIT 1
                    ) as first_serial

                FROM purchases p
                LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
                GROUP BY p.id
            """

            order_clause = self.get_purchase_order_clause()
            sql += f" ORDER BY {order_clause}"

            cur.execute(sql)
            rows = cur.fetchall()

            # ✅ 정확한 할당 여유분 계산 (FIFO)
            fifo_margins = calculate_fifo_allocation_margins()

            if not self.show_all:
                filtered_rows = []
                for row in rows:
                    purchase_id = row[0]
                    if row[3] != '완료' and not is_purchase_completed(purchase_id):
                        filtered_rows.append(row)
                rows = filtered_rows

            self.purchase_data = rows
            self.table.setRowCount(len(rows))
            self.table.setSortingEnabled(False)

            for r, row in enumerate(rows):
                (purchase_id, purchase_dt, purchase_no, status, total_qty,
                 item_count, product_names, amount_krw,
                 produced_qty, delivered_qty, consumed_qty, linked_order_qty, first_serial) = row

                # None 값을 0으로 처리
                total_qty = total_qty or 0
                produced_qty = produced_qty or 0
                delivered_qty = delivered_qty or 0
                consumed_qty = consumed_qty or 0
                linked_order_qty = linked_order_qty or 0

                # 재고 수량 계산
                stock_qty = produced_qty - delivered_qty - consumed_qty
                if stock_qty < 0: stock_qty = 0

                # ✅ 할당 여유: FIFO 계산 결과 적용
                allocation_margin = fifo_margins.get(purchase_id, 0)

                # ✅ [수정] 툴팁 텍스트 조건부 생성 (미생산 vs 재고)
                if produced_qty == 0:
                    # 생산된 수량이 0이면 '미생산' 표시
                    stock_status_str = "미생산"
                else:
                    # 생산된 수량이 있으면 '재고: N개' 표시
                    sn_info = f" (S/N: {first_serial}~)" if (stock_qty > 0 and first_serial) else ""
                    stock_status_str = f"재고: {stock_qty}개{sn_info}"

                tooltip_text = (f"총 발주: {total_qty}개 / "
                                f"{stock_status_str} / "
                                f"할당 여유: {allocation_margin}개")

                # Col 0: 발주일 (가운데 정렬)
                item_0 = QtWidgets.QTableWidgetItem("" if purchase_dt is None else str(purchase_dt))
                item_0.setData(Qt.UserRole, purchase_id)
                item_0.setTextAlignment(Qt.AlignCenter)  # ✅ 가운데 정렬
                item_0.setToolTip(tooltip_text)  # ✅ 툴팁 설정
                self.table.setItem(r, 0, item_0)

                # Col 1: 발주번호 (왼쪽 정렬)
                item_1 = QtWidgets.QTableWidgetItem(str(purchase_no or ""))
                item_1.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # ✅ 왼쪽 정렬
                item_1.setToolTip(tooltip_text)  # ✅ 툴팁 설정
                self.table.setItem(r, 1, item_1)

                # Col 2: 총수량 (가운데 정렬)
                item_2 = QtWidgets.QTableWidgetItem(str(total_qty or 0))
                item_2.setTextAlignment(Qt.AlignCenter)  # ✅ 가운데 정렬
                self.table.setItem(r, 2, item_2)

                # Col 3: 품목수 (가운데 정렬)
                item_3 = QtWidgets.QTableWidgetItem(f"{item_count}개")
                item_3.setTextAlignment(Qt.AlignCenter)  # ✅ 가운데 정렬
                self.table.setItem(r, 3, item_3)

                # Col 4: 발주내용 (왼쪽 정렬)
                if product_names:
                    display_names = product_names if len(product_names) < 80 else product_names[:77] + "..."
                    item_4 = QtWidgets.QTableWidgetItem(display_names)
                else:
                    item_4 = QtWidgets.QTableWidgetItem("")
                item_4.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # ✅ 왼쪽 정렬
                item_4.setToolTip(tooltip_text)  # ✅ 툴팁 설정
                self.table.setItem(r, 4, item_4)

                # Col 5: 발주금액(원) (오른쪽 정렬)
                item_5 = QtWidgets.QTableWidgetItem(format_money(amount_krw))
                item_5.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)  # ✅ 오른쪽 정렬
                self.table.setItem(r, 5, item_5)

                # Col 6: 연결주문 (왼쪽 정렬)
                order_nos = get_orders_for_purchase_display(purchase_id)
                item_6 = QtWidgets.QTableWidgetItem(order_nos or "")
                item_6.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # ✅ 왼쪽 정렬
                self.table.setItem(r, 6, item_6)

                # Col 7: 완료여부 (Checkbox + Label)
                is_manually_completed = (status == '완료')
                is_auto_completed = is_purchase_completed(purchase_id)
                is_completed_overall = is_manually_completed or is_auto_completed

                # 1. 수동 완료 체크박스 (이 체크박스는 'status' 컬럼만 제어)
                manual_checkbox = QtWidgets.QCheckBox()
                manual_checkbox.setChecked(is_manually_completed)
                manual_checkbox.stateChanged.connect(
                    lambda state, pid=purchase_id: self.update_completed_status(pid, state)
                )

                # 2. 상태 표시 라벨
                status_label = QtWidgets.QLabel()
                status_label.setAlignment(Qt.AlignCenter)

                # 3. 상태에 따라 라벨 텍스트와 툴팁 설정
                if is_manually_completed:
                    status_label.setText("<b>수동 완료</b>")
                    status_label.setStyleSheet("color: #6f42c1;")  # 보라색
                    manual_checkbox.setToolTip("수동 '완료' 상태입니다.\n해제하려면 클릭하세요.")
                elif is_auto_completed:
                    status_label.setText("자동 완료")
                    status_label.setStyleSheet("color: #6c757d;")  # 회색
                    manual_checkbox.setToolTip("연결된 주문/수량이 일치하여 자동 완료되었습니다.\n(수동으로 강제 완료하려면 클릭)")
                else:
                    status_label.setText("미완료")
                    status_label.setStyleSheet("color: #dc3545;")  # 붉은색
                    manual_checkbox.setToolTip("수동으로 '완료' 처리하려면 클릭")

                # 4. 위젯을 레이아웃에 담기
                checkbox_widget = QtWidgets.QWidget()
                checkbox_layout = QtWidgets.QHBoxLayout(checkbox_widget)
                checkbox_layout.addWidget(manual_checkbox)
                checkbox_layout.addWidget(status_label)
                checkbox_layout.setAlignment(Qt.AlignCenter)
                checkbox_layout.setContentsMargins(5, 0, 5, 0)  # 좌우 여백
                checkbox_layout.setSpacing(5)  # 체크박스와 라벨 간격
                # ✅ 위젯 전체에 툴팁을 주려면 checkbox_widget.setToolTip(tooltip_text)을 쓸 수 있으나,
                # 내부 요소(체크박스 등)의 툴팁과 충돌할 수 있어 생략하거나 필요시 추가하세요.
                self.table.setCellWidget(r, 7, checkbox_widget)

                # ✅ 2. is_completed_overall 상태에 따라 적용할 색상 결정
                fg_color = QColor(comp_fg if is_completed_overall else incomp_fg)
                bg_color = QColor(comp_bg if is_completed_overall else incomp_bg)

                # ✅ 3. 결정된 색상을 모든 컬럼에 적용
                for col in range(self.table.columnCount()):
                    item = self.table.item(r, col)
                    if item:
                        item.setForeground(QBrush(fg_color))
                        item.setBackground(QBrush(bg_color))

            # 1. 정렬 화살표 표시 (시그널 차단으로 무한 루프 방지)
            with QSignalBlocker(self.table.horizontalHeader()):
                self.table.horizontalHeader().setSortIndicator(
                    self.current_sort_column,
                    self.current_sort_order
                )

            # 2. 그 다음에 정렬 기능을 활성화
            self.table.setSortingEnabled(True)

            # 3. 행 높이 설정
            for i in range(self.table.rowCount()):
                self.table.setRowHeight(i, 25)

            conn.close()

        except Exception as e:
            print(f"발주 목록 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.purchase_data = []
            self.table.setRowCount(0)

    def get_purchase_order_clause(self):
        """(새 함수) 저장된 정렬 기준을 SQL ORDER BY 절로 변환"""
        # ["발주일", "발주번호", "총수량", "품목수", "발주내용", "발주금액(원)", "연결주문", "완료여부"]
        column_names = [
            "p.purchase_dt",  # 0
            "p.purchase_no",  # 1
            "total_qty",  # 2
            "item_count",  # 3
            "product_names",  # 4
            "amount_krw",  # 5
            "NULL",  # 6 (연결주문은 DB에서 가져온 후 Python에서 생성하므로 SQL 정렬 불가)
            "status"  # 7
        ]

        if self.current_sort_column == 6:  # '연결주문'은 SQL 정렬 불가, 기본값으로 대체
            column = "p.purchase_dt"
            direction = "DESC" if self.current_sort_order == Qt.DescendingOrder else "ASC"
        elif 0 <= self.current_sort_column < len(column_names):
            column = column_names[self.current_sort_column]
            direction = "DESC" if self.current_sort_order == Qt.DescendingOrder else "ASC"
        else:  # 기본값
            column = "p.purchase_dt"
            direction = "DESC"

        # 2차 정렬 기준으로 발주번호 사용
        return f"{column} {direction}, p.purchase_no {direction}"

    def on_sort_indicator_changed(self, column_index, order):
        """(새 함수) 발주 테이블 헤더의 정렬 표시기가 변경될 때 호출됩니다."""

        # 1. 현재 상태와 동일하면 (load_purchase_list에 의한 프로그래밍 방식 호출), 무시
        if self.current_sort_column == column_index and self.current_sort_order == order:
            return

        # 2. '연결주문' 컬럼(6)은 정렬 비활성화
        if column_index == 6:
            # 현재 정렬 상태를 유지하고, 화살표만 이전 상태로 되돌림
            with QSignalBlocker(self.table.horizontalHeader()):
                self.table.horizontalHeader().setSortIndicator(
                    self.current_sort_column,
                    self.current_sort_order
                )
            return

        # 3. 사용자 클릭에 의한 변경이므로, 새 정렬 상태를 저장
        self.current_sort_column = column_index
        self.current_sort_order = order # ⬅️ 신호로 받은 'order'를 그대로 사용

        # 4. 새 정렬 상태를 QSettings에 저장
        self.settings.setValue("purchase_table/sort_column", self.current_sort_column)
        self.settings.setValue("purchase_table/sort_order", self.current_sort_order)

        # 5. 새 정렬 기준으로 데이터 목록을 다시 로드 (SQL 정렬)
        self.load_purchase_list()


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
        """새 발주 추가 (모달리스)"""
        dialog = PurchaseDialog(self, is_edit=False)
        dialog.accepted.connect(self.load_purchase_list)
        dialog.finished.connect(lambda: self.cleanup_purchase_dialog(dialog))
        dialog.show()
        self.active_purchase_dialogs.append(dialog)

    def cleanup_purchase_dialog(self, dialog):
        if dialog in self.active_purchase_dialogs:
            self.active_purchase_dialogs.remove(dialog)

    def edit_purchase(self):
        """발주 수정 (모달리스)"""
        purchase_data = self.get_selected_purchase()
        if not purchase_data:
            QtWidgets.QMessageBox.information(self, "알림", "수정할 발주를 선택해주세요.")
            return

        purchase_id = purchase_data[0]

        # 이미 열려있는지 확인
        for dlg in self.active_purchase_dialogs:
            if getattr(dlg, 'purchase_id', None) == purchase_id:
                dlg.raise_()
                dlg.activateWindow()
                return

        dialog = PurchaseDialog(self, is_edit=True, purchase_id=purchase_id)
        dialog.accepted.connect(self.load_purchase_list)
        dialog.finished.connect(lambda: self.cleanup_purchase_dialog(dialog))
        dialog.show()
        self.active_purchase_dialogs.append(dialog)

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
        self.settings = QSettings("KOBATECH", "ProductionManagement") # ✅ QSettings 추가
        self.setup_ui()

        if not self.is_edit:  # 새 발주 추가일 때만
            use_auto_num = self.settings.value("auto_numbering/enable_purchase_no", False, type=bool)
            if use_auto_num:
                try:
                    today = datetime.now()
                    next_no = get_next_purchase_number(today.year, today.month)
                    self.edt_purchase_no.setText(next_no)
                    self.edt_purchase_no.setStyleSheet("background-color: #fffacd;")
                except Exception as e:
                    print(f"추천 발주번호 생성 실패: {e}")

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
        btn_add_item.setStyleSheet("padding: 8px 12px; font-weight: bold;")

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
                    /* 아래 hover 부분은 삭제되었으므로, 메인 윈도우의 스타일이 적용됩니다. */
                """)

        # ✅ [수정] 현재 발주 ID를 전달하여, 이미 연결된 주문도 목록에 포함시킴
        self.load_available_orders(self.purchase_id)
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

        rounded_total = self._get_rounded_item_total(qty, unit_price)
        self.item_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{rounded_total:,}"))

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
        rounded_total = self._get_rounded_item_total(qty, unit_price)
        self.item_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{rounded_total:,}"))

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
        """계산된 금액과 실제 발주금액을 업데이트합니다."""
        # 1. 현재 '실제 발주금액' 필드에 입력된 값과, '계산된 금액' 라벨에 표시된 옛날 합계를 가져옵니다.
        current_actual_amount = self.edt_total_amount.get_value()
        try:
            # 라벨의 텍스트(예: "1,250,000")에서 쉼표를 제거하고 숫자로 변환합니다.
            old_calculated_amount = int(self.lbl_calculated_amount.text().replace(',', ''))
        except ValueError:
            old_calculated_amount = 0

        # 2. 새로 추가된 품목을 포함하여 새로운 합계를 계산합니다.
        new_total = sum(
            self._get_rounded_item_total(item['qty'], item['unit_price_cents'] // 100)
            for item in self.items
        )

        # ✅ [추가] 반올림 설정 적용
        enabled = self.settings.value("calculations/purchase_rounding_enabled", False, type=bool)
        unit = self.settings.value("calculations/purchase_rounding_unit", 1, type=int)

        if enabled and unit > 1:
            # unit(10) -> ndigits(-1), unit(100) -> ndigits(-2)
            unit_to_digits = {10: -1, 100: -2, 1000: -3}
            ndigits = unit_to_digits.get(unit, 0)
            if ndigits != 0:
                new_total = round(new_total, ndigits)

        # 3. '계산된 금액' 라벨은 항상 새로운 합계로 업데이트합니다.
        self.lbl_calculated_amount.setText(f"{new_total:,}")

        # 4. [핵심 로직] '실제 발주금액'이 이전 합계와 동일한 경우 (사용자가 수정하지 않은 경우),
        #    새로운 합계로 함께 업데이트합니다.
        if current_actual_amount == old_calculated_amount:
            self.edt_total_amount.set_value(new_total)

    def load_available_orders(self, purchase_id_to_include=None):
        """연결 가능한 주문 목록 로드 (수정 시 기존 연결 건 포함)"""
        # ✅ [수정] 인자로 받은 ID를 SQL 쿼리 함수에 전달
        orders = get_available_orders_for_purchase(purchase_id_to_include)
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

    def _get_rounded_item_total(self, qty, unit_price):
        """(새 함수) 설정에 따라 '반올림' 또는 '버림'된 개별 품목 금액을 반환"""
        item_total = qty * unit_price

        # ✅ [수정] '계산 방식'과 '자릿수'를 불러옴
        method = self.settings.value("calculations/purchase_rounding_method", "none", type=str)
        digits = self.settings.value("calculations/purchase_rounding_digits", 0, type=int)

        # '적용 안함'이거나 digits가 0이면(1원 단위) 원본 값 반환
        if method == "none" or digits == 0:
            return item_total

        # ✅ [수정] 자릿수(digits)로 단위(unit) 계산
        unit = 10 ** digits  # (digits=1 -> unit=10, digits=4 -> unit=10000)

        if method == "round":
            # --- 반올림 (사사오입) ---
            # (digits=1 -> ndigits=-1, digits=4 -> ndigits=-4)
            ndigits = -digits
            item_total = round(item_total, ndigits)

        elif method == "floor":
            # --- 버림 (내림) ---
            item_total = (item_total // unit) * unit

        return item_total

    def accept_dialog(self):
        # 1. 입력값 검증
        purchase_no = self.edt_purchase_no.text().strip()
        if not purchase_no or not self.items:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "발주번호와 최소 1개 이상의 품목은 필수입니다.")
            return

        purchase_dt = parse_due_text(self.edt_purchase_dt.text())

        # 2. 총액 계산
        calculated_total = sum(item['qty'] * (item['unit_price_cents'] // 100) for item in self.items)
        actual_total = self.edt_total_amount.get_value()

        # 3. 데이터 준비
        purchase_data = {
            'purchase_no': purchase_no,
            'purchase_dt': purchase_dt,
            'status': '발주',
            'actual_amount': (actual_total if actual_total > 0 else calculated_total) * 100
        }

        # ✅ [핵심] 선택된 주문 ID 목록 가져오기
        selected_order_ids = [item.data(Qt.UserRole) for item in self.order_list.selectedItems()]

        try:
            if self.is_edit:
                # 수정 모드: 연결 정보 수정 + 자동 할당 실행
                update_purchase_with_items(
                    self.purchase_id,
                    purchase_data,
                    self.items,
                    selected_order_ids
                )
                action = "수정"
            else:
                # 신규 모드: 연결 정보 저장 (할당은 아직 제품이 없으니 패스)
                create_purchase_with_items(
                    purchase_data,
                    self.items,
                    selected_order_ids  # ✅ 여기서 주문 ID 리스트를 꼭 넘겨줘야 합니다!
                )
                action = "등록"

            QtWidgets.QMessageBox.information(
                self, "완료",
                f"발주 '{purchase_no}'이 {action}되었습니다.\n"
                f"품목 수: {len(self.items)}개\n"
                f"발주금액: {actual_total if actual_total > 0 else calculated_total:,}원"
            )
            self.accept()

        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                QtWidgets.QMessageBox.critical(self, "중복 오류", f"발주번호 '{purchase_no}'는 이미 존재합니다.")
            else:
                QtWidgets.QMessageBox.critical(self, "오류", f"발주 저장 중 오류가 발생했습니다:\n{str(e)}")
            import traceback
            traceback.print_exc()