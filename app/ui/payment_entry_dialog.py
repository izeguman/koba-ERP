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
        
        self.edit_supply = QtWidgets.QSpinBox()
        self.edit_supply.setRange(0, 1000000000)
        self.edit_supply.setGroupSeparatorShown(True)
        self.edit_supply.setSuffix(" 원")
        self.edit_supply.valueChanged.connect(self._on_supply_changed)
        
        self.edit_tax = QtWidgets.QSpinBox()
        self.edit_tax.setRange(0, 1000000000)
        self.edit_tax.setGroupSeparatorShown(True)
        self.edit_tax.setSuffix(" 원")
        self.edit_tax.valueChanged.connect(self._on_tax_or_total_changed)

        self.edit_amount = QtWidgets.QSpinBox()
        self.edit_amount.setRange(0, 1000000000)
        self.edit_amount.setGroupSeparatorShown(True)
        self.edit_amount.setSuffix(" 원")
        self.edit_amount.valueChanged.connect(self._on_tax_or_total_changed)
        
        # 초기값 설정 (잔액 기준)
        balance = self.invoice_data['balance']
        supply = round(balance / 1.1)
        tax = balance - supply
        
        self.edit_supply.setValue(supply)
        self.edit_tax.setValue(tax)
        self.edit_amount.setValue(balance)
        
        self.combo_method = QtWidgets.QComboBox()
        self.combo_method.addItems(["현금", "수표", "어음", "외상"])
        
        self.edit_note = QtWidgets.QLineEdit()
        
        form.addRow("지불일:", self.date_payment)
        form.addRow("공급가액:", self.edit_supply)
        form.addRow("세액 (10%):", self.edit_tax)
        form.addRow("지불 합계:", self.edit_amount)
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

    def _on_supply_changed(self, value):
        """공급가액 변경 시 세액(10%) 및 합계를 자동 계산합니다."""
        self.edit_supply.blockSignals(True)
        self.edit_tax.blockSignals(True)
        self.edit_amount.blockSignals(True)
        
        tax = round(value * 0.1)
        self.edit_tax.setValue(tax)
        self.edit_amount.setValue(value + tax)
        
        self.edit_supply.blockSignals(False)
        self.edit_tax.blockSignals(False)
        self.edit_amount.blockSignals(False)

    def _on_tax_or_total_changed(self, value):
        """세액이나 합계 수동 조정 시 (1원 단위 단수 처리 등) 최종 합계만 갱신합니다."""
        # 이 경우엔 복잡한 역계산 대신 현재 입력된 값들의 합을 합계 필드에 반영하거나, 
        # 합계 필드 수정 시 세액을 조정하는 식으로 처리할 수 있습니다.
        # 여기서는 단순히 두 필드의 합을 합계에 반영합니다 (공급가액 기반이 아닐 때)
        if self.sender() == self.edit_tax:
            self.edit_amount.blockSignals(True)
            self.edit_amount.setValue(self.edit_supply.value() + self.edit_tax.value())
            self.edit_amount.blockSignals(False)
        elif self.sender() == self.edit_amount:
            self.edit_tax.blockSignals(True)
            self.edit_tax.setValue(self.edit_amount.value() - self.edit_supply.value())
            self.edit_tax.blockSignals(False)

    def _on_save(self):
        amount = self.edit_amount.value()
        supply = self.edit_supply.value()
        tax = self.edit_tax.value()
        
        if amount <= 0:
            QtWidgets.QMessageBox.warning(self, "경고", "지불할 금액을 입력해주세요.")
            return

        payment_data = {
            'tax_invoice_id': self.invoice_data['id'],
            'payment_date': self.date_payment.date().toString("yyyy-MM-dd"),
            'amount': amount,
            'supply_amount': supply,
            'tax_amount': tax,
            'payment_method': self.combo_method.currentText(),
            'note': self.edit_note.text().strip()
        }
        
        if add_purchase_payment(payment_data):
            QtWidgets.QMessageBox.information(self, "성공", "지불 내역이 등록되었습니다.")
            self.accept()
        else:
            QtWidgets.QMessageBox.critical(self, "오류", "지불 처리 중 오류가 발생했습니다.")
