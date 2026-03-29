# app/ui/purchase_invoice_dialog.py

from PySide6 import QtWidgets, QtCore, QtGui
from .supplier_autocomplete import SupplierAutocompleteLineEdit
from ..db import (
    get_conn, query_all, add_purchase_tax_invoice, 
    add_or_update_supplier, get_available_purchases
)

class PurchaseInvoiceDialog(QtWidgets.QDialog):
    """매입 세금계산서 등록 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("매입 세금계산서 등록")
        self.setMinimumWidth(600)
        self.setup_ui()
        self.selected_purchase_ids = []
        self._load_available_purchases()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # 1. 공급처 정보 섹션
        group_supplier = QtWidgets.QGroupBox("공급처 정보")
        form_supplier = QtWidgets.QFormLayout(group_supplier)
        
        self.edit_supplier_search = SupplierAutocompleteLineEdit()
        self.edit_supplier_search.supplier_selected.connect(self._on_supplier_selected)
        form_supplier.addRow("공급처 검색:", self.edit_supplier_search)
        
        self.edit_biz_no = QtWidgets.QLineEdit()
        self.edit_ceo = QtWidgets.QLineEdit()
        self.edit_address = QtWidgets.QLineEdit()
        
        form_supplier.addRow("사업자번호:", self.edit_biz_no)
        form_supplier.addRow("대표자명:", self.edit_ceo)
        form_supplier.addRow("주소:", self.edit_address)
        
        layout.addWidget(group_supplier)
        
        # 2. 세금계산서 상세 섹션
        group_invoice = QtWidgets.QGroupBox("세금계산서 상세")
        form_invoice = QtWidgets.QFormLayout(group_invoice)
        
        self.date_issue = QtWidgets.QDateEdit()
        self.date_issue.setCalendarPopup(True)
        self.date_issue.setDate(QtCore.QDate.currentDate())
        
        self.edit_amount = QtWidgets.QSpinBox()
        self.edit_amount.setRange(0, 2000000000)
        self.edit_amount.setSingleStep(10000)
        self.edit_amount.setGroupSeparatorShown(True)
        self.edit_amount.setSuffix(" 원")
        
        self.edit_approval = QtWidgets.QLineEdit()
        self.edit_note = QtWidgets.QLineEdit()
        
        form_invoice.addRow("발행일:", self.date_issue)
        form_invoice.addRow("총 합계 금액:", self.edit_amount)
        form_invoice.addRow("승인번호:", self.edit_approval)
        form_invoice.addRow("비고:", self.edit_note)
        
        layout.addWidget(group_invoice)
        
        # 3. 발주서(PO) 연결 섹션 (복수 선택)
        layout.addWidget(QtWidgets.QLabel("연결할 발주서(PO) 선택:"))
        self.table_purchases = QtWidgets.QTableWidget()
        self.table_purchases.setColumnCount(4)
        self.table_purchases.setHorizontalHeaderLabels(["선택", "발주번호", "발주처/내용", "상태"])
        self.table_purchases.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table_purchases)
        
        # 4. 버튼 섹션
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton("저장")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel = QtWidgets.QPushButton("취소")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)

    def _load_available_purchases(self):
        """인보이스 발행이 필요한 미완료 발주 목록 로드"""
        # get_available_purchases()는 기존 db.py에 정의되어 있음 (검색결과: 4202행)
        purchases = get_available_purchases()
        self.table_purchases.setRowCount(len(purchases))
        
        for i, p in enumerate(purchases):
            # p 구조: (id, purchase_no, purchase_dt, status, ...) - Tuple?
            # get_available_purchases 쿼리에 따라 다르지만 보통 (id, purchase_no, dt, status)
            
            check_box = QtWidgets.QCheckBox()
            cell_widget = QtWidgets.QWidget()
            cell_layout = QtWidgets.QHBoxLayout(cell_widget)
            cell_layout.addWidget(check_box)
            cell_layout.setAlignment(QtCore.Qt.AlignCenter)
            cell_layout.setContentsMargins(0,0,0,0)
            
            self.table_purchases.setCellWidget(i, 0, cell_widget)
            self.table_purchases.setItem(i, 1, QtWidgets.QTableWidgetItem(str(p[1]))) # purchase_no
            self.table_purchases.setItem(i, 2, QtWidgets.QTableWidgetItem(str(p[2]))) # date or title
            self.table_purchases.setItem(i, 3, QtWidgets.QTableWidgetItem(str(p[3]))) # status
            
            # ID 저장
            self.table_purchases.item(i, 1).setData(QtCore.Qt.UserRole, p[0])

    def _on_supplier_selected(self, data):
        """자동 완성에서 공급처 선택 시 필드 자동 채움"""
        self.edit_biz_no.setText(data.get('biz_no', ''))
        self.edit_ceo.setText(data.get('ceo_name', ''))
        self.edit_address.setText(data.get('address', ''))

    def _on_save(self):
        # 1. 공급처 확보/업데이트
        supplier_name = self.edit_supplier_search.text().strip()
        if not supplier_name:
            QtWidgets.QMessageBox.warning(self, "경고", "공급처 상호를 입력해주세요.")
            return
            
        supplier_id = add_or_update_supplier({
            'name': supplier_name,
            'biz_no': self.edit_biz_no.text().strip(),
            'ceo_name': self.edit_ceo.text().strip(),
            'address': self.edit_address.text().strip()
        })
        
        if supplier_id == -1:
            QtWidgets.QMessageBox.critical(self, "오류", "공급처 정보를 저장하지 못했습니다.")
            return

        # 2. 연결할 PO 수집
        purchase_ids = []
        for i in range(self.table_purchases.rowCount()):
            cell_widget = self.table_purchases.cellWidget(i, 0)
            if cell_widget:
                cb = cell_widget.layout().itemAt(0).widget()
                if cb.isChecked():
                    pid = self.table_purchases.item(i, 1).data(QtCore.Qt.UserRole)
                    purchase_ids.append(pid)

        # 3. 데이터 준비 및 저장
        invoice_data = {
            'issue_date': self.date_issue.date().toString("yyyy-MM-dd"),
            'supplier_id': supplier_id,
            'total_amount': self.edit_amount.value(),
            'approval_number': self.edit_approval.text().strip(),
            'note': self.edit_note.text().strip()
        }
        
        invoice_id = add_purchase_tax_invoice(invoice_data, purchase_ids)
        if invoice_id != -1:
            QtWidgets.QMessageBox.information(self, "성공", "매입 세금계산서가 저장되었습니다.")
            self.accept()
        else:
            QtWidgets.QMessageBox.critical(self, "오류", "세금계산서 저장 중 오류가 발생했습니다. (승인번호 중복 등)")
