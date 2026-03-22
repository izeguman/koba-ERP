# app/ui/schedule_dialog.py

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                               QTableWidgetItem, QPushButton, QHeaderView, QMessageBox,
                               QLabel, QLineEdit, QDialogButtonBox, QSpinBox, QInputDialog,
                               QTabWidget, QWidget)
from PySide6.QtCore import Qt, QSettings
from ..db import get_full_schedule_for_order, save_schedule_for_item, get_shipment_change_history
from .utils import parse_due_text


class ScheduleDialog(QDialog):
    """주문 전체의 납기 일정을 품목별 탭으로 관리하는 메인 다이얼로그"""

    def __init__(self, order_id, order_no, parent=None):
        super().__init__(parent)
        self.order_id = order_id
        self.order_no = order_no
        self.schedule_data = get_full_schedule_for_order(self.order_id)

        self.setWindowTitle(f"납기 일정 관리 - {self.order_no}")
        self.setMinimumSize(800, 600)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.item_tabs = QTabWidget()

        # 주문에 포함된 품목별로 탭 생성
        for item_info in self.schedule_data:
            editor_widget = ScheduleEditorWidget(item_info, self)
            self.item_tabs.addTab(editor_widget, item_info['product_name'])

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        main_layout.addWidget(self.item_tabs)
        main_layout.addWidget(buttons)


