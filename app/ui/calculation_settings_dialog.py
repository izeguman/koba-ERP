# app/ui/calculation_settings_dialog.py
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                               QFormLayout, # ⬅️ [추가]
                               QCheckBox, QComboBox, QDialogButtonBox, QLabel,
                               QMessageBox, QSpinBox)  # ✅ QSpinBox 추가


class CalculationSettingsDialog(QDialog):
    """금액 계산 방식 설정 (반올림 등)"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)

        if settings:
            self.settings = settings
        else:
            self.settings = QSettings("KOBATECH", "ProductionManagement")

        self.setWindowTitle("계산 및 자동화 설정")
        self.setMinimumWidth(450)
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # --- 발주 금액 반올림 ---
        group = QGroupBox("발주 금액 계산 (품목별 합계)")
        form_layout = QVBoxLayout(group)

        # 1. 계산 방식 콤보박스
        method_layout = QHBoxLayout()
        self.lbl_rounding_method = QLabel("계산 방식:")
        self.cmb_rounding_method = QComboBox()

        methods = [
            ("적용 안함 (기본값)", "none"),
            ("반올림 (사사오입)", "round"),
            ("버림 (내림)", "floor")
        ]

        for text, method_value in methods:
            self.cmb_rounding_method.addItem(text, method_value)

        self.cmb_rounding_method.currentIndexChanged.connect(self.update_ui_state)

        method_layout.addWidget(self.lbl_rounding_method)
        method_layout.addWidget(self.cmb_rounding_method)
        method_layout.addStretch()

        # 2. ✅ [수정] '단위' 콤보박스를 '자릿수' 스핀박스로 변경
        digits_layout = QHBoxLayout()
        self.lbl_rounding_digits = QLabel("적용 자릿수:")
        self.spin_rounding_digits = QSpinBox()
        self.spin_rounding_digits.setRange(0, 9)  # 0 (1원) ~ 9 (10억)
        self.spin_rounding_digits.setToolTip(
            "버릴 자릿수(0의 개수)를 입력합니다.\n"
            "0 = 1원 (적용 안함)\n"
            "1 = 10원 (일의 자리)\n"
            "3 = 1,000원 (백의 자리)\n"
            "4 = 10,000원 (천의 자리)"
        )

        self.lbl_rounding_digits_desc = QLabel("(0=1원, 1=10원, 4=만원)")

        digits_layout.addWidget(self.lbl_rounding_digits)
        digits_layout.addWidget(self.spin_rounding_digits)
        digits_layout.addWidget(self.lbl_rounding_digits_desc)
        digits_layout.addStretch()

        form_layout.addLayout(method_layout)
        form_layout.addLayout(digits_layout)  # ✅ 'unit_layout' 대신 'digits_layout' 추가

        layout.addWidget(group)

        auto_num_group = QGroupBox("자동 번호 생성")
        form_layout = QFormLayout(auto_num_group)

        self.cb_auto_purchase_no = QCheckBox("새 발주 추가 시 발주번호 자동 추천")
        self.cb_auto_delivery_no = QCheckBox("새 납품 추가 시 납품번호 자동 추천")

        form_layout.addRow(self.cb_auto_purchase_no)
        form_layout.addRow(self.cb_auto_delivery_no)

        layout.addWidget(auto_num_group)

        layout.addStretch()

        # --- 버튼 ---
        btns = QDialogButtonBox(
            QDialogButtonBox.RestoreDefaults | QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.button(QDialogButtonBox.RestoreDefaults).setText("기본값으로")

        btns.accepted.connect(self.save_settings)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.reset_to_defaults)

        layout.addWidget(btns)

        self.update_ui_state()

    def update_ui_state(self):
        """계산 방식에 따라 단위 콤보박스 활성화/비활성화"""
        current_method = self.cmb_rounding_method.currentData()

        # '적용 안함'일 때만 비활성화
        is_enabled = (current_method != "none")

        # ✅ [수정] 스핀박스와 라벨을 제어
        self.lbl_rounding_digits.setEnabled(is_enabled)
        self.spin_rounding_digits.setEnabled(is_enabled)
        self.lbl_rounding_digits_desc.setEnabled(is_enabled)

    def load_settings(self):
        """저장된 설정 불러오기"""
        # 1. 계산 방식 (기본값: "none")
        method = self.settings.value("calculations/purchase_rounding_method", "none", type=str)
        index = self.cmb_rounding_method.findData(method)
        if index >= 0:
            self.cmb_rounding_method.setCurrentIndex(index)
        else:
            self.cmb_rounding_method.setCurrentIndex(0)  # "none"

        # 2. ✅ [수정] '자릿수' 불러오기 (기본값: 4 = 만원 단위)
        digits = self.settings.value("calculations/purchase_rounding_digits", 4, type=int)
        self.spin_rounding_digits.setValue(digits)

        # 3. 자동 번호 설정 로드
        self.cb_auto_purchase_no.setChecked(
            self.settings.value("auto_numbering/enable_purchase_no", False, type=bool)
        )
        self.cb_auto_delivery_no.setChecked(
            self.settings.value("auto_numbering/enable_delivery_no", False, type=bool)
        )

        self.update_ui_state()

    def save_settings(self):
        """설정 저장"""
        self.settings.setValue(
            "calculations/purchase_rounding_method",
            self.cmb_rounding_method.currentData()
        )
        # ✅ [수정] '자릿수' 저장
        self.settings.setValue(
            "calculations/purchase_rounding_digits",
            self.spin_rounding_digits.value()
        )

        # 자동 번호 설정 저장
        self.settings.setValue(
            "auto_numbering/enable_purchase_no", self.cb_auto_purchase_no.isChecked()
        )
        self.settings.setValue(
            "auto_numbering/enable_delivery_no", self.cb_auto_delivery_no.isChecked()
        )

        QMessageBox.information(self, "저장 완료", "계산 및 자동화 설정이 저장되었습니다.")
        self.accept()

    def reset_to_defaults(self):
        """기본값으로 되돌리기 (적용 안함, 만원 단위)"""
        self.cmb_rounding_method.setCurrentIndex(0)  # "적용 안함"
        self.spin_rounding_digits.setValue(4)  # 만원 단위 (4)

        self.cb_auto_purchase_no.setChecked(False)
        self.cb_auto_delivery_no.setChecked(False)

        self.update_ui_state()