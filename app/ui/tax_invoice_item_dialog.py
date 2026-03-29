"""
세금계산서 품목별 입력 다이얼로그
실제 세금계산서 형식에 맞춰 품목별로 입력하고 자동 계산
"""
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from datetime import datetime
from .money_lineedit import MoneyLineEdit
from ..db import (
    get_conn, format_money,
    add_tax_invoice, get_tax_invoice_items, add_tax_invoice_item,
    delete_tax_invoice_item, update_tax_invoice_total,
    get_available_purchases_for_invoice, link_tax_invoice_to_purchase
)


class TaxInvoiceItemDialog(QtWidgets.QDialog):
    """세금계산서 품목별 입력 다이얼로그"""
    
    def __init__(self, purchase_id=None, invoice_id=None, parent=None):
        super().__init__(parent)
        self.purchase_id = purchase_id  # None이면 독립적으로 동작
        self.is_edit_mode = (invoice_id is not None)
        self.invoice_id = invoice_id
        self.supplier_id = None # 공급자 ID 보관용
        self.settings = QtCore.QSettings("KOBATECH", "ProductManager")
        
        self.setWindowTitle("세금계산서 수정" if self.is_edit_mode else "세금계산서 등록")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(600)
        
        self.setup_ui()
        self.restore_column_widths()
        self.load_available_purchases()
        
        # 수정 모드면 기존 데이터 로드
        if self.is_edit_mode:
            self.load_invoice_data()
        
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # 상단: 기본 정보
        header_group = QtWidgets.QGroupBox("기본 정보")
        header_layout = QtWidgets.QFormLayout(header_group)
        
        self.date_edit = QtWidgets.QDateEdit()
        self.date_edit.setDate(QtCore.QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setMinimumWidth(110)  # 날짜 선택 삼각형이 날짜 바로 옆에 오도록
        self.date_edit.setMaximumWidth(110)  # 최대 너비도 제한하여 삼각형이 오른쪽 끝으로 가지 않도록
        
        self.supplier_edit = QtWidgets.QLineEdit()
        self.supplier_edit.setPlaceholderText("예: 위드에프 주식회사")
        
        self.approval_number_edit = QtWidgets.QLineEdit()
        self.approval_number_edit.setPlaceholderText("예: 20260124-10250124-19575989")
        
        header_layout.addRow("발행일:", self.date_edit)
        header_layout.addRow("공급자:", self.supplier_edit)
        header_layout.addRow("승인번호:", self.approval_number_edit)
        
        layout.addWidget(header_group)
        
        # 중간: 품목 테이블
        items_label = QtWidgets.QLabel("📋 품목 내역")
        items_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #007bff;")
        layout.addWidget(items_label)
        
        self.items_table = QtWidgets.QTableWidget(0, 9)
        self.items_table.setHorizontalHeaderLabels([
            "품목", "규격", "수량", "단가", "공급가액", "세액", "비고(발주번호)", "발주ID", "ItemID"
        ])
        self.items_table.setColumnHidden(7, True)  # 발주ID 숨김
        self.items_table.setColumnHidden(8, True)  # ItemID 숨김
        
        # 컬럼 너비 설정
        self.items_table.setColumnWidth(0, 150)  # 품목
        self.items_table.setColumnWidth(1, 100)  # 규격
        self.items_table.setColumnWidth(2, 80)   # 수량
        self.items_table.setColumnWidth(3, 100)  # 단가
        self.items_table.setColumnWidth(4, 120)  # 공급가액
        self.items_table.setColumnWidth(5, 100)  # 세액
        self.items_table.setColumnWidth(6, 150)  # 비고
        
        self.items_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.items_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        
        layout.addWidget(self.items_table)
        
        # 품목 추가/삭제 버튼
        btn_layout = QtWidgets.QHBoxLayout()
        btn_add_item = QtWidgets.QPushButton("+ 품목 추가")
        btn_add_item.clicked.connect(self.add_item)
        btn_del_item = QtWidgets.QPushButton("- 선택 삭제")
        btn_del_item.clicked.connect(self.delete_item)
        
        btn_layout.addWidget(btn_add_item)
        btn_layout.addWidget(btn_del_item)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
        # 하단: 합계
        summary_group = QtWidgets.QGroupBox("합계")
        summary_layout = QtWidgets.QFormLayout(summary_group)
        
        self.lbl_supply_total = QtWidgets.QLabel("0 원")
        self.lbl_tax_total = QtWidgets.QLabel("0 원")
        self.lbl_grand_total = QtWidgets.QLabel("0 원")
        
        self.lbl_supply_total.setStyleSheet("font-weight: bold; color: #007bff;")
        self.lbl_tax_total.setStyleSheet("font-weight: bold; color: #28a745;")
        self.lbl_grand_total.setStyleSheet("font-weight: bold; font-size: 14px; color: #dc3545;")
        
        summary_layout.addRow("합계 공급가액:", self.lbl_supply_total)
        summary_layout.addRow("합계 세액:", self.lbl_tax_total)
        summary_layout.addRow("총액:", self.lbl_grand_total)
        
        layout.addWidget(summary_group)
        
        # 버튼
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.save)
        btn_box.rejected.connect(self.reject_dialog)
        layout.addWidget(btn_box)
     
    def closeEvent(self, event):
        """다이얼로그 닫을 때 컬럼 폭 저장"""
        self.save_column_widths()
        super().closeEvent(event)
    
    def reject_dialog(self):
        """취소 버튼 클릭 시 컬럼 폭 저장"""
        self.save_column_widths()
        self.reject()
    
    def save_column_widths(self):
        """품목 테이블 컬럼 폭 저장"""
        widths = []
        for i in range(self.items_table.columnCount()):
            widths.append(self.items_table.columnWidth(i))
        self.settings.setValue("tax_invoice_item_dialog/col_widths", widths)
    
    def restore_column_widths(self):
        """품목 테이블 컬럼 폭 복원"""
        val = self.settings.value("tax_invoice_item_dialog/col_widths")
        if val and isinstance(val, (list, tuple)):
            for i in range(min(len(val), self.items_table.columnCount())):
                try:
                    w = int(val[i])
                    if w > 10:
                        self.items_table.setColumnWidth(i, w)
                except:
                    pass
    
    def load_available_purchases(self):
        """미완료 발주 목록 로드"""
        self.available_purchases = get_available_purchases_for_invoice()
        
    def add_item(self):
        """품목 추가 다이얼로그"""
        dialog = AddItemDialog(self.available_purchases, self)
        if dialog.exec():
            item_data = dialog.get_data()
            
            # 테이블에 추가
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)
            
            self.items_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item_data['item_name']))
            self.items_table.setItem(row, 1, QtWidgets.QTableWidgetItem(item_data['spec']))
            self.items_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(item_data['quantity'])))
            self.items_table.setItem(row, 3, QtWidgets.QTableWidgetItem(format_money(item_data['unit_price'])))
            self.items_table.setItem(row, 4, QtWidgets.QTableWidgetItem(format_money(item_data['supply_amount'])))
            self.items_table.setItem(row, 5, QtWidgets.QTableWidgetItem(format_money(item_data['tax_amount'])))
            self.items_table.setItem(row, 6, QtWidgets.QTableWidgetItem(item_data['purchase_no']))
            self.items_table.setItem(row, 7, QtWidgets.QTableWidgetItem(str(item_data['purchase_id']) if item_data['purchase_id'] else ""))
            self.items_table.setItem(row, 8, QtWidgets.QTableWidgetItem(""))  # ItemID는 저장 후 설정
            
            self.update_totals()
            
    def delete_item(self):
        """선택된 품목 삭제"""
        current_row = self.items_table.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "경고", "삭제할 품목을 선택해주세요.")
            return
            
        self.items_table.removeRow(current_row)
        self.update_totals()
        
    def update_totals(self):
        """합계 업데이트"""
        supply_total = 0
        tax_total = 0
        
        for row in range(self.items_table.rowCount()):
            supply_text = self.items_table.item(row, 4).text().replace(",", "").replace(" 원", "")
            tax_text = self.items_table.item(row, 5).text().replace(",", "").replace(" 원", "")
            
            try:
                supply_total += int(supply_text)
                tax_total += int(tax_text)
            except:
                pass
                
        grand_total = supply_total + tax_total
        
        self.lbl_supply_total.setText(f"{format_money(supply_total)} 원")
        self.lbl_tax_total.setText(f"{format_money(tax_total)} 원")
        self.lbl_grand_total.setText(f"{format_money(grand_total)} 원")
    
    def load_invoice_data(self):
        """기존 세금계산서 데이터 로드 (수정 모드)"""
        from ..db import get_tax_invoice_detail
        
        detail = get_tax_invoice_detail(self.invoice_id)
        if not detail:
            QtWidgets.QMessageBox.warning(self, "오류", "세금계산서 정보를 찾을 수 없습니다.")
            return
        
        # 기본 정보 설정
        date_parts = detail['issue_date'].split('-')
        self.date_edit.setDate(QtCore.QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2])))
        self.supplier_id = detail.get('supplier_id')
        self.supplier_edit.setText(detail['supplier_name'])
        self.approval_number_edit.setText(detail.get('approval_number', '') or '')
        
        # 품목 로드
        for item in detail['items']:
            # id, item_name, spec, quantity, unit_price, supply_amount, tax_amount, note, purchase_id, purchase_no
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)
            
            self.items_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item['item_name'] or ""))
            self.items_table.setItem(row, 1, QtWidgets.QTableWidgetItem(item.get('spec', "") or ""))
            self.items_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(item.get('quantity', 1))))
            self.items_table.setItem(row, 3, QtWidgets.QTableWidgetItem(format_money(item.get('unit_price', 0))))
            self.items_table.setItem(row, 4, QtWidgets.QTableWidgetItem(format_money(item['supply_amount'])))
            self.items_table.setItem(row, 5, QtWidgets.QTableWidgetItem(format_money(item['tax_amount'])))
            self.items_table.setItem(row, 6, QtWidgets.QTableWidgetItem(item.get('purchase_no', "") or ""))
            self.items_table.setItem(row, 7, QtWidgets.QTableWidgetItem(str(item.get('purchase_id', "")) if item.get('purchase_id') else ""))
            self.items_table.setItem(row, 8, QtWidgets.QTableWidgetItem(str(item['id'])))  # item_id 저장
        
        self.update_totals()
        
    def save(self):
        """저장"""
        try:
            issue_date = self.date_edit.date().toString("yyyy-MM-dd")
            supplier_id = getattr(self, "supplier_id", 0)
            supplier_name = self.supplier_edit.text().strip()
            approval_number = self.approval_number_edit.text().strip()
            
            if not supplier_name:
                QtWidgets.QMessageBox.warning(self, "경고", "공급자를 입력해주세요.")
                return
                
            if self.items_table.rowCount() == 0:
                QtWidgets.QMessageBox.warning(self, "경고", "최소 1개 이상의 품목을 추가해주세요.")
                return
            
            if self.is_edit_mode:
                # 수정 모드: 기존 품목 삭제 후 재생성
                conn = get_conn()
                try:
                    cur = conn.cursor()
                    # 기본 정보 업데이트
                    cur.execute("""
                        UPDATE purchase_tax_invoices
                        SET issue_date = ?, supplier_id = ?, approval_number = ?, updated_at = datetime('now','localtime')
                        WHERE id = ?
                    """, (issue_date, supplier_id if hasattr(self, "supplier_id") else 0, approval_number, self.invoice_id))
                    
                    # 기존 품목 삭제
                    cur.execute("DELETE FROM purchase_tax_invoice_items WHERE tax_invoice_id = ?", (self.invoice_id,))
                    
                    # 기존 매핑 삭제
                    cur.execute("DELETE FROM purchase_invoice_links WHERE tax_invoice_id = ?", (self.invoice_id,))
                    
                    conn.commit()
                finally:
                    conn.close()
            else:
                # 신규 모드: 세금계산서 생성
                invoice_data = {
                    "issue_date": issue_date,
                    "supplier_id": supplier_id,
                    "supplier_name": supplier_name,
                    "total_amount": self.total_amount,
                    "supply_amount": self.supply_amount,
                    "tax_amount": self.tax_amount,
                    "approval_number": approval_number
                }
                self.invoice_id = add_purchase_tax_invoice(invoice_data)
            
            # 품목 추가
            for row in range(self.items_table.rowCount()):
                item_name = self.items_table.item(row, 0).text()
                spec = self.items_table.item(row, 1).text()
                quantity = int(self.items_table.item(row, 2).text())
                unit_price = int(self.items_table.item(row, 3).text().replace(",", "").replace(" 원", ""))
                purchase_no = self.items_table.item(row, 6).text()
                purchase_id_text = self.items_table.item(row, 7).text()
                purchase_id = int(purchase_id_text) if purchase_id_text else None
                
                add_tax_invoice_item(
                    self.invoice_id, item_name, spec, quantity, unit_price,
                    purchase_no, purchase_id
                )
            
            # 총액 업데이트
            update_tax_invoice_total(self.invoice_id)
            
            # 발주 매핑 (품목에 연결된 모든 발주에 대해)
            purchase_amounts = {}
            for row in range(self.items_table.rowCount()):
                purchase_id_text = self.items_table.item(row, 7).text()
                if purchase_id_text:
                    pid = int(purchase_id_text)
                    supply = int(self.items_table.item(row, 4).text().replace(",", "").replace(" 원", ""))
                    tax = int(self.items_table.item(row, 5).text().replace(",", "").replace(" 원", ""))
                    
                    if pid not in purchase_amounts:
                        purchase_amounts[pid] = 0
                    purchase_amounts[pid] += (supply + tax)
            
            # 각 발주에 대해 매핑 생성
            for pid in purchase_amounts.keys():
                link_tax_invoice_to_purchase(self.invoice_id, pid)
            
            msg = "세금계산서가 수정되었습니다." if self.is_edit_mode else "세금계산서가 등록되었습니다."
            QtWidgets.QMessageBox.information(self, "완료", msg)
            self.accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"저장 실패:\n{str(e)}")


