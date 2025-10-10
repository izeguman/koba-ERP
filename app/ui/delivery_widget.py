# app/ui/delivery_widget.py
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QHeaderView
from datetime import datetime
from ..db import (get_conn, create_delivery_with_items, get_delivery_with_items,
                  get_all_deliveries_summary)


def parse_datetime_text(text: str) -> str | None:
    """날짜/시간 파싱 함수"""
    s = (text or "").strip()
    if not s:
        return None

    # 날짜+시간 형식
    datetime_fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ]

    # 날짜만 있는 형식
    date_fmts = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%y-%m-%d",
        "%y/%m/%d",
        "%d-%b-%y",
        "%d-%b-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]

    # 먼저 날짜+시간 형식 시도
    for f in datetime_fmts:
        try:
            dt = datetime.strptime(s, f)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

    # 날짜만 있으면 00:00:00 추가
    for f in date_fmts:
        try:
            dt = datetime.strptime(s, f)
            if dt.year < 2000:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime("%Y-%m-%d 00:00:00")
        except Exception:
            continue

    return None


class DeliveryWidget(QtWidgets.QWidget):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.delivery_data = []
        self.show_completed = False  # ✅ 추가
        self.setup_ui()
        self.load_delivery_list()

    def toggle_show_completed(self, checked):
        """완료된 납품 표시 토글"""
        self.show_completed = checked
        self.btn_show_completed.setText("전체보기" if checked else "미완료만")
        self.load_delivery_list()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("납품 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        # ✅ 완료된 납품 보기 토글 버튼 추가
        self.btn_show_completed = QtWidgets.QPushButton("미완료만")
        self.btn_show_completed.setCheckable(True)
        self.btn_show_completed.setChecked(False)
        self.btn_show_completed.clicked.connect(self.toggle_show_completed)

        btn_new = QtWidgets.QPushButton("새 납품")
        btn_refresh = QtWidgets.QPushButton("새로고침")

        btn_new.clicked.connect(self.add_delivery)
        btn_refresh.clicked.connect(self.load_delivery_list)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(btn_new)
        title_layout.addWidget(btn_refresh)
        title_layout.addWidget(self.btn_show_completed)  # ✅ 추가

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["발송일시", "인보이스번호", "총수량", "품목수", "운송사", "2차포장", "연결정보"]
        )

        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.doubleClicked.connect(self.edit_delivery)

        # ✅ 컬럼 크기 저장/복원
        header = self.table.horizontalHeader()
        for col in range(7):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        if self.settings:
            self.restore_column_widths()

        header.sectionResized.connect(self.save_column_widths)

        button_layout = QtWidgets.QHBoxLayout()
        self.btn_edit = QtWidgets.QPushButton("수정")
        self.btn_delete = QtWidgets.QPushButton("삭제")

        self.btn_edit.clicked.connect(self.edit_delivery)
        self.btn_delete.clicked.connect(self.delete_delivery)

        button_layout.addWidget(self.btn_edit)
        button_layout.addWidget(self.btn_delete)
        button_layout.addStretch()

        layout.addLayout(title_layout)
        layout.addWidget(self.table)
        layout.addLayout(button_layout)

        # ✅ 완료 납품 표시 여부 초기화
        self.show_completed = False

    def save_column_widths(self):
        """테이블 컬럼 크기 저장"""
        if not self.settings:
            return
        widths = []
        for col in range(self.table.columnCount()):
            widths.append(self.table.columnWidth(col))
        self.settings.setValue("delivery_table/column_widths", widths)

    def restore_column_widths(self):
        """테이블 컬럼 크기 복원"""
        if not self.settings:
            return
        widths = self.settings.value("delivery_table/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < self.table.columnCount():
                    self.table.setColumnWidth(col, int(width))

    def refresh_product_list(self):
        """✅ 제품 생산 위젯 새로고침"""
        try:
            main_window = self.window()
            if hasattr(main_window, 'product_production_widget'):
                main_window.product_production_widget.load_product_list()
                # print("✅ 제품 생산 목록이 자동으로 새로고침되었습니다.")
        except Exception as e:
            print(f"제품 생산 목록 새로고침 실패: {e}")

    # delivery_widget.py의 load_delivery_list() 메서드 전체 교체

    # delivery_widget.py의 load_delivery_list() 메서드 전체 교체

    def load_delivery_list(self):
        try:
            # ✅ 링크 테이블을 사용하는 새로운 쿼리 (GROUP_CONCAT DISTINCT 수정)
            sql = """
                SELECT 
                    d.id,
                    d.invoice_no,
                    d.ship_datetime,
                    d.carrier,
                    d.secondary_packaging,
                    (SELECT GROUP_CONCAT(DISTINCT o2.order_no)
                     FROM delivery_order_links dol2
                     LEFT JOIN orders o2 ON dol2.order_id = o2.id
                     WHERE dol2.delivery_id = d.id) as order_nos,
                    (SELECT GROUP_CONCAT(DISTINCT p2.purchase_no)
                     FROM delivery_purchase_links dpl2
                     LEFT JOIN purchases p2 ON dpl2.purchase_id = p2.id
                     WHERE dpl2.delivery_id = d.id) as purchase_nos,
                    -- 연결된 모든 주문이 청구 완료되었는지 확인
                    CASE 
                        WHEN EXISTS (
                            SELECT 1 FROM delivery_order_links dol3 
                            WHERE dol3.delivery_id = d.id
                        ) AND NOT EXISTS (
                            SELECT 1 
                            FROM delivery_order_links dol4
                            LEFT JOIN orders o3 ON dol4.order_id = o3.id
                            WHERE dol4.delivery_id = d.id 
                            AND COALESCE(o3.invoice_done, 0) = 0
                        )
                        THEN 1
                        ELSE 0
                    END as is_completed,
                    COALESCE(item_stats.total_qty, 0) as total_qty,
                    COALESCE(item_stats.unique_items, 0) as item_count
                FROM deliveries d
                LEFT JOIN (
                    SELECT
                        delivery_id,
                        SUM(qty) as total_qty,
                        COUNT(DISTINCT item_code) as unique_items
                    FROM delivery_items
                    WHERE item_code IS NOT NULL AND item_code != ''
                    GROUP BY delivery_id
                ) as item_stats ON d.id = item_stats.delivery_id
                ORDER BY d.ship_datetime DESC
            """

            from ..db import query_all
            self.delivery_data = query_all(sql)
            self.table.setSortingEnabled(False)
            self.table.setRowCount(0)

            for row_data in self.delivery_data:
                (delivery_id, invoice_no, ship_datetime, carrier, secondary_packaging,
                 order_nos, purchase_nos, is_completed, total_qty, item_count) = row_data

                # ✅ 완료된 납품 필터링
                if is_completed and not self.show_completed:
                    continue

                row_position = self.table.rowCount()
                self.table.insertRow(row_position)

                item = QtWidgets.QTableWidgetItem(ship_datetime or "")
                item.setData(Qt.UserRole, delivery_id)
                self.table.setItem(row_position, 0, item)
                self.table.setItem(row_position, 1, QtWidgets.QTableWidgetItem(invoice_no or ""))
                self.table.setItem(row_position, 2, QtWidgets.QTableWidgetItem(str(total_qty)))
                self.table.setItem(row_position, 3, QtWidgets.QTableWidgetItem(str(item_count)))
                self.table.setItem(row_position, 4, QtWidgets.QTableWidgetItem(carrier or ""))
                self.table.setItem(row_position, 5, QtWidgets.QTableWidgetItem(secondary_packaging or ""))

                # ✅ 연결 정보 (여러 개 표시)
                connection_info = []
                if order_nos:
                    connection_info.append(f"주문:{order_nos}")
                if purchase_nos:
                    connection_info.append(f"발주:{purchase_nos}")
                connection_str = " / ".join(connection_info) if connection_info else ""
                self.table.setItem(row_position, 6, QtWidgets.QTableWidgetItem(connection_str))

                # ✅ 완료된 납품은 회색으로 표시
                if is_completed:
                    for col in range(7):
                        if self.table.item(row_position, col):
                            self.table.item(row_position, col).setForeground(QBrush(QColor("#888888")))

            self.table.setSortingEnabled(True)
            for i in range(self.table.rowCount()):
                self.table.setRowHeight(i, 25)

        except Exception as e:
            print(f"납품 목록 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.delivery_data = []
            self.table.setRowCount(0)

    def get_selected_delivery_id(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return None

        item = self.table.item(current_row, 0)
        if not item:
            return None

        return item.data(Qt.UserRole)

    def add_delivery(self):
        dialog = DeliveryDialog(self, is_edit=False)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_delivery_list()
            self.refresh_product_list()

    def edit_delivery(self):
        delivery_id = self.get_selected_delivery_id()
        if not delivery_id:
            QtWidgets.QMessageBox.information(self, "알림", "수정할 납품을 선택해주세요.")
            return

        dialog = DeliveryDialog(self, is_edit=True, delivery_id=delivery_id)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_delivery_list()
            self.refresh_product_list()

    def delete_delivery(self):
        delivery_id = self.get_selected_delivery_id()
        if not delivery_id:
            QtWidgets.QMessageBox.information(self, "알림", "삭제할 납품을 선택해주세요.")
            return

        delivery_info = get_delivery_with_items(delivery_id)
        if not delivery_info:
            QtWidgets.QMessageBox.warning(self, "오류", "납품 정보를 찾을 수 없습니다.")
            return

        header = delivery_info['header']
        items = delivery_info['items']
        invoice_no = header[1]

        reply = QtWidgets.QMessageBox.question(
            self,
            "납품 삭제",
            f"정말로 다음 납품을 삭제하시겠습니까?\n\n"
            f"인보이스번호: {invoice_no}\n"
            f"품목수: {len(items)}개",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            conn = get_conn()

            # ✅ 먼저 납품된 제품들의 상태를 되돌림
            from ..db import unmark_products_as_delivered
            unmark_products_as_delivered(delivery_id, conn)

            # 납품 삭제
            cur = conn.cursor()
            cur.execute("DELETE FROM deliveries WHERE id=?", (delivery_id,))
            conn.commit()
            conn.close()

            self.load_delivery_list()
            self.refresh_product_list()  # ✅ 제품 목록도 새로고침
            QtWidgets.QMessageBox.information(self, "완료", f"납품 '{invoice_no}'이 삭제되었습니다.")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"납품 삭제 중 오류가 발생했습니다:\n{str(e)}")


class DeliveryDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, is_edit=False, delivery_id=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.delivery_id = delivery_id
        self.items = []
        self.setup_ui()

        if is_edit and delivery_id:
            self.load_delivery_data()

    def setup_ui(self):
        title = "납품 수정" if self.is_edit else "새 납품 추가"
        self.setWindowTitle(title)
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)

        main_layout = QtWidgets.QVBoxLayout(self)

        # 상단: 헤더 정보
        header_group = QtWidgets.QGroupBox("납품 기본 정보")
        header_form = QtWidgets.QFormLayout(header_group)

        self.edt_invoice_no = QtWidgets.QLineEdit()
        self.edt_invoice_no.setPlaceholderText("인보이스번호 (필수)")

        self.edt_ship_datetime = QtWidgets.QLineEdit()
        self.edt_ship_datetime.setPlaceholderText("예: 2025-08-27 14:30 / 2025-08-27")

        self.edt_carrier = QtWidgets.QLineEdit()
        self.edt_carrier.setPlaceholderText("운송사")

        if not self.is_edit:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("""
                    SELECT carrier FROM deliveries 
                    WHERE carrier IS NOT NULL AND carrier != ''
                    ORDER BY id DESC 
                    LIMIT 1
                """)
                result = cur.fetchone()
                if result:
                    self.edt_carrier.setText(result[0])
                    self.edt_carrier.setStyleSheet("background-color: #fffacd;")
                conn.close()
            except Exception as e:
                print(f"마지막 운송사 조회 오류: {e}")

        self.edt_secondary_packaging = QtWidgets.QLineEdit()
        self.edt_secondary_packaging.setPlaceholderText("2차 포장 정보")
        self.edt_secondary_packaging.setMinimumWidth(400)

        purchase_label = QtWidgets.QLabel("연결할 발주번호 (복수 선택 가능):")
        purchase_label.setStyleSheet("font-weight: bold;")

        self.purchase_list = QtWidgets.QListWidget()
        self.purchase_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.purchase_list.setMaximumHeight(100)
        self.purchase_list.setStyleSheet("""
            QListWidget::item:selected {
                background-color: #ffeb3b; color: #000000; border: 2px solid #fbc02d;
            }
            QListWidget::item:hover {
                background-color: #fff9c4; border: 1px solid #fbc02d;
            }
        """)
        self.load_available_purchases()

        order_label = QtWidgets.QLabel("연결할 주문번호 (복수 선택 가능):")
        order_label.setStyleSheet("font-weight: bold;")

        self.order_list = QtWidgets.QListWidget()
        self.order_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.order_list.setMaximumHeight(100)
        self.order_list.setStyleSheet("""
            QListWidget::item:selected {
                background-color: #ffeb3b; color: #000000; border: 2px solid #fbc02d;
            }
            QListWidget::item:hover {
                background-color: #fff9c4; border: 1px solid #fbc02d;
            }
        """)
        self.load_available_orders()

        header_form.addRow("인보이스번호*", self.edt_invoice_no)
        header_form.addRow("발송일시", self.edt_ship_datetime)
        header_form.addRow("운송사", self.edt_carrier)
        header_form.addRow("2차 포장 정보", self.edt_secondary_packaging)
        header_form.addRow("", QtWidgets.QLabel(""))
        header_form.addRow(purchase_label)
        header_form.addRow(self.purchase_list)
        header_form.addRow(order_label)
        header_form.addRow(self.order_list)

        item_group = QtWidgets.QGroupBox("납품 품목")
        item_layout = QtWidgets.QVBoxLayout(item_group)

        self.item_table = QtWidgets.QTableWidget(0, 5)
        # ✅ 헤더 수정: "Rev" -> "제조코드"
        self.item_table.setHorizontalHeaderLabels(["생산된 제품 선택", "품목코드", "제조코드", "수량", ""])

        header = self.item_table.horizontalHeader()
        for col in range(5):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.item_table.setColumnWidth(0, 250)
        self.item_table.setColumnWidth(1, 120)
        self.item_table.setColumnWidth(2, 80)  # ✅ 제조코드 컬럼 폭
        self.item_table.setColumnWidth(3, 80)
        self.item_table.setColumnWidth(4, 70)

        from PySide6.QtCore import QSettings
        settings = QSettings("KOBATECH", "ProductionManagement")
        widths = settings.value("delivery_item_table/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < 5:
                    self.item_table.setColumnWidth(col, int(width))

        header.sectionResized.connect(self.save_item_table_column_widths)

        item_button_layout = QtWidgets.QHBoxLayout()
        self.btn_add_item = QtWidgets.QPushButton("+ 품목 추가")
        self.btn_add_item.clicked.connect(self.add_item_row)
        item_button_layout.addWidget(self.btn_add_item)
        item_button_layout.addStretch()

        item_layout.addWidget(self.item_table)
        item_layout.addLayout(item_button_layout)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept_dialog)
        button_box.rejected.connect(self.reject)

        main_layout.addWidget(header_group)
        main_layout.addWidget(item_group, 1)
        main_layout.addWidget(button_box)

        if not self.is_edit:
            self.add_item_row()

    def load_available_purchases(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            if self.is_edit and self.delivery_id:
                cur.execute("""
                    SELECT p.id, p.purchase_no, GROUP_CONCAT(pi.product_name, ' | ') as desc, SUM(pi.qty) as qty
                    FROM purchases p LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
                    WHERE p.id IN (SELECT purchase_id FROM delivery_purchase_links WHERE delivery_id = ?)
                    OR p.id NOT IN (SELECT dpl.purchase_id FROM delivery_purchase_links dpl WHERE dpl.delivery_id != ?)
                    GROUP BY p.id ORDER BY p.purchase_dt DESC
                """, (self.delivery_id, self.delivery_id))
            else:
                cur.execute("""
                    SELECT p.id, p.purchase_no, GROUP_CONCAT(pi.product_name, ' | ') as desc, SUM(pi.qty) as qty
                    FROM purchases p LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
                    WHERE p.id NOT IN (SELECT DISTINCT purchase_id FROM delivery_purchase_links)
                    GROUP BY p.id ORDER BY p.purchase_dt DESC
                """)
            for purchase_id, purchase_no, desc, qty in cur.fetchall():
                display_text = f"{purchase_no} - {desc} ({qty}개)"
                item = QtWidgets.QListWidgetItem(display_text)
                item.setData(Qt.UserRole, purchase_id)
                self.purchase_list.addItem(item)
            conn.close()
        except Exception as e:
            print(f"발주 목록 로드 오류: {e}")

    def load_available_orders(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            if self.is_edit and self.delivery_id:
                cur.execute("""
                    SELECT o.id, o.order_no, GROUP_CONCAT(oi.product_name, ' | ') as desc, SUM(oi.qty) as qty
                    FROM orders o LEFT JOIN order_items oi ON o.id = oi.order_id
                    WHERE o.id IN (SELECT order_id FROM delivery_order_links WHERE delivery_id = ?)
                    OR o.invoice_done = 0
                    GROUP BY o.id ORDER BY o.order_dt DESC
                """, (self.delivery_id,))
            else:
                cur.execute("""
                    SELECT o.id, o.order_no, GROUP_CONCAT(oi.product_name, ' | ') as desc, SUM(oi.qty) as qty
                    FROM orders o LEFT JOIN order_items oi ON o.id = oi.order_id
                    WHERE o.invoice_done = 0 GROUP BY o.id ORDER BY o.order_dt DESC
                """)
            for order_id, order_no, desc, qty in cur.fetchall():
                display_text = f"{order_no} - {desc} ({qty}개)"
                item = QtWidgets.QListWidgetItem(display_text)
                item.setData(Qt.UserRole, order_id)
                self.order_list.addItem(item)
            conn.close()
        except Exception as e:
            print(f"주문 목록 로드 오류: {e}")

    def save_item_table_column_widths(self):
        from PySide6.QtCore import QSettings
        settings = QSettings("KOBATECH", "ProductionManagement")
        widths = []
        for col in range(5):
            widths.append(self.item_table.columnWidth(col))
        settings.setValue("delivery_item_table/column_widths", widths)

    def load_produced_products(self, combo: QtWidgets.QComboBox):
        try:
            conn = get_conn()
            cur = conn.cursor()
            if hasattr(self, 'delivery_id') and self.delivery_id:
                cur.execute("""
                    SELECT pr.id, pr.part_no, pr.product_name, pr.serial_no, pr.manufacture_code,
                           pr.manufacture_date, p.purchase_no, pr.purchase_id
                    FROM products pr LEFT JOIN purchases p ON pr.purchase_id = p.id
                    WHERE (pr.delivery_id IS NULL OR pr.delivery_id = ?)
                    ORDER BY p.purchase_no DESC, pr.part_no ASC, pr.serial_no ASC
                """, (self.delivery_id,))
            else:
                cur.execute("""
                    SELECT pr.id, pr.part_no, pr.product_name, pr.serial_no, pr.manufacture_code,
                           pr.manufacture_date, p.purchase_no, pr.purchase_id
                    FROM products pr LEFT JOIN purchases p ON pr.purchase_id = p.id
                    WHERE pr.delivery_id IS NULL
                    ORDER BY p.purchase_no DESC, pr.part_no ASC, pr.serial_no ASC
                """)
            products = cur.fetchall()
            conn.close()
            if not products:
                combo.addItem("납품 가능한 제품이 없습니다", None)
                combo.setEnabled(False)
                return

            purchase_groups = {}
            for product in products:
                _, _, _, _, _, _, purchase_no, _ = product
                if purchase_no not in purchase_groups:
                    purchase_groups[purchase_no] = []
                purchase_groups[purchase_no].append(dict(zip(['id', 'part_no', 'product_name', 'serial_no',
                                                              'manufacture_code', 'manufacture_date', 'purchase_no',
                                                              'purchase_id'], product)))
            for purchase_no, products_list in purchase_groups.items():
                combo.addItem(f"━━━ {purchase_no or '발주 미지정'} ━━━", None)
                for product in products_list:
                    combo.addItem(f"  {product['serial_no']} | {product['product_name']}", product)
        except Exception as e:
            print(f"생산 제품 로드 중 오류: {e}")

    def on_produced_product_selected(self, index):
        """생산된 제품 선택 시 품목코드와 제조코드 자동 입력"""
        combo = self.sender()
        if not combo: return

        for row in range(self.item_table.rowCount()):
            if self.item_table.cellWidget(row, 0) is combo:
                product_data = combo.currentData()
                item_code_edit = self.item_table.cellWidget(row, 1)
                mfg_code_edit = self.item_table.cellWidget(row, 2)

                if not product_data:
                    if item_code_edit: item_code_edit.setText("")
                    if mfg_code_edit: mfg_code_edit.setText("")
                    return

                if item_code_edit:
                    item_code_edit.setText(product_data.get('part_no', ''))

                # ✅ Rev 대신 제조코드(manufacture_code)를 채웁니다.
                if mfg_code_edit:
                    mfg_code_edit.setText(product_data.get('manufacture_code', ''))

                return

    def add_item_row(self):
        row = self.item_table.rowCount()
        self.item_table.insertRow(row)

        product_combo = QtWidgets.QComboBox()
        product_combo.setEditable(True)
        product_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        product_combo.addItem("생산된 제품 선택...", None)
        self.load_produced_products(product_combo)
        product_combo.currentIndexChanged.connect(self.on_produced_product_selected)
        self.item_table.setCellWidget(row, 0, product_combo)

        item_code_edit = QtWidgets.QLineEdit()
        item_code_edit.setReadOnly(True)
        item_code_edit.setStyleSheet("background-color: #f0f0f0;")
        self.item_table.setCellWidget(row, 1, item_code_edit)

        # ✅ Rev 대신 제조코드 위젯을 추가합니다.
        mfg_code_edit = QtWidgets.QLineEdit()
        mfg_code_edit.setReadOnly(True)
        mfg_code_edit.setStyleSheet("background-color: #f0f0f0;")
        self.item_table.setCellWidget(row, 2, mfg_code_edit)

        qty_spin = QtWidgets.QSpinBox()
        qty_spin.setRange(1, 1_000_000)
        qty_spin.setValue(1)
        qty_spin.setGroupSeparatorShown(True)
        self.item_table.setCellWidget(row, 3, qty_spin)

        btn_delete = QtWidgets.QPushButton("삭제")
        btn_delete.clicked.connect(lambda checked, r=row: self.delete_item_row(r))
        self.item_table.setCellWidget(row, 4, btn_delete)

    def delete_item_row(self, row):
        if self.item_table.rowCount() <= 1:
            QtWidgets.QMessageBox.warning(self, "경고", "최소 1개의 품목이 필요합니다.")
            return
        self.item_table.removeRow(row)

    def load_delivery_data(self):
        if not self.delivery_id: return
        delivery_info = get_delivery_with_items(self.delivery_id)
        if not delivery_info:
            QtWidgets.QMessageBox.warning(self, "오류", "납품 정보를 찾을 수 없습니다.")
            self.reject()
            return

        header = delivery_info['header']
        self.edt_invoice_no.setText(header[1] or "")
        self.edt_ship_datetime.setText(header[2] or "")
        self.edt_carrier.setText(header[3] or "")
        self.edt_secondary_packaging.setText(header[4] or "")

        from ..db import query_all
        linked_purchases = [row[0] for row in
                            query_all("SELECT purchase_id FROM delivery_purchase_links WHERE delivery_id = ?",
                                      (self.delivery_id,))]
        linked_orders = [row[0] for row in query_all("SELECT order_id FROM delivery_order_links WHERE delivery_id = ?",
                                                     (self.delivery_id,))]

        for i in range(self.purchase_list.count()):
            item = self.purchase_list.item(i)
            if item.data(Qt.UserRole) in linked_purchases: item.setSelected(True)
        for i in range(self.order_list.count()):
            item = self.order_list.item(i)
            if item.data(Qt.UserRole) in linked_orders: item.setSelected(True)

        self.item_table.setRowCount(0)
        for item_data in delivery_info['items']:
            _, item_code, serial_no, manufacture_code, product_name, qty = item_data
            row = self.item_table.rowCount()
            self.item_table.insertRow(row)

            product_combo = QtWidgets.QComboBox()
            product_combo.setEditable(True)
            product_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
            product_combo.addItem("생산된 제품 선택...", None)
            self.load_produced_products(product_combo)
            if item_code and serial_no:
                for i in range(product_combo.count()):
                    data = product_combo.itemData(i)
                    if data and isinstance(data, dict) and data.get('part_no') == item_code and data.get(
                            'serial_no') == serial_no:
                        product_combo.blockSignals(True)
                        product_combo.setCurrentIndex(i)
                        product_combo.blockSignals(False)
                        break
            product_combo.currentIndexChanged.connect(self.on_produced_product_selected)
            self.item_table.setCellWidget(row, 0, product_combo)

            item_code_edit = QtWidgets.QLineEdit(item_code or "")
            item_code_edit.setReadOnly(True)
            item_code_edit.setStyleSheet("background-color: #f0f0f0;")
            self.item_table.setCellWidget(row, 1, item_code_edit)

            # ✅ Rev 대신 제조코드 위젯을 추가하고 값을 채웁니다.
            mfg_code_edit = QtWidgets.QLineEdit(manufacture_code or "")
            mfg_code_edit.setReadOnly(True)
            mfg_code_edit.setStyleSheet("background-color: #f0f0f0;")
            self.item_table.setCellWidget(row, 2, mfg_code_edit)

            qty_spin = QtWidgets.QSpinBox()
            qty_spin.setRange(1, 1_000_000)
            qty_spin.setValue(qty)
            qty_spin.setGroupSeparatorShown(True)
            self.item_table.setCellWidget(row, 3, qty_spin)

            btn_delete = QtWidgets.QPushButton("삭제")
            btn_delete.clicked.connect(lambda checked, r=row: self.delete_item_row(r))
            self.item_table.setCellWidget(row, 4, btn_delete)

    def accept_dialog(self):
        invoice_no = self.edt_invoice_no.text().strip()
        if not invoice_no:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "인보이스번호는 필수입니다.")
            return

        ship_datetime_raw = self.edt_ship_datetime.text().strip()
        ship_datetime = parse_datetime_text(ship_datetime_raw) if ship_datetime_raw else None
        if ship_datetime_raw and not ship_datetime:
            QtWidgets.QMessageBox.warning(self, "날짜 형식 오류", "발송일시 형식이 올바르지 않습니다.\n예: 2025-10-15 14:30")
            return

        carrier = self.edt_carrier.text().strip()
        secondary_packaging = self.edt_secondary_packaging.text().strip()
        selected_purchase_ids = [self.purchase_list.item(i).data(Qt.UserRole) for i in range(self.purchase_list.count())
                                 if self.purchase_list.item(i).isSelected()]
        selected_order_ids = [self.order_list.item(i).data(Qt.UserRole) for i in range(self.order_list.count()) if
                              self.order_list.item(i).isSelected()]

        final_items = []
        for row in range(self.item_table.rowCount()):
            product_combo = self.item_table.cellWidget(row, 0)
            if not product_combo or not product_combo.currentData(): continue
            selected_product = product_combo.currentData()
            item_code_edit = self.item_table.cellWidget(row, 1)
            item_code = item_code_edit.text() if item_code_edit else selected_product.get('part_no')
            qty_spin = self.item_table.cellWidget(row, 3)
            qty = qty_spin.value() if qty_spin else 1
            final_items.append({
                'item_code': item_code,
                'serial_no': selected_product.get('serial_no'),
                'manufacture_code': selected_product.get('manufacture_code'),
                'product_name': selected_product.get('product_name'),
                'qty': qty
            })

        if not final_items:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "최소 1개 이상의 품목이 필요합니다.")
            return

        from ..db import mark_products_as_delivered, unmark_products_as_delivered
        conn = get_conn()
        try:
            cur = conn.cursor()
            delivery_id = self.delivery_id
            if self.is_edit:
                unmark_products_as_delivered(delivery_id, conn)
                cur.execute(
                    "UPDATE deliveries SET invoice_no=?, ship_datetime=?, carrier=?, secondary_packaging=?, updated_at=datetime('now','localtime') WHERE id=?",
                    (invoice_no, ship_datetime, carrier, secondary_packaging, delivery_id))
            else:
                cur.execute(
                    "INSERT INTO deliveries (invoice_no, ship_datetime, carrier, secondary_packaging) VALUES (?, ?, ?, ?)",
                    (invoice_no, ship_datetime, carrier, secondary_packaging))
                delivery_id = cur.lastrowid

            cur.execute("DELETE FROM delivery_order_links WHERE delivery_id = ?", (delivery_id,))
            cur.execute("DELETE FROM delivery_purchase_links WHERE delivery_id = ?", (delivery_id,))
            for order_id in selected_order_ids:
                cur.execute("INSERT INTO delivery_order_links (delivery_id, order_id) VALUES (?, ?)",
                            (delivery_id, order_id))
            for purchase_id in selected_purchase_ids:
                cur.execute("INSERT INTO delivery_purchase_links (delivery_id, purchase_id) VALUES (?, ?)",
                            (delivery_id, purchase_id))

            cur.execute("DELETE FROM delivery_items WHERE delivery_id = ?", (delivery_id,))
            for item in final_items:
                cur.execute(
                    "INSERT INTO delivery_items (delivery_id, item_code, serial_no, manufacture_code, product_name, qty) VALUES (?, ?, ?, ?, ?, ?)",
                    (delivery_id, item['item_code'], item['serial_no'], item['manufacture_code'], item['product_name'],
                     item['qty']))

            mark_products_as_delivered(delivery_id, conn)
            conn.commit()
            action = "수정" if self.is_edit else "등록"
            QtWidgets.QMessageBox.information(self, "완료", f"납품 '{invoice_no}'이 {action}되었습니다.")
            self.accept()
        except Exception as e:
            if conn: conn.rollback()
            QtWidgets.QMessageBox.critical(self, "오류", f"납품 저장 중 오류가 발생했습니다:\n{str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            if conn: conn.close()