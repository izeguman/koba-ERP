# app/ui/exchange_rate_dialog.py

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Qt
from datetime import datetime
from ..db import get_monthly_exchange_rates, save_monthly_exchange_rates


class ExchangeRateDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("월별 기준 환율 설정 (100엔 당 원화)")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)

        self.current_year = datetime.now().year
        self.rate_inputs = {}  # {월: QDoubleSpinBox}

        self.setup_ui()
        self.load_rates()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # 1. 연도 선택
        year_layout = QtWidgets.QHBoxLayout()
        btn_prev = QtWidgets.QPushButton("◀")
        btn_prev.clicked.connect(lambda: self.change_year(-1))

        self.lbl_year = QtWidgets.QLabel(f"{self.current_year}년")
        self.lbl_year.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.lbl_year.setAlignment(Qt.AlignCenter)

        btn_next = QtWidgets.QPushButton("▶")
        btn_next.clicked.connect(lambda: self.change_year(1))

        year_layout.addWidget(btn_prev)
        year_layout.addWidget(self.lbl_year)
        year_layout.addWidget(btn_next)
        layout.addLayout(year_layout)

        # 2. 안내 문구
        info = QtWidgets.QLabel("※ 100엔(JPY)당 원화(KRW) 환율을 입력하세요.\n(예: 100엔 = 905원이면 '905' 입력)")
        info.setStyleSheet("color: #666; margin: 10px 0;")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)

        # 3. 월별 입력 그리드
        grid_widget = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(grid_widget)
        grid.setSpacing(10)

        for month in range(1, 13):
            lbl = QtWidgets.QLabel(f"{month}월:")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(0, 5000)  # 범위
            spin.setDecimals(2)  # 소수점 2자리
            spin.setSingleStep(1.0)
            spin.setSuffix(" 원")
            spin.setAlignment(Qt.AlignRight)

            self.rate_inputs[month] = spin

            row = (month - 1) // 2
            col = (month - 1) % 2 * 2  # 0, 2

            grid.addWidget(lbl, row, col)
            grid.addWidget(spin, row, col + 1)

        layout.addWidget(grid_widget)

        # 4. 일괄 적용 도구
        batch_layout = QtWidgets.QHBoxLayout()
        self.spin_batch = QtWidgets.QDoubleSpinBox()
        self.spin_batch.setRange(0, 5000)
        self.spin_batch.setValue(900)
        self.spin_batch.setSuffix(" 원")

        btn_batch = QtWidgets.QPushButton("전체 일괄 적용")
        btn_batch.clicked.connect(self.apply_batch_rate)

        batch_layout.addStretch()
        batch_layout.addWidget(QtWidgets.QLabel("일괄 값:"))
        batch_layout.addWidget(self.spin_batch)
        batch_layout.addWidget(btn_batch)
        layout.addLayout(batch_layout)

        # 5. 저장 버튼
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Close)
        btn_box.accepted.connect(self.save_rates)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def change_year(self, delta):
        self.current_year += delta
        self.lbl_year.setText(f"{self.current_year}년")
        self.load_rates()

    def load_rates(self):
        """DB에서 해당 연도 환율을 불러와 입력창에 세팅"""
        data = get_monthly_exchange_rates(self.current_year)
        for month, rate in data.items():
            if rate > 0:
                self.rate_inputs[month].setValue(rate)
            else:
                self.rate_inputs[month].setValue(0)  # 데이터 없으면 0

    def apply_batch_rate(self):
        """일괄 값을 모든 월에 적용"""
        val = self.spin_batch.value()
        for spin in self.rate_inputs.values():
            spin.setValue(val)

    def save_rates(self):
        """입력된 값을 DB에 저장"""
        data_to_save = {}
        for month, spin in self.rate_inputs.items():
            data_to_save[month] = spin.value()

        try:
            save_monthly_exchange_rates(self.current_year, data_to_save)
            QtWidgets.QMessageBox.information(self, "저장 완료", f"{self.current_year}년 환율 정보가 저장되었습니다.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"저장 실패: {e}")