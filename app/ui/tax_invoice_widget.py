"""
세금계산서 관리 위젯
독립적인 세금계산서 관리 (지불 현황 및 상세 조회 강화 버전)
"""
from PySide6 import QtWidgets, QtCore, QtGui
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
        
        # 중간: 테이블 (컬럼 10개 -> 11개로 확장)
        self.table = QtWidgets.QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "발행일", "사업자등록번호", "공급자", "대표자명", "공급가액", "세액", "총액", "지불상태", "품목수", "비고", "ID"
        ])
        self.table.setColumnHidden(10, True)  # ID 숨김
        
        # 컬럼 너비 설정
        self.table.setColumnWidth(0, 90)   # 발행일
        self.table.setColumnWidth(1, 120)  # 사업자번호
        self.table.setColumnWidth(2, 150)  # 공급자
        self.table.setColumnWidth(3, 90)   # 대표자명
        self.table.setColumnWidth(4, 110)  # 공급가액
        self.table.setColumnWidth(5, 100)  # 세액
        self.table.setColumnWidth(6, 120)  # 총액
        self.table.setColumnWidth(7, 100)  # 지불상태 (NEW)
        self.table.setColumnWidth(8, 70)   # 품목수
        self.table.setColumnWidth(9, 200)  # 비고
        
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.doubleClicked.connect(self.view_invoice_details) # 더블클릭 시 바로 상세 보기
        
        self.table.horizontalHeader().sectionResized.connect(self.save_column_widths)
        
        layout.addWidget(self.table)
        
        # 하단: 버튼
        btn_layout = QtWidgets.QHBoxLayout()
        
        btn_add = QtWidgets.QPushButton("+ 세금계산서 등록")
        btn_add.clicked.connect(self.add_invoice)
        
        btn_view = QtWidgets.QPushButton("🔍 상세보기")
        btn_view.clicked.connect(self.view_invoice_details)
        
        btn_edit = QtWidgets.QPushButton("수정")
        btn_edit.clicked.connect(self.edit_invoice)
        
        btn_delete = QtWidgets.QPushButton("삭제")
        btn_delete.clicked.connect(self.delete_invoice)
        
        btn_suppliers = QtWidgets.QPushButton("공급자 관리")
        btn_suppliers.clicked.connect(self.open_supplier_manager)
        
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_view)
        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_delete)
        btn_layout.addSpacing(20)
        btn_layout.addWidget(btn_suppliers)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
    def load_data(self):
        """세금계산서 목록 로드 (지불 상태 포함)"""
        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")
        
        invoices = get_all_tax_invoices(start_date, end_date)
        
        self.table.setRowCount(0)
        for invoice in invoices:
            # id(0), issue_date(1), biz_no(2), name(3), ceo_name(4), supply(5), tax(6), total(7), count(8), note(9), paid_amount(10)
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            total_amt = invoice[7] or 0
            paid_amt = invoice[10] or 0
            
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(invoice[1] or ""))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(invoice[2] or ""))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(invoice[3] or ""))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(invoice[4] or ""))
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{format_money(invoice[5])} 원"))
            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{format_money(invoice[6])} 원"))
            
            # 총액
            total_item = QtWidgets.QTableWidgetItem(f"{format_money(total_amt)} 원")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 6, total_item)
            
            # 지불상태 결정
            if paid_amt <= 0:
                status = "미지불"
                color = "#dc3545" # Red
            elif paid_amt >= total_amt:
                status = "지불완료"
                color = "#2E7D32" # Green
            else:
                status = f"부분지불"
                color = "#EF6C00" # Orange
            
            status_item = QtWidgets.QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(QtGui.QColor(color))
            self.table.setItem(row, 7, status_item)
            
            self.table.setItem(row, 8, QtWidgets.QTableWidgetItem(str(invoice[8])))
            self.table.setItem(row, 9, QtWidgets.QTableWidgetItem(invoice[9] or ""))
            
            # ID 저장
            id_item = QtWidgets.QTableWidgetItem(str(invoice[0]))
            id_item.setData(Qt.UserRole, invoice[0])
            self.table.setItem(row, 10, id_item)
            
    def show_context_menu(self, position):
        """컨텍스트 메뉴"""
        menu = QtWidgets.QMenu(self)
        
        if self.table.currentRow() >= 0:
            view_action = menu.addAction("🔍 상세보기")
            view_action.triggered.connect(self.view_invoice_details)
            menu.addSeparator()
            
            edit_action = menu.addAction("수정")
            edit_action.triggered.connect(self.edit_invoice)
            
            delete_action = menu.addAction("삭제")
            delete_action.triggered.connect(self.delete_invoice)
            menu.addSeparator()

        add_action = menu.addAction("세금계산서 등록")
        add_action.triggered.connect(self.add_invoice)
        
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
        
        invoice_id = self.table.item(current_row, 10).data(Qt.UserRole)
        dialog = TaxInvoiceItemDialog(purchase_id=None, invoice_id=invoice_id, parent=self)
        if dialog.exec():
            self.load_data()
            
    def view_invoice_details(self):
        """세금계산서 상세보기 (고도화된 다이얼로그)"""
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        
        invoice_id = self.table.item(current_row, 10).data(Qt.UserRole)
        detail = get_tax_invoice_detail(invoice_id)
        
        if not detail:
            QtWidgets.QMessageBox.warning(self, "오류", "세금계산서 정보를 찾을 수 없습니다.")
            return
        
        # 상세보기 다이얼로그
        dialog = TaxInvoiceDetailDialog(detail, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_data() # 지불 등이 이루어졌을 수 있으므로 갱신
        
    def delete_invoice(self):
        """세금계산서 삭제"""
        current_row = self.table.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "경고", "삭제할 세금계산서를 선택해주세요.")
            return
        
        invoice_id = self.table.item(current_row, 10).data(Qt.UserRole)
        
        reply = QtWidgets.QMessageBox.question(
            self, "확인",
            "정말로 이 세금계산서를 삭제하시겠습니까?\n(품목 및 발주 연결 정보도 함께 삭제됩니다)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                delete_tax_invoice(invoice_id)
                self.load_data()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "오류", f"삭제 실패:\n{str(e)}")

    def open_supplier_manager(self):
        """공급자 관리 다이얼로그 열기"""
        from .supplier_editor_dialog import SupplierEditorDialog
        dialog = SupplierEditorDialog(self)
        dialog.exec()