class AddItemDialog(QtWidgets.QDialog):
    """품목 추가 다이얼로그"""
    
    def __init__(self, available_purchases, parent=None):
        super().__init__(parent)
        self.available_purchases = available_purchases
        
        self.setWindowTitle("품목 추가")
        self.setMinimumWidth(500)
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QtWidgets.QFormLayout(self)
        
        self.item_name_edit = QtWidgets.QLineEdit()
        self.item_name_edit.setPlaceholderText("예: CARD RACK PWR 20대 제작")
        
        self.spec_edit = QtWidgets.QLineEdit()
        self.spec_edit.setPlaceholderText("예: 식")
        
        self.quantity_spin = QtWidgets.QSpinBox()
        self.quantity_spin.setRange(1, 1000000)
        self.quantity_spin.setValue(1)
        self.quantity_spin.valueChanged.connect(self.calculate_amounts)
        
        self.unit_price_edit = MoneyLineEdit()
        self.unit_price_edit.setPlaceholderText("단가 (원)")
        self.unit_price_edit.textChanged.connect(self.calculate_amounts)
        
        self.supply_amount_label = QtWidgets.QLabel("0 원")
        self.supply_amount_label.setStyleSheet("font-weight: bold; color: #007bff;")
        
        self.tax_amount_label = QtWidgets.QLabel("0 원")
        self.tax_amount_label.setStyleSheet("font-weight: bold; color: #28a745;")
        
        # 발주번호 선택
        self.purchase_combo = QtWidgets.QComboBox()
        self.purchase_combo.addItem("(선택 안 함)", None)
        for purchase in self.available_purchases:
            # id, purchase_no, purchase_dt, status, total_amount
            display_text = f"{purchase[1]} - {purchase[2]} ({format_money(purchase[4])}원)"
            self.purchase_combo.addItem(display_text, purchase[0])
        self.purchase_combo.currentIndexChanged.connect(self.on_purchase_changed)
        
        # 발주 품목 선택 버튼
        self.btn_select_item = QtWidgets.QPushButton("📋 발주 품목에서 선택")
        self.btn_select_item.setEnabled(False)
        self.btn_select_item.clicked.connect(self.select_from_purchase_items)
        
        layout.addRow("품목명*:", self.item_name_edit)
        layout.addRow("규격:", self.spec_edit)
        layout.addRow("수량*:", self.quantity_spin)
        layout.addRow("단가*:", self.unit_price_edit)
        layout.addRow("공급가액:", self.supply_amount_label)
        layout.addRow("세액 (10%):", self.tax_amount_label)
        layout.addRow("발주번호:", self.purchase_combo)
        layout.addRow("", self.btn_select_item)
        
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.validate_and_accept)
        btn_box.rejected.connect(self.reject)
        
        layout.addRow(btn_box)
        
    def calculate_amounts(self):
        """공급가액 및 세액 자동 계산"""
        try:
            quantity = self.quantity_spin.value()
            unit_price = self.unit_price_edit.get_value()
            
            supply_amount = quantity * unit_price
            tax_amount = int(supply_amount * 0.1)
            
            self.supply_amount_label.setText(f"{format_money(supply_amount)} 원")
            self.tax_amount_label.setText(f"{format_money(tax_amount)} 원")
        except:
            self.supply_amount_label.setText("0 원")
            self.tax_amount_label.setText("0 원")
    
    def on_purchase_changed(self):
        """발주번호 선택 시 품목 자동 조회 및 자동 입력/선택"""
        purchase_id = self.purchase_combo.currentData()
        self.btn_select_item.setEnabled(purchase_id is not None)
        
        if not purchase_id:
            return
            
        # 발주 품목 조회
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT item_code, rev, product_name, qty, unit_price_cents
                FROM purchase_items
                WHERE purchase_id = ?
                ORDER BY item_code
            """, (purchase_id,))
            items = cur.fetchall()
        finally:
            conn.close()
            
        if not items:
            return
            
        if len(items) == 1:
            # 품목이 하나면 즉시 적용
            self.apply_purchase_item(items[0])
        else:
            # 품목이 여러 개면 선택 다이얼로그 자동 팝업
            self.select_from_purchase_items(items)

    def apply_purchase_item(self, item):
        """선택된 발주 품목 데이터를 UI 필드에 적용"""
        # item: (item_code, rev, product_name, qty, unit_price_cents)
        item_code, rev, product_name, qty, unit_price_cents = item
        
        # 품목명 조합
        item_name = f"{item_code}"
        if rev:
            item_name += f" Rev.{rev}"
        if product_name:
            item_name = product_name
            
        self.item_name_edit.setText(item_name)
        self.spec_edit.setText("식")
        self.quantity_spin.setValue(qty)
        self.unit_price_edit.set_value(unit_price_cents // 100)
        self.calculate_amounts()

    def select_from_purchase_items(self, items=None):
        """발주 품목 목록에서 선택"""
        if items is None:
            purchase_id = self.purchase_combo.currentData()
            if not purchase_id:
                return
            
            # 발주 품목 조회
            conn = get_conn()
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT item_code, rev, product_name, qty, unit_price_cents
                    FROM purchase_items
                    WHERE purchase_id = ?
                    ORDER BY item_code
                """, (purchase_id,))
                items = cur.fetchall()
            finally:
                conn.close()
        
        if not items:
            QtWidgets.QMessageBox.information(self, "알림", "이 발주에 품목이 없습니다.")
            return
        
        # 품목 선택 다이얼로그
        dialog = PurchaseItemSelectionDialog(items, self)
        if dialog.exec():
            selected_item = dialog.get_selected_item()
            if selected_item:
                self.apply_purchase_item(selected_item)
            
    def validate_and_accept(self):
        """유효성 검사 후 승인"""
        if not self.item_name_edit.text().strip():
            QtWidgets.QMessageBox.warning(self, "경고", "품목명을 입력해주세요.")
            return
            
        if self.unit_price_edit.get_value() <= 0:
            QtWidgets.QMessageBox.warning(self, "경고", "단가를 입력해주세요.")
            return
            
        self.accept()
        
    def get_data(self):
        """입력된 데이터 반환"""
        quantity = self.quantity_spin.value()
        unit_price = self.unit_price_edit.get_value()
        supply_amount = quantity * unit_price
        tax_amount = int(supply_amount * 0.1)
        
        purchase_id = self.purchase_combo.currentData()
        purchase_no = ""
        if purchase_id:
            for purchase in self.available_purchases:
                if purchase[0] == purchase_id:
                    purchase_no = purchase[1]
                    break
        
        return {
            'item_name': self.item_name_edit.text().strip(),
            'spec': self.spec_edit.text().strip(),
            'quantity': quantity,
            'unit_price': unit_price,
            'supply_amount': supply_amount,
            'tax_amount': tax_amount,
            'purchase_no': purchase_no,
            'purchase_id': purchase_id
        }


