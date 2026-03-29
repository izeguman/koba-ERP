# app/ui/payment_entry_dialog.py

from PySide6 import QtWidgets, QtCore, QtGui
from ..db import add_purchase_payment

class PaymentEntryDialog(QtWidgets.QDialog):
    """대금 지불 등록 다이얼로그"""
    
    def __init__(self, invoice_data, parent=None):
        """
        invoice_data: {'id': 1, 'total_amount': 10000, 'paid_amount': 5000, 'balance': 5000, ...}
        """
        super().__init__(parent)
        self.invoice_data = invoice_data
        self.setWindowTitle("대금 지불 등록")
        self.setMinimumWidth(400)
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # 1. 정보 표시
        info_layout = QtWidgets.QFormLayout()
        info_layout.addRow("세금계산서 총액:", QtWidgets.QLabel(f"{self.invoice_data['total_amount']:,} 원"))
        info_layout.addRow("이미 지불된 금액:", QtWidgets.QLabel(f"{self.invoice_data['paid_amount']:,} 원"))
        info_layout.addRow("남은 잔액:", QtWidgets.QLabel(f"{self.invoice_data['balance']:,} 원"))
        layout.addLayout(info_layout)
        
        layout.addWidget(QtWidgets.QFrame()) # 구분선 대용
        
        # 2. 지불 정보 입력
        form = QtWidgets.QFormLayout()
        
        self.date_payment = QtWidgets.QDateEdit()
        self.date_payment.setCalendarPopup(True)
        self.date_payment.setDate(QtCore.QDate.currentDate())
        
        self.edit_amount = QtWidgets.QSpinBox()
        self.edit_amount.setRange(0, self.invoice_data['balance'])
        self.edit_amount.setValue(self.invoice_data['balance'])
        self.edit_amount.setSingleStep(10000)
        self.edit_amount.setGroupSeparatorShown(True)
        self.edit_amount.setSuffix(" 원")
        
        self.combo_method = QtWidgets.QComboBox()
        self.combo_method.addItems(["현금", "수표", "어음", "외상"])
        
        self.edit_note = QtWidgets.QLineEdit()
        
        form.addRow("지불일:", self.date_payment)
        form.addRow("지불금액:", self.edit_amount)
        form.addRow("지불수단:", self.combo_method)
        form.addRow("비고:", self.edit_note)
        
        layout.addLayout(form)
        
        # 3. 버튼
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton("지불 처리")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel = QtWidgets.QPushButton("취소")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)

    def _on_save(self):
        amount = self.edit_amount.value()
        if amount <= 0:
            QtWidgets.QMessageBox.warning(self, "경고", "지불할 금액을 입력해주세요.")
            return

        payment_data = {
            'tax_invoice_id': self.invoice_data['id'],
            'payment_date': self.date_payment.date().toString("yyyy-MM-dd"),
            'amount': amount,
            'payment_method': self.combo_method.currentText(),
            'note': self.edit_note.text().strip()
        }
        
        if add_purchase_payment(payment_data):
            QtWidgets.QMessageBox.information(self, "성공", "지불 내역이 등록되었습니다.")
            self.accept()
        else:
            QtWidgets.QMessageBox.critical(self, "오류", "지불 처리 중 오류가 발생했습니다.")