class TaxInvoiceDetailDialog(QtWidgets.QDialog):
    """세금계산서 상세보기 다이얼로그 (고도화 버전)"""
    
    def __init__(self, detail, parent=None):
        super().__init__(parent)
        self.detail = detail
        self.settings = QtCore.QSettings("KOBATECH", "ProductManager")
        
        self.setWindowTitle(f"세금계산서 상세 - {self.detail['supplier_name']} ({self.detail['issue_date']})")
        self.setMinimumWidth(900)
        self.setMinimumHeight(700)
        
        self.setup_ui()
        self.restore_column_widths()
        
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # --- 1. 상단 정보 요약 섹션 ---
        header_layout = QtWidgets.QHBoxLayout()
        
        basic_group = QtWidgets.QGroupBox("📄 기본 정보")
        basic_form = QtWidgets.QFormLayout(basic_group)
        basic_form.addRow("발행일:", QtWidgets.QLabel(f"<b>{self.detail['issue_date']}</b>"))
        basic_form.addRow("공급자:", QtWidgets.QLabel(f"<b>{self.detail['supplier_name']}</b>"))
        basic_form.addRow("승인번호:", QtWidgets.QLabel(self.detail.get('approval_number') or "-"))
        if self.detail.get('note'):
            basic_form.addRow("계산서 비고:", QtWidgets.QLabel(self.detail['note']))
        header_layout.addWidget(basic_group, 1)
        
        # 💰 지불 요약 정보
        total_amt = self.detail['total_amount'] or 0
        payments = self.detail.get('payments', [])
        paid_amt = sum(p['amount'] for p in payments)
        balance = total_amt - paid_amt
        
        payment_summary_group = QtWidgets.QGroupBox("💰 지불 현황")
        payment_form = QtWidgets.QFormLayout(payment_summary_group)
        
        lbl_total = QtWidgets.QLabel(f"{format_money(total_amt)} 원")
        lbl_total.setStyleSheet("font-weight: bold;")
        
        lbl_paid = QtWidgets.QLabel(f"{format_money(paid_amt)} 원")
        lbl_paid.setStyleSheet("color: #2E7D32; font-weight: bold;")
        
        lbl_balance = QtWidgets.QLabel(f"{format_money(balance)} 원")
        lbl_balance.setStyleSheet(f"color: {'#dc3545' if balance > 0 else '#2E7D32'}; font-size: 14px; font-weight: bold;")
        
        payment_form.addRow("계산서 총액:", lbl_total)
        payment_form.addRow("총 지불 완료액:", lbl_paid)
        payment_form.addRow("미지불 잔액:", lbl_balance)
        
        status_text = "미발행" if total_amt == 0 else ("완납" if balance <= 0 else "미납/부분지불")
        status_color = "#2E7D32" if balance <= 0 else "#dc3545"
        lbl_status = QtWidgets.QLabel(status_text)
        lbl_status.setStyleSheet(f"color: white; background-color: {status_color}; padding: 3px 10px; border-radius: 5px; font-weight: bold;")
        lbl_status.setAlignment(Qt.AlignCenter)
        payment_form.addRow("정산 상태:", lbl_status)
        
        header_layout.addWidget(payment_summary_group, 1)
        layout.addLayout(header_layout)
        
        # --- 2. 품목 목록 섹션 ---
        layout.addSpacing(10)
        items_label = QtWidgets.QLabel("📋 포함 품목 명세")
        items_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #0d6efd;")
        layout.addWidget(items_label)
        
        self.items_table = QtWidgets.QTableWidget(len(self.detail['items']), 9)
        self.items_table.setHorizontalHeaderLabels([
            "품목", "규격", "수량", "단가", "공급가액", "세액", "연결 발주서", "지불상태", "비고"
        ])
        self.items_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.items_table.setAlternatingRowColors(True)
        self.items_table.verticalHeader().setVisible(False)
        
        for row, item in enumerate(self.detail['items']):
            self.items_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item['item_name'] or ""))
            self.items_table.setItem(row, 1, QtWidgets.QTableWidgetItem(item.get('spec', "") or ""))
            
            qty_item = QtWidgets.QTableWidgetItem(f"{item.get('quantity', 0):,}")
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.items_table.setItem(row, 2, qty_item)
            
            price_item = QtWidgets.QTableWidgetItem(format_money(item.get('unit_price', 0)))
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.items_table.setItem(row, 3, price_item)
            
            supply_item = QtWidgets.QTableWidgetItem(format_money(item['supply_amount']))
            supply_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.items_table.setItem(row, 4, supply_item)
            
            tax_item = QtWidgets.QTableWidgetItem(format_money(item['tax_amount']))
            tax_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.items_table.setItem(row, 5, tax_item)
            
            self.items_table.setItem(row, 6, QtWidgets.QTableWidgetItem(item.get('purchase_no', "-") or "-"))
            
            # --- 지불 상태 컬럼 (NEW) ---
            po_status = item.get('po_status', '-')
            status_item = QtWidgets.QTableWidgetItem(po_status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if po_status == '지불완료':
                status_item.setForeground(QtGui.QColor("#2E7D32"))
            elif po_status == '부분지불':
                status_item.setForeground(QtGui.QColor("#EF6C00"))
            elif po_status == '미지불':
                status_item.setForeground(QtGui.QColor("#dc3545"))
            self.items_table.setItem(row, 7, status_item)
            
            self.items_table.setItem(row, 8, QtWidgets.QTableWidgetItem(item.get('note', "") or ""))
        
        layout.addWidget(self.items_table, 3)
        
        # --- 3. 지불 내역 히스토리 섹션 ---
        layout.addSpacing(10)
        pay_history_label = QtWidgets.QLabel("✔️ 지불 내역 히스토리")
        pay_history_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #198754;")
        layout.addWidget(pay_history_label)
        
        self.pay_table = QtWidgets.QTableWidget(len(payments), 4)
        self.pay_table.setHorizontalHeaderLabels(["지불일", "지불수단", "지불금액(원)", "비고"])
        self.pay_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.pay_table.setAlternatingRowColors(True)
        self.pay_table.verticalHeader().setVisible(False)
        self.pay_table.horizontalHeader().setStretchLastSection(True)
        
        for row, p in enumerate(payments):
            self.pay_table.setItem(row, 0, QtWidgets.QTableWidgetItem(p['payment_date']))
            self.pay_table.setItem(row, 1, QtWidgets.QTableWidgetItem(p['payment_method']))
            
            amt_item = QtWidgets.QTableWidgetItem(format_money(p['amount']))
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amt_item.setForeground(QtGui.QColor("#2E7D32"))
            self.pay_table.setItem(row, 2, amt_item)
            
            self.pay_table.setItem(row, 3, QtWidgets.QTableWidgetItem(p.get('note', "") or ""))
            
        if not payments:
            self.pay_table.setRowCount(1)
            self.pay_table.setItem(0, 0, QtWidgets.QTableWidgetItem("등록된 지불 내역이 없습니다."))
            self.pay_table.setSpan(0, 0, 1, 4)
            
        layout.addWidget(self.pay_table, 2)
        
        # --- 하단 버튼 ---
        btn_layout = QtWidgets.QHBoxLayout()
        
        btn_print = QtWidgets.QPushButton("인쇄 (준비중)")
        btn_print.setEnabled(False)
        
        btn_close = QtWidgets.QPushButton("닫기")
        btn_close.setMinimumWidth(100)
        btn_close.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_print)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
    
    def save_column_widths(self):
        """테이블 컬럼 폭 저장"""
        if self.items_table:
            widths = [self.items_table.columnWidth(i) for i in range(self.items_table.columnCount())]
            self.settings.setValue("tax_invoice_detail_dialog/items_widths", widths)
        if hasattr(self, 'pay_table'):
            widths = [self.pay_table.columnWidth(i) for i in range(self.pay_table.columnCount())]
            self.settings.setValue("tax_invoice_detail_dialog/pay_widths", widths)
    
    def restore_column_widths(self):
        """테이블 컬럼 폭 복원"""
        if self.items_table:
            val = self.settings.value("tax_invoice_detail_dialog/items_widths")
            if val:
                for i, w in enumerate(val):
                    if i < self.items_table.columnCount(): self.items_table.setColumnWidth(i, int(w))
            else:
                self.items_table.resizeColumnsToContents()
                
        if hasattr(self, 'pay_table'):
            val = self.settings.value("tax_invoice_detail_dialog/pay_widths")
            if val:
                for i, w in enumerate(val):
                    if i < self.pay_table.columnCount(): self.pay_table.setColumnWidth(i, int(w))
            else:
                self.pay_table.resizeColumnsToContents()

    def accept(self):
        self.save_column_widths()
        super().accept()

    def reject(self):
        self.save_column_widths()
        super().reject()