class PurchaseItemSelectionDialog(QtWidgets.QDialog):
    """발주 품목 선택 다이얼로그 (컬럼 폭 저장 기능 포함)"""
    
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items
        self.selected_item = None
        self.settings = QtCore.QSettings("KOBATECH", "ProductManager")
        
        self.setWindowTitle("발주 품목 선택")
        self.setMinimumWidth(600)
        
        self.setup_ui()
        self.restore_column_widths()
    
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        label = QtWidgets.QLabel("품목을 선택하세요:")
        layout.addWidget(label)
        
        self.table = QtWidgets.QTableWidget(len(self.items), 5)
        self.table.setHorizontalHeaderLabels(["품목코드", "Rev", "품명", "수량", "단가"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        
        for row, item in enumerate(self.items):
            item_code, rev, product_name, qty, unit_price_cents = item
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(item_code or ""))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(rev or ""))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(product_name or ""))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(qty)))
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(format_money(unit_price_cents // 100)))
        
        layout.addWidget(self.table)
        
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.accept_selection)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
    
    def closeEvent(self, event):
        """다이얼로그 닫을 때 컬럼 폭 저장"""
        self.save_column_widths()
        super().closeEvent(event)
    
    def accept_selection(self):
        """선택 확인"""
        selected_row = self.table.currentRow()
        if selected_row >= 0:
            self.selected_item = self.items[selected_row]
        self.save_column_widths()
        self.accept()
    
    def reject(self):
        """취소"""
        self.save_column_widths()
        super().reject()
    
    def save_column_widths(self):
        """컬럼 폭 저장"""
        widths = []
        for i in range(self.table.columnCount()):
            widths.append(self.table.columnWidth(i))
        self.settings.setValue("purchase_item_selection_dialog/col_widths", widths)
    
    def restore_column_widths(self):
        """컬럼 폭 복원"""
        val = self.settings.value("purchase_item_selection_dialog/col_widths")
        if val and isinstance(val, (list, tuple)):
            for i in range(min(len(val), self.table.columnCount())):
                try:
                    w = int(val[i])
                    if w > 10:
                        self.table.setColumnWidth(i, w)
                except:
                    pass
        else:
            # 저장된 폭이 없으면 기본값으로 내용에 맞춤
            self.table.resizeColumnsToContents()
    
    def get_selected_item(self):
        """선택된 품목 반환"""
        return self.selected_item
