# app/ui/filter_settings_dialog.py
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QSettings


class FilterSettingsDialog(QtWidgets.QDialog):
    """필터 초기값 설정 대화상자"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("필터 초기값 설정")
        self.setMinimumWidth(500)
        self.settings = QSettings("KOBATECH", "ProductionManagement")
        self.setup_ui()
        self.load_current_settings()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # 안내 메시지
        info_label = QtWidgets.QLabel(
            "프로그램 시작 시 각 탭의 필터 초기값을 설정합니다.\n"
            "체크하면 '전체보기'가 기본값이 됩니다."
        )
        info_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # 구분선
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(line)

        # 각 필터에 대한 체크박스
        self.checkboxes = {}

        filters = [
            ("orders", "주문 정보", "미청구만", "전체보기"),
            ("purchases", "발주 정보", "미완료만", "전체보기"),
            ("inventory", "재고 현황", "미완료만", "전체보기"),
            ("delivery", "납품 정보", "미완료만", "전체보기"),
            ("product_master", "제품 마스터", "생산가능만", "전체보기"),
            ("product", "제품 생산", "미납품만", "전체보기"),
        ]

        for key, label, unchecked_text, checked_text in filters:
            row_layout = QtWidgets.QHBoxLayout()

            checkbox = QtWidgets.QCheckBox()
            checkbox.stateChanged.connect(
                lambda state, k=key, ut=unchecked_text, ct=checked_text:
                self.update_label(k, state, ut, ct)
            )
            self.checkboxes[key] = checkbox

            label_widget = QtWidgets.QLabel(f"<b>{label}:</b>")
            label_widget.setMinimumWidth(120)

            status_label = QtWidgets.QLabel(unchecked_text)
            status_label.setStyleSheet("color: #0078d4; font-weight: bold;")

            # 저장용
            checkbox.status_label = status_label
            checkbox.unchecked_text = unchecked_text
            checkbox.checked_text = checked_text

            row_layout.addWidget(label_widget)
            row_layout.addWidget(checkbox)
            row_layout.addWidget(status_label)
            row_layout.addStretch()

            layout.addLayout(row_layout)

        layout.addSpacing(10)

        # 구분선
        line2 = QtWidgets.QFrame()
        line2.setFrameShape(QtWidgets.QFrame.HLine)
        line2.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(line2)

        # 버튼
        button_layout = QtWidgets.QHBoxLayout()
        btn_reset = QtWidgets.QPushButton("기본값으로")
        btn_save = QtWidgets.QPushButton("저장")
        btn_cancel = QtWidgets.QPushButton("취소")

        btn_reset.clicked.connect(self.reset_to_defaults)
        btn_save.clicked.connect(self.save_settings)
        btn_cancel.clicked.connect(self.reject)

        button_layout.addWidget(btn_reset)
        button_layout.addStretch()
        button_layout.addWidget(btn_save)
        button_layout.addWidget(btn_cancel)

        layout.addLayout(button_layout)

    def update_label(self, key, state, unchecked_text, checked_text):
        """체크박스 상태에 따라 라벨 업데이트"""
        checkbox = self.checkboxes[key]
        is_checked = state == Qt.CheckState.Checked.value
        checkbox.status_label.setText(checked_text if is_checked else unchecked_text)

    def load_current_settings(self):
        """현재 저장된 설정 불러오기"""
        settings_map = {
            "orders": "filters/orders_show_all",
            "purchases": "filters/purchases_show_all",
            "inventory": "filters/inventory_show_all",
            "delivery": "filters/delivery_show_all",
            "product_master": "filters/product_master_show_all",
            "product": "filters/product_show_all",
        }

        for key, setting_key in settings_map.items():
            # 기본값은 False (필터링 모드)
            value = self.settings.value(setting_key, False, type=bool)
            checkbox = self.checkboxes[key]
            checkbox.setChecked(value)

    def reset_to_defaults(self):
        """모든 필터를 기본값(필터링 모드)으로 초기화"""
        reply = QtWidgets.QMessageBox.question(
            self,
            "기본값으로 초기화",
            "모든 필터를 기본값(필터링 모드)으로 초기화하시겠습니까?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            for checkbox in self.checkboxes.values():
                checkbox.setChecked(False)

    def save_settings(self):
        """설정 저장"""
        settings_map = {
            "orders": "filters/orders_show_all",
            "purchases": "filters/purchases_show_all",
            "inventory": "filters/inventory_show_all",
            "delivery": "filters/delivery_show_all",
            "product_master": "filters/product_master_show_all",
            "product": "filters/product_show_all",
        }

        for key, setting_key in settings_map.items():
            value = self.checkboxes[key].isChecked()
            self.settings.setValue(setting_key, value)

        QtWidgets.QMessageBox.information(
            self,
            "저장 완료",
            "필터 설정이 저장되었습니다.\n프로그램을 다시 시작하면 적용됩니다."
        )
        self.accept()