# app/ui/repair_widget.py

from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import (QHeaderView, QTableWidgetItem, QDialogButtonBox, QTabWidget,
                               QFormLayout, QGroupBox, QPlainTextEdit, QCompleter, QListWidget,
                               QListWidgetItem, QHBoxLayout, QVBoxLayout, QLabel, QMessageBox,
                               QFileDialog, QPushButton, QTableWidget)
from PySide6.QtCore import Qt, QSignalBlocker, QStringListModel, QUrl
from PySide6.QtGui import QDesktopServices, QBrush, QColor  # ✅ QBrush, QColor import 추가
from datetime import datetime
import os

from ..db import (get_all_repairs, add_or_update_repair, delete_repair, query_one,
                  get_repair_details, query_all, get_conn)
from .utils import parse_due_text, get_dynamic_onedrive_path
from .money_lineedit import MoneyLineEdit


class RepairWidget(QtWidgets.QWidget):
    """수리 관리 탭 위젯"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings

        self._open_dialogs = []

        self.setup_ui()

        self.current_sort_column = self.settings.value("repair_table/sort_column", 0, type=int)
        sort_order_val = self.settings.value("repair_table/sort_order", Qt.DescendingOrder)
        self.current_sort_order = Qt.SortOrder(sort_order_val)

        self.load_repair_list()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("수리 관리")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        self.filter_combo = QtWidgets.QComboBox()
        self.filter_combo.addItems(['전체', '접수', '수리중', '수리완료', '재출고', '자체처리'])
        self.filter_combo.currentTextChanged.connect(self.load_repair_list)

        # ✅ [수정] 새로고침 버튼 제거 (탭 이동 시 자동 갱신됨)
        # btn_refresh = QtWidgets.QPushButton("새로고침")
        # btn_refresh.clicked.connect(self.load_repair_list)

        btn_new = QtWidgets.QPushButton("새 수리 접수")
        btn_new.clicked.connect(self.add_repair)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.filter_combo)
        # title_layout.addWidget(btn_refresh) # 레이아웃에서도 제거
        title_layout.addWidget(btn_new)

        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["접수일", "품질보고서 번호", "품목코드", "제품명", "시리얼번호", "불량증상", "당사 조사내용", "상태", "수리일"]
        )

        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        self.table.itemDoubleClicked.connect(self.edit_repair)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        if self.settings:
            self.restore_column_widths()

        header.sectionResized.connect(self.save_column_widths)
        header.sortIndicatorChanged.connect(self.on_header_sort_changed)
        header.setSortIndicatorShown(True)

        layout.addLayout(title_layout)
        layout.addWidget(self.table)

    def save_column_widths(self):
        if not self.settings:
            return
        # ✅ [수정] self.table_attachments -> self.table 로 변경
        widths = [self.table.columnWidth(i) for i in range(self.table.columnCount())]
        self.settings.setValue("repair_table/column_widths", widths)

    def restore_column_widths(self):
        if not self.settings:
            return
        widths = self.settings.value("repair_table/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < self.table.columnCount():
                    self.table.setColumnWidth(col, int(width))

    def show_context_menu(self, position):
        item = self.table.itemAt(position)
        if not item: return

        menu = QtWidgets.QMenu(self)
        edit_action = menu.addAction("수정")
        edit_action.triggered.connect(self.edit_repair)
        delete_action = menu.addAction("삭제")
        delete_action.triggered.connect(self.delete_repair)
        menu.exec_(self.table.mapToGlobal(position))

    def load_repair_list(self):
        status_filter = self.filter_combo.currentText()
        order_clause = self.get_repair_order_clause()

        rows = get_all_repairs(
            status_filter=status_filter,
            order_by_clause=order_clause
        )

        # ✅ [추가] 색상 설정 로드
        comp_fg = QColor(self.settings.value("colors/repair_completed_fg", "#000000"))
        comp_bg = QColor(self.settings.value("colors/repair_completed_bg", "#FFCCBC"))  # 기본값: 연한 살구색
        incomp_fg = QColor(self.settings.value("colors/repair_incomplete_fg", "#000000"))
        incomp_bg = QColor(self.settings.value("colors/repair_incomplete_bg", "#FFFFFF"))

        self.table.setRowCount(len(rows))
        self.table.setSortingEnabled(False)
        for r, row in enumerate(rows):
            (repair_id, receipt_date, report_no, part_no, product_name, serial_no,
             symptom, investigation, status, repair_date, redelivery_invoice, product_id) = row

            item_0 = QTableWidgetItem(receipt_date or "")
            item_0.setData(Qt.UserRole, repair_id)
            item_0.setData(Qt.UserRole + 1, product_id)
            self.table.setItem(r, 0, item_0)
            self.table.setItem(r, 1, QTableWidgetItem(report_no or ""))
            self.table.setItem(r, 2, QTableWidgetItem(part_no or ""))
            self.table.setItem(r, 3, QTableWidgetItem(product_name or ""))
            self.table.setItem(r, 4, QTableWidgetItem(serial_no or ""))
            self.table.setItem(r, 5, QTableWidgetItem(symptom or ""))
            self.table.setItem(r, 6, QTableWidgetItem(investigation or ""))
            self.table.setItem(r, 7, QTableWidgetItem(status or ""))
            self.table.setItem(r, 8, QTableWidgetItem(repair_date or ""))

            # ✅ 상태가 '재출고' 또는 '자체처리'이면 완료된 것으로 간주
            status_str = str(status).strip()
            is_completed = (status_str in ['재출고', '자체처리'])

            fg_color = comp_fg if is_completed else incomp_fg
            bg_color = comp_bg if is_completed else incomp_bg

            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item:
                    item.setForeground(QBrush(fg_color))
                    item.setBackground(QBrush(bg_color))

        self.table.setSortingEnabled(True)
        with QSignalBlocker(self.table.horizontalHeader()):
            self.table.horizontalHeader().setSortIndicator(
                self.current_sort_column,
                self.current_sort_order
            )

    def get_repair_order_clause(self):
        column_names = [
            "r.receipt_date", "r.quality_report_no", "p.part_no",
            "p.product_name", "p.serial_no", "r.defect_symptom",
            "r.investigation_internal", "r.status", "r.repair_date"
        ]

        if 0 <= self.current_sort_column < len(column_names):
            column = column_names[self.current_sort_column]
            direction = "DESC" if self.current_sort_order == Qt.DescendingOrder else "ASC"
        else:
            column = "r.receipt_date"
            direction = "DESC"

        return f"{column} {direction}, r.id DESC"

    # ... (이하 메서드들은 기존과 동일) ...
    def on_header_sort_changed(self, column_index, order):
        if self.current_sort_column == column_index and self.current_sort_order == order:
            return

        self.current_sort_column = column_index
        self.current_sort_order = order
        self.settings.setValue("repair_table/sort_column", self.current_sort_column)
        self.settings.setValue("repair_table/sort_order", self.current_sort_order)
        self.load_repair_list()

    def _open_repair_dialog(self, dialog):
        dialog.finished.connect(lambda result: self._on_dialog_finished(result, dialog))
        self._open_dialogs.append(dialog)
        dialog.show()

    def _on_dialog_finished(self, result, dialog):
        if result == QtWidgets.QDialog.Accepted:
            self.load_repair_list()
        if dialog in self._open_dialogs:
            self._open_dialogs.remove(dialog)
        dialog.deleteLater()

    def add_repair(self):
        dialog = RepairDialog(self, settings=self.settings)
        self._open_repair_dialog(dialog)

    def edit_repair(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QtWidgets.QMessageBox.information(self, "알림", "수정할 항목을 선택해주세요.")
            return

        repair_id = self.table.item(selected_row, 0).data(Qt.UserRole)
        product_id = self.table.item(selected_row, 0).data(Qt.UserRole + 1)
        serial_no = self.table.item(selected_row, 4).text()

        dialog = RepairDialog(self, repair_id=repair_id, product_id=product_id, serial_no=serial_no,
                              settings=self.settings)
        self._open_repair_dialog(dialog)

    def delete_repair(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QtWidgets.QMessageBox.information(self, "알림", "삭제할 항목을 선택해주세요.")
            return

        repair_id = self.table.item(selected_row, 0).data(Qt.UserRole)
        serial_no = self.table.item(selected_row, 4).text()

        reply = QtWidgets.QMessageBox.question(
            self, "수리 내역 삭제", f"정말로 '{serial_no}' 제품의 수리 내역을 삭제하시겠습니까?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            delete_repair(repair_id)
            self.load_repair_list()


class RepairDialog(QtWidgets.QDialog):
    """수리 등록/수정 다이얼로그"""

    def __init__(self, parent=None, repair_id=None, product_id=None, serial_no=None, settings=None):
        super().__init__(parent)
        self.repair_id = repair_id
        self.product_id = product_id
        self.serial_no = serial_no
        self.settings = settings
        self.is_edit = (repair_id is not None)
        self.search_map = {}
        self.selected_products_map = {}

        self.attachment_data = []  # List of dicts: {'path': str, 'description': str}

        self.setup_ui()

        if self.settings:
            geometry = self.settings.value("repair_dialog/geometry")
            if geometry:
                self.restoreGeometry(geometry)

        if self.is_edit:
            self.load_repair_data()

    def setup_ui(self):
        title = "수리 내역 수정" if self.is_edit else "새 수리 접수"
        self.setWindowTitle(title)
        self.setMinimumSize(800, 700)

        main_layout = QtWidgets.QVBoxLayout(self)

        # --- 제품 선택 영역 ---
        product_group = QGroupBox("수리 대상 제품")
        product_layout = QVBoxLayout(product_group)

        search_layout = QHBoxLayout()
        self.product_search = QtWidgets.QLineEdit()
        self.product_search.setPlaceholderText("시리얼 번호로 검색하여 추가...")
        search_layout.addWidget(QLabel("제품 검색:"))
        search_layout.addWidget(self.product_search)

        self.selected_list_widget = QListWidget()
        self.selected_list_widget.setMaximumHeight(80)
        self.selected_list_widget.setToolTip("더블 클릭하면 목록에서 제거됩니다.")
        self.selected_list_widget.itemDoubleClicked.connect(self.remove_product_from_list)

        self.product_info_label = QtWidgets.QLabel("")
        self.product_info_label.setStyleSheet("color: blue; font-weight: bold;")
        self.product_info_label.setVisible(False)

        if not self.is_edit:
            product_layout.addLayout(search_layout)
            product_layout.addWidget(QLabel("선택된 제품 목록 (더블클릭하여 제거):"))
            product_layout.addWidget(self.selected_list_widget)

            self.search_completer = QCompleter(self)
            self.search_completer.setCaseSensitivity(Qt.CaseInsensitive)
            self.search_completer.setFilterMode(Qt.MatchContains)
            self.search_completer.activated.connect(self.on_search_result_selected)

            self.product_search.setCompleter(self.search_completer)
            self.product_search.textChanged.connect(self.update_search_suggestions)
        else:
            self.product_info_label.setVisible(True)
            product_layout.addWidget(self.product_info_label)

        # --- 탭 위젯 ---
        tab_widget = QTabWidget()

        # 1. 기본 정보
        tab_basic = QtWidgets.QWidget()
        form1 = QFormLayout(tab_basic)
        self.edt_receipt_date = QtWidgets.QLineEdit()
        self.edt_receipt_date.setPlaceholderText("YYYY-MM-DD")

        if not self.is_edit:
            self.edt_receipt_date.setText(datetime.now().strftime("%Y-%m-%d"))

        self.edt_defect_date = QtWidgets.QLineEdit()
        self.edt_defect_date.setPlaceholderText("YYYY-MM-DD")
        self.edt_quality_report_no = QtWidgets.QLineEdit()
        self.edt_repair_pic = QtWidgets.QLineEdit()
        self.txt_defect_symptom = QPlainTextEdit()

        form1.addRow("접수일*", self.edt_receipt_date)
        form1.addRow("불량 발생일", self.edt_defect_date)
        form1.addRow("품질보고서 번호", self.edt_quality_report_no)
        form1.addRow("발주 담당자", self.edt_repair_pic)
        form1.addRow("불량 증상", self.txt_defect_symptom)

        # 첨부 파일 섹션
        attach_group = QGroupBox("첨부 파일")
        attach_layout = QVBoxLayout(attach_group)
        attach_layout.setContentsMargins(10, 5, 10, 5)
        attach_layout.setSpacing(5)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_add_attachment = QPushButton("파일 추가")
        self.btn_remove_attachment = QPushButton("선택 삭제")
        btn_layout.addWidget(self.btn_add_attachment)
        btn_layout.addWidget(self.btn_remove_attachment)

        self.table_attachments = QTableWidget(0, 2)
        self.table_attachments.setHorizontalHeaderLabels(["첨부파일", "설명"])
        self.table_attachments.setMaximumHeight(200)
        self.table_attachments.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table_attachments.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table_attachments.verticalHeader().setVisible(False)

        # ✅ [수정] 컬럼 폭 설정 및 저장 기능 연결 (이 부분이 핵심입니다!)
        header = self.table_attachments.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)  # 사용자 조절 가능
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setStretchLastSection(True)

        # 1. 기본 폭 설정 (400px)
        self.table_attachments.setColumnWidth(0, 400)
        self.table_attachments.setColumnWidth(1, 200)

        # 2. 저장된 설정 불러오기 (이전에 조절한 값이 있다면 덮어씀)
        self.restore_column_widths()

        # 3. 조절할 때마다 저장되도록 연결
        header.sectionResized.connect(self.save_column_widths)

        # 더블클릭으로 파일 열기
        self.table_attachments.cellDoubleClicked.connect(self.open_attachment)

        attach_layout.addLayout(btn_layout)
        attach_layout.addWidget(self.table_attachments)

        form1.addRow(attach_group)

        self.btn_add_attachment.clicked.connect(self.add_attachment)
        self.btn_remove_attachment.clicked.connect(self.remove_attachment)

        # 2. 원인 분석
        tab_analysis = QtWidgets.QWidget()
        form2 = QFormLayout(tab_analysis)
        self.txt_investigation_customer = QPlainTextEdit()
        self.txt_investigation_internal = QPlainTextEdit()
        self.txt_root_cause_occurrence = QPlainTextEdit()
        self.txt_root_cause_outflow = QPlainTextEdit()

        form2.addRow("고객사 조사내용", self.txt_investigation_customer)
        form2.addRow("당사 조사내용", self.txt_investigation_internal)
        form2.addRow("근본원인 (발생)", self.txt_root_cause_occurrence)
        form2.addRow("근본원인 (유출)", self.txt_root_cause_outflow)

        # 3. 조치 및 대책
        tab_action = QtWidgets.QWidget()
        form3 = QFormLayout(tab_action)
        self.txt_immediate_action = QPlainTextEdit()
        self.txt_prevention_occurrence = QPlainTextEdit()
        self.txt_prevention_outflow = QPlainTextEdit()

        form3.addRow("즉각 대응조치", self.txt_immediate_action)
        form3.addRow("재발방지대책 (발생)", self.txt_prevention_occurrence)
        form3.addRow("재발방지대책 (유출)", self.txt_prevention_outflow)

        # 4. 처리 결과
        tab_result = QtWidgets.QWidget()
        form4 = QFormLayout(tab_result)
        self.cmb_status = QtWidgets.QComboBox()
        self.cmb_status.addItems(['접수', '수리중', '수리완료', '재출고', '자체처리'])

        self.edt_repair_date = QtWidgets.QLineEdit()
        self.edt_repair_date.setPlaceholderText("YYYY-MM-DD")

        self.edt_redelivery_invoice = QtWidgets.QLineEdit()
        self.edt_redelivery_invoice.setReadOnly(True)
        self.edt_redelivery_invoice.setStyleSheet("background-color: #f0f0f0;")

        form4.addRow("상태", self.cmb_status)
        form4.addRow("수리일", self.edt_repair_date)
        form4.addRow("재출고 인보이스", self.edt_redelivery_invoice)

        import_group = QGroupBox("수입비용")
        import_layout = QFormLayout(import_group)
        import_layout.setContentsMargins(10, 10, 10, 10)

        self.edt_import_invoice_no = QtWidgets.QLineEdit()
        self.edt_import_declaration_no = QtWidgets.QLineEdit()
        self.edt_import_carrier = QtWidgets.QLineEdit()
        self.cost_deposit = MoneyLineEdit(max_value=1_000_000_000)
        self.cost_air_freight = MoneyLineEdit(max_value=1_000_000_000)

        import_layout.addRow("수입 인보이스 번호:", self.edt_import_invoice_no)
        import_layout.addRow("수입신고필증번호:", self.edt_import_declaration_no)
        import_layout.addRow("수입운송사:", self.edt_import_carrier)
        import_layout.addRow("담보금(수입관세):", self.cost_deposit)
        import_layout.addRow("항공운송요금:", self.cost_air_freight)
        form4.addRow(import_group)

        export_group = QGroupBox("수출비용")
        export_layout = QFormLayout(export_group)
        export_layout.setContentsMargins(10, 10, 10, 10)
        self.cost_shipping_jp = MoneyLineEdit(max_value=1_000_000_000)
        self.cost_tax_jp = MoneyLineEdit(max_value=1_000_000_000)
        export_layout.addRow("한국->일본 운반비:", self.cost_shipping_jp)
        export_layout.addRow("부가세 및 일본 국내 세금:", self.cost_tax_jp)
        form4.addRow(export_group)

        tab_widget.addTab(tab_basic, "기본 정보")
        tab_widget.addTab(tab_analysis, "원인 분석")
        tab_widget.addTab(tab_action, "조치 및 대책")
        tab_widget.addTab(tab_result, "처리 결과")

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept_dialog)
        button_box.rejected.connect(self.reject)

        main_layout.addWidget(product_group)
        main_layout.addWidget(tab_widget)

        self.setStyleSheet("""
            QPlainTextEdit { border: 1px solid #c0c0c0; max-height: 160px; }
            QLineEdit { border: 1px solid #c0c0c0; background-color: white; padding: 3px 5px; }
            QLineEdit:read-only { background-color: #f0f0f0; }
        """)

        main_layout.addWidget(button_box)

        if self.product_id and self.is_edit:
            self.update_product_info_single(self.product_id)

        if self.serial_no:
            pass

    def add_attachment(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "첨부할 파일 선택", "",
            "All Files (*);;Image Files (*.png *.jpg *.jpeg);;PDF Files (*.pdf)"
        )
        if files:
            for file_path in files:
                # 중복 체크
                if not any(att['path'] == file_path for att in self.attachment_data):
                    self.attachment_data.append({'path': file_path, 'description': ''})

                    row = self.table_attachments.rowCount()
                    self.table_attachments.insertRow(row)

                    # 파일명 (읽기 전용)
                    filename_item = QTableWidgetItem(os.path.basename(file_path))
                    filename_item.setData(Qt.UserRole, file_path)
                    filename_item.setFlags(filename_item.flags() & ~Qt.ItemIsEditable)
                    self.table_attachments.setItem(row, 0, filename_item)

                    # 설명 (편집 가능)
                    desc_item = QTableWidgetItem('')
                    self.table_attachments.setItem(row, 1, desc_item)

    def remove_attachment(self):
        selected_rows = sorted(set(item.row() for item in self.table_attachments.selectedItems()), reverse=True)
        for row in selected_rows:
            file_path_item = self.table_attachments.item(row, 0)
            if file_path_item:
                file_path = file_path_item.data(Qt.UserRole)
                # attachment_data에서 제거
                self.attachment_data = [att for att in self.attachment_data if att['path'] != file_path]
            self.table_attachments.removeRow(row)

    def open_attachment(self, row, column):
        file_path_item = self.table_attachments.item(row, 0)
        if file_path_item:
            original_path = file_path_item.data(Qt.UserRole)

            # ✅ [핵심] DB에 저장된 경로를 현재 PC에 맞는 경로로 변환
            real_path = get_dynamic_onedrive_path(original_path)

            if real_path and os.path.exists(real_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(real_path))
            else:
                # 파일을 못 찾았을 때 안내 메시지
                QtWidgets.QMessageBox.warning(self, "파일 오류",
                                              f"파일을 찾을 수 없습니다.\n\n"
                                              f"저장된 경로: {original_path}\n")
                                              #f"현재 PC 경로(추정): {real_path if real_path else '변환 실패'}")

    def update_search_suggestions(self, text):
        if "|" in text: return
        if len(text) < 2: return

        sql = """
            SELECT id, serial_no, part_no, product_name, manufacture_code 
            FROM products 
            WHERE serial_no LIKE ?
            LIMIT 20
        """
        rows = query_all(sql, (f"%{text}%",))

        suggestions = []
        self.search_map = {}

        for r in rows:
            p_id, sn, code, name, date_code = r
            date_str = date_code if date_code else "DateCode 없음"
            display_text = f"{sn} | {name} ({code}) [{date_str}]"

            suggestions.append(display_text)
            self.search_map[display_text] = p_id

        model = QStringListModel(suggestions)
        self.search_completer.setModel(model)

    def on_search_result_selected(self, text):
        p_id = self.search_map.get(text)
        if p_id:
            self.add_product_to_list(p_id, text)
            self.product_search.clear()
            self.product_search.setFocus()

    def add_product_to_list(self, product_id, display_text):
        if product_id in self.selected_products_map:
            return

        self.selected_products_map[product_id] = display_text

        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, product_id)
        self.selected_list_widget.addItem(item)

    def remove_product_from_list(self, item):
        p_id = item.data(Qt.UserRole)
        if p_id in self.selected_products_map:
            del self.selected_products_map[p_id]

        row = self.selected_list_widget.row(item)
        self.selected_list_widget.takeItem(row)

    def update_product_info_single(self, product_id):
        product_info = query_one("SELECT part_no, product_name, serial_no, manufacture_code FROM products WHERE id=?",
                                 (product_id,))
        if product_info:
            part_no, name, serial, manufacture_code = product_info
            self.product_info_label.setText(f"{name} (S/N: {serial} / Date Code: {manufacture_code or 'N/A'})")

    def load_repair_data(self):
        if not self.repair_id: return
        data = get_repair_details(self.repair_id)
        if not data: return

        (product_id, receipt_date, report_no, symptom, inv_cust, inv_int,
         imm_action, cause_occ, cause_out, details, prev_occ, prev_out,
         status, repair_date, invoice,
         cost_deposit, cost_air_freight, cost_shipping_jp, cost_tax_jp,
         repair_pic, ncr_qty,
         import_invoice_no, import_declaration_no, import_carrier,
         defect_date, attachments_text) = data

        self.edt_receipt_date.setText(receipt_date or "")
        self.edt_defect_date.setText(defect_date or "")
        self.edt_quality_report_no.setText(report_no or "")
        self.edt_repair_pic.setText(repair_pic or "")
        self.txt_defect_symptom.setPlainText(symptom or "")
        self.txt_investigation_customer.setPlainText(inv_cust or "")
        self.txt_investigation_internal.setPlainText(inv_int or "")
        self.txt_root_cause_occurrence.setPlainText(cause_occ or "")
        self.txt_root_cause_outflow.setPlainText(cause_out or "")
        self.txt_immediate_action.setPlainText(imm_action or "")

        self.txt_prevention_occurrence.setPlainText(prev_occ or "")
        self.txt_prevention_outflow.setPlainText(prev_out or "")
        self.cmb_status.setCurrentText(status or '접수')
        self.edt_repair_date.setText(repair_date or "")
        self.edt_redelivery_invoice.setText(invoice or "")

        self.cost_deposit.set_value((cost_deposit or 0) // 100)
        self.cost_air_freight.set_value((cost_air_freight or 0) // 100)
        self.cost_shipping_jp.set_value((cost_shipping_jp or 0) // 100)
        self.cost_tax_jp.set_value((cost_tax_jp or 0) // 100)

        self.edt_import_invoice_no.setText(import_invoice_no or "")
        self.edt_import_declaration_no.setText(import_declaration_no or "")
        self.edt_import_carrier.setText(import_carrier or "")

        # 첨부 파일 로드
        self.attachment_data.clear()
        self.table_attachments.setRowCount(0)
        if attachments_text:
            import json
            try:
                # JSON 형식으로 저장된 경우
                attachments = json.loads(attachments_text)
                for att in attachments:
                    self.attachment_data.append(att)
                    row = self.table_attachments.rowCount()
                    self.table_attachments.insertRow(row)

                    filename_item = QTableWidgetItem(os.path.basename(att['path']))
                    filename_item.setData(Qt.UserRole, att['path'])
                    filename_item.setFlags(filename_item.flags() & ~Qt.ItemIsEditable)
                    self.table_attachments.setItem(row, 0, filename_item)

                    desc_item = QTableWidgetItem(att.get('description', ''))
                    self.table_attachments.setItem(row, 1, desc_item)
            except (json.JSONDecodeError, KeyError):
                # 이전 형식 (세미콜론으로 구분된 경로만)
                paths = [p.strip() for p in attachments_text.split(';') if p.strip()]
                for file_path in paths:
                    self.attachment_data.append({'path': file_path, 'description': ''})
                    row = self.table_attachments.rowCount()
                    self.table_attachments.insertRow(row)

                    filename_item = QTableWidgetItem(os.path.basename(file_path))
                    filename_item.setData(Qt.UserRole, file_path)
                    filename_item.setFlags(filename_item.flags() & ~Qt.ItemIsEditable)
                    self.table_attachments.setItem(row, 0, filename_item)

                    desc_item = QTableWidgetItem('')
                    self.table_attachments.setItem(row, 1, desc_item)

        # ✅ 상태가 '재출고'라면 수정을 막음 (단, 관리자/특수 상황 고려해 해제 기능은 없음)
        if status == '재출고':
            self.setWindowTitle(f"수리 내역 조회 (재출고 완료 - 수정 불가)")
            self.cmb_status.setEnabled(False)  # 상태 변경 불가
            self.edt_redelivery_invoice.setReadOnly(True)  # 인보이스 수정 불가


    def accept_dialog(self):
        target_product_ids = []

        if self.is_edit:
            if not self.product_id:
                QtWidgets.QMessageBox.warning(self, "입력 오류", "제품 정보가 없습니다.")
                return
            target_product_ids.append(self.product_id)
        else:
            if not self.selected_products_map:
                QtWidgets.QMessageBox.warning(self, "입력 오류", "최소 1개 이상의 제품을 목록에 추가해주세요.")
                return
            target_product_ids = list(self.selected_products_map.keys())

        receipt_date = parse_due_text(self.edt_receipt_date.text())
        if not receipt_date:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "접수일은 필수이며, YYYY-MM-DD 형식이어야 합니다.")
            return

        # -------------------------------------------------------------------------
        # ✅ [추가] 수리 등록 전 유효성 검사 (출하 여부 & 중복 접수 확인)
        # -------------------------------------------------------------------------
        conn_check = get_conn()
        cur_check = conn_check.cursor()
        try:
            for p_id in target_product_ids:
                # 1. 제품 정보 조회 (S/N, 납품ID)
                cur_check.execute("SELECT serial_no, delivery_id FROM products WHERE id = ?", (p_id,))
                prod_row = cur_check.fetchone()

                if not prod_row:
                    continue

                sn, delivery_id = prod_row

                # (수정 모드가 아닐 때만 체크)
                if not self.is_edit:
                    # 조건 1: 출하된 제품인가? (delivery_id가 있어야 함)
                    if delivery_id is None:
                        QtWidgets.QMessageBox.warning(
                            self, "등록 불가",
                            f"시리얼번호 '{sn}' 제품은 현재 '재고(미납품)' 상태입니다.\n"
                            "납품이 완료된 제품만 수리 접수가 가능합니다."
                        )
                        conn_check.close()
                        return

                    # 조건 2: 현재 수리 진행 중인가? (종결되지 않은 수리 이력이 있는지 확인)
                    # '재출고'나 '자체처리'가 아닌 상태의 레코드가 있다면 이미 수리 중인 것임
                    cur_check.execute("""
                            SELECT status FROM product_repairs 
                            WHERE product_id = ? 
                              AND status NOT IN ('재출고', '자체처리')
                        """, (p_id,))
                    active_repair = cur_check.fetchone()

                    if active_repair:
                        status_now = active_repair[0]
                        QtWidgets.QMessageBox.warning(
                            self, "중복 접수 불가",
                            f"시리얼번호 '{sn}' 제품은 이미 수리 진행 중입니다.\n"
                            f"현재 상태: {status_now}\n\n"
                            "해당 수리 건을 '재출고' 또는 '자체처리'로 완료한 후에\n"
                            "새로 접수할 수 있습니다."
                        )
                        conn_check.close()
                        return

        except Exception as e:
            print(f"Validation Error: {e}")
        finally:
            conn_check.close()
        # -------------------------------------------------------------------------

        # 테이블에서 설명 업데이트
        for row in range(self.table_attachments.rowCount()):
            file_path_item = self.table_attachments.item(row, 0)
            desc_item = self.table_attachments.item(row, 1)
            if file_path_item and desc_item:
                file_path = file_path_item.data(Qt.UserRole)
                description = desc_item.text()
                # attachment_data 업데이트
                for att in self.attachment_data:
                    if att['path'] == file_path:
                        att['description'] = description
                        break

        # JSON 형식으로 저장
        import json
        attachments_str = json.dumps(self.attachment_data, ensure_ascii=False)

        base_repair_data = {
            'receipt_date': receipt_date,
            'defect_date': parse_due_text(self.edt_defect_date.text().strip()),
            'quality_report_no': self.edt_quality_report_no.text(),
            'repair_pic': self.edt_repair_pic.text(),
            'ncr_qty': None,
            'defect_symptom': self.txt_defect_symptom.toPlainText(),
            'investigation_customer': self.txt_investigation_customer.toPlainText(),
            'investigation_internal': self.txt_investigation_internal.toPlainText(),
            'root_cause_occurrence': self.txt_root_cause_occurrence.toPlainText(),
            'root_cause_outflow': self.txt_root_cause_outflow.toPlainText(),
            'immediate_action': self.txt_immediate_action.toPlainText(),
            'repair_details': "",
            'prevention_occurrence': self.txt_prevention_occurrence.toPlainText(),
            'prevention_outflow': self.txt_prevention_outflow.toPlainText(),
            'status': self.cmb_status.currentText(),
            'repair_date': parse_due_text(self.edt_repair_date.text()),
            'redelivery_invoice_no': self.edt_redelivery_invoice.text(),
            'cost_deposit': self.cost_deposit.get_value() * 100,
            'cost_air_freight': self.cost_air_freight.get_value() * 100,
            'cost_shipping_jp': self.cost_shipping_jp.get_value() * 100,
            'cost_tax_jp': self.cost_tax_jp.get_value() * 100,
            'import_invoice_no': self.edt_import_invoice_no.text(),
            'import_declaration_no': self.edt_import_declaration_no.text(),
            'import_carrier': self.edt_import_carrier.text(),
            'attachments': attachments_str
        }

        conn = None
        try:
            conn = get_conn()
            cur = conn.cursor()

            current_status = self.cmb_status.currentText()

            for p_id in target_product_ids:
                repair_data = base_repair_data.copy()
                repair_data['product_id'] = p_id

                r_id = self.repair_id if self.is_edit else None

                add_or_update_repair(repair_data, r_id, external_cursor=cur)

            if current_status in ['접수', '수리중', '수리완료']:
                # 입고 수리: 우리 공장 재고로 잡혀야 하므로 납품 연결 해제 (delivery_id = NULL)
                cur.execute("UPDATE products SET delivery_id = NULL WHERE id = ?", (p_id,))

            elif current_status == '자체처리':
                # 자체 처리: 고객사에서 끝난 건이므로 납품 정보가 유지되어야 함.
                # 만약 실수로 '접수'로 저장했다가 '자체처리'로 바꾼 경우, 끊어진 연결을 다시 복구함.

                # 1. 현재 제품 정보 조회
                cur.execute("SELECT delivery_id, part_no, serial_no FROM products WHERE id = ?", (p_id,))
                prod_row = cur.fetchone()

                if prod_row:
                    curr_did, part_no, serial_no = prod_row

                    # 2. 납품 정보가 끊겨 있다면(NULL), 과거 기록을 찾아 복구
                    if curr_did is None:
                        cur.execute("""
                                            SELECT delivery_id FROM delivery_items
                                            WHERE item_code = ? AND serial_no = ?
                                            ORDER BY id DESC LIMIT 1
                                        """, (part_no, serial_no))

                        history = cur.fetchone()
                        if history:
                            restored_delivery_id = history[0]
                            cur.execute("UPDATE products SET delivery_id = ? WHERE id = ?",
                                        (restored_delivery_id, p_id))
                            print(f"✅ '자체처리' 건에 대한 납품 연결 자동 복구 완료: {part_no} ({serial_no})")

            conn.commit()
            self.accept()

        except Exception as e:
            if conn: conn.rollback()
            QtWidgets.QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if conn: conn.close()

    # 컬럼 폭 저장
    def save_column_widths(self):
        if not self.settings: return
        widths = [self.table_attachments.columnWidth(i) for i in range(self.table_attachments.columnCount())]
        self.settings.setValue("repair_dialog/attachment_widths", widths)

    # 컬럼 폭 복원
    def restore_column_widths(self):
        if not self.settings: return
        widths = self.settings.value("repair_dialog/attachment_widths")
        if widths:
            for i, width in enumerate(widths):
                # 저장된 값이 있으면 적용 (저장된 값이 0보다 클 때만)
                if i < self.table_attachments.columnCount() and int(width) > 0:
                    self.table_attachments.setColumnWidth(i, int(width))

    # 창 닫을 때 크기 저장
    def closeEvent(self, event):
        if self.settings:
            self.settings.setValue("repair_dialog/geometry", self.saveGeometry())
        super().closeEvent(event)