class ScheduleEditorWidget(QWidget):
    """품목 하나의 납기 일정과 이력을 관리하는 위젯 (탭 안에 들어감)"""

    def __init__(self, item_info, parent=None):
        super().__init__(parent)
        self.item_id = item_info['item_id']
        self.product_name = item_info['product_name']
        self.total_qty = item_info['total_qty']

        # ✅ QSettings 초기화
        self.settings = QSettings("KOBATECH", "ProductionManagement")

        layout = QVBoxLayout(self)

        # --- 상단 정보 및 요약 ---
        info_layout = QHBoxLayout()
        self.lbl_info = QLabel(f"<b>{self.product_name}</b> (총 주문 수량: {self.total_qty}개)")
        self.lbl_sum_info = QLabel()
        info_layout.addWidget(self.lbl_info)
        info_layout.addStretch()
        info_layout.addWidget(self.lbl_sum_info)

        # --- 스케줄 편집 테이블 ---
        schedule_group = QtWidgets.QGroupBox("납기 일정 편집")
        schedule_layout = QVBoxLayout(schedule_group)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["납기일 (YYYY-MM-DD)", "수량", ""])

        # ✅ [수정] 모든 컬럼을 Interactive로 변경
        header_edit = self.table.horizontalHeader()
        header_edit.setSectionResizeMode(0, QHeaderView.Interactive)
        header_edit.setSectionResizeMode(1, QHeaderView.Interactive)
        header_edit.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.model().dataChanged.connect(self.update_summary)  # 셀 내용 변경 시 요약 업데이트

        schedule_button_layout = QHBoxLayout()
        btn_add = QPushButton("+ 일정 추가");
        btn_add.clicked.connect(self.add_row)
        btn_save = QPushButton("이 품목 일정 저장");
        btn_save.clicked.connect(self.save_schedule)
        schedule_button_layout.addStretch()
        schedule_button_layout.addWidget(btn_add)
        schedule_button_layout.addWidget(btn_save)

        schedule_layout.addWidget(self.table)
        schedule_layout.addLayout(schedule_button_layout)

        # --- 변경 이력 테이블 ---
        history_group = QtWidgets.QGroupBox("변경 이력")
        history_layout = QVBoxLayout(history_group)
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["변경 요청일", "변경 전", "변경 후", "사유"])
        self.history_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        # ✅ [수정] 모든 컬럼을 Interactive로 변경
        history_header = self.history_table.horizontalHeader()
        history_header.setSectionResizeMode(0, QHeaderView.Interactive)
        history_header.setSectionResizeMode(1, QHeaderView.Interactive)
        history_header.setSectionResizeMode(2, QHeaderView.Interactive)
        history_header.setSectionResizeMode(3, QHeaderView.Interactive)
        history_layout.addWidget(self.history_table)

        layout.addLayout(info_layout)
        layout.addWidget(schedule_group)
        layout.addWidget(history_group)

        self.populate_table(item_info['shipments'])
        self.load_history()

        # ✅ [추가] 컬럼 너비 복원 및 저장 시그널 연결
        self.restore_column_widths(self.table, "schedule_edit_table")
        self.restore_column_widths(self.history_table, "schedule_history_table")

        header_edit.sectionResized.connect(
            lambda: self.save_column_widths(self.table, "schedule_edit_table")
        )
        history_header.sectionResized.connect(
            lambda: self.save_column_widths(self.history_table, "schedule_history_table")
        )


    def populate_table(self, shipments):
        self.table.model().dataChanged.disconnect(self.update_summary)
        self.table.setRowCount(0)
        for shipment in shipments:
            self.add_row(shipment['due_date'], shipment['ship_qty'], is_loading=True)
        self.update_summary()
        self.table.model().dataChanged.connect(self.update_summary)

    def add_row(self, due_date="", qty=1, is_loading=False):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(due_date))
        self.table.setItem(row, 1, QTableWidgetItem(str(qty)))
        btn_delete = QPushButton("삭제")
        btn_delete.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        self.table.setCellWidget(row, 2, btn_delete)
        if not is_loading: self.update_summary()

    def update_summary(self):
        current_sum = 0;
        has_error = False
        for row in range(self.table.rowCount()):
            try:
                item = self.table.item(row, 1)
                current_sum += int(item.text())
            except (ValueError, AttributeError):
                has_error = True;
                pass

        remaining = self.total_qty - current_sum
        self.lbl_sum_info.setText(f"할당된 수량: {current_sum} / 남은 수량: {remaining}")

        if remaining == 0 and not has_error:
            self.lbl_sum_info.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_sum_info.setStyleSheet("color: red; font-weight: bold;")

    def load_history(self):
        history = get_shipment_change_history(self.item_id)
        self.history_table.setRowCount(len(history))
        for r, row in enumerate(history):
            for c, val in enumerate(row):
                self.history_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(val)))
        # self.history_table.resizeColumnsToContents()
        self.history_table.horizontalHeader().setStretchLastSection(True)

    def save_schedule(self):
        new_shipments = []
        current_sum = 0
        for row in range(self.table.rowCount()):
            date_str = self.table.item(row, 0).text()
            qty_str = self.table.item(row, 1).text()
            due_date = parse_due_text(date_str)
            if not due_date:
                QMessageBox.warning(self, "입력 오류", f"{row + 1}행의 납기일 형식이 올바르지 않습니다. (YYYY-MM-DD)");
                return
            try:
                qty = int(qty_str)
                if qty <= 0: raise ValueError
            except (ValueError, AttributeError):
                QMessageBox.warning(self, "입력 오류", f"{row + 1}행의 수량이 잘못되었습니다.");
                return
            new_shipments.append({'due_date': due_date, 'ship_qty': qty});
            current_sum += qty

        if current_sum != self.total_qty:
            QMessageBox.warning(self, "수량 오류", f"분할 납기 수량의 합({current_sum})이 총 주문 수량({self.total_qty})과 일치하지 않습니다.");
            return
# app/ui/schedule_dialog.py

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                               QTableWidgetItem, QPushButton, QHeaderView, QMessageBox,
                               QLabel, QLineEdit, QDialogButtonBox, QSpinBox, QInputDialog,
                               QTabWidget, QWidget)
from PySide6.QtCore import Qt, QSettings
from ..db import get_full_schedule_for_order, save_schedule_for_item, get_shipment_change_history
from .utils import parse_due_text


