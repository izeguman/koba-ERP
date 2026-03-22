# app/ui/tax_invoice_management_dialog.py
"""
세금계산서 관리 전용 다이얼로그
발주에 매핑된 세금계산서 내역만 관리합니다.
"""
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from .tax_invoice_item_dialog import TaxInvoiceItemDialog
from ..db import (
    get_conn, format_money,
    get_tax_invoices_for_purchase,
    get_purchase_payment_summary
)


class TaxInvoiceManagementDialog(QtWidgets.QDialog):
    """세금계산서 관리 전용 다이얼로그"""
    
    def __init__(self, purchase_id, parent=None):
        super().__init__(parent)
        self.purchase_id = purchase_id
        self.settings = QtCore.QSettings("KOBATECH", "ProductManager")
        self.setWindowTitle("세금계산서 관리")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        
        self.setup_ui()
        self.load_data()

    def closeEvent(self, event):
        print("[DEBUG] closeEvent 호출됨")
        self.save_column_widths()
        super().closeEvent(event)
    
    def accept(self):
        print("[DEBUG] accept 호출됨")
        self.save_column_widths()
        super().accept()
    
    def reject(self):
        print("[DEBUG] reject 호출됨")
        self.save_column_widths()
        super().reject()

    def save_column_widths(self):
        widths = []
        for i in range(self.invoice_table.columnCount()):
            widths.append(self.invoice_table.columnWidth(i))
        self.settings.setValue("tax_invoice_management_dialog/col_widths", widths)
        print(f"[DEBUG] 세금계산서 관리 - 컬럼 폭 저장: {widths}")

    def restore_column_widths(self):
        val = self.settings.value("tax_invoice_management_dialog/col_widths")
        print(f"[DEBUG] 세금계산서 관리 - 저장된 컬럼 폭: {val}")
        
        if val and isinstance(val, (list, tuple)):
            for i in range(min(len(val), self.invoice_table.columnCount())):
                try:
                    w = int(val[i])
                    if w > 10:
                        self.invoice_table.setColumnWidth(i, w)
                        print(f"[DEBUG] 컬럼 {i} 폭 복원: {w}")
                except Exception as e:
                    print(f"[DEBUG] 컬럼 {i} 폭 복원 실패: {e}")
        else:
            print("[DEBUG] 저장된 컬럼 폭 없음 - 기본 폭 설정")
            # 기본 컬럼 폭 설정
            default_widths = [100, 150, 120, 120, 200, 150, 0]
            for i, w in enumerate(default_widths):
                if i < self.invoice_table.columnCount():
                    self.invoice_table.setColumnWidth(i, w)

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # 요약 정보
        group_summary = QtWidgets.QGroupBox("📄 세금계산서 요약")
        form_summary = QtWidgets.QFormLayout(group_summary)
        
        self.lbl_po_amount = QtWidgets.QLabel("-")
        self.lbl_po_amount_with_tax = QtWidgets.QLabel("-")
        self.lbl_invoiced = QtWidgets.QLabel("-")
        self.lbl_invoiced_supply = QtWidgets.QLabel("-")
        
        form_summary.addRow("발주 총액 (부가세 별도):", self.lbl_po_amount)
        form_summary.addRow("발주 총액 (부가세 포함):", self.lbl_po_amount_with_tax)
        form_summary.addRow("세금계산서(청구) 합계 (부가세 별도):", self.lbl_invoiced_supply)
        form_summary.addRow("세금계산서(청구) 합계 (부가세 포함):", self.lbl_invoiced)
        
        layout.addWidget(group_summary)
        
        # 세금계산서 내역 테이블
        lbl_invoice = QtWidgets.QLabel("세금계산서(청구) 매핑 내역")
        lbl_invoice.setStyleSheet("font-size: 14px; font-weight: bold; color: #28a745;")
        layout.addWidget(lbl_invoice)
        
        self.invoice_table = QtWidgets.QTableWidget(0, 7)
        self.invoice_table.setHorizontalHeaderLabels(["발행일", "공급자", "이 발주 매핑액", "총액", "승인번호", "비고", "InvoiceID"])
        self.invoice_table.setColumnHidden(6, True)  # InvoiceID 숨김
        
        # [FIX] Stretch 모드 제거 - 컬럼 폭 저장을 위해 Interactive 모드 사용
        header = self.invoice_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(False)  # 마지막 섹션도 늘리지 않음
        
        self.invoice_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.invoice_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.invoice_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.invoice_table)
        
        # 컬럼 폭 복원 (테이블 생성 직후)
        self.restore_column_widths()
        
        # 버튼
        btn_layout = QtWidgets.QHBoxLayout()
        
        btn_add_invoice = QtWidgets.QPushButton("세금계산서 등록/연결")
        btn_add_invoice.clicked.connect(self.open_invoice_dialog)
        
        btn_close = QtWidgets.QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        
        btn_layout.addWidget(btn_add_invoice)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        
        layout.addLayout(btn_layout)

    def load_data(self):
        self.load_invoices()
        self.update_summary()

    def load_invoices(self):
        """세금계산서 내역 로드"""
        try:
            data = get_tax_invoices_for_purchase(self.purchase_id)
            self.invoice_table.setRowCount(0)
            for row in data:
                # id, issue, supplier, total, mapped, note
                r = self.invoice_table.rowCount()
                self.invoice_table.insertRow(r)
                self.invoice_table.setItem(r, 0, QtWidgets.QTableWidgetItem(row[1]))
                self.invoice_table.setItem(r, 1, QtWidgets.QTableWidgetItem(row[2]))
                self.invoice_table.setItem(r, 2, QtWidgets.QTableWidgetItem(format_money(row[4])))  # Mapped
                self.invoice_table.setItem(r, 3, QtWidgets.QTableWidgetItem(format_money(row[3])))  # Total
                
                # 승인번호 조회
                approval_number = self.get_approval_number(row[0])
                self.invoice_table.setItem(r, 4, QtWidgets.QTableWidgetItem(approval_number or "-"))
                
                self.invoice_table.setItem(r, 5, QtWidgets.QTableWidgetItem(row[5]))  # Note
                self.invoice_table.setItem(r, 6, QtWidgets.QTableWidgetItem(str(row[0])))  # Invoice ID
        except Exception as e:
            print(f"Invoice load error: {e}")
    
    def get_approval_number(self, invoice_id):
        """세금계산서 승인번호 조회"""
        try:
            conn = get_conn()
            try:
                cur = conn.cursor()
                cur.execute("SELECT approval_number FROM tax_invoices WHERE id = ?", (invoice_id,))
                row = cur.fetchone()
                return row[0] if row else None
            finally:
                conn.close()
        except:
            return None

    def open_invoice_dialog(self):
        """세금계산서 등록/연결 다이얼로그 열기"""
        dlg = TaxInvoiceItemDialog(purchase_id=self.purchase_id, parent=self)
        if dlg.exec():
            self.load_data()
            
            # 부모 위젯에 변경 알림
            if self.parent():
                if hasattr(self.parent(), 'load_purchase_list'):
                    self.parent().load_purchase_list()

    def update_summary(self):
        """요약 정보 업데이트"""
        summary = get_purchase_payment_summary(self.purchase_id)
        
        # 발주 총액 (부가세 별도)
        self.lbl_po_amount.setText(f"{format_money(summary['po_amount'])} 원")
        
        # 발주 총액 (부가세 포함)
        self.lbl_po_amount_with_tax.setText(f"{format_money(summary['po_amount_with_tax'])} 원")
        
        # 세금계산서 합계 (부가세 포함)
        self.lbl_invoiced.setText(f"{format_money(summary['total_invoiced'])} 원")
        
        # 세금계산서 합계 (부가세 별도) - 부가세 포함 금액을 1.1로 나눔
        invoiced_supply = summary['total_invoiced'] / 1.1 if summary['total_invoiced'] > 0 else 0
        self.lbl_invoiced_supply.setText(f"{format_money(invoiced_supply)} 원")
