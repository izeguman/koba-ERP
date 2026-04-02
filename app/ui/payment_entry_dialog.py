# app/ui/payment_entry_dialog.py

from PySide6 import QtWidgets, QtCore, QtGui
from ..db import add_purchase_payment, get_tax_invoice_items, get_supplier, get_purchase_payments, delete_purchase_payment

class PaymentEntryDialog(QtWidgets.QDialog):
    """대금 지불 등록 다이얼로그"""
    
    def __init__(self, invoices, target_purchase_id=None, parent=None):
        """
        invoices: [{...}, {...}] 세금계산서 목록
        target_purchase_id: 현재 클릭한 발주서 ID (해당 건 품목만 필터링)
        """
        super().__init__(parent)
        if isinstance(invoices, dict):
            invoices = [invoices]
        self.invoices = invoices
        self.target_purchase_id = target_purchase_id
        self.invoice_data = self.invoices[0] if self.invoices else {}
        
        # ✅ QSettings 초기화
        self.settings = QtCore.QSettings("KOBATECH", "ProductManager")
        
        self.setWindowTitle("대금 지불 등록")
        self.setMinimumWidth(650)
        self.setMinimumHeight(650)
        self.setup_ui()
        self._on_invoice_changed(0) # 초기 데이터 세팅

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # 0. 세금계산서 선택
        select_layout = QtWidgets.QFormLayout()
        self.combo_invoice = QtWidgets.QComboBox()
        for inv in self.invoices:
            text = f"{inv['issue_date']} | {inv['supplier_name']}"
            self.combo_invoice.addItem(text, inv)
        
        self.combo_invoice.currentIndexChanged.connect(self._on_invoice_changed)
        select_layout.addRow("대상 계산서:", self.combo_invoice)
        layout.addLayout(select_layout)
        
        layout.addWidget(QtWidgets.QFrame()) # 구분선
        
        # 1. 계산서 상세 및 픽스 라벨
        info_layout = QtWidgets.QHBoxLayout()
        supplier_layout = QtWidgets.QFormLayout()
        self.lbl_supp_biz_no = QtWidgets.QLabel()
        self.lbl_supp_name = QtWidgets.QLabel()
        self.lbl_supp_ceo = QtWidgets.QLabel()
        self.lbl_approval_no = QtWidgets.QLabel()
        
        supplier_layout.addRow("등록번호:", self.lbl_supp_biz_no)
        supplier_layout.addRow("상호(법인명):", self.lbl_supp_name)
        supplier_layout.addRow("대표자명:", self.lbl_supp_ceo)
        supplier_layout.addRow("승인번호:", self.lbl_approval_no)
        info_layout.addLayout(supplier_layout)
        info_layout.addStretch()
        
        sum_layout = QtWidgets.QFormLayout()
        self.lbl_total_amount = QtWidgets.QLabel()
        self.lbl_paid_amount = QtWidgets.QLabel()
        self.lbl_balance = QtWidgets.QLabel()
        self.lbl_total_amount.setStyleSheet("color: #6c757d;")
        self.lbl_paid_amount.setStyleSheet("color: #6c757d;")
        self.lbl_balance.setStyleSheet("color: #6c757d; font-weight: bold;")
        sum_layout.addRow("계산서 전체 총액:", self.lbl_total_amount)
        sum_layout.addRow("기존 지불된 금액:", self.lbl_paid_amount)
        sum_layout.addRow("세금계산서 잔액:", self.lbl_balance)
        info_layout.addLayout(sum_layout)
        layout.addLayout(info_layout)
        
        # 2. 포함 품목
        label_items = QtWidgets.QLabel("<b>[현재 발주건 포함 품목]</b>")
        label_items.setStyleSheet("color: #0d6efd; font-size: 13px; margin-top: 10px;")
        layout.addWidget(label_items)
        
        self.table_items = QtWidgets.QTableWidget(0, 4)
        self.table_items.setHorizontalHeaderLabels(["품명", "규격", "수량", "공급가(원)"])
        self.table_items.horizontalHeader().setStretchLastSection(True)
        self.table_items.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table_items.verticalHeader().setVisible(False)
        self.table_items.setColumnWidth(0, 200)
        self.table_items.setColumnWidth(1, 100)
        self.table_items.setColumnWidth(2, 60)
        self.table_items.setColumnWidth(3, 100)
        self.table_items.setMaximumHeight(150)
        
        # ✅ 컬럼 폭 복원 및 시그널 연결
        self.restore_column_widths(self.table_items, "payment_dialog_items")
        self.table_items.horizontalHeader().sectionResized.connect(
            lambda: self.save_column_widths(self.table_items, "payment_dialog_items")
        )
        
        layout.addWidget(self.table_items)

        self.lbl_target_total = QtWidgets.QLabel()
        self.lbl_target_total.setStyleSheet("color: #dc3545; font-size: 13px; font-weight: bold; margin-bottom: 5px;")
        self.lbl_target_total.setAlignment(QtCore.Qt.AlignRight)
        layout.addWidget(self.lbl_target_total)

        # 3. 지불 내역 히스토리
        label_payments = QtWidgets.QLabel("<b>[이 발주 건의 지불 내역]</b>")
        label_payments.setStyleSheet("color: #198754; font-size: 13px;")
        layout.addWidget(label_payments)

        self.table_payments = QtWidgets.QTableWidget(0, 4)
        self.table_payments.setHorizontalHeaderLabels(["지불일", "지불수단", "지불 금액(원)", "비고"])
        self.table_payments.horizontalHeader().setStretchLastSection(True)
        self.table_payments.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table_payments.verticalHeader().setVisible(False)
        self.table_payments.setColumnWidth(0, 100)
        self.table_payments.setColumnWidth(1, 80)
        self.table_payments.setColumnWidth(2, 120)
        self.table_payments.setColumnWidth(3, 150)
        self.table_payments.setMaximumHeight(120)
        
        # ✅ 컬럼 폭 복원 및 시그널 연결
        self.restore_column_widths(self.table_payments, "payment_dialog_history")
        self.table_payments.horizontalHeader().sectionResized.connect(
            lambda: self.save_column_widths(self.table_payments, "payment_dialog_history")
        )
        
        # 삭제 기능을 위한 컨텍스트 메뉴 설정
        self.table_payments.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table_payments.customContextMenuRequested.connect(self._show_payment_context_menu)
        
        layout.addWidget(self.table_payments)

        layout.addWidget(QtWidgets.QFrame()) # 구분선
        
        # 4. 지불 정보 입력
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
        
        self.combo_method = QtWidgets.QComboBox()
        self.combo_method.addItems(["계좌이체", "현금", "수표", "어음", "외상"])
        
        # ✅ 마지막 사용된 지불수단 복원 (없으면 '계좌이체'가 기본값)
        last_method = self.settings.value("payment_dialog/last_method", "계좌이체")
        index = self.combo_method.findText(last_method)
        if index >= 0:
            self.combo_method.setCurrentIndex(index)
        
        self.edit_note = QtWidgets.QLineEdit()
        
        form.addRow("지불일:", self.date_payment)
        form.addRow("공급가액:", self.edit_supply)
        form.addRow("세액 (10%):", self.edit_tax)
        form.addRow("지불 합계:", self.edit_amount)
        form.addRow("지불수단:", self.combo_method)
        form.addRow("비고:", self.edit_note)
        
        layout.addLayout(form)
        
        # 버튼
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton("지불 처리")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel = QtWidgets.QPushButton("닫기" if getattr(self, '_fully_paid', False) else "취소")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def save_column_widths(self, table: QtWidgets.QTableWidget, key: str):
        """테이블의 컬럼 너비를 QSettings에 저장"""
        widths = [table.columnWidth(col) for col in range(table.columnCount())]
        self.settings.setValue(f"{key}/column_widths", widths)

    def restore_column_widths(self, table: QtWidgets.QTableWidget, key: str):
        """QSettings에서 테이블의 컬럼 너비를 복원"""
        widths = self.settings.value(f"{key}/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < table.columnCount():
                    table.setColumnWidth(col, int(width))

    def _on_invoice_changed(self, index):
        if index < 0 or not self.invoices:
            return
            
        self.invoice_data = self.combo_invoice.itemData(index)
        invoice_id = self.invoice_data['id']
        
        # 1. 공급자 정보 갱신
        supplier_id = self.invoice_data.get('supplier_id')
        if supplier_id:
            supp = get_supplier(supplier_id)
            if supp:
                self.lbl_supp_biz_no.setText(supp.get('biz_no', ''))
                self.lbl_supp_name.setText(supp.get('name', ''))
                self.lbl_supp_ceo.setText(supp.get('ceo_name', ''))
            else:
                self.lbl_supp_biz_no.setText("")
                self.lbl_supp_name.setText("")
                self.lbl_supp_ceo.setText("")
        self.lbl_approval_no.setText(self.invoice_data.get('approval_number') or "없음")
        self.lbl_total_amount.setText(f"{self.invoice_data['total_amount']:,} 원")
        self.lbl_paid_amount.setText(f"{self.invoice_data['paid_amount']:,} 원")
        self.lbl_balance.setText(f"{self.invoice_data['balance']:,} 원")
        
        # 2. 품목 필터링 로드
        all_items = get_tax_invoice_items(invoice_id)
        if self.target_purchase_id:
            items = [i for i in all_items if i.get('purchase_id') == self.target_purchase_id]
        else:
            items = all_items
        
        self.table_items.setRowCount(len(items))
        target_supply = 0
        target_tax = 0
        for r, item in enumerate(items):
            item_name = QtWidgets.QTableWidgetItem(item.get('item_name', ''))
            item_spec = QtWidgets.QTableWidgetItem(item.get('spec', '') or '')
            item_qty = QtWidgets.QTableWidgetItem(f"{item.get('quantity', 0):,}")
            item_qty.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            item_supply = QtWidgets.QTableWidgetItem(f"{item.get('supply_amount', 0):,}")
            item_supply.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            self.table_items.setItem(r, 0, item_name)
            self.table_items.setItem(r, 1, item_spec)
            self.table_items.setItem(r, 2, item_qty)
            self.table_items.setItem(r, 3, item_supply)
            target_supply += item.get('supply_amount', 0)
            target_tax += item.get('tax_amount', 0)
            
        target_total = target_supply + target_tax

        # 3. 지불 내역 조회
        payments = get_purchase_payments(invoice_id, self.target_purchase_id)
        self.table_payments.setRowCount(len(payments))
        current_paid = 0
        for r, p in enumerate(payments):
            item_date = QtWidgets.QTableWidgetItem(p.get('payment_date', ''))
            item_date.setData(QtCore.Qt.UserRole, p.get('id')) # 고유 ID 저장
            item_method = QtWidgets.QTableWidgetItem(p.get('payment_method', ''))
            item_amount = QtWidgets.QTableWidgetItem(f"{p.get('amount', 0):,}")
            item_amount.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            item_note = QtWidgets.QTableWidgetItem(p.get('note', '') or "")
            
            self.table_payments.setItem(r, 0, item_date)
            self.table_payments.setItem(r, 1, item_method)
            self.table_payments.setItem(r, 2, item_amount)
            self.table_payments.setItem(r, 3, item_note)
            current_paid += p.get('amount', 0)

        # 상태 텍스트 갱신
        if current_paid > 0:
            self.lbl_target_total.setText(f"현재 발주 건 항목 합계: {target_total:,} 원 (확인된 지불액: {current_paid:,} 원)")
        else:
            self.lbl_target_total.setText(f"현재 발주 건 항목 합계: {target_total:,} 원")

        # 4. 지불 완료 판별 및 UI 제어
        remaining = max(0, target_total - current_paid)
        if remaining == 0 and target_total > 0:
            self.btn_save.setEnabled(False)
            self.btn_save.setText("지불완료 (추가등록 불가)")
            self.btn_cancel.setText("닫기")
            self._fully_paid = True
            
            # 입력 폼 비활성화
            self.date_payment.setEnabled(False)
            self.edit_supply.setEnabled(False)
            self.edit_tax.setEnabled(False)
            self.edit_amount.setEnabled(False)
            self.combo_method.setEnabled(False)
            self.edit_note.setEnabled(False)
        else:
            self.btn_save.setEnabled(True)
            self.btn_save.setText("지불 처리")
            self.btn_cancel.setText("취소")
            self._fully_paid = False
            
            # 입력 폼 활성화
            self.date_payment.setEnabled(True)
            self.edit_supply.setEnabled(True)
            self.edit_tax.setEnabled(True)
            self.edit_amount.setEnabled(True)
            self.combo_method.setEnabled(True)
            self.edit_note.setEnabled(True)

        # 초기값 재설정 (미납 금액 한도)
        initial_total = remaining
        if initial_total == target_total and target_total > 0:
            initial_supply = target_supply
            initial_tax = target_tax
        else:
            initial_supply = round(initial_total / 1.1)
            initial_tax = initial_total - initial_supply
        
        self.edit_supply.blockSignals(True)
        self.edit_tax.blockSignals(True)
        self.edit_amount.blockSignals(True)
        self.edit_supply.setValue(initial_supply)
        self.edit_tax.setValue(initial_tax)
        self.edit_amount.setValue(initial_total)
        self.edit_supply.blockSignals(False)
        self.edit_tax.blockSignals(False)
        self.edit_amount.blockSignals(False)

    def _on_supply_changed(self, value):
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
            'purchase_id': self.target_purchase_id,
            'payment_date': self.date_payment.date().toString("yyyy-MM-dd"),
            'amount': amount,
            'supply_amount': supply,
            'tax_amount': tax,
            'payment_method': self.combo_method.currentText(),
            'note': self.edit_note.text().strip()
        }
        
        # ✅ 사용된 지불수단을 기억 (QSettings)
        self.settings.setValue("payment_dialog/last_method", self.combo_method.currentText())
        
        if add_purchase_payment(payment_data):
            QtWidgets.QMessageBox.information(self, "성공", "지불 내역이 등록되었습니다.")
            self.accept()
        else:
            QtWidgets.QMessageBox.critical(self, "오류", "지불 처리 중 오류가 발생했습니다.")

    def _show_payment_context_menu(self, pos):
        """지불 내역 테이블 우클릭 메뉴 표시"""
        row = self.table_payments.currentRow()
        if row < 0: return
        
        menu = QtWidgets.QMenu(self.table_payments)
        del_action = QtGui.QAction("선택한 지불 내역 삭제", self)
        del_action.triggered.connect(lambda: self._delete_payment(row))
        menu.addAction(del_action)
        menu.exec_(self.table_payments.viewport().mapToGlobal(pos))

    def _delete_payment(self, row):
        """선택한 지불 내역을 삭제하고 UI를 갱신합니다."""
        item = self.table_payments.item(row, 0)
        if not item: return
        
        payment_id = item.data(QtCore.Qt.UserRole)
        if not payment_id: return
        
        reply = QtWidgets.QMessageBox.question(
            self, "삭제 확인", "정말로 이 지불 내역을 삭제하시겠습니까?\n삭제 즉시 지불 상태가 재계산됩니다.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            if delete_purchase_payment(payment_id):
                QtWidgets.QMessageBox.information(self, "성공", "지불 내역이 삭제되었습니다.")
                self._on_invoice_changed(self.combo_invoice.currentIndex()) # 갱신
            else:
                QtWidgets.QMessageBox.warning(self, "오류", "지불 내역 삭제 중 오류가 발생했습니다.")
