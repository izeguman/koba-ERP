# app/ui/supplier_autocomplete.py

from PySide6 import QtWidgets, QtCore, QtGui
from ..db import search_suppliers

class SupplierAutocompleteLineEdit(QtWidgets.QLineEdit):
    """
    공급처 상호, 사업자번호, 대표자명으로 검색하여 자동 완성을 제공하는 위젯입니다.
    """
    supplier_selected = QtCore.Signal(dict)  # 공급처 선택 시 데이터 전달

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("상호, 사업자번호 또는 대표자 입력...")
        
        # 검색 타이머 (타이핑 중 잦은 DB 접근 방지)
        self.search_timer = QtCore.QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self._perform_search)
        
        self.textChanged.connect(self._on_text_changed)
        
        # 팝업 리스트 위젯 설정
        self.popup = QtWidgets.QListWidget()
        self.popup.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.popup.setFocusProxy(self)
        self.popup.itemClicked.connect(self._on_item_clicked)
        self.popup.installEventFilter(self)
        
        self.results = []

    def _on_text_changed(self, text):
        if not text.strip():
            self.popup.hide()
            return
        self.search_timer.start()

    def _perform_search(self):
        text = self.text().strip()
        if not text:
            return
            
        # DB 검색 실행
        self.results = search_suppliers(text)
        
        if not self.results:
            self.popup.hide()
            return
            
        # 팝업 내용 업데이트
        self.popup.clear()
        for res in self.results:
            # 표시 형식: 상호 (사업자번호) - 대표자
            display_text = f"{res['name']} ({res['biz_no'] or '번호없음'}) - {res['ceo_name'] or '대표미상'}"
            item = QtWidgets.QListWidgetItem(display_text)
            item.setData(QtCore.Qt.UserRole, res)
            self.popup.addItem(item)
            
        # 팝업 위치 및 크기 조절
        pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        self.popup.setGeometry(pos.x(), pos.y(), self.width(), 200)
        self.popup.show()

    def _on_item_clicked(self, item):
        data = item.data(QtCore.Qt.UserRole)
        self.setText(data['name'])
        self.popup.hide()
        self.supplier_selected.emit(data)

    def eventFilter(self, source, event):
        if source == self.popup and event.type() == QtCore.QEvent.MouseButtonPress:
            if not self.popup.geometry().contains(event.globalPos()):
                self.popup.hide()
        return super().eventFilter(source, event)

    def keyPressEvent(self, event):
        if self.popup.isVisible():
            if event.key() == QtCore.Qt.Key_Down:
                self.popup.setFocus()
                self.popup.setCurrentRow(0)
                return
            elif event.key() == QtCore.Qt.Key_Escape:
                self.popup.hide()
                return
            elif event.key() == QtCore.Qt.Key_Enter or event.key() == QtCore.Qt.Key_Return:
                if self.popup.currentItem():
                    self._on_item_clicked(self.popup.currentItem())
                    return
        super().keyPressEvent(event)

    def hidePopup(self):
        self.popup.hide()
