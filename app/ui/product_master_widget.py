# app/ui/product_master_widget.py
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QHeaderView, QCompleter
from PySide6.QtCore import Qt, QStringListModel
from datetime import datetime
from ..db import (get_conn, get_all_product_master, add_or_update_product_master,
                  delete_product_master, search_product_master)
from .money_lineedit import MoneyLineEdit


def format_money(val: float | None) -> str:
    if val is None:
        return ""
    try:
        return f"{val:,.0f}"
    except Exception:
        return str(val)


class ProductMasterWidget(QtWidgets.QWidget):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.setup_ui()
        self.load_product_list()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("제품 마스터 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        # ✅ 필터 버튼 추가
        self.btn_show_all = QtWidgets.QPushButton("생산 가능만")
        self.btn_show_all.setCheckable(True)
        self.btn_show_all.setChecked(False)
        self.btn_show_all.toggled.connect(self.toggle_show_all)

        self.btn_new_product = QtWidgets.QPushButton("새 제품")
        self.btn_refresh_product = QtWidgets.QPushButton("새로고침")

        self.btn_new_product.clicked.connect(self.add_product)
        self.btn_refresh_product.clicked.connect(self.load_product_list)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.btn_new_product)
        title_layout.addWidget(self.btn_refresh_product)
        title_layout.addWidget(self.btn_show_all)  # ✅ 필터 버튼 추가

        # ✅ 테이블 컬럼에 "생산 가능" 추가
        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["품목코드", "Rev", "제품명", "판매단가(엔)", "발주단가(원)", "설명", "생산가능", "등록일"]
        )
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.setShowGrid(True)

        self.table.itemDoubleClicked.connect(self.edit_product)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 250)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 200)
        self.table.setColumnWidth(6, 80)  # ✅ 생산가능
        self.table.setColumnWidth(7, 100)  # ✅ 등록일

        if self.settings:
            self.restore_column_widths()

        header.sectionResized.connect(self.save_column_widths)

        layout.addLayout(title_layout)
        layout.addWidget(self.table)

        self.product_data = []
        self.show_all = False  # ✅ 필터 상태

    def toggle_show_all(self, checked: bool):
        """생산 가능 제품만 / 전체보기 토글"""
        self.show_all = checked
        self.btn_show_all.setText("전체보기" if checked else "생산 가능만")
        self.load_product_list()

    def save_column_widths(self):
        if not self.settings:
            return
        widths = []
        for col in range(self.table.columnCount()):
            widths.append(self.table.columnWidth(col))
        self.settings.setValue("product_master_table/column_widths", widths)

    def restore_column_widths(self):
        if not self.settings:
            return
        widths = self.settings.value("product_master_table/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < self.table.columnCount():
                    self.table.setColumnWidth(col, int(width))

    def show_context_menu(self, position):
        if self.table.itemAt(position) is None:
            return

        menu = QtWidgets.QMenu(self)

        edit_action = menu.addAction("수정")
        edit_action.triggered.connect(self.edit_product)

        # ✅ 단종 토글 메뉴 추가
        product_data = self.get_selected_product()
        if product_data:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT is_active FROM product_master WHERE id = ?", (product_data[0],))
            result = cur.fetchone()
            is_active = result[0] if result else 1
            conn.close()

            toggle_text = "단종 처리" if is_active else "생산 가능으로 변경"
            toggle_action = menu.addAction(toggle_text)
            toggle_action.triggered.connect(lambda: self.toggle_product_active(product_data[0]))

        delete_action = menu.addAction("삭제")
        delete_action.triggered.connect(self.delete_product)

        menu.exec_(self.table.mapToGlobal(position))

    def toggle_product_active(self, product_id: int):
        """제품 생산 가능 상태 토글"""
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT is_active FROM product_master WHERE id = ?", (product_id,))
        result = cur.fetchone()
        current_active = result[0] if result else 1

        new_active = 0 if current_active else 1
        cur.execute("UPDATE product_master SET is_active=?, updated_at=datetime('now','localtime') WHERE id=?",
                    (new_active, product_id))
        conn.commit()
        conn.close()

        self.load_product_list()
        status_text = "생산 가능" if new_active else "단종"
        QtWidgets.QMessageBox.information(self, "완료", f"제품이 '{status_text}' 상태로 변경되었습니다.")

    def load_product_list(self):
        try:
            # ✅ show_all 상태에 따라 필터링
            self.product_data = get_all_product_master(include_inactive=self.show_all)

            self.table.setRowCount(len(self.product_data))
            self.table.setSortingEnabled(False)

            for r, row in enumerate(self.product_data):
                product_id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, created_at, updated_at = row

                item_0 = QtWidgets.QTableWidgetItem(str(item_code))
                item_0.setData(Qt.UserRole, product_id)
                self.table.setItem(r, 0, item_0)

                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(rev or "")))
                self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(product_name)))
                self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(format_money((unit_price_jpy or 0) / 100)))
                self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(format_money((purchase_price_krw or 0) / 100)))
                self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(description or "")))

                # ✅ 생산 가능 여부 체크박스
                is_active_checkbox = QtWidgets.QCheckBox()

                # is_active 값 가져오기
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT is_active FROM product_master WHERE id = ?", (product_id,))
                result = cur.fetchone()
                is_active = result[0] if result else 1
                conn.close()

                is_active_checkbox.setChecked(bool(is_active))
                is_active_checkbox.setStyleSheet("QCheckBox { margin-left: 20px; }")
                is_active_checkbox.stateChanged.connect(
                    lambda state, pid=product_id: self.update_active_status(pid, state)
                )

                active_widget = QtWidgets.QWidget()
                active_layout = QtWidgets.QHBoxLayout(active_widget)
                active_layout.addWidget(is_active_checkbox)
                active_layout.setAlignment(Qt.AlignCenter)
                active_layout.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(r, 6, active_widget)

                self.table.setItem(r, 7, QtWidgets.QTableWidgetItem(str(created_at.split()[0] if created_at else "")))

                # ✅ 단종 제품은 회색으로 표시
                if is_active == 0:
                    from PySide6.QtGui import QBrush, QColor
                    for col in range(6):  # 0~5번 컬럼 (체크박스는 제외)
                        if self.table.item(r, col):
                            self.table.item(r, col).setForeground(QBrush(QColor("#888888")))

            self.table.setSortingEnabled(True)
            for i in range(self.table.rowCount()):
                self.table.setRowHeight(i, 25)

        except Exception as e:
            print(f"제품 마스터 목록 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.product_data = []
            self.table.setRowCount(0)

    def update_active_status(self, product_id: int, state: int):
        """생산 가능 상태 업데이트"""
        is_active = 1 if state == QtCore.Qt.CheckState.Checked.value else 0

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE product_master SET is_active=?, updated_at=datetime('now','localtime') WHERE id=?",
                        (is_active, product_id))
            conn.commit()

            status_text = "생산 가능" if is_active else "단종"

            # 생산 가능만 보기 모드에서 단종으로 변경하면 목록에서 제거
            if not self.show_all and is_active == 0:
                self.load_product_list()
                QtWidgets.QMessageBox.information(
                    self, "알림",
                    f"제품이 '{status_text}' 상태로 변경되었습니다.\n(생산 가능 목록에서 제거됨)"
                )

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"상태 업데이트 중 오류:\n{str(e)}")
        finally:
            conn.close()

    def get_selected_product(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return None

        item = self.table.item(current_row, 0)
        if not item:
            return None

        product_id = item.data(Qt.UserRole)
        if not product_id:
            return None

        for row in self.product_data:
            if row[0] == product_id:
                return row

        return None

    def add_product(self):
        dialog = ProductMasterDialog(self, is_edit=False)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_product_list()

    def edit_product(self):
        product_data = self.get_selected_product()
        if not product_data:
            QtWidgets.QMessageBox.information(self, "알림", "수정할 제품을 선택해주세요.")
            return

        dialog = ProductMasterDialog(self, is_edit=True, product_data=product_data)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_product_list()

    def delete_product(self):
        product_data = self.get_selected_product()
        if not product_data:
            QtWidgets.QMessageBox.information(self, "알림", "삭제할 제품을 선택해주세요.")
            return

        product_id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, created_at, updated_at = product_data

        reply = QtWidgets.QMessageBox.question(
            self,
            "제품 삭제",
            f"정말로 다음 제품을 삭제하시겠습니까?\n\n"
            f"품목코드: {item_code}\n"
            f"제품명: {product_name}\n"
            f"Rev: {rev}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            delete_product_master(product_id)
            self.load_product_list()
            QtWidgets.QMessageBox.information(self, "완료", f"제품 '{item_code}'이 삭제되었습니다.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"제품 삭제 중 오류가 발생했습니다:\n{str(e)}")


class ProductMasterDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, is_edit=False, product_data=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.product_data = product_data
        self.setup_ui()

        if is_edit and product_data:
            self.load_product_data()

    def setup_ui(self):
        title = "제품 수정" if self.is_edit else "새 제품 추가"
        self.setWindowTitle(title)
        self.setMinimumWidth(600)

        form = QtWidgets.QFormLayout(self)

        self.edt_item_code = QtWidgets.QLineEdit()
        self.edt_item_code.setPlaceholderText("예: B10000805")

        self.edt_rev = QtWidgets.QLineEdit()
        self.edt_rev.setPlaceholderText("예: 055")

        self.edt_product_name = QtWidgets.QLineEdit()
        self.edt_product_name.setMinimumWidth(400)
        self.edt_product_name.setPlaceholderText("예: ASSY-MOD 29,CTRL,HEATER,XTAL,ROHS,TESTED")

        self.edt_unit_price_jpy = MoneyLineEdit(max_value=1_000_000_000)
        self.edt_unit_price_jpy.setPlaceholderText("예: 405000")
        self.edt_unit_price_jpy.setMinimumWidth(200)

        self.edt_purchase_price_krw = MoneyLineEdit(max_value=1_000_000_000)
        self.edt_purchase_price_krw.setPlaceholderText("예: 3249333")
        self.edt_purchase_price_krw.setMinimumWidth(200)

        self.edt_description = QtWidgets.QLineEdit()
        self.edt_description.setMinimumWidth(400)
        self.edt_description.setPlaceholderText("제품에 대한 추가 설명")

        form.addRow("품목코드*", self.edt_item_code)
        form.addRow("Rev", self.edt_rev)
        form.addRow("제품명*", self.edt_product_name)
        form.addRow("판매단가(엔)", self.edt_unit_price_jpy)
        form.addRow("발주단가(원)", self.edt_purchase_price_krw)
        form.addRow("설명", self.edt_description)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept_dialog)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def load_product_data(self):
        if not self.product_data:
            return

        product_id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, created_at, updated_at = self.product_data

        self.edt_item_code.setText(str(item_code))
        self.edt_rev.setText(str(rev or ""))
        self.edt_product_name.setText(str(product_name))
        self.edt_unit_price_jpy.set_value((unit_price_jpy or 0) // 100)
        self.edt_purchase_price_krw.set_value((purchase_price_krw or 0) // 100)
        self.edt_description.setText(str(description or ""))

    def accept_dialog(self):
        item_code = self.edt_item_code.text().strip()
        rev = self.edt_rev.text().strip() or None
        product_name = self.edt_product_name.text().strip()

        if not item_code or not product_name:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "품목코드와 제품명은 필수입니다.")
            return

        unit_price_jpy_cents = self.edt_unit_price_jpy.get_value() * 100
        purchase_price_krw_cents = self.edt_purchase_price_krw.get_value() * 100
        description = self.edt_description.text().strip() or None

        try:
            is_new = add_or_update_product_master(
                item_code, rev, product_name,
                unit_price_jpy_cents, purchase_price_krw_cents, description
            )

            action = "추가" if is_new else "수정"
            QtWidgets.QMessageBox.information(self, "완료", f"제품이 {action}되었습니다.")
            self.accept()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"제품 저장 중 오류가 발생했습니다:\n{str(e)}")