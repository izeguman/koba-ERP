# app/ui/payment_management_dialog.py
"""
결제 관리 전용 다이얼로그 (개선 버전)
발주에 대한 실제 지출 내역을 관리하며, 세금계산서 매핑 금액을 자동으로 표시합니다.
"""
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from datetime import datetime
from .money_lineedit import MoneyLineEdit
from ..db import (
    get_conn, format_money, 
    add_payment, get_payments_for_purchase, delete_payment, update_payment,
    get_purchase_payment_summary, get_tax_invoices_for_purchase
)


class PaymentManagementDialog(QtWidgets.QDialog):
    """결제(지출) 관리 전용 다이얼로그"""
    
    def __init__(self, purchase_id, parent=None):
        super().__init__(parent)
        self.purchase_id = purchase_id
        self.settings = QtCore.QSettings("KOBATECH", "ProductManager")
        self.setWindowTitle("결제 관리")
        self.setMinimumWidth(900)
        self.setMinimumHeight(700)
        
        self.setup_ui()
        self.restore_column_widths()
        self.load_data()

    def closeEvent(self, event):
        print("[DEBUG] 결제관리 - closeEvent 호출됨")
        self.save_column_widths()
        super().closeEvent(event)
    
    def accept(self):
        print("[DEBUG] 결제관리 - accept 호출됨")
        self.save_column_widths()
        super().accept()
    
    def reject(self):
        print("[DEBUG] 결제관리 - reject 호출됨")
        self.save_column_widths()
        super().reject()

    def save_column_widths(self):
        # 결제 테이블 컬럼 폭 저장
        widths = []
        for i in range(self.payment_table.columnCount()):
            widths.append(self.payment_table.columnWidth(i))
        self.settings.setValue("payment_management_dialog/payment_col_widths", widths)
        
        # 세금계산서 테이블 컬럼 폭 저장
        invoice_widths = []
        for i in range(self.invoice_table.columnCount()):
            invoice_widths.append(self.invoice_table.columnWidth(i))
        self.settings.setValue("payment_management_dialog/invoice_col_widths", invoice_widths)

    def restore_column_widths(self):
        # 결제 테이블 컬럼 폭 복원
        val = self.settings.value("payment_management_dialog/payment_col_widths")
        if val and isinstance(val, (list, tuple)):
            for i in range(min(len(val), self.payment_table.columnCount())):
                try:
                    w = int(val[i])
                    if w > 10:
                        self.payment_table.setColumnWidth(i, w)
                except:
                    pass
        
        # 세금계산서 테이블 컬럼 폭 복원
        invoice_val = self.settings.value("payment_management_dialog/invoice_col_widths")
        if invoice_val and isinstance(invoice_val, (list, tuple)):
            for i in range(min(len(invoice_val), self.invoice_table.columnCount())):
                try:
                    w = int(invoice_val[i])
                    if w > 10:
                        self.invoice_table.setColumnWidth(i, w)
                except:
                    pass

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # 요약 정보
        group_summary = QtWidgets.QGroupBox("💰 결제 요약")
        form_summary = QtWidgets.QFormLayout(group_summary)
        
        self.lbl_po_amount = QtWidgets.QLabel("-")
        self.lbl_po_amount_with_tax = QtWidgets.QLabel("-")
        self.lbl_paid = QtWidgets.QLabel("-")
        self.lbl_unpaid = QtWidgets.QLabel("-")
        self.lbl_progress = QtWidgets.QLabel("-")
        
        form_summary.addRow("발주 총액 (부가세 제외):", self.lbl_po_amount)
        form_summary.addRow("발주 총액 (부가세 포함):", self.lbl_po_amount_with_tax)
        form_summary.addRow("지불(지출) 합계:", self.lbl_paid)
        form_summary.addRow("미지급액:", self.lbl_unpaid)
        form_summary.addRow("진행률:", self.lbl_progress)
        
        layout.addWidget(group_summary)
        
        # [NEW] 세금계산서 매핑 금액 목록
        lbl_invoice = QtWidgets.QLabel("📄 세금계산서 매핑 금액 (결제 처리 대상)")
        lbl_invoice.setStyleSheet("font-size: 14px; font-weight: bold; color: #28a745;")
        layout.addWidget(lbl_invoice)
        
        self.invoice_table = QtWidgets.QTableWidget(0, 5)
        self.invoice_table.setHorizontalHeaderLabels(["발행일", "공급자", "매핑 금액", "승인번호", "InvoiceID"])
        self.invoice_table.setColumnHidden(4, True)  # InvoiceID hidden
        self.invoice_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.invoice_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.invoice_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.invoice_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.invoice_table.setMaximumHeight(150)
        layout.addWidget(self.invoice_table)
        
        # 세금계산서 금액으로 결제 추가 버튼
        btn_add_from_invoice = QtWidgets.QPushButton("↓ 선택한 세금계산서 금액으로 결제 추가")
        btn_add_from_invoice.setStyleSheet("padding: 8px; font-weight: bold; background-color: #28a745; color: white;")
        btn_add_from_invoice.clicked.connect(self.add_payment_from_invoice)
        layout.addWidget(btn_add_from_invoice)
        
        # 결제 내역 테이블
        lbl_payment = QtWidgets.QLabel("결제(지출) 내역")
        lbl_payment.setStyleSheet("font-size: 14px; font-weight: bold; color: #007bff;")
        layout.addWidget(lbl_payment)
        
        self.payment_table = QtWidgets.QTableWidget(0, 5)
        self.payment_table.setHorizontalHeaderLabels(["날짜", "구분", "금액", "비고", "ID"])
        self.payment_table.setColumnHidden(4, True)  # ID hidden
        self.payment_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.payment_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.payment_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.payment_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.payment_table.setStyleSheet("""
            QTableWidget {
                selection-background-color: #0078d7;
                selection-color: white;
            }
            QTableWidget::item:selected {
                background-color: #0078d7;
                color: white;
            }
        """)
        layout.addWidget(self.payment_table)
        
        # 결제 입력 폼
        form_layout = QtWidgets.QHBoxLayout()
        
        self.date_edit = QtWidgets.QDateEdit()
        self.date_edit.setDate(QtCore.QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumWidth(110)
        
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["계약금", "중도금", "잔금", "선지급", "기타"])
        self.type_combo.setMinimumWidth(120)
        self.type_combo.setView(QtWidgets.QListView())
        self.type_combo.setStyleSheet("""
            QComboBox {
                padding: 5px;
                background-color: white;
                color: black;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #ced4da;
                border-left-style: solid;
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                color: black;
                selection-background-color: #0078d7;
                selection-color: white;
                border: 1px solid #ced4da;
            }
        """)
        
        self.amount_edit = MoneyLineEdit()
        self.amount_edit.setPlaceholderText("금액")
        self.amount_edit.setMinimumWidth(120)
        
        self.note_edit = QtWidgets.QLineEdit()
        self.note_edit.setPlaceholderText("비고")
        
        btn_add = QtWidgets.QPushButton("추가")
        btn_add.setMinimumWidth(60)
        btn_add.clicked.connect(self.add_payment_record)
        
        form_layout.addWidget(self.date_edit)
        form_layout.addWidget(self.type_combo)
        form_layout.addWidget(self.amount_edit)
        form_layout.addWidget(self.note_edit)
        form_layout.addWidget(btn_add)
        
        layout.addLayout(form_layout)
        
        # 버튼
        btn_layout = QtWidgets.QHBoxLayout()
        
        btn_del = QtWidgets.QPushButton("선택 삭제")
        btn_del.clicked.connect(self.delete_payment_record)
        
        btn_close = QtWidgets.QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        
        btn_layout.addWidget(btn_del)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        
        layout.addLayout(btn_layout)

    def load_data(self):
        self.load_invoices()
        self.load_payments()
        self.update_summary()

    def load_invoices(self):
        """세금계산서 매핑 금액 로드"""
        try:
            data = get_tax_invoices_for_purchase(self.purchase_id)
            self.invoice_table.setRowCount(0)
            for row in data:
                # id, issue_date, supplier_name, total_amount, mapped_amount, note
                r = self.invoice_table.rowCount()
                self.invoice_table.insertRow(r)
                self.invoice_table.setItem(r, 0, QtWidgets.QTableWidgetItem(row[1]))
                self.invoice_table.setItem(r, 1, QtWidgets.QTableWidgetItem(row[2]))
                self.invoice_table.setItem(r, 2, QtWidgets.QTableWidgetItem(format_money(row[4])))  # Mapped amount
                
                # 승인번호 조회
                approval_number = self.get_approval_number(row[0])
                self.invoice_table.setItem(r, 3, QtWidgets.QTableWidgetItem(approval_number or "-"))
                self.invoice_table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(row[0])))  # Invoice ID
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

    def add_payment_from_invoice(self):
        """선택한 세금계산서 금액으로 결제 추가"""
        current_row = self.invoice_table.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "경고", "세금계산서를 선택해주세요.")
            return
        
        # 매핑 금액 가져오기
        amount_text = self.invoice_table.item(current_row, 2).text().replace(",", "").replace(" 원", "")
        amount = int(amount_text)
        
        # 금액 입력란에 자동 설정
        self.amount_edit.set_value(amount)
        
        # 비고에 세금계산서 정보 추가
        supplier = self.invoice_table.item(current_row, 1).text()
        issue_date = self.invoice_table.item(current_row, 0).text()
        approval = self.invoice_table.item(current_row, 3).text()
        
        note = f"{supplier} ({issue_date})"
        if approval and approval != "-":
            note += f" - {approval}"
        self.note_edit.setText(note)
        
        QtWidgets.QMessageBox.information(
            self, "안내", 
            f"금액이 자동으로 입력되었습니다: {format_money(amount)}원\n\n"
            "결제 구분과 날짜를 확인한 후 '추가' 버튼을 클릭하세요."
        )

    def load_payments(self):
        """결제 내역 로드"""
        data = get_payments_for_purchase(self.purchase_id)
        self.payment_table.setRowCount(0)
        for row in data:
            r = self.payment_table.rowCount()
            self.payment_table.insertRow(r)
            # id, date, amount, type, note
            self.payment_table.setItem(r, 0, QtWidgets.QTableWidgetItem(row[1]))
            self.payment_table.setItem(r, 1, QtWidgets.QTableWidgetItem(row[3]))
            self.payment_table.setItem(r, 2, QtWidgets.QTableWidgetItem(format_money(row[2])))
            self.payment_table.setItem(r, 3, QtWidgets.QTableWidgetItem(row[4]))
            self.payment_table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(row[0])))

    def add_payment_record(self):
        """결제 내역 추가"""
        try:
            date_str = self.date_edit.date().toString("yyyy-MM-dd")
            p_type = self.type_combo.currentText()
            amount = self.amount_edit.get_value()
            note = self.note_edit.text()
            
            if amount <= 0:
                QtWidgets.QMessageBox.warning(self, "경고", "금액을 입력해주세요.")
                return
                
            add_payment(self.purchase_id, date_str, amount, p_type, note)
            
            # 입력 초기화
            self.amount_edit.clear()
            self.note_edit.clear()
            
            self.load_data()  # 재로딩
            
            # 부모 위젯에 변경 알림 (발주 목록 갱신용)
            if self.parent():
                if hasattr(self.parent(), 'load_purchase_list'):
                    self.parent().load_purchase_list()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"결제 추가 중 오류: {e}")

    def delete_payment_record(self):
        """결제 내역 삭제"""
        current_row = self.payment_table.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "경고", "삭제할 항목을 선택해주세요.")
            return
            
        item_id = int(self.payment_table.item(current_row, 4).text())
        
        confirm = QtWidgets.QMessageBox.question(
            self, "확인", "정말로 삭제하시겠습니까?", 
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if confirm == QtWidgets.QMessageBox.Yes:
            delete_payment(item_id)
            self.load_data()
            
            # 부모 위젯에 변경 알림
            if self.parent():
                if hasattr(self.parent(), 'load_purchase_list'):
                    self.parent().load_purchase_list()

    def update_summary(self):
        """요약 정보 업데이트"""
        summary = get_purchase_payment_summary(self.purchase_id)
        
        self.lbl_po_amount.setText(f"{format_money(summary['po_amount'])} 원")
        self.lbl_po_amount_with_tax.setText(f"{format_money(summary['po_amount_with_tax'])} 원")
        self.lbl_paid.setText(f"{format_money(summary['total_paid'])} 원")
        self.lbl_unpaid.setText(f"{format_money(summary['unpaid_amount'])} 원")
        
        pct = summary['progress_percent']
        self.lbl_progress.setText(f"{pct}%")
        
        if pct >= 100:
            self.lbl_progress.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_progress.setStyleSheet("color: orange; font-weight: bold;")
