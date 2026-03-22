# app/ui/color_settings_dialog.py

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, QSettings


class ColorSettingsDialog(QtWidgets.QDialog):
    """데이터 상태별 색상 설정 대화상자"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)

        if settings:
            self.settings = settings
        else:
            from PySide6.QtCore import QSettings
            self.settings = QSettings("KOBATECH", "ProductionManagement")

        self.setWindowTitle("색상 설정")
        self.setMinimumWidth(600)

        # 기본 색상 정의
        self.default_colors = {
            'order_completed_fg': '#000000',
            'order_completed_bg': '#C8E6C9',
            'order_incomplete_fg': '#000000',
            'order_incomplete_bg': '#FFFFFF',

            'purchase_completed_fg': '#000000',
            'purchase_completed_bg': '#BBDEFB',
            'purchase_incomplete_fg': '#000000',
            'purchase_incomplete_bg': '#FFFFFF',

            'delivery_completed_fg': '#000000',
            'delivery_completed_bg': '#FFE082',
            'delivery_incomplete_fg': '#000000',
            'delivery_incomplete_bg': '#FFFFFF',

            'product_completed_fg': '#000000',
            'product_completed_bg': '#E1BEE7',
            'product_incomplete_fg': '#000000',
            'product_incomplete_bg': '#FFFFFF',

            'product_master_completed_fg': '#000000',
            'product_master_completed_bg': '#E0F7FA',
            'product_master_incomplete_fg': '#000000',
            'product_master_incomplete_bg': '#FFFFFF',

            'inventory_completed_fg': '#000000',
            'inventory_completed_bg': '#E8F5E9',
            'inventory_incomplete_fg': '#000000',
            'inventory_incomplete_bg': '#FFFFFF',

            # ✅ [추가] 수리 관리 색상 (재출고 완료 vs 미출고)
            'repair_completed_fg': '#000000',    # 재출고 글자색
            'repair_completed_bg': '#FFCCBC',    # 재출고 배경색 (연한 살구색)
            'repair_incomplete_fg': '#000000',   # 미출고 글자색
            'repair_incomplete_bg': '#FFFFFF',   # 미출고 배경색
        }

        self.color_buttons = {}
        self.setup_ui()
        self.load_current_colors()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # 안내 메시지
        info_label = QtWidgets.QLabel(
            "각 데이터의 완료/미완료 상태에 따른 색상을 설정합니다.\n"
            "색상 버튼을 클릭하여 원하는 색상을 선택하세요."
        )
        info_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # 구분선
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(line)

        # 스크롤 영역
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)

        # 색상 설정 섹션들
        categories = [
            ("주문 정보", "order",          ("완료", "미완료")),
            ("발주 정보", "purchase",       ("완료", "미완료")),
            ("납품 정보", "delivery",       ("완료", "미완료")),
            ("제품 생산", "product",        ("완료", "미완료")),
            ("품목 관리", "product_master", ("판매중", "내부용")),
            ("재고 현황", "inventory", ("재고 있음", "재고 없음")),
            # ✅ [추가] 수리 관리 카테고리
            ("수리 관리", "repair", ("재출고/자체", "진행중")),
        ]

        for category_label, category_key, labels in categories:
            group = self.create_color_group(category_label, category_key, labels)
            scroll_layout.addWidget(group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

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
        btn_save.clicked.connect(self.save_colors)
        btn_cancel.clicked.connect(self.reject)

        button_layout.addWidget(btn_reset)
        button_layout.addStretch()
        button_layout.addWidget(btn_save)
        button_layout.addWidget(btn_cancel)

        layout.addLayout(button_layout)

    def create_color_group(self, title, key_prefix, labels=("완료", "미완료")):
        """색상 설정 그룹 박스 생성"""
        group = QtWidgets.QGroupBox(title)
        group_layout = QtWidgets.QVBoxLayout()

        # 완료 상태
        completed_layout = QtWidgets.QHBoxLayout()
        completed_label = QtWidgets.QLabel(f"{labels[0]}:")
        completed_label.setMinimumWidth(80)  # 라벨 너비 조금 늘림

        fg_completed_key = f"{key_prefix}_completed_fg"
        bg_completed_key = f"{key_prefix}_completed_bg"

        fg_completed_btn = self.create_color_button(fg_completed_key, "글자색")
        bg_completed_btn = self.create_color_button(bg_completed_key, "배경색")

        completed_layout.addWidget(completed_label)
        completed_layout.addWidget(QtWidgets.QLabel("글자색:"))
        completed_layout.addWidget(fg_completed_btn)
        completed_layout.addWidget(QtWidgets.QLabel("배경색:"))
        completed_layout.addWidget(bg_completed_btn)
        completed_layout.addStretch()

        # 미완료 상태
        incomplete_layout = QtWidgets.QHBoxLayout()
        incomplete_label = QtWidgets.QLabel(f"{labels[1]}:")
        incomplete_label.setMinimumWidth(80)

        fg_incomplete_key = f"{key_prefix}_incomplete_fg"
        bg_incomplete_key = f"{key_prefix}_incomplete_bg"

        fg_incomplete_btn = self.create_color_button(fg_incomplete_key, "글자색")
        bg_incomplete_btn = self.create_color_button(bg_incomplete_key, "배경색")

        incomplete_layout.addWidget(incomplete_label)
        incomplete_layout.addWidget(QtWidgets.QLabel("글자색:"))
        incomplete_layout.addWidget(fg_incomplete_btn)
        incomplete_layout.addWidget(QtWidgets.QLabel("배경색:"))
        incomplete_layout.addWidget(bg_incomplete_btn)
        incomplete_layout.addStretch()

        group_layout.addLayout(completed_layout)
        group_layout.addLayout(incomplete_layout)
        group.setLayout(group_layout)

        return group

    def create_color_button(self, color_key, label_text):
        """색상 선택 버튼 생성"""
        button = QtWidgets.QPushButton(label_text)
        button.setMinimumSize(80, 25)
        button.clicked.connect(lambda: self.choose_color(color_key, button))
        self.color_buttons[color_key] = button
        return button

    def choose_color(self, color_key, button):
        """색상 선택 대화상자 열기"""
        current_color = button.property("color") or self.default_colors[color_key]
        color = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(current_color),
            self,
            "색상 선택"
        )

        if color.isValid():
            color_hex = color.name()
            button.setProperty("color", color_hex)
            self.update_button_color(button, color_hex)

    def update_button_color(self, button, color_hex):
        """버튼 배경색 업데이트"""
        # 밝기에 따라 글자색 자동 조정
        color = QtGui.QColor(color_hex)
        brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
        text_color = "#000000" if brightness > 128 else "#FFFFFF"

        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {color_hex};
                color: {text_color};
                border: 1px solid #999;
                border-radius: 3px;
                padding: 5px;
            }}
            QPushButton:hover {{
                border: 2px solid #0078d4;
            }}
        """)

    def load_current_colors(self):
        """현재 저장된 색상 불러오기"""
        for color_key, button in self.color_buttons.items():
            setting_key = f"colors/{color_key}"
            # 설정이 없으면 기본값 사용
            color_hex = self.settings.value(setting_key, self.default_colors.get(color_key, "#FFFFFF"))
            button.setProperty("color", color_hex)
            self.update_button_color(button, color_hex)

    def reset_to_defaults(self):
        """기본 색상으로 초기화"""
        reply = QtWidgets.QMessageBox.question(
            self,
            "기본값으로 초기화",
            "모든 색상을 기본값으로 초기화하시겠습니까?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            for color_key, button in self.color_buttons.items():
                default_color = self.default_colors[color_key]
                button.setProperty("color", default_color)
                self.update_button_color(button, default_color)

    def save_colors(self):
        """색상 설정 저장"""
        for color_key, button in self.color_buttons.items():
            color_hex = button.property("color")
            if color_hex:
                setting_key = f"colors/{color_key}"
                self.settings.setValue(setting_key, color_hex)

        QtWidgets.QMessageBox.information(
            self,
            "저장 완료",
            "색상 설정이 저장되었습니다.\n"
            "변경사항을 적용하려면 해당 탭을 새로고침하세요."
        )
        self.accept()