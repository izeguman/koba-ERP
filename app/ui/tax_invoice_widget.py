"""
세금계산서 관리 위젯
독립적인 세금계산서 관리 (여러 발주 포함 가능)
"""
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from datetime import datetime, timedelta
from ..db import (
    get_conn, format_money,
    get_all_tax_invoices, get_tax_invoice_detail, delete_tax_invoice
)
from .tax_invoice_item_dialog import TaxInvoiceItemDialog


class TaxInvoiceWidget(QtWidgets.QWidget):
    """세금계산서 관리 위젯"""
    
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings or QtCore.QSettings("KOBATECH", "ProductManager")
        self.setup_ui()
        self.restore_column_widths()
        self.load_data()
        
    def closeEvent(self, event):
        self.save_column_widths()
        super().closeEvent(event)
    
    def save_column_widths(self):
        widths = []
        for i in range(self.table.columnCount()):
            widths.append(self.table.columnWidth(i))
        self.settings.setValue("tax_invoice_widget/col_widths", widths)
    
    def restore_column_widths(self):
        val = self.settings.value("tax_invoice_widget/col_widths")
        if val and isinstance(val, (list, tuple)):
            for i in range(min(len(val), self.table.columnCount())):
                try:
                    w = int(val[i])
                    if w > 10:
                        self.table.setColumnWidth(i, w)
                except:
                    pass
    
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # 상단: 필터
        filter_layout = QtWidgets.QHBoxLayout()
        
        filter_layout.addWidget(QtWidgets.QLabel("기간:"))
        
        # 기본값: 최근 1년
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        self.start_date_edit = QtWidgets.QDateEdit()
        self.start_date_edit.setDate(QtCore.QDate(start_date.year, start_date.month, start_date.day))
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        
        self.end_date_edit = QtWidgets.QDateEdit()
        self.end_date_edit.setDate(QtCore.QDate(end_date.year, end_date.month, end_date.day))
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        
        btn_search = QtWidgets.QPushButton("검색")
        btn_search.clicked.connect(self.load_data)
        
        filter_layout.addWidget(self.start_date_edit)
        filter_layout.addWidget(QtWidgets.QLabel("~"))
        filter_layout.addWidget(self.end_date_edit)
        filter_layout.addWidget(btn_search)
        filter_layout.addStretch()
        
        layout.addLayout(filter_layout)
        
        # 중간: 테이블
        self.table = QtWidgets.QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "발행일", "사업자등록번호", "공급자", "대표자명", "공급가액", "세액", "총액", "품목수", "비고", "ID"
        ])
        self.table.setColumnHidden(9, True)  # ID 숨김
        
        # 컬럼 너비
        self.table.setColumnWidth(0, 90)   # 발행일
        self.table.setColumnWidth(1, 120)  # 사업자번호
        self.table.setColumnWidth(2, 150)  # 공급자
        self.table.setColumnWidth(3, 90)   # 대표자명
        self.table.setColumnWidth(4, 110)  # 공급가액
        self.table.setColumnWidth(5, 100)  # 세액
        self.table.setColumnWidth(6, 120)  # 총액
        self.table.setColumnWidth(7, 70)   # 품목수
        self.table.setColumnWidth(8, 200)  # 비고
        
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.doubleClicked.connect(self.edit_invoice)
        
        # 컬럼 너비 변경 시 자동 저장 연결
        self.table.horizontalHeader().sectionResized.connect(self.save_column_widths)
        
        layout.addWidget(self.table)
        
        # 하단: 버튼
        btn_layout = QtWidgets.QHBoxLayout()
        
        btn_add = QtWidgets.QPushButton("+ 세금계산서 등록")
        btn_add.clicked.connect(self.add_invoice)
        
        btn_edit = QtWidgets.QPushButton("수정")
        btn_edit.clicked.connect(self.edit_invoice)
        
        btn_view = QtWidgets.QPushButton("상세보기")
        btn_view.clicked.connect(self.view_invoice_details)
        
        btn_delete = QtWidgets.QPushButton("삭제")
        btn_delete.clicked.connect(self.delete_invoice)
        
        btn_suppliers = QtWidgets.QPushButton("공급자 관리")
        btn_suppliers.clicked.connect(self.open_supplier_manager)
        
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_view)
        btn_layout.addWidget(btn_delete)
        btn_layout.addSpacing(20)
        btn_layout.addWidget(btn_suppliers)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
    def load_data(self):
        """세금계산서 목록 로드"""
        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")
        
        invoices = get_all_tax_invoices(start_date, end_date)
        
        self.table.setRowCount(0)
        for invoice in invoices:
            # id(0), issue_date(1), biz_no(2), name(3), ceo_name(4), supply(5), tax(6), total(7), count(8), note(9)
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(invoice[1] or ""))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(invoice[2] or ""))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(invoice[3] or ""))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(invoice[4] or ""))
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{format_money(invoice[5])} 원"))
            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{format_money(invoice[6])} 원"))
            self.table.setItem(row, 6, QtWidgets.QTableWidgetItem(f"{format_money(invoice[7])} 원"))
            self.table.setItem(row, 7, QtWidgets.QTableWidgetItem(str(invoice[8])))
            self.table.setItem(row, 8, QtWidgets.QTableWidgetItem(invoice[9] or ""))
            
            # ID 저장
            id_item = QtWidgets.QTableWidgetItem(str(invoice[0]))
            id_item.setData(Qt.UserRole, invoice[0])
            self.table.setItem(row, 9, id_item)
            
    def show_context_menu(self, position):
        """컨텍스트 메뉴"""
        menu = QtWidgets.QMenu(self)
        
        add_action = menu.addAction("세금계산서 등록")
        add_action.triggered.connect(self.add_invoice)
        
        if self.table.currentRow() >= 0:
            menu.addSeparator()
            edit_action = menu.addAction("수정")
            edit_action.triggered.connect(self.edit_invoice)
            
            view_action = menu.addAction("상세보기")
            view_action.triggered.connect(self.view_invoice_details)
            
            delete_action = menu.addAction("삭제")
            delete_action.triggered.connect(self.delete_invoice)
        
        menu.exec(self.table.viewport().mapToGlobal(position))
        
    def add_invoice(self):
        """세금계산서 등록"""
        dialog = TaxInvoiceItemDialog(purchase_id=None, parent=self)
        if dialog.exec():
            self.load_data()
    
    def edit_invoice(self):
        """세금계산서 수정"""
        current_row = self.table.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "경고", "수정할 세금계산서를 선택해주세요.")
            return
        
        invoice_id = self.table.item(current_row, 9).data(Qt.UserRole)
        dialog = TaxInvoiceItemDialog(purchase_id=None, invoice_id=invoice_id, parent=self)
        if dialog.exec():
            self.load_data()
            
    def view_invoice_details(self):
        """세금계산서 상세보기"""
        current_row = self.table.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "경고", "세금계산서를 선택해주세요.")
            return
        
        invoice_id = self.table.item(current_row, 9).data(Qt.UserRole)
        detail = get_tax_invoice_detail(invoice_id)
        
        if not detail:
            QtWidgets.QMessageBox.warning(self, "오류", "세금계산서 정보를 찾을 수 없습니다.")
            return
        
        # 상세보기 다이얼로그
        dialog = TaxInvoiceDetailDialog(detail, self)
        dialog.exec()
        
    def delete_invoice(self):
        """세금계산서 삭제"""
        current_row = self.table.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "경고", "삭제할 세금계산서를 선택해주세요.")
            return
        
        invoice_id = self.table.item(current_row, 9).data(Qt.UserRole)
        
        reply = QtWidgets.QMessageBox.question(
            self, "확인",
            "정말로 이 세금계산서를 삭제하시겠습니까?\n(품목 및 발주 연결 정보도 함께 삭제됩니다)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                delete_tax_invoice(invoice_id)
                self.load_data()
                QtWidgets.QMessageBox.information(self, "완료", "세금계산서가 삭제되었습니다.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "오류", f"삭제 실패:\n{str(e)}")

    def open_supplier_manager(self):
        """공급자 관리 다이얼로그 열기"""
        from .supplier_editor_dialog import SupplierEditorDialog
        dialog = SupplierEditorDialog(self)
        dialog.exec()


class TaxInvoiceDetailDialog(QtWidgets.QDialog):
    """세금계산서 상세보기 다이얼로그"""
    
    def __init__(self, detail, parent=None):
        super().__init__(parent)
        self.detail = detail
        self.settings = QtCore.QSettings("KOBATECH", "ProductManager")
        self.items_table = None
        
        self.setWindowTitle("세금계산서 상세")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        
        self.setup_ui()
        self.restore_column_widths()
        
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # 기본 정보
        info_group = QtWidgets.QGroupBox("기본 정보")
        info_layout = QtWidgets.QFormLayout(info_group)
        
        info_layout.addRow("발행일:", QtWidgets.QLabel(self.detail['issue_date']))
        info_layout.addRow("공급자:", QtWidgets.QLabel(self.detail['supplier_name']))
        info_layout.addRow("총액:", QtWidgets.QLabel(f"{format_money(self.detail['total_amount'])} 원"))
        if self.detail['note']:
            info_layout.addRow("비고:", QtWidgets.QLabel(self.detail['note']))
        
        layout.addWidget(info_group)
        
        # 품목 목록
        items_label = QtWidgets.QLabel("📋 품목 내역")
        items_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #007bff;")
        layout.addWidget(items_label)
        
        self.items_table = QtWidgets.QTableWidget(len(self.detail['items']), 8)
        self.items_table.setHorizontalHeaderLabels([
            "품목", "규격", "수량", "단가", "공급가액", "세액", "발주번호", "비고"
        ])
        self.items_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        
        for row, item in enumerate(self.detail['items']):
            # id, item_name, spec, quantity, unit_price, supply_amount, tax_amount, purchase_id, purchase_no
            self.items_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item['item_name'] or ""))
            self.items_table.setItem(row, 1, QtWidgets.QTableWidgetItem(item.get('spec', "") or ""))
            self.items_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(item.get('quantity', 1))))
            self.items_table.setItem(row, 3, QtWidgets.QTableWidgetItem(format_money(item.get('unit_price', 0))))
            self.items_table.setItem(row, 4, QtWidgets.QTableWidgetItem(format_money(item['supply_amount'])))
            self.items_table.setItem(row, 5, QtWidgets.QTableWidgetItem(format_money(item['tax_amount'])))
            self.items_table.setItem(row, 6, QtWidgets.QTableWidgetItem(item.get('purchase_no', "-") or "-"))
            self.items_table.setItem(row, 7, QtWidgets.QTableWidgetItem(item.get('note', "") or ""))
        
        layout.addWidget(self.items_table)
        
        # 닫기 버튼
        btn_close = QtWidgets.QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
    
    def closeEvent(self, event):
        """다이얼로그 닫을 때 컬럼 폭 저장"""
        self.save_column_widths()
        super().closeEvent(event)
    
    def accept(self):
        """확인 버튼 클릭 시"""
        self.save_column_widths()
        super().accept()
    
    def reject(self):
        """취소 버튼 클릭 시"""
        self.save_column_widths()
        super().reject()
    
    def save_column_widths(self):
        """품목 테이블 컬럼 폭 저장"""
        if self.items_table:
            widths = []
            for i in range(self.items_table.columnCount()):
                widths.append(self.items_table.columnWidth(i))
            self.settings.setValue("tax_invoice_detail_dialog/items_col_widths", widths)
    
    def restore_column_widths(self):
        """품목 테이블 컬럼 폭 복원"""
        if self.items_table:
            val = self.settings.value("tax_invoice_detail_dialog/items_col_widths")
            if val and isinstance(val, (list, tuple)):
                for i in range(min(len(val), self.items_table.columnCount())):
                    try:
                        w = int(val[i])
                        if w > 10:
                            self.items_table.setColumnWidth(i, w)
                    except:
                        pass
            else:
                # 저장된 폭이 없으면 기본값으로 내용에 맞춤
                self.items_table.resizeColumnsToContents()
