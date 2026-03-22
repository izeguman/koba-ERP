# app/ui/log_settings_dialog.py

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QSettings

class LogSettingsDialog(QtWidgets.QDialog):
    """로그 설정 대화상자"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)

        if settings:
            self.settings = settings
        else:
            self.settings = QSettings("KOBATECH", "ProductionManagement")

        self.setWindowTitle("로그 설정")
        self.setFixedWidth(400)
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # 안내 메시지
        info_label = QtWidgets.QLabel(
            "오류 추적을 위한 로그 파일 보관 기간을 설정합니다.\n"
            "설정된 기간이 지난 오래된 로그 파일은 자동으로 삭제됩니다."
        )
        info_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(info_label)

        # 구분선
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(line)

        # 폼 레이아웃
        form_layout = QtWidgets.QFormLayout()
        
        self.spin_retention = QtWidgets.QSpinBox()
        self.spin_retention.setRange(1, 365)
        self.spin_retention.setSuffix(" 일")
        self.spin_retention.setValue(30) # 기본값
        
        form_layout.addRow("로그 보관 기간:", self.spin_retention)
        
        layout.addLayout(form_layout)
        
        layout.addStretch()

        # 구분선
        line2 = QtWidgets.QFrame()
        line2.setFrameShape(QtWidgets.QFrame.HLine)
        line2.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(line2)
        
        # 알림
        warning_label = QtWidgets.QLabel("※ 설정 변경은 프로그램을 다시 시작한 후에 적용됩니다.")
        warning_label.setStyleSheet("color: #d9534f; font-size: 11px;")
        layout.addWidget(warning_label)

        # 버튼
        button_layout = QtWidgets.QHBoxLayout()
        btn_save = QtWidgets.QPushButton("저장")
        btn_cancel = QtWidgets.QPushButton("취소")

        btn_save.clicked.connect(self.save_settings)
        btn_cancel.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(btn_save)
        button_layout.addWidget(btn_cancel)

        layout.addLayout(button_layout)

    def load_settings(self):
        """현재 설정 불러오기"""
        days = self.settings.value("logging/retention_days", 30, type=int)
        self.spin_retention.setValue(days)

    def save_settings(self):
        """설정 저장"""
        days = self.spin_retention.value()
        self.settings.setValue("logging/retention_days", days)
        
        QtWidgets.QMessageBox.information(
            self,
            "저장 완료",
            f"로그 보관 기간이 {days}일로 설정되었습니다.\n"
            "변경사항은 다음 실행 시부터 적용됩니다."
        )
        self.accept()