class ScheduleDialog(QDialog):
    """주문 전체의 납기 일정을 품목별 탭으로 관리하는 메인 다이얼로그"""

    def __init__(self, order_id, order_no, parent=None):
        super().__init__(parent)
        self.order_id = order_id
        self.order_no = order_no
        self.schedule_data = get_full_schedule_for_order(self.order_id)

        self.setWindowTitle(f"납기 일정 관리 - {self.order_no}")
        self.setMinimumSize(800, 600)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.item_tabs = QTabWidget()

        # 주문에 포함된 품목별로 탭 생성
        for item_info in self.schedule_data:
            editor_widget = ScheduleEditorWidget(item_info, self)
            self.item_tabs.addTab(editor_widget, item_info['product_name'])

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        main_layout.addWidget(self.item_tabs)
        main_layout.addWidget(buttons)


class ScheduleEditorWidget(QWidget):
    """품목 하나의 납기 일정과 이력을 관리하는 위젯 (탭 안에 들어감)"""

    def __init__(self, item_info, parent=None):
        super().__init__(parent)
        self.item_id = item_info['item_id']
        self.product_name = item_info['product_name']
        self.total_qty = item_info['total_qty']

        # ✅ QSettings 초기화
        self.settings = QSettings("KOBATECH", "ProductionManagement")

        layout = QVBoxLayout(self)

        # --- 상단 정보 및 요약 ---
        info_layout = QHBoxLayout()
        self.lbl_info = QLabel(f"<b>{self.product_name}</b> (총 주문 수량: {self.total_qty}개)")
        self.lbl_sum_info = QLabel()
        info_layout.addWidget(self.lbl_info)
        info_layout.addStretch()
        info_layout.addWidget(self.lbl_sum_info)

        # --- 스케줄 편집 테이블 ---
        schedule_group = QtWidgets.QGroupBox("납기 일정 편집")
        schedule_layout = QVBoxLayout(schedule_group)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["납기일 (YYYY-MM-DD)", "수량", ""])

        # ✅ [수정] 모든 컬럼을 Interactive로 변경
        header_edit = self.table.horizontalHeader()
        header_edit.setSectionResizeMode(0, QHeaderView.Interactive)
        header_edit.setSectionResizeMode(1, QHeaderView.Interactive)
        header_edit.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.model().dataChanged.connect(self.update_summary)  # 셀 내용 변경 시 요약 업데이트

        schedule_button_layout = QHBoxLayout()
        btn_add = QPushButton("+ 일정 추가");
        btn_add.clicked.connect(self.add_row)
        btn_save = QPushButton("이 품목 일정 저장");
        btn_save.clicked.connect(self.save_schedule)
        schedule_button_layout.addStretch()
        schedule_button_layout.addWidget(btn_add)
        schedule_button_layout.addWidget(btn_save)

        schedule_layout.addWidget(self.table)
        schedule_layout.addLayout(schedule_button_layout)

        # --- 변경 이력 테이블 ---
        history_group = QtWidgets.QGroupBox("변경 이력")
        history_layout = QVBoxLayout(history_group)
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["변경 요청일", "변경 전", "변경 후", "사유"])
        self.history_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        # ✅ [수정] 모든 컬럼을 Interactive로 변경
        history_header = self.history_table.horizontalHeader()
        history_header.setSectionResizeMode(0, QHeaderView.Interactive)
        history_header.setSectionResizeMode(1, QHeaderView.Interactive)
        history_header.setSectionResizeMode(2, QHeaderView.Interactive)
        history_header.setSectionResizeMode(3, QHeaderView.Interactive)
        history_layout.addWidget(self.history_table)

        layout.addLayout(info_layout)
        layout.addWidget(schedule_group)
        layout.addWidget(history_group)

        self.populate_table(item_info['shipments'])
        self.load_history()

        # ✅ [추가] 컬럼 너비 복원 및 저장 시그널 연결
        self.restore_column_widths(self.table, "schedule_edit_table")
        self.restore_column_widths(self.history_table, "schedule_history_table")

        header_edit.sectionResized.connect(
            lambda: self.save_column_widths(self.table, "schedule_edit_table")
        )
        history_header.sectionResized.connect(
            lambda: self.save_column_widths(self.history_table, "schedule_history_table")
        )


    def populate_table(self, shipments):
        self.table.model().dataChanged.disconnect(self.update_summary)
        self.table.setRowCount(0)
        for shipment in shipments:
            self.add_row(shipment['due_date'], shipment['ship_qty'], is_loading=True)
        self.update_summary()
        self.table.model().dataChanged.connect(self.update_summary)

    def add_row(self, due_date="", qty=1, is_loading=False):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(due_date))
        self.table.setItem(row, 1, QTableWidgetItem(str(qty)))
        btn_delete = QPushButton("삭제")
        btn_delete.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        self.table.setCellWidget(row, 2, btn_delete)
        if not is_loading: self.update_summary()

    def update_summary(self):
        current_sum = 0;
        has_error = False
        for row in range(self.table.rowCount()):
            try:
                item = self.table.item(row, 1)
                current_sum += int(item.text())
            except (ValueError, AttributeError):
                has_error = True;
                pass

        remaining = self.total_qty - current_sum
        self.lbl_sum_info.setText(f"할당된 수량: {current_sum} / 남은 수량: {remaining}")

        if remaining == 0 and not has_error:
            self.lbl_sum_info.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_sum_info.setStyleSheet("color: red; font-weight: bold;")

    def load_history(self):
        history = get_shipment_change_history(self.item_id)
        self.history_table.setRowCount(len(history))
        for r, row in enumerate(history):
            for c, val in enumerate(row):
                self.history_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(val)))
        # self.history_table.resizeColumnsToContents()
        self.history_table.horizontalHeader().setStretchLastSection(True)

    def save_schedule(self):
        new_shipments = []
        current_sum = 0
        for row in range(self.table.rowCount()):
            date_str = self.table.item(row, 0).text()
            qty_str = self.table.item(row, 1).text()
            due_date = parse_due_text(date_str)
            if not due_date:
                QMessageBox.warning(self, "입력 오류", f"{row + 1}행의 납기일 형식이 올바르지 않습니다. (YYYY-MM-DD)");
                return
            try:
                qty = int(qty_str)
                if qty <= 0: raise ValueError
            except (ValueError, AttributeError):
                QMessageBox.warning(self, "입력 오류", f"{row + 1}행의 수량이 잘못되었습니다.");
                return
            new_shipments.append({'due_date': due_date, 'ship_qty': qty});
            current_sum += qty

        if current_sum != self.total_qty:
            QMessageBox.warning(self, "수량 오류", f"분할 납기 수량의 합({current_sum})이 총 주문 수량({self.total_qty})과 일치하지 않습니다.");
            return

        reason, ok = QInputDialog.getText(self, "변경 사유", "납기일 변경 사유를 입력하세요:", text="고객사 요청")
        if current_sum != self.total_qty:
            QMessageBox.warning(self, "수량 오류", f"분할 납기 수량의 합({current_sum})이 총 주문 수량({self.total_qty})과 일치하지 않습니다.");
            return
