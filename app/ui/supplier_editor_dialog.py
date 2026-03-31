# app/ui/supplier_editor_dialog.py

from PySide6 import QtWidgets, QtCore, QtGui
from ..db import get_all_suppliers, get_supplier, add_or_update_supplier

class SupplierEditorDialog(QtWidgets.QDialog):
    """
    공급자 정보를 관리하고 편집하는 다이얼로그입니다.
    세금계산서 관리 화면에서 호출됩니다.
    """
    def __init__(self, parent=None, initial_supplier_id=None):
        super().__init__(parent)
        self.setWindowTitle("공급자 관리")
        self.setMinimumSize(700, 500)
        self.supplier_id = initial_supplier_id
        
        self.setup_ui()
        self.load_supplier_list()
        
        if self.supplier_id:
            self.load_supplier_details(self.supplier_id)

    def setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)
        
        # 좌측: 공급자 목록
        list_group = QtWidgets.QGroupBox("공급자 목록")
        list_layout = QtWidgets.QVBoxLayout(list_group)
        
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("상호 검색...")
        self.search_edit.textChanged.connect(self.filter_list)
        list_layout.addWidget(self.search_edit)
        
        self.supplier_list = QtWidgets.QListWidget()
        self.supplier_list.itemClicked.connect(self._on_item_clicked)
        list_layout.addWidget(self.supplier_list)
        
        self.btn_new = QtWidgets.QPushButton("+ 새 공급자 추가")
        self.btn_new.clicked.connect(self.prepare_new_supplier)
        list_layout.addWidget(self.btn_new)
        
        main_layout.addWidget(list_group, 1)
        
        # 우측: 상세 정보 입력 폼
        detail_group = QtWidgets.QGroupBox("상세 정보")
        detail_layout = QtWidgets.QVBoxLayout(detail_group)
        
        form_layout = QtWidgets.QFormLayout()
        
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("필수: 상호(회사명)")
        form_layout.addRow("상호(필수):", self.name_edit)
        
        self.biz_no_edit = QtWidgets.QLineEdit()
        self.biz_no_edit.setPlaceholderText("예: 000-00-00000")
        form_layout.addRow("사업자등록번호:", self.biz_no_edit)
        
        self.ceo_name_edit = QtWidgets.QLineEdit()
        form_layout.addRow("대표자명:", self.ceo_name_edit)
        
        self.biz_type_edit = QtWidgets.QLineEdit()
        self.biz_type_edit.setPlaceholderText("예: 제조업")
        form_layout.addRow("업태:", self.biz_type_edit)
        
        self.biz_item_edit = QtWidgets.QLineEdit()
        self.biz_item_edit.setPlaceholderText("예: 전자부품")
        form_layout.addRow("종목:", self.biz_item_edit)
        
        self.address_edit = QtWidgets.QLineEdit()
        form_layout.addRow("사업장 주소:", self.address_edit)
        
        self.contact_edit = QtWidgets.QLineEdit()
        self.contact_edit.setPlaceholderText("전화번호 등")
        form_layout.addRow("연락처:", self.contact_edit)
        
        self.email_edit = QtWidgets.QLineEdit()
        self.email_edit.setPlaceholderText("이메일 주소")
        form_layout.addRow("이메일:", self.email_edit)
        
        detail_layout.addLayout(form_layout)
        detail_layout.addStretch()
        
        # 버튼 영역
        btn_box = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton("저장")
        self.btn_save.clicked.connect(self.save_supplier)
        self.btn_save.setStyleSheet("background-color: #007bff; color: white; font-weight: bold; padding: 8px;")
        
        self.btn_close = QtWidgets.QPushButton("닫기")
        self.btn_close.clicked.connect(self.accept)
        
        btn_box.addWidget(self.btn_save)
        btn_box.addWidget(self.btn_close)
        detail_layout.addLayout(btn_box)
        
        main_layout.addWidget(detail_group, 2)

    def load_supplier_list(self):
        """DB에서 전체 공급자 목록을 로드하여 리스트 위젯에 표시합니다."""
        self.supplier_list.clear()
        suppliers = get_all_suppliers()
        for s in suppliers:
            item = QtWidgets.QListWidgetItem(f"{s['name']} ({s['biz_no'] or '번호없음'})")
            item.setData(QtCore.Qt.UserRole, s['id'])
            self.supplier_list.addItem(item)

    def filter_list(self, text):
        """검색어에 따라 목록을 필터링합니다."""
        for i in range(self.supplier_list.count()):
            item = self.supplier_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def _on_item_clicked(self, item):
        sid = item.data(QtCore.Qt.UserRole)
        self.load_supplier_details(sid)

    def load_supplier_details(self, supplier_id):
        """공급자 ID로 상세 정보를 조회하여 폼에 채웁니다."""
        self.supplier_id = supplier_id
        data = get_supplier(supplier_id)
        if data:
            self.name_edit.setText(data['name'] or "")
            self.biz_no_edit.setText(data['biz_no'] or "")
            self.ceo_name_edit.setText(data['ceo_name'] or "")
            self.biz_type_edit.setText(data['biz_type'] or "")
            self.biz_item_edit.setText(data['biz_item'] or "")
            self.address_edit.setText(data['address'] or "")
            self.contact_edit.setText(data['contact'] or "")
            self.email_edit.setText(data['email'] or "")

    def prepare_new_supplier(self):
        """입력 폼을 비우고 신규 등록 준비 상태로 전환합니다."""
        self.supplier_id = None
        self.name_edit.clear()
        self.biz_no_edit.clear()
        self.ceo_name_edit.clear()
        self.biz_type_edit.clear()
        self.biz_item_edit.clear()
        self.address_edit.clear()
        self.contact_edit.clear()
        self.email_edit.clear()
        self.name_edit.setFocus()

    def save_supplier(self):
        """현재 폼의 내용을 DB에 저장합니다."""
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "경고", "상호(회사명)는 필수 입력 사항입니다.")
            return
            
        data = {
            'name': name,
            'biz_no': self.biz_no_edit.text().strip(),
            'ceo_name': self.ceo_name_edit.text().strip(),
            'biz_type': self.biz_type_edit.text().strip(),
            'biz_item': self.biz_item_edit.text().strip(),
            'address': self.address_edit.text().strip(),
            'contact': self.contact_edit.text().strip(),
            'email': self.email_edit.text().strip()
        }
        
        try:
            new_id = add_or_update_supplier(data)
            if new_id != -1:
                QtWidgets.QMessageBox.information(self, "완료", "공급자 정보가 저장되었습니다.")
                self.load_supplier_list()
                # 저장 후 저장된 항목 선택
                for i in range(self.supplier_list.count()):
                    if self.supplier_list.item(i).data(QtCore.Qt.UserRole) == new_id:
                        self.supplier_list.setCurrentRow(i)
                        break
            else:
                QtWidgets.QMessageBox.critical(self, "오류", "공급자 정보 저장에 실패했습니다.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"저장 중 오류 발생:\n{str(e)}")
