# app/ui/recall_widget.py

from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import (QHeaderView, QTableWidgetItem, QDialogButtonBox, QTabWidget,
                               QFormLayout, QGroupBox, QPlainTextEdit, QCompleter, QListWidget,
                               QListWidgetItem, QHBoxLayout, QVBoxLayout, QLabel, QMessageBox,
                               QFileDialog, QPushButton, QTableWidget, QDialog)
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QBrush, QColor
from datetime import datetime
import os
import json

from ..db import (get_all_recall_cases, create_recall_case, update_recall_case, 
                  delete_recall_case, get_recall_case_details, get_next_recall_no,
                  update_recall_item_status, add_or_update_recall_shipment, 
                  delete_recall_shipment, query_all, query_one, get_conn)
from .utils import parse_due_text, get_dynamic_onedrive_path
from .money_lineedit import MoneyLineEdit
# .product_widget에서 ProductSearchDialog를 시도했으나, RecallDialog 내부에 직접 구현했으므로 제거함


class RecallWidget(QtWidgets.QWidget):
    """리콜 관리 탭 위젯"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self._open_dialogs = []

        self.setup_ui()

        self.current_sort_column = self.settings.value("recall_table/sort_column", 0, type=int) if self.settings else 0
        sort_order_val = self.settings.value("recall_table/sort_order", Qt.DescendingOrder) if self.settings else Qt.DescendingOrder
        self.current_sort_order = Qt.SortOrder(sort_order_val)

        self.load_recall_list()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("리콜 관리")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        self.filter_combo = QtWidgets.QComboBox()
        self.filter_combo.addItems(['전체', '접수', '진행중', '완료'])
        self.filter_combo.currentTextChanged.connect(self.load_recall_list)

        btn_new = QtWidgets.QPushButton("새 리콜 등록")
        btn_new.clicked.connect(self.add_recall)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.filter_combo)
        title_layout.addWidget(btn_new)

        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["리콜번호", "제목", "접수일", "대상수량", "처리수량", "잔여수량", "수입비용합계", "수출비용합계", "상태"]
        )

        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        self.table.itemDoubleClicked.connect(self.edit_recall)
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
        if not self.settings: return
        widths = [self.table.columnWidth(i) for i in range(self.table.columnCount())]
        self.settings.setValue("recall_table/column_widths", widths)

    def restore_column_widths(self):
        if not self.settings: return
        widths = self.settings.value("recall_table/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < self.table.columnCount():
                    self.table.setColumnWidth(col, int(width))

    def on_header_sort_changed(self, index, order):
        self.current_sort_column = index
        self.current_sort_order = order
        if self.settings:
            self.settings.setValue("recall_table/sort_column", index)
            self.settings.setValue("recall_table/sort_order", order.value)

    def show_context_menu(self, position):
        item = self.table.itemAt(position)
        if not item: return

        menu = QtWidgets.QMenu(self)
        edit_action = menu.addAction("수정/상세")
        edit_action.triggered.connect(self.edit_recall)
        delete_action = menu.addAction("삭제")
        delete_action.triggered.connect(self.delete_recall)
        menu.exec_(self.table.mapToGlobal(position))

    def get_recall_order_clause(self):
        col_map = {
            0: "rc.case_no", 1: "rc.title", 2: "rc.receipt_date", 
            8: "rc.status"
        }
        col_name = col_map.get(self.current_sort_column, "rc.case_no")
        order_str = "ASC" if self.current_sort_order == Qt.AscendingOrder else "DESC"
        return f"{col_name} {order_str}"

    def load_recall_list(self):
        status_filter = self.filter_combo.currentText()
        rows = get_all_recall_cases(status_filter=status_filter)

        self.table.setRowCount(len(rows))
        self.table.setSortingEnabled(False)
        
        for r, row in enumerate(rows):
            (case_id, case_no, title, receipt_date, status, 
             total_qty, handled_qty, import_cost, export_cost) = row
            
            remaining_qty = (total_qty or 0) - (handled_qty or 0)
            
            item_no = QTableWidgetItem(case_no or "")
            item_no.setData(Qt.UserRole, case_id)
            
            self.table.setItem(r, 0, item_no)
            self.table.setItem(r, 1, QTableWidgetItem(title or ""))
            self.table.setItem(r, 2, QTableWidgetItem(receipt_date or ""))
            
            self.table.setItem(r, 3, QTableWidgetItem(str(total_qty or 0)))
            self.table.setItem(r, 4, QTableWidgetItem(str(handled_qty or 0)))
            self.table.setItem(r, 5, QTableWidgetItem(str(remaining_qty)))
            
            # 비용 표시 (단위: 원, 100으로 나눔)
            imp_cost_str = f"{int(import_cost/100):,}" if import_cost else "0"
            exp_cost_str = f"{int(export_cost/100):,}" if export_cost else "0"
            
            self.table.setItem(r, 6, QTableWidgetItem(imp_cost_str))
            self.table.setItem(r, 7, QTableWidgetItem(exp_cost_str))
            self.table.setItem(r, 8, QTableWidgetItem(status or ""))
            
            # 상태에 따른 배경색 처리 (완료된 경우 연한 녹색 계열 등)
            if status == "완료":
                for c in range(self.table.columnCount()):
                    self.table.item(r, c).setBackground(QBrush(QColor("#E8F5E9")))
            elif status == "진행중":
                for c in range(self.table.columnCount()):
                    self.table.item(r, c).setBackground(QBrush(QColor("#FFFDE7")))

        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(self.current_sort_column, self.current_sort_order)

    def add_recall(self):
        dlg = RecallDialog(self, is_edit=False, settings=self.settings)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.load_recall_list()

    def edit_recall(self):
        row = self.table.currentRow()
        if row < 0: return
        case_id = self.table.item(row, 0).data(Qt.UserRole)
        
        dlg = RecallDialog(self, is_edit=True, case_id=case_id, settings=self.settings)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.load_recall_list()

    def delete_recall(self):
        row = self.table.currentRow()
        if row < 0: return
        case_id = self.table.item(row, 0).data(Qt.UserRole)
        case_no = self.table.item(row, 0).text()
        
        reply = QMessageBox.question(self, "삭제 확인", f"리콜 건 [{case_no}]을(를) 삭제하시겠습니까?\n관련된 모든 대상 제품 및 배송 정보가 삭제됩니다.", 
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                delete_recall_case(case_id)
                self.load_recall_list()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"삭제 중 오류 발생: {e}")


class RecallDialog(QtWidgets.QDialog):
    """리콜 등록/수정 다이얼로그 (탭 구조)"""
    def __init__(self, parent=None, is_edit=False, case_id=None, settings=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.case_id = case_id
        self.settings = settings
        self.setWindowTitle("리콜 등록" if not is_edit else "리콜 수정/상세")
        self.setMinimumSize(1000, 700)
        
        if self.settings:
            geom = self.settings.value("recall_dialog/geometry")
            if geom: self.restoreGeometry(geom)
        
        # 임시 관리용 데이터
        self.products_map = {} # {product_id: {info}}
        self.shipments_to_delete = []
        self.products_to_delete = [] # 삭제할 recall_items.id 추적
        
        self._loading = True  # UI 구축 및 데이터 로딩 중 컬럼 폭 저장 방지
        self.setup_ui()
        
        if is_edit:
            self.load_case_data()
        else:
            self.edt_case_no.setText(get_next_recall_no())
            self.edt_receipt_date.setText(datetime.now().strftime('%Y-%m-%d'))
        
        if self.settings:
            self.restore_column_widths()
        
        self._loading = False

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        
        # 1. 기본 정보 탭
        tab1 = QtWidgets.QWidget()
        self.setup_basic_tab(tab1)
        self.tabs.addTab(tab1, "기본 정보")
        
        # 2. 분석 및 대책 탭
        tab2 = QtWidgets.QWidget()
        self.setup_analysis_tab(tab2)
        self.tabs.addTab(tab2, "분석 및 대책")
        
        # 3. 대상 제품 탭
        tab3 = QtWidgets.QWidget()
        self.setup_products_tab(tab3)
        self.tabs.addTab(tab3, "대상 제품")
        
        # 4. 배송비용 탭
        tab4 = QtWidgets.QWidget()
        self.setup_shipments_tab(tab4)
        self.tabs.addTab(tab4, "배송비용")
        
        layout.addWidget(self.tabs)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        # 검색창에서 엔터 시 다이얼로그가 닫히지 않도록 기본 버튼 설정 해제
        # QDialog에서 모든 QPushButton은 기본적으로 autoDefault가 True일 수 있으므로 확실히 끔
        for btn in buttons.buttons():
            btn.setAutoDefault(False)
            btn.setDefault(False)
            
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def setup_basic_tab(self, widget):
        layout = QFormLayout(widget)
        self.edt_case_no = QtWidgets.QLineEdit()
        self.edt_case_no.setPlaceholderText("RC-YYMMDD-XXX")
        self.edt_title = QtWidgets.QLineEdit()
        self.edt_receipt_date = QtWidgets.QLineEdit()
        self.edt_report_no = QtWidgets.QLineEdit()
        self.cmb_status = QtWidgets.QComboBox()
        self.cmb_status.addItems(["접수", "진행중", "완료"])
        self.txt_defect = QPlainTextEdit()
        self.txt_notes = QPlainTextEdit()
        
        layout.addRow("리콜번호:", self.edt_case_no)
        layout.addRow("제목:", self.edt_title)
        layout.addRow("접수일:", self.edt_receipt_date)
        layout.addRow("보고서 번호:", self.edt_report_no)
        layout.addRow("상태:", self.cmb_status)
        layout.addRow("불량 증상:", self.txt_defect)
        layout.addRow("비고:", self.txt_notes)

    def setup_analysis_tab(self, widget):
        layout = QVBoxLayout(widget)
        
        group1 = QGroupBox("원인 분석")
        form1 = QFormLayout(group1)
        self.txt_inv_cust = QPlainTextEdit()
        self.txt_inv_int = QPlainTextEdit()
        self.txt_root_occ = QPlainTextEdit()
        self.txt_root_out = QPlainTextEdit()
        form1.addRow("고객사 조사내용:", self.txt_inv_cust)
        form1.addRow("당사 조사내용:", self.txt_inv_int)
        form1.addRow("근본원인(발생):", self.txt_root_occ)
        form1.addRow("근본원인(유출):", self.txt_root_out)
        
        group2 = QGroupBox("조치 및 대책")
        form2 = QFormLayout(group2)
        self.txt_action = QPlainTextEdit()
        self.txt_prev_occ = QPlainTextEdit()
        self.txt_prev_out = QPlainTextEdit()
        form2.addRow("즉각 대응조치:", self.txt_action)
        form2.addRow("재발방지대책(발생):", self.txt_prev_occ)
        form2.addRow("재발방지대책(유출):", self.txt_prev_out)
        
        layout.addWidget(group1)
        layout.addWidget(group2)

    def setup_products_tab(self, widget):
        layout = QVBoxLayout(widget)
        
        # 상단 검색 및 추가
        search_layout = QHBoxLayout()
        self.edt_product_search = QtWidgets.QLineEdit()
        self.edt_product_search.setPlaceholderText("시리얼 번호(쉼표 또는 줄바꿈으로 구분)를 입력하고 엔터를 누르면 검색합니다...")
        self.edt_product_search.returnPressed.connect(self.search_and_add_product)
        
        btn_search = QPushButton("제품 검색/선택")
        btn_search.setAutoDefault(False)
        btn_search.setDefault(False)
        btn_search.clicked.connect(self.open_product_search)
        
        search_layout.addWidget(self.edt_product_search)
        search_layout.addWidget(btn_search)
        
        # 목록 테이블
        self.table_products = QTableWidget(0, 6)
        self.table_products.setHorizontalHeaderLabels(["S/N", "품목코드", "제품명", "상태", "수리완료일", "삭제"])
        self.table_products.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_products.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        
        layout.addLayout(search_layout)
        layout.addWidget(self.table_products)
        
        # 일괄 업데이트 영역
        batch_layout = QHBoxLayout()
        batch_layout.addWidget(QLabel("선택 제품 상태 일괄 변경:"))
        self.cmb_batch_status = QtWidgets.QComboBox()
        self.cmb_batch_status.addItems(["대기", "수리중", "완료", "자체처리"])
        btn_batch_apply = QPushButton("적용")
        btn_batch_apply.setAutoDefault(False)
        btn_batch_apply.setDefault(False)
        btn_batch_apply.clicked.connect(self.apply_batch_status)
        batch_layout.addWidget(self.cmb_batch_status)
        batch_layout.addWidget(btn_batch_apply)
        batch_layout.addStretch()
        
        layout.addLayout(batch_layout)

    def setup_shipments_tab(self, widget):
        layout = QVBoxLayout(widget)
        
        btn_add_s = QPushButton("배송 건 추가")
        btn_add_s.setAutoDefault(False)
        btn_add_s.setDefault(False)
        btn_add_s.clicked.connect(lambda: self.add_shipment_row())
        
        self.table_shipments = QTableWidget(0, 13)
        self.table_shipments.setHorizontalHeaderLabels(["구분", "날짜", "인보이스", "신고번호", "운송사", "운반비", "관세", "부가세", "담보금", "반환금", "입금일", "반환일", "삭제"])
        
        layout.addWidget(btn_add_s)
        layout.addWidget(self.table_shipments)
        
        # 컬럼 너비 변경 시 저장 연결
        self.table_products.horizontalHeader().sectionResized.connect(self.save_column_widths)
        self.table_shipments.horizontalHeader().sectionResized.connect(self.save_column_widths)
        
        # 합계 표시
        sum_layout = QHBoxLayout()
        self.lbl_import_sum = QLabel("수입 비용 합계: 0원")
        self.lbl_export_sum = QLabel("수출 비용 합계: 0원")
        sum_layout.addWidget(self.lbl_import_sum)
        sum_layout.addWidget(self.lbl_export_sum)
        sum_layout.addStretch()
        layout.addLayout(sum_layout)

    def load_case_data(self):
        data = get_recall_case_details(self.case_id)
        if not data: return
        
        info = data['info']
        # info는 tuple이므로 매핑 (id, case_no, title, receipt_date, report_no, defect, inv_cust, inv_int, root_occ, root_out, action, prev_occ, prev_out, status, notes, attachments, created, updated)
        # DB 컬럼 순서에 따라 매핑 필요.
        # id=0, case_no=1, title=2, receipt_date=3, quality_report_no=4, defect_symptom=5, 
        # investigation_customer=6, investigation_internal=7, root_cause_occurrence=8, root_cause_outflow=9,
        # immediate_action=10, prevention_occurrence=11, prevention_outflow=12, status=13, notes=14
        
        self.edt_case_no.setText(str(info[1] or ""))
        self.edt_title.setText(str(info[2] or ""))
        self.edt_receipt_date.setText(str(info[3] or ""))
        self.edt_report_no.setText(str(info[4] or ""))
        self.cmb_status.setCurrentText(str(info[13] or "접수"))
        self.txt_defect.setPlainText(str(info[5] or ""))
        self.txt_notes.setPlainText(str(info[14] or ""))
        
        self.txt_inv_cust.setPlainText(str(info[6] or ""))
        self.txt_inv_int.setPlainText(str(info[7] or ""))
        self.txt_root_occ.setPlainText(str(info[8] or ""))
        self.txt_root_out.setPlainText(str(info[9] or ""))
        self.txt_action.setPlainText(str(info[10] or ""))
        self.txt_prev_occ.setPlainText(str(info[11] or ""))
        self.txt_prev_out.setPlainText(str(info[12] or ""))
        
        # 제품 목록 채우기
        for row in data['items']:
            # 튜플을 딕셔너리로 변환
            id_val, p_id, part_no, p_name, sn, status, r_date, notes = row
            item_dict = {
                'id': id_val,
                'product_id': p_id,
                'part_no': part_no,
                'product_name': p_name,
                'serial_no': sn,
                'item_status': status,
                'repair_date': r_date,
                'notes': notes
            }
            self.add_product_row(item_dict)
            
        # 배송 목록 채우기
        for ship in data['shipments']:
            # ship 구조: (id, recall_case_id, shipment_type, shipment_date, invoice_no, decl_no, carrier, cost_shipping, cost_customs, cost_tax, deposit_date, ret_date, cost_refund, cost_deposit)
            # DB 컬럼 순서나 쿼리에 따라 다를 수 있으므로 인덱스 주의
            self.add_shipment_row(ship)
        
        self.update_total_costs()

    def open_product_search(self):
        initial_q = self.edt_product_search.text().strip()
        dlg = ProductSearchDialog(self, settings=self.settings, initial_query=initial_q)
        if dlg.exec_():
            selected_products = dlg.selected_products
            for p_id, p_info in selected_products.items():
                if p_id not in self.products_map:
                    item_data = {
                        'id': None,
                        'product_id': p_id,
                        'part_no': p_info['part_no'],
                        'product_name': p_info['product_name'],
                        'serial_no': p_info['serial_no'],
                        'item_status': '대기',
                        'repair_date': '',
                        'notes': ''
                    }
                    self.add_product_row(item_data)

    def search_and_add_product(self):
        print(f"[DEBUG] search_and_add_product called with text: {self.edt_product_search.text()}")
        text = self.edt_product_search.text().strip()
        if not text: return
        
        # 쉼표, 공백, 줄바꿈으로 분리
        serials = [s.strip() for s in text.replace(',', ' ').split() if s.strip()]
        
        found_any = False
        for sn in serials:
            # DB에서 시리얼로 제품 조회
            row = query_one("SELECT id, part_no, product_name, serial_no FROM products WHERE serial_no = ?", (sn,))
            if row:
                p_id = row[0]
                if p_id not in self.products_map:
                    item_data = {
                        'id': None, # recall_items.id
                        'product_id': p_id,
                        'part_no': row[1],
                        'product_name': row[2],
                        'serial_no': row[3],
                        'item_status': '대기',
                        'repair_date': '',
                        'notes': ''
                    }
                    self.add_product_row(item_data)
                    found_any = True
            else:
                print(f"시리얼 {sn} 제품을 찾을 수 없습니다.")
        
        if found_any:
            self.edt_product_search.clear()

    def add_product_row(self, item_data):
        p_id = item_data['product_id']
        self.products_map[p_id] = item_data
        
        row_idx = self.table_products.rowCount()
        self.table_products.insertRow(row_idx)
        
        item_sn = QTableWidgetItem(item_data['serial_no'])
        item_sn.setData(Qt.UserRole, p_id)
        
        self.table_products.setItem(row_idx, 0, item_sn)
        self.table_products.setItem(row_idx, 1, QTableWidgetItem(item_data['part_no']))
        self.table_products.setItem(row_idx, 2, QTableWidgetItem(item_data['product_name']))
        
        cmb = QtWidgets.QComboBox()
        cmb.addItems(["대기", "수리중", "완료", "자체처리"])
        cmb.setCurrentText(item_data['item_status'])
        self.table_products.setCellWidget(row_idx, 3, cmb)
        
        edt_date = QtWidgets.QLineEdit(item_data['repair_date'] or "")
        edt_date.setPlaceholderText("YYYY-MM-DD")
        self.table_products.setCellWidget(row_idx, 4, edt_date)

        # ✅ 상태를 '완료'로 변경 시 수리완료일 자동 입력 (사용자 요청)
        def on_status_changed(txt):
            if txt == "완료" and not edt_date.text():
                edt_date.setText(datetime.now().strftime('%Y-%m-%d'))
        cmb.currentTextChanged.connect(on_status_changed)
        
        btn_del = QPushButton("제거")
        btn_del.clicked.connect(lambda: self.remove_product_row(p_id))
        self.table_products.setCellWidget(row_idx, 5, btn_del)

    def remove_product_row(self, product_id):
        if product_id in self.products_map:
            item_data = self.products_map[product_id]
            if item_data.get('id'): # DB에 이미 존재하는 항목이면
                self.products_to_delete.append(item_data['id'])
            
            del self.products_map[product_id]
            # 테이블에서 해당 행 찾아서 삭제
            for r in range(self.table_products.rowCount()):
                if self.table_products.item(r, 0).data(Qt.UserRole) == product_id:
                    self.table_products.removeRow(r)
                    break

    def apply_batch_status(self):
        status = self.cmb_batch_status.currentText()
        today = datetime.now().strftime('%Y-%m-%d') if status == "완료" else ""
        
        for r in range(self.table_products.rowCount()):
            cmb = self.table_products.cellWidget(r, 3)
            if cmb: cmb.setCurrentText(status)
            if today:
                edt = self.table_products.cellWidget(r, 4)
                if edt and not edt.text(): edt.setText(today)

    def add_shipment_row(self, ship_data=None):
        row_idx = self.table_shipments.rowCount()
        self.table_shipments.insertRow(row_idx)
        
        # 구분 (IMPORT/EXPORT)
        cmb_type = QtWidgets.QComboBox()
        cmb_type.addItems(["IMPORT", "EXPORT"])
        if ship_data: cmb_type.setCurrentText(ship_data[2]) # shipment_type
        self.table_shipments.setCellWidget(row_idx, 0, cmb_type)
        
        # 날짜
        edt_date = QtWidgets.QLineEdit(ship_data[3] if ship_data else datetime.now().strftime('%Y-%m-%d'))
        self.table_shipments.setCellWidget(row_idx, 1, edt_date)
        
        # 인보이스
        edt_inv = QtWidgets.QLineEdit(ship_data[4] if ship_data else "")
        self.table_shipments.setCellWidget(row_idx, 2, edt_inv)
        
        # 신고번호
        edt_decl = QtWidgets.QLineEdit(ship_data[5] if ship_data else "")
        self.table_shipments.setCellWidget(row_idx, 3, edt_decl)
        
        # 운송사
        edt_carrier = QtWidgets.QLineEdit(ship_data[6] if ship_data else "")
        self.table_shipments.setCellWidget(row_idx, 4, edt_carrier)
        
        # 비용 필드들 (MoneyLineEdit 사용)
        def create_money_edit(val_cents):
            mle = MoneyLineEdit()
            mle.set_value_from_cents(val_cents or 0)
            mle.textChanged.connect(self.update_total_costs)
            return mle
            
        mle_ship = create_money_edit(ship_data[7] if ship_data else 0)
        mle_cust = create_money_edit(ship_data[8] if ship_data else 0)
        mle_tax = create_money_edit(ship_data[9] if ship_data else 0)
        mle_deposit = create_money_edit(ship_data[13] if ship_data and len(ship_data) > 13 else 0) # cost_deposit
        mle_refund = create_money_edit(ship_data[12] if ship_data and len(ship_data) > 12 else 0)
        
        self.table_shipments.setCellWidget(row_idx, 5, mle_ship)
        self.table_shipments.setCellWidget(row_idx, 6, mle_cust)
        self.table_shipments.setCellWidget(row_idx, 7, mle_tax)
        self.table_shipments.setCellWidget(row_idx, 8, mle_deposit)
        self.table_shipments.setCellWidget(row_idx, 9, mle_refund)
        
        # 담보금 입금일
        edt_deposit = QtWidgets.QLineEdit(ship_data[10] if ship_data and len(ship_data) > 10 and ship_data[10] else "")
        edt_deposit.setPlaceholderText("YYYY-MM-DD")
        self.table_shipments.setCellWidget(row_idx, 10, edt_deposit)
        
        # 담보금 반환일
        edt_deposit_ret = QtWidgets.QLineEdit(ship_data[11] if ship_data and len(ship_data) > 11 and ship_data[11] else "")
        edt_deposit_ret.setPlaceholderText("YYYY-MM-DD")
        self.table_shipments.setCellWidget(row_idx, 11, edt_deposit_ret)
        
        btn_del = QPushButton("삭제")
        s_id = ship_data[0] if ship_data else None
        btn_del.clicked.connect(lambda: self.remove_shipment_row(row_idx, s_id))
        self.table_shipments.setCellWidget(row_idx, 12, btn_del)
        
        # ID 저장용 (숨김 아이템)
        id_item = QTableWidgetItem()
        id_item.setData(Qt.UserRole, s_id)
        self.table_shipments.setItem(row_idx, 0, id_item)
        
        self.update_total_costs()

    def remove_shipment_row(self, row_idx, shipment_id):
        if shipment_id:
            self.shipments_to_delete.append(shipment_id)
        self.table_shipments.removeRow(row_idx)
        self.update_total_costs()

    def update_total_costs(self):
        imp_sum = 0
        exp_sum = 0
        for r in range(self.table_shipments.rowCount()):
            ship_type = self.table_shipments.cellWidget(r, 0).currentText()
            cost = 0
            # 운반비, 관세, 부가세, 담보금 더하고 반환금은 뺌
            for c in [5, 6, 7, 8]: # 8번이 담보금(cost_deposit)
                mle = self.table_shipments.cellWidget(r, c)
                if mle: cost += mle.get_value_cents()
            
            # 반환금 차감 (9번 컬럼)
            mle_refund = self.table_shipments.cellWidget(r, 9)
            if mle_refund:
                cost -= mle_refund.get_value_cents()
            
            if ship_type == "IMPORT": imp_sum += cost
            else: exp_sum += cost
            
        self.lbl_import_sum.setText(f"수입 비용 합계: {int(imp_sum/100):,}원")
        self.lbl_export_sum.setText(f"수출 비용 합계: {int(exp_sum/100):,}원")

    def save(self):
        case_no = self.edt_case_no.text().strip()
        if not case_no:
            QMessageBox.warning(self, "경고", "리콜번호는 필수입니다.")
            return
            
        case_data = {
            'case_no': case_no,
            'title': self.edt_title.text(),
            'receipt_date': self.edt_receipt_date.text(),
            'quality_report_no': self.edt_report_no.text(),
            'status': self.cmb_status.currentText(),
            'defect_symptom': self.txt_defect.toPlainText(),
            'notes': self.txt_notes.toPlainText(),
            'investigation_customer': self.txt_inv_cust.toPlainText(),
            'investigation_internal': self.txt_inv_int.toPlainText(),
            'root_cause_occurrence': self.txt_root_occ.toPlainText(),
            'root_cause_outflow': self.txt_root_out.toPlainText(),
            'immediate_action': self.txt_action.toPlainText(),
            'prevention_occurrence': self.txt_prev_occ.toPlainText(),
            'prevention_outflow': self.txt_prev_out.toPlainText(),
        }
        
        try:
            conn = get_conn()
            cur = conn.cursor()
            
            if self.is_edit:
                update_recall_case(self.case_id, case_data, external_cursor=cur)
                
                # 배송 삭제 처리
                for s_id in self.shipments_to_delete:
                    delete_recall_shipment(s_id, external_cursor=cur)
                
                # 제품 삭제 처리 (추가)
                for item_id in self.products_to_delete:
                    cur.execute("DELETE FROM recall_items WHERE id = ?", (item_id,))
            else:
                product_ids = list(self.products_map.keys())
                self.case_id = create_recall_case(case_data, product_ids)
                # create_recall_case는 내부적으로 트랜잭션을 관리하므로 여기서는 그대로 유지하거나 
                # 필요시 나중에 리팩토링할 수 있으나, 현재 Lock의 주범은 is_edit 시의 복합 작업임
                
            # 현재 테이블의 배송 정보 저장/업데이트
            for r in range(self.table_shipments.rowCount()):
                # 테이블 아이템에서 기존 ID 가져오기
                id_item = self.table_shipments.item(r, 0)
                ship_id = id_item.data(Qt.UserRole) if id_item else None
                
                s_data = {
                    'recall_case_id': self.case_id,
                    'shipment_type': self.table_shipments.cellWidget(r, 0).currentText(),
                    'shipment_date': self.table_shipments.cellWidget(r, 1).text().strip(),
                    'invoice_no': self.table_shipments.cellWidget(r, 2).text().strip(),
                    'declaration_no': self.table_shipments.cellWidget(r, 3).text().strip(),
                    'carrier': self.table_shipments.cellWidget(r, 4).text().strip(),
                    'cost_shipping': self.table_shipments.cellWidget(r, 5).get_value_cents(),
                    'cost_customs': self.table_shipments.cellWidget(r, 6).get_value_cents(),
                    'cost_tax': self.table_shipments.cellWidget(r, 7).get_value_cents(),
                    'cost_deposit': self.table_shipments.cellWidget(r, 8).get_value_cents(),
                    'cost_refund': self.table_shipments.cellWidget(r, 9).get_value_cents(),
                    'deposit_date': self.table_shipments.cellWidget(r, 10).text().strip(),
                    'deposit_return_date': self.table_shipments.cellWidget(r, 11).text().strip(),
                }
                add_or_update_recall_shipment(s_data, shipment_id=ship_id, external_cursor=cur)
                
            # 제품 정보 저장/업데이트 (INSERT OR REPLACE 사용)
            for r in range(self.table_products.rowCount()):
                p_id = self.table_products.item(r, 0).data(Qt.UserRole)
                status = self.table_products.cellWidget(r, 3).currentText()
                repair_date = self.table_products.cellWidget(r, 4).text()
                
                cur.execute("""
                    INSERT OR REPLACE INTO recall_items (recall_case_id, product_id, item_status, repair_date)
                    VALUES (?, ?, ?, ?)
                """, (self.case_id, p_id, status, repair_date))

                # ✅ [추가] 제품 상태에 따른 delivery_id 제어 (최소한의 기본 초기화만 수행)
                if status in ['대기', '수리중']:
                    # 리콜 진행 중인 제품은 delivery_id를 NULL로 만들어 출고 가능 목록에 나오게 함
                    cur.execute("UPDATE products SET delivery_id = NULL WHERE id = ?", (p_id,))
                elif status in ['완료', '자체처리']:
                    # 리콜 상황이 종료된 경우(완료/자체처리), 기존 납품 정보를 복원하여 재고 목록에서 다시 제외함
                    cur.execute("SELECT part_no, serial_no FROM products WHERE id = ?", (p_id,))
                    prod_info = cur.fetchone()
                    if prod_info:
                        pno, sn = prod_info
                        cur.execute("""
                            SELECT delivery_id FROM delivery_items 
                            WHERE item_code = ? AND serial_no = ? 
                            ORDER BY id DESC LIMIT 1
                        """, (pno, sn))
                        history = cur.fetchone()
                        if history:
                            cur.execute("UPDATE products SET delivery_id = ? WHERE id = ?", (history[0], p_id))
            
            conn.commit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()

    def save_column_widths(self):
        if not self.settings: return
        if getattr(self, '_loading', False): return
        # 다이얼로그가 보이지 않거나 최소화된 상태에서의 자동 저장은 무시
        if not self.isVisible(): return
        
        p_widths = [self.table_products.columnWidth(i) for i in range(self.table_products.columnCount())]
        s_widths = [self.table_shipments.columnWidth(i) for i in range(self.table_shipments.columnCount())]
        
        # 모든 너비가 0 또는 기본값(100)인 경우 비정상적인 상태로 보고 저장하지 않음 (선택 사항)
        if all(w == 0 or w == 100 for w in s_widths) and self.table_shipments.rowCount() > 0:
            return

        print(f"[DEBUG] save_column_widths (persisting): products={p_widths}, shipments={s_widths}")
        self.settings.setValue("recall_dialog/product_column_widths", p_widths)
        self.settings.setValue("recall_dialog/shipment_column_widths", s_widths)
        self.settings.sync()

    def restore_column_widths(self):
        if not self.settings: return
        p_widths = self.settings.value("recall_dialog/product_column_widths")
        print(f"[DEBUG] restore_column_widths: raw products={p_widths}")
        if p_widths:
            for col, w in enumerate(p_widths):
                if col < self.table_products.columnCount():
                    self.table_products.setColumnWidth(col, int(w))
        
        s_widths = self.settings.value("recall_dialog/shipment_column_widths")
        print(f"[DEBUG] restore_column_widths: raw shipments={s_widths}")
        if s_widths:
            for col, w in enumerate(s_widths):
                if col < self.table_shipments.columnCount():
                    self.table_shipments.setColumnWidth(col, int(w))

    def done(self, result):
        """accept/reject 모두에서 호출됨 — 다이얼로그 종료 시 설정 저장"""
        if self.settings:
            self.settings.setValue("recall_dialog/geometry", self.saveGeometry())
            # 강제로 한 번 더 저장
            self.save_column_widths()
            self.settings.sync()
        super().done(result)

    # closeEvent는 done()에서 이미 처리하므로 불필요하게 중복 저장될 수 있어 제거하거나 단순하게 유지
    def closeEvent(self, event):
        super().closeEvent(event)

    def keyPressEvent(self, event):
        # 입력창(QLineEdit 등)에서 엔터 키를 누를 때 다이얼로그가 자동 수락(accept)되는 것을 방지
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focus_widget = self.focusWidget()
            if isinstance(focus_widget, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
                # 엔터 키 이벤트를 여기서 차단 (QLineEdit의 returnPressed는 정상 작동함)
                event.accept()
                return
        super().keyPressEvent(event)


class ProductSearchDialog(QDialog):
    """제품 검색 및 선택 다이얼로그 (리콜 대상 추가용)"""
    def __init__(self, parent=None, settings=None, initial_query=""):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("제품 검색 및 선택")
        self.setMinimumSize(800, 600)
        
        if self.settings:
            geom = self.settings.value("product_search_dialog/geometry")
            if geom: self.restoreGeometry(geom)
            
        self.selected_products = {} # {id: {part_no, product_name, serial_no}}
        self.setup_ui()
        
        if initial_query:
            self.edt_search.setText(initial_query)
            self.search_products()
        
        if self.settings:
            self.restore_column_widths()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        search_layout = QHBoxLayout()
        self.edt_search = QtWidgets.QLineEdit()
        self.edt_search.setPlaceholderText("품목코드, 제품명, 또는 시리얼 번호 입력...")
        self.edt_search.returnPressed.connect(self.search_products)
        btn_search = QPushButton("검색")
        btn_search.clicked.connect(self.search_products)
        search_layout.addWidget(self.edt_search)
        search_layout.addWidget(btn_search)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["시리얼 번호", "품목코드", "제품명"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().sectionResized.connect(self.save_column_widths)
        layout.addWidget(self.table)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.on_accepted)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def search_products(self):
        query_text = self.edt_search.text().strip()
        if not query_text:
            return

        sql = """
            SELECT p.id, p.serial_no, p.part_no, p.product_name
            FROM products p
            WHERE p.serial_no LIKE ? OR p.part_no LIKE ? OR p.product_name LIKE ?
            LIMIT 100
        """
        pattern = f"%{query_text}%"
        try:
            results = query_all(sql, (pattern, pattern, pattern))
            self.table.setRowCount(0)
            for row in results:
                r_idx = self.table.rowCount()
                self.table.insertRow(r_idx)
                
                item_sn = QTableWidgetItem(row[1])
                item_sn.setData(Qt.UserRole, row[0]) # ID 저장
                self.table.setItem(r_idx, 0, item_sn)
                self.table.setItem(r_idx, 1, QTableWidgetItem(row[2]))
                self.table.setItem(r_idx, 2, QTableWidgetItem(row[3]))
        except Exception as e:
            QMessageBox.critical(self, "검색 오류", f"제품 검색 중 오류가 발생했습니다: {e}")

    def on_accepted(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "알림", "선택된 제품이 없습니다.")
            return

        for row_model in selected_rows:
            r = row_model.row()
            p_id = self.table.item(r, 0).data(Qt.UserRole)
            self.selected_products[p_id] = {
                'serial_no': self.table.item(r, 0).text(),
                'part_no': self.table.item(r, 1).text(),
                'product_name': self.table.item(r, 2).text()
            }
        self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focus_widget = self.focusWidget()
            if isinstance(focus_widget, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
                event.accept()
                return
        super().keyPressEvent(event)

    def save_column_widths(self):
        if not self.settings: return
        widths = [self.table.columnWidth(i) for i in range(self.table.columnCount())]
        self.settings.setValue("product_search_dialog/column_widths", widths)

    def restore_column_widths(self):
        if not self.settings: return
        widths = self.settings.value("product_search_dialog/column_widths")
        if widths:
            for col, w in enumerate(widths):
                if col < self.table.columnCount():
                    self.table.setColumnWidth(col, int(w))

    def closeEvent(self, event):
        if self.settings:
            self.settings.setValue("product_search_dialog/geometry", self.saveGeometry())
            self.save_column_widths()
        super().closeEvent(event)