# app/ui/schedule_dialog.py

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                               QTableWidgetItem, QPushButton, QHeaderView, QMessageBox,
                               QLabel, QLineEdit, QDialogButtonBox, QSpinBox, QInputDialog,
                               QTabWidget, QWidget)
from PySide6.QtCore import Qt, QSettings
from ..db import get_full_schedule_for_order, save_schedule_for_item, get_shipment_change_history
from .utils import parse_due_text


class ScheduleDialog(QDialog):
    """주문 전체의 납기 일정을 품목별 탭으로 관리하는 메인 다이얼로그"""

    def __init__(self, order_id, order_no, parent=None):
        super().__init__(parent)
        self.order_id = order_id
        self.order_no = order_no
        self.schedule_data = get_full_schedule_for_order(self.order_id)

        self.setWindowTitle(f"납기 일정 관리 - {self.order_no}")
        self.setMinimumSize(800, 600)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.item_tabs = QTabWidget()

        # 주문에 포함된 품목별로 탭 생성
        for item_info in self.schedule_data:
            editor_widget = ScheduleEditorWidget(item_info, self)
            self.item_tabs.addTab(editor_widget, item_info['product_name'])

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        main_layout.addWidget(self.item_tabs)
        main_layout.addWidget(buttons)


class ScheduleEditorWidget(QWidget):
    """품목 하나의 납기 일정과 이력을 관리하는 위젯 (탭 안에 들어감)"""

    def __init__(self, item_info, parent=None):
        super().__init__(parent)
        self.item_id = item_info['item_id']
        self.product_name = item_info['product_name']
        self.total_qty = item_info['total_qty']

        # ✅ QSettings 초기화
        self.settings = QSettings("KOBATECH", "ProductionManagement")

        layout = QVBoxLayout(self)

        # --- 상단 정보 및 요약 ---
        info_layout = QHBoxLayout()
        self.lbl_info = QLabel(f"<b>{self.product_name}</b> (총 주문 수량: {self.total_qty}개)")
        self.lbl_sum_info = QLabel()
        info_layout.addWidget(self.lbl_info)
        info_layout.addStretch()
        info_layout.addWidget(self.lbl_sum_info)

        # --- 스케줄 편집 테이블 ---
        schedule_group = QtWidgets.QGroupBox("납기 일정 편집")
        schedule_layout = QVBoxLayout(schedule_group)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["납기일 (YYYY-MM-DD)", "수량", ""])

        # ✅ [수정] 모든 컬럼을 Interactive로 변경
        header_edit = self.table.horizontalHeader()
        header_edit.setSectionResizeMode(0, QHeaderView.Interactive)
        header_edit.setSectionResizeMode(1, QHeaderView.Interactive)
        header_edit.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.model().dataChanged.connect(self.update_summary)  # 셀 내용 변경 시 요약 업데이트

        schedule_button_layout = QHBoxLayout()
        btn_add = QPushButton("+ 일정 추가");
        btn_add.clicked.connect(self.add_row)
        btn_save = QPushButton("이 품목 일정 저장");
        btn_save.clicked.connect(self.save_schedule)
        schedule_button_layout.addStretch()
        schedule_button_layout.addWidget(btn_add)
        schedule_button_layout.addWidget(btn_save)

        schedule_layout.addWidget(self.table)
        schedule_layout.addLayout(schedule_button_layout)

        # --- 변경 이력 테이블 ---
        history_group = QtWidgets.QGroupBox("변경 이력")
        history_layout = QVBoxLayout(history_group)
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["변경 요청일", "변경 전", "변경 후", "사유"])
        self.history_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        # ✅ [수정] 모든 컬럼을 Interactive로 변경
        history_header = self.history_table.horizontalHeader()
        history_header.setSectionResizeMode(0, QHeaderView.Interactive)
        history_header.setSectionResizeMode(1, QHeaderView.Interactive)
        history_header.setSectionResizeMode(2, QHeaderView.Interactive)
        history_header.setSectionResizeMode(3, QHeaderView.Interactive)
        history_layout.addWidget(self.history_table)

        layout.addLayout(info_layout)
        layout.addWidget(schedule_group)
        layout.addWidget(history_group)

        self.populate_table(item_info['shipments'])
        self.load_history()

        # ✅ [추가] 컬럼 너비 복원 및 저장 시그널 연결
        self.restore_column_widths(self.table, "schedule_edit_table")
        self.restore_column_widths(self.history_table, "schedule_history_table")

        header_edit.sectionResized.connect(
            lambda: self.save_column_widths(self.table, "schedule_edit_table")
        )
        history_header.sectionResized.connect(
            lambda: self.save_column_widths(self.history_table, "schedule_history_table")
        )


    def populate_table(self, shipments):
        self.table.model().dataChanged.disconnect(self.update_summary)
        self.table.setRowCount(0)
        for shipment in shipments:
            self.add_row(shipment['due_date'], shipment['ship_qty'], is_loading=True)
        self.update_summary()
        self.table.model().dataChanged.connect(self.update_summary)

    def add_row(self, due_date="", qty=1, is_loading=False):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(due_date))
        self.table.setItem(row, 1, QTableWidgetItem(str(qty)))
        btn_delete = QPushButton("삭제")
        btn_delete.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        self.table.setCellWidget(row, 2, btn_delete)
        if not is_loading: self.update_summary()

    def update_summary(self):
        current_sum = 0;
        has_error = False
        for row in range(self.table.rowCount()):
            try:
                item = self.table.item(row, 1)
                current_sum += int(item.text())
            except (ValueError, AttributeError):
                has_error = True;
                pass

        remaining = self.total_qty - current_sum
        self.lbl_sum_info.setText(f"할당된 수량: {current_sum} / 남은 수량: {remaining}")

        if remaining == 0 and not has_error:
            self.lbl_sum_info.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_sum_info.setStyleSheet("color: red; font-weight: bold;")

    def load_history(self):
        history = get_shipment_change_history(self.item_id)
        self.history_table.setRowCount(len(history))
        for r, row in enumerate(history):
            for c, val in enumerate(row):
                self.history_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(val)))
        # self.history_table.resizeColumnsToContents()
        self.history_table.horizontalHeader().setStretchLastSection(True)

    def save_schedule(self):
        new_shipments = []
        current_sum = 0
        for row in range(self.table.rowCount()):
            date_str = self.table.item(row, 0).text()
            qty_str = self.table.item(row, 1).text()
            due_date = parse_due_text(date_str)
            if not due_date:
                QMessageBox.warning(self, "입력 오류", f"{row + 1}행의 납기일 형식이 올바르지 않습니다. (YYYY-MM-DD)");
                return
            try:
                qty = int(qty_str)
                if qty <= 0: raise ValueError
            except (ValueError, AttributeError):
                QMessageBox.warning(self, "입력 오류", f"{row + 1}행의 수량이 잘못되었습니다.");
                return
            new_shipments.append({'due_date': due_date, 'ship_qty': qty});
            current_sum += qty

        if current_sum != self.total_qty:
            QMessageBox.warning(self, "수량 오류", f"분할 납기 수량의 합({current_sum})이 총 주문 수량({self.total_qty})과 일치하지 않습니다.");
            return

        reason, ok = QInputDialog.getText(self, "변경 사유", "납기일 변경 사유를 입력하세요:", text="고객사 요청")
        if not ok or not reason:
            QMessageBox.warning(self, "알림", "변경 사유를 입력해야 합니다.");
            return

        try:
            save_schedule_for_item(self.item_id, new_shipments, reason)

            # ✅ [수정] 백그라운드 스레드에서 Outlook 동기화 실행 (미래 일정만)
            # 공용 모듈에서 가져온 Worker 사용
            from .outlook_sync import OutlookSyncWorker
            self.sync_worker = OutlookSyncWorker(future_only=True)
            self.sync_worker.sync_finished.connect(lambda msg: print(f"Sync Finished: {msg}"))
            self.sync_worker.start()

            QMessageBox.information(self, "완료", "납기 일정이 성공적으로 저장되었습니다.")
            self.load_history()  # 저장 후 이력 테이블 새로고침
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다:\n{e}")

    def save_column_widths(self, table: QTableWidget, key: str):
        """(새 함수) 테이블의 컬럼 너비를 QSettings에 저장"""
        if not self.settings:
            return
        widths = []
        for col in range(table.columnCount()):
            widths.append(table.columnWidth(col))
        self.settings.setValue(f"{key}/column_widths", widths)

    def restore_column_widths(self, table: QTableWidget, key: str):
        """(새 함수) QSettings에서 테이블의 컬럼 너비를 복원"""
        if not self.settings:
            return
        widths = self.settings.value(f"{key}/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < table.columnCount():
                    table.setColumnWidth(col, int(width))