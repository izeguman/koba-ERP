# app/ui/main_window.py
from PySide6 import QtGui
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QHeaderView, QMenu, QSplitter, QTabWidget
from PySide6.QtCore import QLocale, Qt, QSettings
from datetime import datetime
from ..db import (get_conn, get_due_change_history, add_due_change_record, update_order_final_due_date,
                  add_or_update_product_master, search_product_master)
from .purchase_widget import PurchaseWidget
from .delivery_widget import DeliveryWidget
from .product_widget import ProductWidget
from .product_master_widget import ProductMasterWidget
from .autocomplete_widgets import ProductOrderDialog
from .money_lineedit import MoneyLineEdit
from PySide6.QtGui import QAction  # ✅ 이 줄 추가


# ── 표시용 포맷 ──────────────────────────────────────────────────────────────
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


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KOBATECH 생산 관리 시스템")
        self.resize(1600, 900)
        self.only_future = False
        self.show_all_billed = False
        self.show_all_inventory = False

        # 설정 저장을 위한 QSettings 초기화
        self.settings = QSettings("KOBATECH", "ProductionManagement")

        # ✅ 윈도우 아이콘 설정
        from pathlib import Path
        icon_path = Path(__file__).parent / "koba_erp_final.ico"

        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))
        else:
            print(f"⚠️ 아이콘 파일을 찾을 수 없습니다: {icon_path}")

        # ✅ 로고 툴바를 먼저 생성
        self.setup_logo_toolbar()

        # ✅ 메뉴바 추가
        self.setup_menubar()

        self.main_tabs = QTabWidget()

        # 각 탭 위젯 생성 및 저장
        self.order_purchase_delivery_widget = self.create_order_purchase_delivery_widget()
        self.main_tabs.addTab(self.order_purchase_delivery_widget, "주문/발주/납품")

        self.product_master_widget = ProductMasterWidget(settings=self.settings)
        self.main_tabs.addTab(self.product_master_widget, "품목 관리")

        self.product_production_widget = ProductWidget(settings=self.settings)
        self.main_tabs.addTab(self.product_production_widget, "제품 생산")

        self.inventory_widget = self.create_inventory_widget()
        self.main_tabs.addTab(self.inventory_widget, "재고 현황")

        # 🆕 탭 전환 시 자동 새로고침 연결
        self.main_tabs.currentChanged.connect(self.on_tab_changed)

        self.setCentralWidget(self.main_tabs)
        self.statusBar().showMessage("준비됨")

        self.current_sort_column = 7
        self.current_sort_order = Qt.AscendingOrder

        self.load_due_list(only_future=False)

    def setup_logo_toolbar(self):
        """로고 전용 툴바 생성"""
        try:
            from pathlib import Path
            logo_path = Path(__file__).parent / "logo.png"

            if logo_path.exists():
                logo_toolbar = self.addToolBar("Logo")
                logo_toolbar.setMovable(False)
                logo_toolbar.setFloatable(False)

                # ✅ 툴바 구분선 제거
                logo_toolbar.setStyleSheet("""
                    QToolBar {
                        border: none;
                        spacing: 0px;
                    }
                """)

                '''# 왼쪽: 시스템 정보
                info_label = QtWidgets.QLabel("KOBATECH 생산 관리 시스템 v1.0")
                info_label.setStyleSheet("color: #666; font-size: 11px; padding-left: 15px;")
                logo_toolbar.addWidget(info_label)'''

                # 스페이서
                spacer = QtWidgets.QWidget()
                spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
                logo_toolbar.addWidget(spacer)

                # 오른쪽: 로고
                logo_label = QtWidgets.QLabel()
                pixmap = QtGui.QPixmap(str(logo_path))
                scaled_pixmap = pixmap.scaledToHeight(35, Qt.SmoothTransformation)
                logo_label.setPixmap(scaled_pixmap)
                logo_label.setStyleSheet("padding: 5px 15px;")

                logo_toolbar.addWidget(logo_label)

        except Exception as e:
            print(f"로고 툴바 생성 오류: {e}")

    def setup_menubar(self):
        """메뉴바 설정 (로고 제외)"""
        menubar = self.menuBar()

        # 설정 메뉴
        settings_menu = menubar.addMenu("설정")

        # 디스플레이 초기화 액션
        reset_display_action = QAction("디스플레이 초기화", self)
        reset_display_action.setStatusTip("모든 테이블 컬럼 폭과 트리 확장 상태를 기본값으로 되돌립니다")
        reset_display_action.triggered.connect(self.reset_display_settings)
        settings_menu.addAction(reset_display_action)

        # 도움말 메뉴
        help_menu = menubar.addMenu("도움말")

        about_action = QAction("정보", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def reset_display_settings(self):
        """디스플레이 설정 초기화 (데이터는 안전합니다)"""
        reply = QtWidgets.QMessageBox.question(
            self,
            "디스플레이 초기화",
            "테이블 컬럼 폭과 트리 확장 상태를 기본값으로 되돌리시겠습니까?\n\n"
            "✓ 초기화 항목:\n"
            "  • 주문/발주/납품 테이블 컬럼 폭\n"
            "  • 제품 마스터/생산 테이블 컬럼 폭\n"
            "  • 재고 현황 테이블 컬럼 폭\n"
            "  • 납품 품목 입력창 컬럼 폭\n"
            "  • 제품 트리 확장 상태\n\n"
            "✓ 안전:\n"
            "  • 데이터베이스 내용은 변경되지 않습니다\n"
            "  • 모든 업무 데이터는 그대로 유지됩니다",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            # 저장된 UI 설정만 삭제 (데이터는 안전)
            keys_to_remove = [
                "orders_table/column_widths",
                "purchase_table/column_widths",
                "product_table/column_widths",
                "product_master_table/column_widths",
                "inventory_table/column_widths",
                "delivery_item_table/column_widths",
                "product_tree/expanded_state"
            ]

            for key in keys_to_remove:
                self.settings.remove(key)

            QtWidgets.QMessageBox.information(
                self,
                "완료",
                "디스플레이 설정이 초기화되었습니다.\n\n"
                "프로그램을 다시 시작하면 기본 레이아웃이 적용됩니다.\n\n"
                "✓ 모든 데이터는 안전하게 보존되었습니다."
            )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "오류",
                f"디스플레이 초기화 중 오류가 발생했습니다:\n{str(e)}"
            )

    def show_about(self):
        """프로그램 정보 표시"""
        QtWidgets.QMessageBox.about(
            self,
            "KOBATECH 생산 관리 시스템",
            "<h3>KOBATECH 생산 관리 시스템</h3>"
            "<p>버전: 1.0.0</p>"
            "<p>제품 생산 및 재고 관리를 위한 통합 시스템</p>"
            "<br>"
            "<p><b>주요 기능:</b></p>"
            "<ul>"
            "<li>주문/발주/납품 관리</li>"
            "<li>제품 생산 관리</li>"
            "<li>재고 현황 추적</li>"
            "<li>제품 마스터 데이터 관리</li>"
            "</ul>"
            "<br>"
            "<p>© 2025 KOBATECH. All rights reserved.</p>"
        )

    def on_tab_changed(self, index):
        """탭 전환 시 해당 탭의 데이터를 새로고침"""
        tab_name = self.main_tabs.tabText(index)

        if tab_name == "주문/발주/납품":
            # 주문, 발주, 납품 모두 새로고침
            self.load_due_list(self.only_future)
            if hasattr(self, 'purchase_widget'):
                self.purchase_widget.load_purchase_list()
            if hasattr(self, 'delivery_widget'):
                self.delivery_widget.load_delivery_list()

        elif tab_name == "제품 마스터":
            self.product_master_widget.load_product_list()

        elif tab_name == "제품 생산":
            # ✅ 제품 생산 탭으로 전환 시 무조건 새로고침
            self.product_production_widget.load_product_list()
            # print("✅ 제품 생산 목록 새로고침됨")  # 디버깅용

        elif tab_name == "재고 현황":
            self.load_inventory_data()

    def closeEvent(self, event):
        """🆕 프로그램 종료 시 설정 저장"""
        self.save_all_column_widths()
        event.accept()

    def save_column_widths(self, table: QtWidgets.QTableWidget, table_name: str):
        """🆕 테이블의 컬럼 크기 저장"""
        widths = []
        for col in range(table.columnCount()):
            widths.append(table.columnWidth(col))
        self.settings.setValue(f"{table_name}/column_widths", widths)

    def restore_column_widths(self, table: QtWidgets.QTableWidget, table_name: str):
        """🆕 테이블의 컬럼 크기 복원"""
        widths = self.settings.value(f"{table_name}/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < table.columnCount():
                    table.setColumnWidth(col, int(width))

    def save_all_column_widths(self):
        """🆕 모든 테이블의 컬럼 크기 저장"""
        self.save_column_widths(self.table, "orders_table")
        self.save_column_widths(self.inventory_table, "inventory_table")

    def create_order_purchase_delivery_widget(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        main_splitter = QSplitter(Qt.Vertical)

        order_widget = self.create_order_widget()
        self.purchase_widget = PurchaseWidget(settings=self.settings)  # 🆕 self.purchase_widget로 저장
        self.delivery_widget = DeliveryWidget(self, settings=self.settings)  # ✅ settings 전달
        self.delivery_widget.layout().setContentsMargins(10, 10, 10, 10)  # ✅

        main_splitter.addWidget(order_widget)
        main_splitter.addWidget(self.purchase_widget)
        main_splitter.addWidget(self.delivery_widget)

        main_splitter.setSizes([300, 300, 300])

        layout.addWidget(main_splitter)
        return widget

    def create_inventory_widget(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("재고 현황")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")

        refresh_btn = QtWidgets.QPushButton("새로고침")
        refresh_btn.clicked.connect(lambda: self.load_inventory_data())

        # 전체보기 버튼 추가
        self.btn_show_all_inventory = QtWidgets.QPushButton("미완료만")
        self.btn_show_all_inventory.setCheckable(True)
        self.btn_show_all_inventory.setChecked(False)
        self.btn_show_all_inventory.toggled.connect(self.toggle_show_all_inventory)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(refresh_btn)
        title_layout.addSpacing(12)
        title_layout.addWidget(self.btn_show_all_inventory)

        self.inventory_table = QtWidgets.QTableWidget(0, 6)
        self.inventory_table.setHorizontalHeaderLabels(
            ["발주번호", "발주내용", "발주량/생산량", "납품완료", "재고수량", "상태"]
        )
        self.inventory_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.inventory_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.inventory_table.setAlternatingRowColors(True)
        self.inventory_table.setSortingEnabled(True)

        self.inventory_table.verticalHeader().setDefaultSectionSize(25)
        self.inventory_table.setShowGrid(True)

        header = self.inventory_table.horizontalHeader()
        for col in range(self.inventory_table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.inventory_table.setColumnWidth(0, 100)
        self.inventory_table.setColumnWidth(1, 300)
        self.inventory_table.setColumnWidth(2, 120)
        self.inventory_table.setColumnWidth(3, 100)
        self.inventory_table.setColumnWidth(4, 100)
        self.inventory_table.setColumnWidth(5, 100)

        self.restore_column_widths(self.inventory_table, "inventory_table")
        header.sectionResized.connect(lambda: self.save_column_widths(self.inventory_table, "inventory_table"))

        layout.addLayout(title_layout)
        layout.addWidget(self.inventory_table)

        self.load_inventory_data()

        return widget

    def create_order_widget(self):
        """주문 위젯 생성"""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("주문 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        self.btn_new = QtWidgets.QPushButton("새 주문")
        self.btn_refresh = QtWidgets.QPushButton("새로고침")
        self.btn_show_all = QtWidgets.QPushButton("미청구만")

        self.btn_new.clicked.connect(self.add_order_with_autocomplete)
        self.btn_refresh.clicked.connect(lambda: self.load_due_list(self.only_future))
        self.btn_show_all.setCheckable(True)
        self.btn_show_all.setChecked(False)
        self.btn_show_all.toggled.connect(self.toggle_show_all_billed)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.btn_new)
        title_layout.addSpacing(12)
        title_layout.addWidget(self.btn_refresh)
        title_layout.addWidget(self.btn_show_all)

        # 테이블 컬럼: "품목수" → "품목/수량"으로 변경
        self.table = QtWidgets.QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            ["주문일", "주문번호", "품목코드", "Rev", "품목 / 수량", "제품명", "주문금액(엔)",
             "최초납기", "최종납기", "OA 발송", "청구 완료"]
        )
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.setShowGrid(True)

        self.table.itemDoubleClicked.connect(self.edit_order)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.table.setColumnWidth(0, 100)  # 주문일
        self.table.setColumnWidth(1, 120)  # 주문번호
        self.table.setColumnWidth(2, 120)  # 품목코드
        self.table.setColumnWidth(3, 60)  # Rev
        self.table.setColumnWidth(4, 90)  # 품목/수량 (폭 조정)
        self.table.setColumnWidth(5, 300)  # 제품명
        self.table.setColumnWidth(6, 120)  # 주문금액
        self.table.setColumnWidth(7, 100)  # 최초납기
        self.table.setColumnWidth(8, 100)  # 최종납기
        self.table.setColumnWidth(9, 80)  # OA 발송
        self.table.setColumnWidth(10, 90)  # 청구 완료

        if self.settings:
            self.restore_column_widths(self.table, "orders_table")

        header.sectionResized.connect(lambda: self.save_column_widths(self.table, "orders_table"))

        layout.addLayout(title_layout)
        layout.addWidget(self.table)

        self.order_data = []

        return widget

    def toggle_show_all_billed(self, checked: bool):
        self.show_all_billed = checked
        self.btn_show_all.setText("전체보기" if checked else "미청구만")
        self.load_due_list(self.only_future)

    def sort_by_column(self, column):
        if self.current_sort_column == column:
            self.current_sort_order = Qt.DescendingOrder if self.current_sort_order == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            self.current_sort_column = column
            self.current_sort_order = Qt.AscendingOrder

        self.load_due_list(self.only_future)

    def show_context_menu(self, position):
        if self.table.itemAt(position) is None:
            return

        menu = QMenu(self)

        edit_action = menu.addAction("수정")
        edit_action.triggered.connect(self.edit_order)

        delete_action = menu.addAction("삭제")
        delete_action.triggered.connect(self.delete_order)

        due_change_action = menu.addAction("납기 변경")
        due_change_action.triggered.connect(self.change_due_date)

        menu.exec_(self.table.mapToGlobal(position))

    def add_order_with_autocomplete(self):
        """새 주문 추가"""
        dialog = ProductOrderDialog(self, is_edit=False)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_due_list(self.only_future)

    def load_due_list(self, only_future: bool = True):
        """주문 목록 로드 (신규 구조)"""
        self.only_future = only_future
        try:
            conn = get_conn()
            cur = conn.cursor()

            sql = """
                SELECT 
                    o.id,
                    o.order_dt,
                    o.order_no,
                    o.req_due,
                    o.final_due,
                    o.oa_sent,
                    o.invoice_done,
                    COUNT(oi.id) as item_count,
                    SUM(oi.qty) as total_qty,
                    GROUP_CONCAT(oi.item_code, ', ') as item_codes,
                    GROUP_CONCAT(oi.rev, ', ') as revs,
                    GROUP_CONCAT(oi.product_name, ' | ') as product_names,
                    oa.total_cents / 100.0 as amount_jpy
                FROM orders o
                LEFT JOIN order_items oi ON o.id = oi.order_id
                LEFT JOIN order_amounts oa ON o.id = oa.order_id
            """

            conds = []
            if not self.show_all_billed:
                conds.append("COALESCE(o.invoice_done, 0) = 0")
            if self.only_future:
                conds.append("(o.req_due IS NULL OR date(COALESCE(o.final_due, o.req_due)) >= date('now','localtime'))")

            if conds:
                sql += " WHERE " + " AND ".join(conds)

            sql += " GROUP BY o.id"

            order_clause = self.get_order_clause()
            sql += f" ORDER BY {order_clause}"

            cur.execute(sql)
            rows = cur.fetchall()

            self.order_data = rows
            self.table.setRowCount(len(rows))
            self.table.setSortingEnabled(False)

            for r, row in enumerate(rows):
                (order_id, order_dt, order_no, req_due, final_due,
                 oa_sent, invoice_done, item_count, total_qty, item_codes, revs, product_names, amount_jpy) = row

                # order_id 저장
                item_0 = QtWidgets.QTableWidgetItem("" if order_dt is None else str(order_dt))
                item_0.setData(Qt.UserRole, order_id)
                self.table.setItem(r, 0, item_0)

                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(order_no or "")))

                # 품목코드 표시 (중복 제거 처리)
                if item_codes:
                    codes_list = [c.strip() for c in str(item_codes).split(',') if c.strip() and c.strip() != 'None']
                    unique_codes = []
                    for code in codes_list:
                        if code not in unique_codes:
                            unique_codes.append(code)
                    display_codes = ', '.join(unique_codes)
                    if len(display_codes) > 50:
                        display_codes = display_codes[:47] + "..."
                    self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(display_codes))
                else:
                    self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(""))

                # Rev 표시 (중복 제거 처리)
                if revs:
                    revs_list = [rv.strip() for rv in str(revs).split(',') if rv.strip() and rv.strip() != 'None']
                    unique_revs = []
                    for rv in revs_list:
                        if rv not in unique_revs:
                            unique_revs.append(rv)
                    display_revs = ', '.join(unique_revs) if unique_revs else ""
                    if len(display_revs) > 30:
                        display_revs = display_revs[:27] + "..."
                    self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(display_revs))
                else:
                    self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(""))

                # 품목/수량 표시 (예: "1종/5개")
                total_qty_display = total_qty if total_qty else 0
                self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(f"{item_count}종 / {total_qty_display}개"))

                # 제품명 (여러 개면 요약)
                if product_names:
                    display_names = product_names if len(product_names) < 80 else product_names[:77] + "..."
                    self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(display_names))
                else:
                    self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(""))

                self.table.setItem(r, 6, QtWidgets.QTableWidgetItem(format_money(amount_jpy)))
                self.table.setItem(r, 7, QtWidgets.QTableWidgetItem(str(req_due or "")))
                self.table.setItem(r, 8, QtWidgets.QTableWidgetItem(str(final_due or "")))

                # OA 발송 체크박스
                oa_checkbox = QtWidgets.QCheckBox()
                oa_checkbox.setChecked(bool(oa_sent))
                oa_checkbox.setStyleSheet("QCheckBox { margin-left: 20px; }")
                oa_checkbox.stateChanged.connect(
                    lambda state, oid=order_id: self.update_oa_status(oid, state)
                )

                oa_widget = QtWidgets.QWidget()
                oa_layout = QtWidgets.QHBoxLayout(oa_widget)
                oa_layout.addWidget(oa_checkbox)
                oa_layout.setAlignment(Qt.AlignCenter)
                oa_layout.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(r, 9, oa_widget)

                # 청구 완료 체크박스
                invoice_checkbox = QtWidgets.QCheckBox()
                invoice_checkbox.setChecked(bool(invoice_done))
                invoice_checkbox.setStyleSheet("QCheckBox { margin-left: 20px; }")
                invoice_checkbox.stateChanged.connect(
                    lambda state, oid=order_id: self.update_invoice_status(oid, state)
                )

                invoice_widget = QtWidgets.QWidget()
                invoice_layout = QtWidgets.QHBoxLayout(invoice_widget)
                invoice_layout.addWidget(invoice_checkbox)
                invoice_layout.setAlignment(Qt.AlignCenter)
                invoice_layout.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(r, 10, invoice_widget)

                # ✅ 청구 완료된 항목은 회색으로 표시
                if invoice_done:
                    from PySide6.QtGui import QBrush, QColor
                    for col in range(11):  # 0~10번 컬럼
                        if self.table.item(r, col):
                            self.table.item(r, col).setForeground(QBrush(QColor("#888888")))

            self.table.setSortingEnabled(True)
            for i in range(self.table.rowCount()):
                self.table.setRowHeight(i, 25)

        except Exception as e:
            print(f"주문 목록 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.order_data = []
            self.table.setRowCount(0)
        finally:
            conn.close()

    def update_invoice_status(self, order_id: int, state: int):
        """청구 완료 상태 업데이트"""
        invoice_done = 1 if state == QtCore.Qt.CheckState.Checked.value else 0

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE orders SET invoice_done=?, updated_at=datetime('now','localtime') WHERE id=?",
                        (invoice_done, order_id))
            conn.commit()

            if invoice_done == 1 and not self.show_all_billed:
                self.load_due_list(self.only_future)
                self.statusBar().showMessage("청구 완료 처리되었습니다. (미청구 목록에서 제거됨)", 3000)
            else:
                self.statusBar().showMessage("청구 완료 상태가 변경되었습니다.", 2000)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"청구 상태 업데이트 중 오류:\n{str(e)}")
        finally:
            conn.close()

    def update_oa_status(self, order_id: int, state: int):
        """OA 발송 상태 업데이트"""
        oa_sent = 1 if state == QtCore.Qt.CheckState.Checked.value else 0

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE orders SET oa_sent = ?, updated_at=datetime('now','localtime') WHERE id = ?",
                        (oa_sent, order_id))

            if cur.rowcount > 0:
                conn.commit()
                status_text = "발송됨" if oa_sent else "미발송"
                self.statusBar().showMessage(f"OA 발송 상태가 '{status_text}'으로 변경되었습니다.", 2000)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"OA 상태 업데이트 중 오류 발생:\n{str(e)}")
        finally:
            conn.close()

    def get_order_clause(self):
        """정렬 조건 반환"""
        column_names = [
            "o.order_dt",  # 0: 주문일
            "o.order_no",  # 1: 주문번호
            "item_codes",  # 2: 품목코드
            "revs",  # 3: Rev
            "item_count",  # 4: 품목수
            "product_names",  # 5: 제품명
            "amount_jpy",  # 6: 주문금액
            "o.req_due",  # 7: 최초납기
            "o.final_due",  # 8: 최종납기
            "o.oa_sent",  # 9: OA 발송
            "o.invoice_done"  # 10: 청구 완료
        ]

        if 0 <= self.current_sort_column < len(column_names):
            column = column_names[self.current_sort_column]
            direction = "DESC" if self.current_sort_order == Qt.DescendingOrder else "ASC"
            if self.current_sort_column in [7, 8]:  # 납기일 컬럼
                return f"date({column}) {direction}, o.order_no ASC"
            else:
                return f"{column} {direction}, date(COALESCE(o.final_due, o.req_due)) ASC, o.order_no ASC"
        else:
            return "date(COALESCE(o.final_due, o.req_due)) ASC, o.order_no ASC"

    def get_selected_order(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return None

        item = self.table.item(current_row, 0)
        if not item:
            return None

        order_id = item.data(Qt.UserRole)
        if not order_id:
            return None

        for row in self.order_data:
            if row[0] == order_id:
                return row

        return None

    def change_due_date(self):
        order_data = self.get_selected_order()
        if not order_data:
            QtWidgets.QMessageBox.information(self, "알림", "납기를 변경할 주문을 선택해주세요.")
            return

        # order_data 구조: (order_id, order_dt, order_no, req_due, final_due, oa_sent, invoice_done,
        #                    item_count, item_codes, product_names, amount_jpy)
        order_id = order_data[0]
        order_no = order_data[2]
        req_due = order_data[3]
        final_due = order_data[4]
        product_names = order_data[9]

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"납기 변경 - {order_no}")
        dlg.setMinimumWidth(700)
        form = QtWidgets.QFormLayout(dlg)

        info_label = QtWidgets.QLabel(f"주문: {order_no} - {product_names}")
        info_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
        form.addRow(info_label)

        current_due_label = QtWidgets.QLabel(f"현재 최종납기: {final_due or req_due}")
        current_due_label.setStyleSheet("color: #666;")
        form.addRow(current_due_label)

        form.addRow(QtWidgets.QLabel(""))

        change_date_entry = QtWidgets.QLineEdit()
        change_date_entry.setText(datetime.now().strftime('%Y-%m-%d'))
        change_date_entry.setPlaceholderText("예: 2025-10-15")

        new_due_entry = QtWidgets.QLineEdit()
        new_due_entry.setText(final_due or req_due or "")
        new_due_entry.setPlaceholderText("예: 2025-10-20")

        reason_entry = QtWidgets.QLineEdit()
        reason_entry.setText("고객 요청에 의한 연기")
        reason_entry.setPlaceholderText("예: 고객 요청에 의한 연기")

        form.addRow("변경 요청일*:", change_date_entry)
        form.addRow("새로운 납기일*:", new_due_entry)
        form.addRow("변경 사유:", reason_entry)

        form.addRow(QtWidgets.QLabel(""))
        history_label = QtWidgets.QLabel("납기 변경 이력:")
        history_label.setStyleSheet("font-weight: bold;")
        form.addRow(history_label)

        history_table = QtWidgets.QTableWidget(0, 4)
        history_table.setHorizontalHeaderLabels(["변경일자", "변경전", "변경후", "사유"])
        history_table.setMaximumHeight(150)

        header = history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        history_table.setColumnWidth(3, 200)

        history_data = get_due_change_history(order_id)
        history_table.setRowCount(len(history_data))

        for r, (change_id, change_date, old_due, new_due, reason, created_at) in enumerate(history_data):
            history_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(change_date)))
            history_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(old_due or "")))
            history_table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(new_due)))
            history_table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(reason or "")))

        form.addRow(history_table)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        change_date_raw = change_date_entry.text().strip()
        new_due_raw = new_due_entry.text().strip()
        reason = reason_entry.text().strip()

        if not change_date_raw or not new_due_raw:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "변경 요청일과 새로운 납기일은 필수입니다.")
            return

        change_date = parse_due_text(change_date_raw)
        new_due = parse_due_text(new_due_raw)

        if not change_date or not new_due:
            QtWidgets.QMessageBox.warning(self, "날짜 형식 오류", "날짜 형식이 올바르지 않습니다. 예: 2025-10-15")
            return

        try:
            old_due = final_due or req_due
            add_due_change_record(order_id, change_date, old_due, new_due, reason)
            update_order_final_due_date(order_id, new_due)

            self.load_due_list(self.only_future)
            QtWidgets.QMessageBox.information(self, "완료", "납기일이 변경되었습니다.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"납기 변경 중 오류가 발생했습니다:\n{str(e)}")

    def edit_order(self):
        """주문 수정"""
        order_data = self.get_selected_order()
        if not order_data:
            QtWidgets.QMessageBox.information(self, "알림", "수정할 주문을 선택해주세요.")
            return

        order_id = order_data[0]
        dialog = ProductOrderDialog(self, is_edit=True, order_id=order_id)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_due_list(self.only_future)

        '''order_id, order_dt, order_no, item_code, rev, order_desc, qty, amount_jpy, oa_sent, req_due, final_due, unit_price_cents, invoice_done = order_data

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"주문 수정 - {order_no}")
        form = QtWidgets.QFormLayout(dlg)

        edt_order_dt = QtWidgets.QLineEdit(order_dt or "")
        edt_order_dt.setPlaceholderText("예: 2025-08-27 / 2025/8/27")
        edt_no = QtWidgets.QLineEdit(order_no or "")
        edt_item = QtWidgets.QLineEdit(item_code or "")
        edt_rev = QtWidgets.QLineEdit(rev or "")
        edt_desc = QtWidgets.QLineEdit(order_desc or "")
        edt_desc.setMinimumWidth(560)

        sp_qty = QtWidgets.QSpinBox()
        sp_qty.setRange(1, 1_000_000)
        sp_qty.setValue(qty or 1)
        sp_qty.setGroupSeparatorShown(True)

        # ✅ 변경 전: sp_price_jpy = QtWidgets.QSpinBox()
        # ✅ 변경 후:
        edt_price_jpy = MoneyLineEdit(max_value=1_000_000_000)
        edt_price_jpy.set_value((unit_price_cents or 0) // 100)
        edt_price_jpy.setMinimumWidth(200)

        edt_initial_due = QtWidgets.QLineEdit(req_due or "")
        edt_initial_due.setPlaceholderText("예: 2025-09-03 / 2025/9/3 / 30-Jul-25")

        edt_final_due = QtWidgets.QLineEdit(final_due or "")
        edt_final_due.setPlaceholderText("예: 2025-09-03 / 2025/9/3 / 30-Jul-25")

        form.addRow("주문일", edt_order_dt)
        form.addRow("주문번호*", edt_no)
        form.addRow("품목코드", edt_item)
        form.addRow("Rev", edt_rev)
        form.addRow("주문제품명*", edt_desc)
        form.addRow("주문대수", sp_qty)
        form.addRow("단가(엔)", edt_price_jpy)  # ✅ 변경됨
        form.addRow("최초 납기일", edt_initial_due)
        form.addRow("최종 납기일", edt_final_due)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        new_order_dt_raw = edt_order_dt.text().strip()
        new_order_dt = parse_due_text(new_order_dt_raw) if new_order_dt_raw else None
        new_order_no = edt_no.text().strip()
        new_item_code = edt_item.text().strip() or None
        new_rev = edt_rev.text().strip() or None
        new_order_desc = edt_desc.text().strip()

        if not new_order_no or not new_order_desc:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "주문번호와 주문제품명은 필수입니다.")
            return

        if new_order_dt_raw and not new_order_dt:
            QtWidgets.QMessageBox.warning(self, "주문일", "주문일 형식이 올바르지 않습니다. 예: 2025-08-27 / 30-Jul-25")
            return

        new_qty = sp_qty.value()
        new_unit_price_cents = edt_price_jpy.get_value() * 100  # ✅ 변경됨

        initial_due_raw = edt_initial_due.text().strip()
        new_initial_due = parse_due_text(initial_due_raw) if initial_due_raw else None

        final_due_raw = edt_final_due.text().strip()
        new_final_due = parse_due_text(final_due_raw) if final_due_raw else None

        if initial_due_raw and not new_initial_due:
            QtWidgets.QMessageBox.warning(self, "최초 납기일", "최초 납기일 형식이 올바르지 않습니다. 예: 2025-09-03 / 30-Jul-25")
            return

        if final_due_raw and not new_final_due:
            QtWidgets.QMessageBox.warning(self, "최종 납기일", "최종 납기일 형식이 올바르지 않습니다. 예: 2025-09-03 / 30-Jul-25")
            return

        conn = get_conn()
        cur = conn.cursor()

        if new_order_no != order_no:
            cur.execute("SELECT 1 FROM orders WHERE order_no=? AND id!=?", (new_order_no, order_id))
            if cur.fetchone():
                reply = QtWidgets.QMessageBox.question(
                    self, "주문번호 중복",
                    f"주문번호 '{new_order_no}'가 이미 존재합니다.\n"
                    f"동일한 주문번호로 여러 항목을 주문하는 경우가 있습니다.\n\n"
                    f"계속 진행하시겠습니까?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No
                )
                if reply != QtWidgets.QMessageBox.Yes:
                    return

        cur.execute("""
            UPDATE orders 
            SET order_dt=?, order_no=?, item_code=?, rev=?, order_desc=?, qty=?, req_due=?, final_due=?, unit_price_cents=?
            WHERE id=?
        """, (new_order_dt, new_order_no, new_item_code, new_rev, new_order_desc, new_qty, new_initial_due,
              new_final_due, new_unit_price_cents, order_id))
        conn.commit()

        self.load_due_list(self.only_future)
        QtWidgets.QMessageBox.information(self, "완료", "주문이 수정되었습니다.")'''

    def delete_order(self):
        """주문 삭제"""
        order_data = self.get_selected_order()
        if not order_data:
            QtWidgets.QMessageBox.information(self, "알림", "삭제할 주문을 선택해주세요.")
            return

        order_id = order_data[0]
        order_no = order_data[2]
        item_count = order_data[7]
        amount_jpy = order_data[10]
        final_due = order_data[4]
        req_due = order_data[3]

        reply = QtWidgets.QMessageBox.question(
            self,
            "주문 삭제",
            f"정말로 다음 주문을 삭제하시겠습니까?\n\n"
            f"주문번호: {order_no}\n"
            f"품목 수: {item_count}개\n"
            f"금액: {format_money(amount_jpy)}엔\n"
            f"최종납기: {final_due or req_due}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        from ..db import delete_order

        try:
            delete_order(order_id)
            self.load_due_list(self.only_future)
            QtWidgets.QMessageBox.information(self, "완료", f"주문 '{order_no}'이 삭제되었습니다.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"주문 삭제 중 오류가 발생했습니다:\n{str(e)}")

    def toggle_show_all_inventory(self, checked: bool):
        """재고 현황 전체보기 토글"""
        self.show_all_inventory = checked
        self.btn_show_all_inventory.setText("전체보기" if checked else "미완료만")
        self.load_inventory_data()

    def load_inventory_data(self):
        """재고 현황 로드"""
        try:
            conn = get_conn()
            cur = conn.cursor()

            # ✅ 수정된 SQL 쿼리: d.purchase_id -> delivery_purchase_links 테이블 조인으로 변경
            sql = """
                SELECT
                    p.id,
                    p.purchase_no,
                    GROUP_CONCAT(pi.product_name, ' | ') as purchase_desc,
                    SUM(pi.qty) as order_qty,
                    (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id) as produced_qty,
                    (SELECT COALESCE(SUM(di.qty), 0)
                     FROM delivery_items di
                     JOIN delivery_purchase_links dpl ON di.delivery_id = dpl.delivery_id
                     WHERE dpl.purchase_id = p.id) as delivered_qty
                FROM purchases p
                LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
                WHERE p.purchase_no IS NOT NULL
                GROUP BY p.id
                ORDER BY p.purchase_dt DESC
            """

            cur.execute(sql)
            rows = cur.fetchall()

            # 필터링: 미완료만 보기
            if not self.show_all_inventory:
                filtered_rows = []
                for row in rows:
                    purchase_id, purchase_no, purchase_desc, order_qty, produced_qty, delivered_qty = row
                    order_qty = order_qty or 0
                    produced_qty = produced_qty or 0
                    delivered_qty = delivered_qty or 0
                    inventory_qty = produced_qty - delivered_qty
                    is_completed = (
                                order_qty > 0 and order_qty == produced_qty == delivered_qty and inventory_qty == 0)

                    if not is_completed:
                        filtered_rows.append(row)
                rows = filtered_rows

            self.inventory_table.setRowCount(len(rows))
            self.inventory_table.setSortingEnabled(False)

            for r, row in enumerate(rows):
                purchase_id, purchase_no, purchase_desc, order_qty, produced_qty, delivered_qty = row
                order_qty = order_qty or 0
                produced_qty = produced_qty or 0
                delivered_qty = delivered_qty or 0
                inventory_qty = produced_qty - delivered_qty
                is_completed = (order_qty > 0 and order_qty == produced_qty == delivered_qty and inventory_qty == 0)

                # 상태 표시 로직 개선
                if is_completed:
                    status = "정상 납품 완료"
                    status_color = "#888888"  # 완료는 회색
                elif produced_qty == 0:
                    status = "미생산"
                    status_color = "#6c757d"
                elif delivered_qty > produced_qty:
                    status = "납품 초과"
                    status_color = "#dc3545"  # 오류는 빨간색
                elif inventory_qty == 0 and produced_qty > 0:
                    status = "재고없음 (납품대기)"
                    status_color = "#007bff"  # 파란색
                elif inventory_qty > 0:
                    status = f"재고 {inventory_qty}개"
                    status_color = "#28a745"  # 정상 재고는 초록색
                else:
                    status = "확인필요"
                    status_color = "#ffc107"  # 노란색

                self.inventory_table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(purchase_no or "")))
                self.inventory_table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(purchase_desc or "")))
                self.inventory_table.setItem(r, 2,
                                             QtWidgets.QTableWidgetItem(f"{order_qty or 0} / {produced_qty or 0}"))
                self.inventory_table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(delivered_qty or 0)))
                self.inventory_table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(inventory_qty or 0)))

                status_item = QtWidgets.QTableWidgetItem(status)
                status_item.setForeground(QtGui.QBrush(QtGui.QColor(status_color)))
                font = status_item.font()
                font.setBold(True)
                status_item.setFont(font)
                self.inventory_table.setItem(r, 5, status_item)

                if is_completed:
                    for col in range(6):
                        if self.inventory_table.item(r, col):
                            self.inventory_table.item(r, col).setForeground(QtGui.QBrush(QtGui.QColor("#888888")))

            self.inventory_table.setSortingEnabled(True)
            for i in range(self.table.rowCount()):
                self.table.setRowHeight(i, 25)

            conn.close()

        except Exception as e:
            print(f"재고 현황 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.inventory_table.setRowCount(0)