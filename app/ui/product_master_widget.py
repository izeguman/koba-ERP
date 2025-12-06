# app/ui/product_master_widget.py
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QHeaderView, QCompleter
from PySide6.QtCore import Qt, QStringListModel, QSignalBlocker
from PySide6.QtGui import QBrush, QColor
from datetime import datetime
from ..db import (get_conn, get_all_product_master, add_or_update_product_master,
                  delete_product_master, search_product_master)
from .money_lineedit import MoneyLineEdit
from .utils import apply_table_resize_policy


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

        # ✅ 저장된 설정 불러오기
        if self.settings:
            self.show_all = self.settings.value("filters/product_master_show_all", False, type=bool)
        else:
            self.show_all = False

        self.setup_ui()

        # ✅ 저장된 정렬 상태 불러오기 (기본값: 0-품목코드, 0-오름차순)
        self.current_sort_column = self.settings.value("product_master_table/sort_column", 0, type=int)
        # [수정] type=int를 제거하여 QSettings가 Enum 객체를 직접 읽도록 함
        sort_order_val = self.settings.value("product_master_table/sort_order", Qt.AscendingOrder)
        self.current_sort_order = Qt.SortOrder(sort_order_val)

        self.load_product_list()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("품목 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        # ✅ 필터 버튼 추가
        self.btn_show_all = QtWidgets.QPushButton("전체보기" if self.show_all else "생산 가능만")
        self.btn_show_all.setCheckable(True)
        self.btn_show_all.setChecked(self.show_all)  # ✅ 저장된 값으로 설정
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
        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["품목코드", "Rev", "제품명", "판매단가(엔)", "발주단가(원)", "설명", "생산유형", "생산가능", "등록일"]  # ✅ "생산유형" 추가
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

        self.table.setColumnWidth(0, 120)   # 품목코드
        self.table.setColumnWidth(1, 60)    # Rev
        self.table.setColumnWidth(2, 500)   # 제품명
        self.table.setColumnWidth(3, 120)   # 판매단가(엔)
        self.table.setColumnWidth(4, 120)   # 발주단가(원)
        self.table.setColumnWidth(5, 300)  # 설명
        self.table.setColumnWidth(6, 100)  # ✅ [신규] 생산유형
        self.table.setColumnWidth(7, 80)  # ✅ [변경] 생산가능 (인덱스 6->7)
        self.table.setColumnWidth(8, 100)  # ✅ [변경] 등록일 (인덱스 7->8)

        if self.settings:
            self.restore_column_widths()

        header.sectionResized.connect(self.save_column_widths)

        # ✅ [추가] 시그널 연결 및 화살표 강제 표시
        header.sortIndicatorChanged.connect(self.on_header_sort_changed)
        header.setSortIndicatorShown(True)

        layout.addLayout(title_layout)
        layout.addWidget(self.table)

        apply_table_resize_policy(self.table)

        self.product_data = []

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
            # ✅ [추가] 동적 정렬 절 생성 (이 라인이 빠졌습니다)
            order_clause = self.get_product_master_order_clause()

            # ✅ show_all 상태와 정렬 절에 따라 필터링
            self.product_data = get_all_product_master(
                include_inactive=self.show_all,
                order_by_clause=order_clause
            )

            self.table.setRowCount(len(self.product_data))
            self.table.setSortingEnabled(False)

            # 품목 관리 색상(활성=completed, 비활성=inactive→incomplete) 읽기
            pm_comp_fg = QColor(self.settings.value("colors/product_master_completed_fg", "#000000"))
            pm_comp_bg = QColor(self.settings.value("colors/product_master_completed_bg", "#E0F7FA"))
            pm_incomp_fg = QColor(self.settings.value("colors/product_master_incomplete_fg", "#000000"))
            pm_incomp_bg = QColor(self.settings.value("colors/product_master_incomplete_bg", "#FFFFFF"))

            for r, row in enumerate(self.product_data):
                product_id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, created_at, updated_at, is_active, item_type = row

                # 0열: 품목코드 (왼쪽 정렬)
                item_0 = QtWidgets.QTableWidgetItem(str(item_code))
                item_0.setData(Qt.UserRole, product_id)
                item_0.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # ✅ 왼쪽 정렬
                self.table.setItem(r, 0, item_0)

                # 1열: Rev (가운데 정렬)
                item_1 = QtWidgets.QTableWidgetItem(str(rev or ""))
                item_1.setTextAlignment(Qt.AlignCenter)  # ✅ 가운데 정렬
                self.table.setItem(r, 1, item_1)

                # 2열: 제품명 (왼쪽 정렬)
                item_2 = QtWidgets.QTableWidgetItem(str(product_name))
                item_2.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # ✅ 왼쪽 정렬
                self.table.setItem(r, 2, item_2)

                # 3열: 판매단가(엔) (오른쪽 정렬)
                item_3 = QtWidgets.QTableWidgetItem(format_money((unit_price_jpy or 0) / 100))
                item_3.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)  # ✅ 오른쪽 정렬
                self.table.setItem(r, 3, item_3)

                # 4열: 발주단가(원) (오른쪽 정렬)
                item_4 = QtWidgets.QTableWidgetItem(format_money((purchase_price_krw or 0) / 100))
                item_4.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)  # ✅ 오른쪽 정렬
                self.table.setItem(r, 4, item_4)

                # 5열: 설명 (왼쪽 정렬)
                item_5 = QtWidgets.QTableWidgetItem(str(description or ""))
                item_5.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # ✅ 왼쪽 정렬
                self.table.setItem(r, 5, item_5)

                # 6열: ✅ [신규] 생산유형
                type_str = "판매/조립품" if item_type == 'SELLABLE' else "순수 하위 부품"
                item_6 = QtWidgets.QTableWidgetItem(type_str)
                item_6.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, 6, item_6)

                # 7열: ✅ [변경] 생산가능 체크박스 (인덱스 6->7)
                is_active_checkbox = QtWidgets.QCheckBox()

                # [수정] DB 조회 대신, 이미 받아온 'is_active' 변수 사용
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
                self.table.setCellWidget(r, 7, active_widget)  # ✅ [변경] 6 -> 7

                # 8열: ✅ [변경] 등록일 (인덱스 7->8)
                item_8 = QtWidgets.QTableWidgetItem(str(created_at.split()[0] if created_at else ""))
                item_8.setTextAlignment(Qt.AlignCenter)  # ✅ 가운데 정렬
                self.table.setItem(r, 8, item_8)

                # ✅ 단종 제품 스타일 적용 (is_active == 0)
                target_cols = [0, 1, 2, 3, 4, 5, 6, 8]  # ✅ [변경] 6, 8 (7 제외)
                if is_active == 0:
                    # 단종(비활성) → 미완료 색
                    fg, bg = pm_incomp_fg, pm_incomp_bg
                else:
                    # 생산 가능(활성) → 완료 색
                    fg, bg = pm_comp_fg, pm_comp_bg

                for col in target_cols:
                    item = self.table.item(r, col)
                    if item:
                        item.setForeground(QBrush(fg))
                        item.setBackground(QBrush(bg))

            # ✅ [수정] 정렬 기능 활성화 및 QSignalBlocker로 화살표 표시
            self.table.setSortingEnabled(True)
            with QSignalBlocker(self.table.horizontalHeader()):
                self.table.horizontalHeader().setSortIndicator(
                    self.current_sort_column,
                    self.current_sort_order
                )
            for i in range(self.table.rowCount()):
                self.table.setRowHeight(i, 25)

        except Exception as e:
            print(f"제품 마스터 목록 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.product_data = []
            self.table.setRowCount(0)

    def get_product_master_order_clause(self):
        """(새 함수) 품목 관리 테이블의 정렬 기준을 SQL ORDER BY 절로 변환"""
        # ["품목코드", "Rev", "제품명", "판매단가(엔)", "발주단가(원)", "설명", "생산유형", "생산가능", "등록일"]
        column_names = [
            "item_code",           # 0
            "rev",                 # 1
            "product_name",        # 2
            "unit_price_jpy",      # 3
            "purchase_price_krw",  # 4
            "description",         # 5
            "item_type",           # 6 ✅ [추가]
            "is_active",           # 7 ✅ [변경]
            "created_at"           # 8 ✅ [변경]
        ]

        if 0 <= self.current_sort_column < len(column_names):
            column = column_names[self.current_sort_column]
            direction = "DESC" if self.current_sort_order == Qt.DescendingOrder else "ASC"
        else:  # 기본값
            column = "item_code"
            direction = "ASC"

        # 2차 정렬 기준
        return f"{column} {direction}, item_code ASC, rev ASC"

    def on_header_sort_changed(self, column_index, order):
        """(새 함수) 품목 관리 테이블 헤더의 정렬 표시기가 변경될 때 호출됩니다."""

        # 1. 현재 상태와 동일하면 (load_due_list에 의한 프로그래밍 방식 호출), 무시
        if self.current_sort_column == column_index and self.current_sort_order == order:
            return

        # 2. 사용자 클릭에 의한 변경이므로, 새 정렬 상태를 저장
        self.current_sort_column = column_index
        self.current_sort_order = order

        # 3. 새 정렬 상태를 QSettings에 저장
        self.settings.setValue("product_master_table/sort_column", self.current_sort_column)
        self.settings.setValue("product_master_table/sort_order", self.current_sort_order)

        # 4. SQL 정렬을 다시 적용하기 위해 목록 새로고침
        self.load_product_list()


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

        self.cmb_item_type = QtWidgets.QComboBox()
        self.cmb_item_type.addItem("판매/조립품 (재고 관리 대상)", "SELLABLE")
        self.cmb_item_type.addItem("순수 하위 부품 (조립용)", "SUB_COMPONENT")

        form.addRow("품목코드*", self.edt_item_code)
        form.addRow("Rev", self.edt_rev)
        form.addRow("제품명*", self.edt_product_name)
        form.addRow("판매단가(엔)", self.edt_unit_price_jpy)
        form.addRow("발주단가(원)", self.edt_purchase_price_krw)
        form.addRow("설명", self.edt_description)
        form.addRow("생산 유형*", self.cmb_item_type)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept_dialog)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def load_product_data(self):
        if not self.product_data:
            return

        # ✅ [수정] is_active, item_type 포함하여 언패킹
        product_id, item_code, rev, product_name, unit_price_jpy, purchase_price_krw, description, created_at, updated_at, is_active, item_type = self.product_data

        self.edt_item_code.setText(str(item_code))
        self.edt_rev.setText(str(rev or ""))
        self.edt_product_name.setText(str(product_name))
        self.edt_unit_price_jpy.set_value((unit_price_jpy or 0) // 100)
        self.edt_purchase_price_krw.set_value((purchase_price_krw or 0) // 100)
        self.edt_description.setText(str(description or ""))

        # ✅ [추가] item_type 설정
        index = self.cmb_item_type.findData(item_type or "SELLABLE")
        self.cmb_item_type.setCurrentIndex(index if index >= 0 else 0)

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

        item_type = self.cmb_item_type.currentData()

        try:
            is_new = add_or_update_product_master(
                item_code, rev, product_name,
                unit_price_jpy_cents, purchase_price_krw_cents, description, item_type
            )

            action = "추가" if is_new else "수정"
            QtWidgets.QMessageBox.information(self, "완료", f"제품이 {action}되었습니다.")
            self.accept()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"제품 저장 중 오류가 발생했습니다:\n{str(e)}")