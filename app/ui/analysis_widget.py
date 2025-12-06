# app/ui/analysis_widget.py

import matplotlib

matplotlib.use('QtAgg')  # Qt 백엔드 사용 설정

from PySide6 import QtWidgets, QtCore
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc
import platform

from ..db import (get_defect_rate_by_model, get_defect_stats_by_model, get_defect_trend_monthly)

# --- 한글/일본어 폰트 설정 (수정됨) ---
system_name = platform.system()
if system_name == 'Windows':
    # ✅ 리스트로 설정하면 앞에서부터 순서대로 찾아서 적용합니다.
    # 1순위: 맑은 고딕 (한글)
    # 2순위: Meiryo (일본어 표준)
    # 3순위: Yu Gothic (윈도우 내장 일본어)
    font_name = ["Malgun Gothic", "Meiryo", "Yu Gothic", "Segoe UI"]
elif system_name == 'Darwin':    # Mac
    font_name = ["AppleGothic", "Hiragino Sans"]
else:
    font_name = ["NanumGothic"]

try:
    # ✅ font.family에 리스트를 전달하여 다국어 지원 강화
    rc('font', family=font_name)
    rc('axes', unicode_minus=False)
except:
    print("폰트 설정 실패. 기본 폰트를 사용합니다.")


class AnalysisWidget(QtWidgets.QWidget):
    """품질 분석 차트를 보여주는 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # 1. 헤더 (제목 + 새로고침 버튼)
        header_layout = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("품질 불량 분석 대시보드")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; margin-bottom: 10px;")

        # ✅ [추가] 기간 선택 콤보박스
        self.combo_period = QtWidgets.QComboBox()
        self.combo_period.addItem("최근 1년", 12)
        self.combo_period.addItem("최근 2년", 24)
        self.combo_period.addItem("최근 3년", 36)
        self.combo_period.addItem("최근 4년", 48)
        self.combo_period.addItem("최근 5년", 60)
        self.combo_period.setCurrentIndex(4)  # 기본값 5년
        self.combo_period.currentIndexChanged.connect(self.load_data)  # 변경 시 자동 로드

        btn_refresh = QtWidgets.QPushButton("데이터 새로고침")
        btn_refresh.setCursor(QtCore.Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self.load_data)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(QtWidgets.QLabel("분석 기간:"))  # ✅ 라벨 추가
        header_layout.addWidget(self.combo_period)  # ✅ 콤보박스 추가
        header_layout.addWidget(btn_refresh)
        layout.addLayout(header_layout)

        # 2. 차트 영역 (그리드 레이아웃)
        self.chart_area = QtWidgets.QWidget()
        self.chart_layout = QtWidgets.QGridLayout(self.chart_area)
        self.chart_layout.setSpacing(15)  # 차트 간 간격

        # (1) 불량 증상 파레토 차트 (Bar)
        self.fig_symptom = Figure(figsize=(5, 4), dpi=100)
        self.canvas_symptom = FigureCanvas(self.fig_symptom)
        self.chart_layout.addWidget(self.canvas_symptom, 0, 0)

        # (2) 모델별 점유율 (Pie)
        self.fig_model = Figure(figsize=(5, 4), dpi=100)
        self.canvas_model = FigureCanvas(self.fig_model)
        self.chart_layout.addWidget(self.canvas_model, 0, 1)

        # (3) 월별 발생 추이 (Line) - 하단에 길게 배치
        self.fig_trend = Figure(figsize=(5, 3), dpi=100)
        self.canvas_trend = FigureCanvas(self.fig_trend)
        self.chart_layout.addWidget(self.canvas_trend, 1, 0, 1, 2)

        layout.addWidget(self.chart_area)

    def load_data(self):
        """DB에서 데이터를 가져와 모든 차트를 다시 그립니다."""
        if hasattr(self, 'combo_period'):
            months = self.combo_period.currentData()
        else:
            months = 60  # 기본값 5년

        self.plot_defect_rate_by_model(months)  # ✅ 교체됨 (인자 전달)
        self.plot_model_share(months)
        self.plot_monthly_trend(months)

    def plot_defect_rate_by_model(self, months=60):
        """모델별 불량률(생산량 대비) 막대 그래프"""
        data = get_defect_rate_by_model(months)  # [(모델명, 생산, 불량, 율), ...]

        self.fig_symptom.clear()  # 변수명은 fig_symptom 그대로 재사용 (화면 위치 유지)
        ax = self.fig_symptom.add_subplot(111)

        if not data:
            ax.text(0.5, 0.5, "데이터 없음", ha='center', va='center', transform=ax.transAxes)
            ax.set_title("모델별 불량률 분석 (데이터 없음)")
        else:
            # 데이터 분리
            models = []
            rates = []
            details = []  # (불량/생산) 라벨용

            for row in data:
                # 모델명 콤마 앞부분만 사용
                name = str(row[0]).replace('\t', ' ')
                if ',' in name: name = name.split(',')[0]
                models.append(name.strip())

                prod_cnt = row[1]
                defect_cnt = row[2]
                rate = row[3]

                rates.append(rate)
                details.append(f"{defect_cnt}건/{prod_cnt}대")

            # 막대 그래프 그리기 (불량률 %)
            bars = ax.bar(models, rates, color='#d62728', alpha=0.8)  # 빨간색 계열

            # 제목 설정
            years = months // 12
            ax.set_title(f"모델별 불량률 (Worst 10) - 최근 {years}년", fontsize=12, pad=10)
            ax.set_ylabel("불량률 (%)")
            ax.grid(axis='y', linestyle='--', alpha=0.5)

            # X축 라벨 회전
            ax.tick_params(axis='x', rotation=30, labelsize=9)

            # 막대 위에 정보 표시 (불량률% + 건수/생산)
            for i, bar in enumerate(bars):
                height = bar.get_height()
                label_text = f"{height:.1f}%\n({details[i]})"

                ax.annotate(label_text,
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3), textcoords="offset points",
                            ha='center', va='bottom', fontsize=8)

        # 여백 조정
        try:
            self.fig_symptom.tight_layout()
        except Exception:
            pass

        self.canvas_symptom.draw()

    def plot_model_share(self, months=60):
        """모델별 불량 점유율 파이 차트"""
        data = get_defect_stats_by_model(months)  # [(모델명, 횟수), ...]
        self.fig_model.clear()
        ax = self.fig_model.add_subplot(111)

        if not data:
            ax.text(0.5, 0.5, "데이터 없음", ha='center', va='center', transform=ax.transAxes)
            ax.set_title("모델별 점유율 (데이터 없음)")
        else:
            # ✅ [수정] 탭 제거 + 쉼표(,) 기준으로 앞부분만 표시
            models = []
            for row in data:
                text = str(row[0]).replace('\t', ' ')

                # 콤마가 있으면 그 앞부분만 잘라냄
                if ',' in text:
                    text = text.split(',')[0]

                models.append(text.strip())  # 앞뒤 공백 제거

            counts = [row[1] for row in data]

            # 파이 차트 그리기
            wedges, texts, autotexts = ax.pie(counts, labels=models, autopct='%1.1f%%',
                                              startangle=140, textprops={'fontsize': 9},
                                              colors=plt.cm.Pastel1.colors)
            years = months // 12
            ax.set_title(f"제품(모델)별 불량 점유율 - 최근 {years}년", fontsize=12, pad=10)

        self.fig_model.tight_layout()
        self.canvas_model.draw()

    def plot_monthly_trend(self, months=12):  # ✅ 인자 추가
        """월별 불량 추이 꺾은선 그래프"""
        data = get_defect_trend_monthly(months)  # ✅ DB에 개월 수 전달
        self.fig_trend.clear()
        ax = self.fig_trend.add_subplot(111)

        if not data:
            ax.text(0.5, 0.5, "데이터 없음", ha='center', va='center', transform=ax.transAxes)
            ax.set_title("월별 추이 (데이터 없음)")
        else:
            # 탭 문자 제거
            months_label = [str(row[0]).replace('\t', ' ') for row in data]
            counts = [row[1] for row in data]

            ax.plot(months_label, counts, marker='o', linestyle='-', color='#1f77b4', linewidth=2)

            # ✅ 제목에 기간 표시
            years = months // 12
            ax.set_title(f"월별 불량 발생 추이 (최근 {years}년)", fontsize=12, pad=10)

            ax.grid(True, linestyle='--', alpha=0.7)
            ax.set_ylabel("건수")

            # 데이터가 많아지면(2년 이상) 모든 숫자를 표시하면 지저분하므로
            # 1년(12개월) 이하일 때만 숫자를 표시하거나, 간격을 두고 표시
            if len(data) <= 12:
                for i, txt in enumerate(counts):
                    ax.annotate(txt, (months_label[i], counts[i]), textcoords="offset points", xytext=(0, 8),
                                ha='center')

            # X축 라벨이 많으면 겹치므로 회전 및 간격 조정
            if len(data) > 12:
                ax.tick_params(axis='x', rotation=45, labelsize=8)
                # 데이터가 너무 많으면 라벨을 띄엄띄엄 표시 (예: 3개월마다)
                import matplotlib.ticker as ticker
                ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=20))

        try:
            self.fig_trend.tight_layout()
        except Exception:
            pass

        self.canvas_trend.draw()