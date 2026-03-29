from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from datetime import datetime
from .money_lineedit import MoneyLineEdit
from .tax_invoice_item_dialog import TaxInvoiceItemDialog
from ..db import (
    get_conn, format_money, 
    add_payment, get_payments_for_purchase, delete_payment, update_payment,
    add_tax_invoice, link_tax_invoice_to_purchase, get_tax_invoices_for_purchase,
    get_purchase_payment_summary, query_all
)

class PurchasePaymentDialog(QtWidgets.QDialog):
    """발주 결제 및 세금계산서 관리 다이얼로그"""
    
    def __init__(self, purchase_id, parent=None):
        super().__init__(parent)
        self.purchase_id = purchase_id
        self.settings = QtCore.QSettings("KOBATECH", "ProductManager")
        self.setWindowTitle("결제 및 세금계산서 관리")
        self.setMinimumWidth(1100)
        self.setMinimumHeight(700)
        
        self.setup_ui()
        self.restore_column_widths()
        self.load_data()

    def closeEvent(self, event):
        self.save_column_widths()
        super().closeEvent(event)

    def save_column_widths(self):
        widths = []
        for i in range(self.invoice_table.columnCount()):
            widths.append(self.invoice_table.columnWidth(i))
        self.settings.setValue("purchase_payment_dialog/invoice_col_widths", widths)

    def restore_column_widths(self):
        val = self.settings.value("purchase_payment_dialog/invoice_col_widths")
        if val and isinstance(val, (list, tuple)):
            for i in range(min(len(val), self.invoice_table.columnCount())):
                try:
                    w = int(val[i])
                    if w > 10:
                        self.invoice_table.setColumnWidth(i, w)
                except:
                    pass

    def setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        
        # --- 좌측: 결제 관리 (지출) ---
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        
        lbl_payment = QtWidgets.QLabel("💰 결제(지출) 내역")
        lbl_payment.setStyleSheet("font-size: 14px; font-weight: bold; color: #007bff;")
        left_layout.addWidget(lbl_payment)
        
        self.payment_table = QtWidgets.QTableWidget(0, 5)
        self.payment_table.setHorizontalHeaderLabels(["날짜", "구분", "금액", "비고", "ID"])
        self.payment_table.setColumnHidden(4, True) # ID hidden
        self.payment_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.payment_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.payment_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.payment_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        # 선택 시 반전(파란 배경, 흰 글씨) 명시적 스타일링 + 포커스 여부 관계없이 유지
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
        left_layout.addWidget(self.payment_table)
        
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
        # 콤보박스 드롭다운 아이템 호버/선택 시 색상 문제 해결 (QListView 스타일링)
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
        
        left_layout.addLayout(form_layout)
        
        btn_del = QtWidgets.QPushButton("선택 삭제")
        btn_del.clicked.connect(self.delete_payment_record)
        left_layout.addWidget(btn_del)
        
        left_panel.setStyleSheet("background-color: #f8f9fa; border-radius: 5px;")
        
        # --- 우측: 세금계산서 (청구) & 요약 ---
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        
        # 1. 요약 정보
        group_summary = QtWidgets.QGroupBox("요약 정보")
        form_summary = QtWidgets.QFormLayout(group_summary)
        
        self.lbl_po_amount = QtWidgets.QLabel("-")
        self.lbl_paid = QtWidgets.QLabel("-")
        self.lbl_invoiced = QtWidgets.QLabel("-")
        self.lbl_unpaid = QtWidgets.QLabel("-")
        self.lbl_progress = QtWidgets.QLabel("-")
        
        form_summary.addRow("발주 총액:", self.lbl_po_amount)
        form_summary.addRow("세금계산서(청구) 합계:", self.lbl_invoiced)
        form_summary.addRow("지불(지출) 합계:", self.lbl_paid)
        form_summary.addRow("미지급액:", self.lbl_unpaid)
        form_summary.addRow("진행률:", self.lbl_progress)
        
        right_layout.addWidget(group_summary)
        
        # 2. 세금계산서 내역
        lbl_invoice = QtWidgets.QLabel("📄 세금계산서(청구) 매핑 내역")
        lbl_invoice.setStyleSheet("font-size: 14px; font-weight: bold; color: #28a745;")
        right_layout.addWidget(lbl_invoice)
        
        self.invoice_table = QtWidgets.QTableWidget(0, 6)
        self.invoice_table.setHorizontalHeaderLabels(["발행일", "공급자", "공급가액", "세액", "총액", "비고"])
        self.invoice_table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.Stretch)
        self.invoice_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.invoice_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.invoice_table.itemDoubleClicked.connect(self.edit_invoice)
        right_layout.addWidget(self.invoice_table)
        
        btn_add_invoice = QtWidgets.QPushButton("세금계산서 등록/연결")
        btn_add_invoice.clicked.connect(self.open_invoice_dialog)
        right_layout.addWidget(btn_add_invoice)
        
        right_layout.addStretch()

        # 전체 배치
        layout.addWidget(left_panel, 6) # 6:4 비율
        layout.addWidget(right_panel, 4)
        
    def load_data(self):
        self.load_payments()
        self.load_invoices()
        self.update_summary()

    def load_payments(self):
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
            
            self.load_data() # 재로딩
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"결제 추가 중 오류: {e}")

    def delete_payment_record(self):
        current_row = self.payment_table.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "경고", "삭제할 항목을 선택해주세요.")
            return
            
        item_id = int(self.payment_table.item(current_row, 4).text())
        
        confirm = QtWidgets.QMessageBox.question(self, "확인", "정말로 삭제하시겠습니까?", 
                                                 QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if confirm == QtWidgets.QMessageBox.Yes:
            delete_payment(item_id)
            self.load_data()

    def load_invoices(self):
        try:
            data = get_tax_invoices_for_purchase(self.purchase_id)
            self.invoice_table.setRowCount(0)
            for row in data:
                # row: {'id': 1, 'issue_date': '...', 'supplier_name': '...', 'total_amount': ..., 
                #       'supply_amount': ..., 'tax_amount': ..., 'note': ...}
                r = self.invoice_table.rowCount()
                self.invoice_table.insertRow(r)
                
                item_date = QtWidgets.QTableWidgetItem(row.get('issue_date', ''))
                item_date.setData(QtCore.Qt.UserRole, row.get('id')) # ID 저장
                
                self.invoice_table.setItem(r, 0, item_date)
                self.invoice_table.setItem(r, 1, QtWidgets.QTableWidgetItem(row.get('supplier_name', '')))
                self.invoice_table.setItem(r, 2, QtWidgets.QTableWidgetItem(format_money(row.get('supply_amount', 0))))
                self.invoice_table.setItem(r, 3, QtWidgets.QTableWidgetItem(format_money(row.get('tax_amount', 0))))
                self.invoice_table.setItem(r, 4, QtWidgets.QTableWidgetItem(format_money(row.get('total_amount', 0))))
                self.invoice_table.setItem(r, 5, QtWidgets.QTableWidgetItem(row.get('note', '')))
        except Exception as e:
            print(f"Invoice load error: {e}")

    def edit_invoice(self, item):
        """세금계산서 항목 더블클릭 시 수정 다이얼로그를 엽니다."""
        row = item.row()
        invoice_id = self.invoice_table.item(row, 0).data(QtCore.Qt.UserRole)
        if not invoice_id:
            return
            
        dlg = TaxInvoiceItemDialog(purchase_id=self.purchase_id, invoice_id=invoice_id, parent=self)
        if dlg.exec():
            self.load_data()

    def open_invoice_dialog(self):
        # 새로운 품목별 입력 다이얼로그 사용
        dlg = TaxInvoiceItemDialog(purchase_id=self.purchase_id, parent=self)
        if dlg.exec():
            self.load_data()

    def update_summary(self):
        summary = get_purchase_payment_summary(self.purchase_id)
        
        self.lbl_po_amount.setText(f"{format_money(summary['po_amount'])} 원")
        self.lbl_paid.setText(f"{format_money(summary['total_paid'])} 원")
        self.lbl_invoiced.setText(f"{format_money(summary['total_invoiced'])} 원")
        self.lbl_unpaid.setText(f"{format_money(summary['unpaid_amount'])} 원")
        
        pct = summary['progress_percent']
        self.lbl_progress.setText(f"{pct}%")
        
        if pct >= 100:
            self.lbl_progress.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_progress.setStyleSheet("color: orange; font-weight: bold;")


class SimpleInvoiceDialog(QtWidgets.QDialog):
    """(임시) 간단 세금계산서 등록 다이얼로그"""
    def __init__(self, purchase_id, parent=None):
        super().__init__(parent)
        self.purchase_id = purchase_id
        self.setWindowTitle("세금계산서 등록")
        self.setup_ui()
        
    def setup_ui(self):
        layout = QtWidgets.QFormLayout(self)
        
        self.date_edit = QtWidgets.QDateEdit()
        self.date_edit.setDate(QtCore.QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        
        self.supplier_edit = QtWidgets.QLineEdit()
        
        self.total_amount_edit = MoneyLineEdit()
        self.total_amount_edit.setPlaceholderText("세금계산서 총액")
        
        self.mapped_amount_edit = MoneyLineEdit()
        self.mapped_amount_edit.setPlaceholderText("이 발주에 해당하는 금액")
        
        self.note_edit = QtWidgets.QLineEdit()
        
        layout.addRow("발행일:", self.date_edit)
        layout.addRow("공급자:", self.supplier_edit)
        layout.addRow("계산서 총액:", self.total_amount_edit)
        layout.addRow("이 발주 적용액:", self.mapped_amount_edit)
        layout.addRow("비고:", self.note_edit)
        
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.save)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)
        
        # 기본값 세팅 (편의상)
        # 발주 잔액을 기본으로 넣어주면 좋음 (DB 조회 필요하지만 여기선 생략)
        
    def save(self):
        try:
            issue_date = self.date_edit.date().toString("yyyy-MM-dd")
            supplier = self.supplier_edit.text()
            total = self.total_amount_edit.get_value()
            mapped = self.mapped_amount_edit.get_value()
            note = self.note_edit.text()
            
            if total <= 0 or mapped <= 0:
                QtWidgets.QMessageBox.warning(self, "경고", "금액을 입력해주세요.")
                return

            if mapped > total:
                 QtWidgets.QMessageBox.warning(self, "경고", "적용액이 총액보다 클 수 없습니다.")
                 return
                 
            # 1. 세금계산서 생성
            inv_id = add_tax_invoice(issue_date, supplier, total, note)
            
            # 2. 매핑 생성
            link_tax_invoice_to_purchase(inv_id, self.purchase_id)
            
            self.accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"저장 실패: {e}")
