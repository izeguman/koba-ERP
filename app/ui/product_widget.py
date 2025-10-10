# app/ui/product_widget.py
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import QLocale, Qt
from datetime import datetime
import re
from ..db import get_conn, query_all, get_all_product_master
from .autocomplete_widgets import AutoCompleteLineEdit


def get_next_serial_number(conn, part_no: str) -> str:
    """특정 품목의 다음 시리얼 번호를 생성합니다 (KT001 ~ KT999)"""
    cur = conn.cursor()
    cur.execute("""
        SELECT serial_no FROM products
        WHERE serial_no LIKE 'KT%'
        AND part_no = ?
        ORDER BY id DESC
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


def get_purchase_info(purchase_id: int):
    """특정 발주의 상세 정보 반환"""
    sql = """
        SELECT
            p.purchase_no,
            GROUP_CONCAT(pi.product_name, ' | ') as purchase_desc,
            SUM(pi.qty) as total_qty,
            AVG(pi.unit_price_cents) as avg_unit_price
        FROM purchases p
        LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
        WHERE p.id = ?
        GROUP BY p.id
    """
    result = query_all(sql, (purchase_id,))
    return result[0] if result else None


def get_produced_quantity(purchase_id: int):
    """특정 발주의 총 생산 수량 반환 (개별 제품 수 카운트)"""
    sql = """
        SELECT COUNT(*) as total_produced
        FROM products
        WHERE purchase_id = ?
    """
    result = query_all(sql, (purchase_id,))
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


def get_available_purchases():
    """발주 목록을 반환 (미완료만)"""
    sql = """
        SELECT
            p.id,
            p.purchase_no,
            GROUP_CONCAT(pi.product_name, ' | ') as purchase_desc,
            SUM(pi.qty) as total_qty,
            p.purchase_dt,
            (SELECT COUNT(*) FROM products pr WHERE pr.purchase_id = p.id) as produced_qty,
            (SELECT COALESCE(SUM(di.qty), 0)
             FROM deliveries d
             JOIN delivery_items di ON d.id = di.delivery_id
             WHERE d.purchase_id = p.id) as delivered_qty
        FROM purchases p
        LEFT JOIN purchase_items pi ON p.id = pi.purchase_id
        WHERE p.purchase_no IS NOT NULL
        GROUP BY p.id
        ORDER BY p.purchase_dt DESC, p.purchase_no ASC
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()

    # 필터링: 완료되지 않은 발주만
    filtered = []
    for row in rows:
        purchase_id, purchase_no, purchase_desc, total_qty, purchase_dt, produced_qty, delivered_qty = row
        # 발주량 != 생산량 또는 생산량 != 납품량이면 미완료
        total_qty = total_qty or 0
        produced_qty = produced_qty or 0
        delivered_qty = delivered_qty or 0

        if not (total_qty == produced_qty == delivered_qty):
            filtered.append((purchase_id, purchase_no, purchase_desc, total_qty, purchase_dt))

    conn.close()
    return filtered


class ProductWidget(QtWidgets.QWidget):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.expanded_state = {}
        self.show_all_products = False  # ✅ 추가: 필터 상태 변수 (기본값: 미납품만 보기)
        self.setup_ui()
        self.load_product_list()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("제품 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        self.btn_new_product = QtWidgets.QPushButton("새 제품")
        self.btn_refresh_product = QtWidgets.QPushButton("새로고침")

        # ✅ 추가: 미납품/전체보기 토글 버튼
        self.btn_show_all_products = QtWidgets.QPushButton("미납품만")
        self.btn_show_all_products.setCheckable(True)
        self.btn_show_all_products.setChecked(False)
        self.btn_show_all_products.toggled.connect(self.toggle_show_all)

        self.btn_new_product.clicked.connect(self.add_product)
        self.btn_refresh_product.clicked.connect(self.load_product_list)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.btn_new_product)
        title_layout.addWidget(self.btn_refresh_product)
        title_layout.addWidget(self.btn_show_all_products)  # ✅ 추가: 버튼 레이아웃에 추가

        self.tree = QTreeWidget()
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
        for col in range(self.tree.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.tree.setColumnWidth(0, 100)
        self.tree.setColumnWidth(1, 120)
        self.tree.setColumnWidth(2, 300)
        self.tree.setColumnWidth(3, 120)
        self.tree.setColumnWidth(4, 100)
        self.tree.setColumnWidth(5, 120)
        self.tree.setColumnWidth(6, 100)

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
        if not item:
            return

        menu = QtWidgets.QMenu(self)

        if item.parent():
            edit_action = menu.addAction("수정")
            edit_action.triggered.connect(self.edit_product)

            delete_action = menu.addAction("삭제")
            delete_action.triggered.connect(self.delete_product)

        selected_items = self.tree.selectedItems()
        child_items = [item for item in selected_items if item.parent()]
        if len(child_items) > 1:
            delete_multiple_action = menu.addAction(f"선택한 {len(child_items)}개 삭제")
            delete_multiple_action.triggered.connect(self.delete_multiple_products)

        menu.exec_(self.tree.mapToGlobal(position))

    def load_product_list(self):
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
                  d.invoice_no as delivery_invoice
                FROM products pr
                LEFT JOIN purchases p ON pr.purchase_id = p.id
                LEFT JOIN deliveries d ON pr.delivery_id = d.id
                ORDER BY p.purchase_no DESC, pr.part_no ASC, pr.serial_no ASC
            """

            cur.execute(sql)
            rows = cur.fetchall()

            grouped_data = {}
            for row in rows:
                product_id, manufacture_date, part_no, product_name, serial_no, manufacture_code, \
                    purchase_no, purchase_id, is_delivered, delivered_at, delivery_invoice = row

                key = (part_no or "미지정", purchase_no or "미지정")
                if key not in grouped_data:
                    grouped_data[key] = []
                grouped_data[key].append(row)

            self.product_data = grouped_data
            self.tree.clear()

            # ✅ 수정: 필터링 로직 추가
            data_to_display = {}
            if self.show_all_products:
                # '전체보기' 상태면 모든 데이터 표시
                data_to_display = self.product_data
            else:
                # '미납품만' 상태면 납품되지 않은 제품이 하나라도 있는 그룹만 필터링
                for key, products in self.product_data.items():
                    # is_delivered (인덱스 8) 값이 0인(미납품) 제품이 있는지 확인
                    if any(p[8] == 0 for p in products):
                        data_to_display[key] = products

            # ✅ 수정: 필터링된 데이터를 사용하여 트리 구성
            for (part_no, purchase_no), products in data_to_display.items():
                serial_numbers = [p[4] for p in products if p[4]]
                if serial_numbers:
                    serial_numbers.sort()
                    serial_range = f"{serial_numbers[0]} ~ {serial_numbers[-1]}"
                else:
                    serial_range = "시리얼 없음"

                delivered_count = sum(1 for p in products if p[8])
                total_count = len(products)
                delivery_status = f"{delivered_count}/{total_count}"

                parent_item = QTreeWidgetItem(self.tree)
                parent_item.setText(0, products[0][1] or "")
                parent_item.setText(1, part_no)
                parent_item.setText(2, products[0][3] or "")
                parent_item.setText(3, f"{serial_range} ({total_count}개)")
                parent_item.setText(4, products[0][5] or "")
                parent_item.setText(5, purchase_no)
                parent_item.setText(6, delivery_status)

                font = parent_item.font(0)
                font.setBold(True)
                for col in range(7):
                    parent_item.setFont(col, font)
                    parent_item.setBackground(col, QtGui.QBrush(QtGui.QColor("#f0f0f0")))

                # ✅ 모두 납품 완료된 그룹은 회색으로 처리 (전체보기 시)
                if delivered_count == total_count:
                    for col in range(7):
                        parent_item.setForeground(col, QtGui.QBrush(QtGui.QColor("#888888")))

                parent_key = f"{part_no}|{purchase_no}"
                parent_item.setData(0, Qt.UserRole, parent_key)

                for product in products:
                    child_item = QTreeWidgetItem(parent_item)

                    product_id, manufacture_date, part_no, product_name, serial_no, manufacture_code, \
                        purchase_no, purchase_id, is_delivered, delivered_at, delivery_invoice = product

                    child_item.setText(0, manufacture_date or "")
                    child_item.setText(1, part_no or "")
                    child_item.setText(2, product_name or "")
                    child_item.setText(3, serial_no or "")
                    child_item.setText(4, manufacture_code or "")
                    child_item.setText(5, purchase_no or "")

                    if is_delivered:
                        status_text = "납품됨"
                        if delivery_invoice:
                            status_text += f" ({delivery_invoice})"
                        child_item.setText(6, status_text)
                        for col in range(7):
                            child_item.setForeground(col, QtGui.QBrush(QtGui.QColor("#888888")))
                    else:
                        child_item.setText(6, "미납품")

                    child_item.setData(0, Qt.UserRole + 1, product_id)

                if parent_key in self.expanded_state:
                    parent_item.setExpanded(self.expanded_state[parent_key])
                else:
                    # ✅ 미납품이 있는 그룹은 기본적으로 펼쳐진 상태로 표시
                    if any(p[8] == 0 for p in products):
                        parent_item.setExpanded(True)
                    else:
                        parent_item.setExpanded(False)

        except Exception as e:
            print(f"제품 목록 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.product_data = {}
            self.tree.clear()

    # 이하 나머지 코드는 기존과 동일합니다.
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
                  d.invoice_no as delivery_invoice
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
                      d.invoice_no as delivery_invoice
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

        product_id, manufacture_date, part_no, product_name, serial_no, manufacture_code, purchase_no, purchase_id, is_delivered, delivered_at, delivery_invoice = product_data

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


# ProductDialog 클래스는 변경사항이 없으므로 기존 코드를 그대로 사용합니다.
class ProductDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, is_edit=False, product_data=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.product_data = product_data
        self.current_product_info = None
        self.setup_ui()

        if is_edit and product_data:
            self.load_product_data()

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

        self.edt_manufacture_code = QtWidgets.QLineEdit()
        self.edt_manufacture_code.setPlaceholderText("예: 2534 (YY주차) - 제조일자 입력 시 자동 생성")

        self.sp_production_qty = QtWidgets.QSpinBox()
        self.sp_production_qty.setRange(1, 1_000_000)
        self.sp_production_qty.setValue(1)
        self.sp_production_qty.setGroupSeparatorShown(True)

        qty_note = QtWidgets.QLabel("※ 생산수량만큼 개별 제품이 생성되며, 시리얼번호(KT001~KT999)가 자동 할당됩니다.")
        qty_note.setStyleSheet("color: #666; font-size: 10px;")
        qty_note.setWordWrap(True)

        form.addRow("제조일자", self.edt_manufacture_date)
        form.addRow("품목코드*", self.edt_item_code)
        form.addRow("제품명*", self.edt_product_name)
        form.addRow("시리얼번호", self.edt_serial_no)
        form.addRow("제조코드", self.edt_manufacture_code)

        if not self.is_edit:
            form.addRow("생산수량", self.sp_production_qty)
            form.addRow("", qty_note)

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
        self.current_product_info = product_info
        self.edt_product_name.setText(product_info['product_name'])

        if not self.is_edit:
            try:
                conn = get_conn()
                cur = conn.cursor()

                cur.execute("""
                    SELECT serial_no FROM products
                    WHERE part_no = ?
                    ORDER BY id DESC
                    LIMIT 1
                """, (product_info['item_code'],))
                result = cur.fetchone()
                if result and result[0]:
                    last_serial = result[0]
                    try:
                        if last_serial.startswith('KT'):
                            last_num = int(last_serial[2:])
                            next_num = (last_num % 999) + 1
                            next_serial = f"KT{next_num:03d}"
                        else:
                            match = re.search(r'(\d+)$', last_serial)
                            if match:
                                prefix = last_serial[:match.start()]
                                last_num = int(match.group(1))
                                next_num = last_num + 1
                                num_width = len(match.group(1))
                                next_serial = f"{prefix}{next_num:0{num_width}d}"
                            else:
                                next_serial = last_serial

                        self.edt_serial_no.setText(next_serial)
                        self.edt_serial_no.setStyleSheet("background-color: #fffacd;")
                    except (ValueError, AttributeError):
                        self.edt_serial_no.setText(last_serial)
                        self.edt_serial_no.setStyleSheet("background-color: #fffacd;")

                cur.execute("""
                    SELECT COUNT(*) as batch_qty
                    FROM products
                    WHERE part_no = ?
                    AND manufacture_date = (
                        SELECT manufacture_date FROM products
                        WHERE part_no = ?
                        ORDER BY id DESC
                        LIMIT 1
                    )
                """, (product_info['item_code'], product_info['item_code']))
                result = cur.fetchone()
                if result and result[0]:
                    last_qty = result[0]
                    self.sp_production_qty.setValue(last_qty)

                conn.close()
            except Exception as e:
                print(f"마지막 생산 정보 조회 오류: {e}")
                import traceback
                traceback.print_exc()

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
                purchase_info = get_purchase_info(purchase_id)
                if purchase_info:
                    purchase_no, purchase_desc, total_qty, unit_price_cents = purchase_info
                    produced_qty = get_produced_quantity(purchase_id)
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
            for purchase_id, purchase_no, purchase_desc, qty, purchase_dt in purchases:
                display_text = f"{purchase_no} - {purchase_desc} (수량: {qty}, 발주일: {purchase_dt})"
                self.purchase_combo.addItem(display_text, purchase_id)
        except Exception as e:
            print(f"발주 목록 로드 실패: {e}")

    def load_product_data(self):
        if not self.product_data:
            return

        product_id, manufacture_date, part_no, product_name, serial_no, manufacture_code, \
            purchase_no, purchase_id, is_delivered, delivered_at, delivery_invoice = self.product_data

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
        manufacture_date_raw = self.edt_manufacture_date.text().strip()
        manufacture_date = parse_date_text(manufacture_date_raw) if manufacture_date_raw else None
        item_code = self.edt_item_code.text().strip()
        product_name = self.edt_product_name.text().strip()

        if not item_code or not product_name:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "품목코드와 제품명은 필수입니다.")
            return

        if manufacture_date_raw and not manufacture_date:
            QtWidgets.QMessageBox.warning(self, "제조일자", "제조일자 형식이 올바르지 않습니다. 예: 2025-08-27 / 30-Jul-25")
            return

        serial_no = self.edt_serial_no.text().strip() or None
        manufacture_code = self.edt_manufacture_code.text().strip() or None
        purchase_id = self.purchase_combo.currentData()

        try:
            conn = get_conn()
            cur = conn.cursor()

            if self.is_edit:
                product_id = self.product_data[0]
                cur.execute("""
                    UPDATE products
                    SET manufacture_date=?, part_no=?, product_name=?, serial_no=?, manufacture_code=?, purchase_id=?
                    WHERE id=?
                """, (manufacture_date, item_code, product_name, serial_no, manufacture_code, purchase_id, product_id))
            else:
                production_qty = self.sp_production_qty.value()
                if purchase_id:
                    purchase_info = get_purchase_info(purchase_id)
                    if purchase_info:
                        total_qty = purchase_info[2]
                        produced_qty = get_produced_quantity(purchase_id)
                        if produced_qty + production_qty > total_qty:
                            reply = QtWidgets.QMessageBox.question(
                                self, "생산 수량 초과",
                                f"생산 수량이 발주 수량을 초과합니다.\n\n"
                                f"발주 수량: {total_qty}개\n"
                                f"기 생산량: {produced_qty}개\n"
                                f"이번 생산: {production_qty}개\n"
                                f"총 생산량: {produced_qty + production_qty}개\n\n"
                                f"계속 진행하시겠습니까?",
                                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                QtWidgets.QMessageBox.No
                            )
                            if reply != QtWidgets.QMessageBox.Yes:
                                return
                for i in range(production_qty):
                    if serial_no and i == 0:
                        current_serial = serial_no
                    else:
                        current_serial = get_next_serial_number(conn, item_code)
                    cur.execute("""
                        INSERT INTO products
                        (manufacture_date, part_no, product_name, serial_no, manufacture_code, purchase_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (manufacture_date, item_code, product_name, current_serial, manufacture_code, purchase_id))
            conn.commit()
            conn.close()
            if not self.is_edit:
                QtWidgets.QMessageBox.information(
                    self, "완료",
                    f"제품 {self.sp_production_qty.value()}개가 생성되었습니다.\n시리얼 번호가 자동으로 할당되었습니다."
                )
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"제품 저장 중 오류가 발생했습니다:\n{str(e)}")