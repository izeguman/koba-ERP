# app/ui/profit_widget.py

import matplotlib

matplotlib.use('QtAgg')

# 경고 제어를 위한 모듈
import warnings

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib import rc
import platform

from ..db import get_yearly_financials, get_model_profitability, get_available_data_years

# 한글 폰트 설정
system_name = platform.system()
font_name = ["Malgun Gothic", "Meiryo", "Yu Gothic", "Segoe UI"] if system_name == 'Windows' else ["AppleGothic"]
rc('font', family=font_name)
rc('axes', unicode_minus=False)


class ProfitWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # 1. 헤더
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("수익성 및 사업 분석")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")

        self.combo_years = QtWidgets.QComboBox()

        # 1. 기본 옵션 (3년, 5년)
        self.combo_years.addItem("최근 3년", {"type": "range", "value": 3})
        self.combo_years.addItem("최근 5년", {"type": "range", "value": 5})

        # 2. DB에 있는 실제 연도들 추가 (예: 2025년, 2024년...)
        available_years = get_available_data_years()
        for year in available_years:
            self.combo_years.addItem(f"{year}년 단독", {"type": "year", "value": year})

        self.combo_years.currentIndexChanged.connect(self.load_data)

        btn_refresh = QtWidgets.QPushButton("새로고침")
        btn_refresh.clicked.connect(self.load_data)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.combo_years)
        header.addWidget(btn_refresh)
        layout.addLayout(header)

        # 2. KPI 카드 (상단 요약)
        self.kpi_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(self.kpi_layout)

        # 3. 메인 차트 (연도별 손익)
        self.fig_main = Figure(figsize=(8, 4), dpi=100)
        self.canvas_main = FigureCanvas(self.fig_main)
        layout.addWidget(self.canvas_main)

        # 4. 하단: 모델별 분석 테이블
        # ✅ [수정] lbl_table -> self.lbl_table (멤버 변수로 변경)
        self.lbl_table = QtWidgets.QLabel("모델별 수익 기여도 Top 20 (총 마진액 순)")
        self.lbl_table.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(self.lbl_table)  # ✅ self.lbl_table 로 추가

        # ✅ [수정] 컬럼 8개로 확장 및 순서 정리
        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "모델명", "판매수량",
            "판매단가(JPY)", "매입단가(KRW)",
            "총 매출액(예상)", "총 매입액(예상)",  # 👈 새로 추가됨
            "대당 마진", "총 마진액(예상)"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

    def create_kpi_card(self, title, value, color="#333"):
        """간단한 KPI 카드 위젯 생성"""
        group = QtWidgets.QGroupBox()
        group.setStyleSheet("QGroupBox { border: 1px solid #ddd; border-radius: 5px; background: white; }")
        vbox = QtWidgets.QVBoxLayout(group)

        lbl_title = QtWidgets.QLabel(title)
        lbl_title.setStyleSheet("color: #666; font-size: 12px;")
        lbl_title.setAlignment(Qt.AlignCenter)

        lbl_value = QtWidgets.QLabel(value)
        lbl_value.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
        lbl_value.setAlignment(Qt.AlignCenter)

        vbox.addWidget(lbl_title)
        vbox.addWidget(lbl_value)
        return group

    def load_data(self):
        from datetime import datetime
        current_year = datetime.now().year

        # 1. 콤보박스 선택값 가져오기
        selection = self.combo_years.currentData()
        if not selection:
            selection = {"type": "range", "value": 3}  # 기본값

        filter_type = selection["type"]
        filter_value = selection["value"]

        # 2. 기간 표시 문자열(period_str) 생성
        if filter_type == 'year':
            period_str = f"{filter_value}년"
        else:
            period_str = f"최근 {filter_value}년"

        # ✅ [수정 1] 테이블 제목에 'years' 대신 'period_str' 사용
        self.lbl_table.setText(f"모델별 수익 기여도 Top 20 (총 마진액 순) - {period_str}")

        # 3. DB 데이터 조회
        data = get_yearly_financials(filter_type, filter_value)
        model_data = get_model_profitability(filter_type, filter_value)

        # 4. KPI 업데이트
        while self.kpi_layout.count():
            child = self.kpi_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        if data:
            # 데이터가 있으면 마지막 항목(최신)을 가져옴
            last_year_data = data[-1]

            # 합계 및 평균 계산
            total_rev = sum(d['revenue'] for d in data)
            avg_margin = sum(d['margin'] for d in data) / len(data)
            total_prod = sum(d['production_qty'] for d in data)

            # KPI 카드 생성
            # (단일 연도 선택 시에는 '2024년 매출' 등으로 표시됨)
            target_year_str = f"{last_year_data['year']}년" if filter_type == 'range' else period_str

            self.kpi_layout.addWidget(self.create_kpi_card(
                f"{target_year_str} 매출",
                f"{last_year_data['revenue'] / 1000000:,.0f}백만",
                "#007bff"
            ))

            self.kpi_layout.addWidget(self.create_kpi_card(
                f"{target_year_str} 매출총이익",
                f"{last_year_data['profit'] / 1000000:,.0f}백만",
                "#28a745"
            ))

            # ✅ [수정 2] KPI 제목에도 'period_str' 적용
            self.kpi_layout.addWidget(self.create_kpi_card(
                f"평균 이익률 ({period_str})",
                f"{avg_margin:.1f}%",
                "#dc3545"
            ))

            self.kpi_layout.addWidget(self.create_kpi_card(
                f"누적 판매 ({period_str})",
                f"{total_prod:,}대",
                "#666"
            ))

        # 5. 차트 그리기
        self.fig_main.clear()
        ax1 = self.fig_main.add_subplot(111)

        years_lbl = []
        revs = []
        costs = []
        margins = []

        for d in data:
            r_val = d['revenue'] / 1000000
            c_val = d['cost'] / 1000000
            p_val = d['profit'] / 1000000

            revs.append(r_val)
            costs.append(c_val)
            margins.append(d['margin'])

            years_lbl.append(f"{d['year']}\n(이익: {p_val:,.0f})")

        x = range(len(years_lbl))
        width = 0.35

        bars1 = ax1.bar([i - width / 2 for i in x], revs, width, label='매출(백만)', color='#4e79a7', alpha=0.8)
        bars2 = ax1.bar([i + width / 2 for i in x], costs, width, label='원가(백만)', color='#e15759', alpha=0.8)

        ax1.set_ylabel("금액 (백만원)")
        # ✅ [수정 3] 차트 제목에도 'period_str' 적용
        ax1.set_title(f"연도별 매출/원가 및 이익률 추이 ({period_str})")
        ax1.set_xticks(x)
        ax1.set_xticklabels(years_lbl)
        ax1.legend(loc='upper left')
        ax1.grid(axis='y', linestyle='--', alpha=0.3)

        # 값 표시 함수
        def add_value_labels(bars):
            for bar in bars:
                height = bar.get_height()
                ax1.annotate(f'{height:,.0f}',
                             xy=(bar.get_x() + bar.get_width() / 2, height),
                             xytext=(0, 3),
                             textcoords="offset points",
                             ha='center', va='bottom', fontsize=9, fontweight='bold')

        add_value_labels(bars1)
        add_value_labels(bars2)

        # 꺾은선 그래프
        ax2 = ax1.twinx()
        ax2.plot(x, margins, color='#f28e2b', marker='o', linewidth=2, label='이익률(%)')
        ax2.set_ylabel("이익률 (%)")

        max_margin = max(margins) if margins else 0
        min_margin = min(margins) if margins else 0
        ax2.set_ylim(min(0, min_margin - 5), max(30, max_margin + 10))
        ax2.legend(loc='upper right')

        for i, v in enumerate(margins):
            ax2.text(i, v + 2, f"{v:.1f}%", ha='center', color='#f28e2b', fontweight='bold')

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.fig_main.tight_layout()

        self.canvas_main.draw()

        # 6. 테이블 채우기
        self.table.setRowCount(0)

        # (합계 변수 초기화 - 기존 동일)
        sum_qty = 0;
        sum_total_rev = 0;
        sum_total_cost = 0;
        sum_total_margin = 0

        def set_right(item):
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return item

        for row_idx, row in enumerate(model_data):
            # qty는 이제 '판매수량'입니다.
            name, qty, avg_price_dummy, avg_cost_dummy, total_rev, total_cost, total_margin = row

            # 데이터 보정 (None 방지)
            qty = qty or 0
            total_rev = total_rev or 0
            total_cost = total_cost or 0
            total_margin = total_margin or 0

            # ✅ 역산으로 정확한 평균 단가 구하기 (총액 / 수량)
            real_avg_price = (total_rev / qty) if qty > 0 else 0
            real_avg_cost = (total_cost / qty) if qty > 0 else 0
            unit_margin = (total_margin / qty) if qty > 0 else 0

            # 합계 누적
            sum_qty += qty
            sum_total_rev += total_rev
            sum_total_cost += total_cost
            sum_total_margin += total_margin

            self.table.insertRow(row_idx)

            # 0. 모델명
            self.table.setItem(row_idx, 0, QtWidgets.QTableWidgetItem(str(name)))

            # 1. 판매수량
            self.table.setItem(row_idx, 1, set_right(QtWidgets.QTableWidgetItem(f"{qty:,}")))

            # 2. 평균판매가 (KRW로 환산된 값)
            self.table.setItem(row_idx, 2, set_right(QtWidgets.QTableWidgetItem(f"₩{real_avg_price:,.0f}")))

            # 3. 평균원가 (KRW)
            self.table.setItem(row_idx, 3, set_right(QtWidgets.QTableWidgetItem(f"₩{real_avg_cost:,.0f}")))

            # 4. 총 매출액
            self.table.setItem(row_idx, 4, set_right(QtWidgets.QTableWidgetItem(f"₩{total_rev:,.0f}")))

            # 5. 총 매출원가
            self.table.setItem(row_idx, 5, set_right(QtWidgets.QTableWidgetItem(f"₩{total_cost:,.0f}")))

            # 6. 대당 마진
            item_unit = QtWidgets.QTableWidgetItem(f"₩{unit_margin:,.0f}")
            if unit_margin > 0:
                item_unit.setForeground(QtGui.QBrush(QtGui.QColor("blue")))
            else:
                item_unit.setForeground(QtGui.QBrush(QtGui.QColor("red")))
            self.table.setItem(row_idx, 6, set_right(item_unit))

            # 7. 총 마진액
            item_total = QtWidgets.QTableWidgetItem(f"₩{total_margin:,.0f}")
            font = item_total.font();
            font.setBold(True);
            item_total.setFont(font)
            if total_margin > 0:
                item_total.setForeground(QtGui.QBrush(QtGui.QColor("#0066cc")))
            else:
                item_total.setForeground(QtGui.QBrush(QtGui.QColor("#dc3545")))
            self.table.setItem(row_idx, 7, set_right(item_total))

        # 소계(Total) 행 추가
        if model_data:
            last_row = self.table.rowCount()
            self.table.insertRow(last_row)

            bg_color = QtGui.QColor("#f0f0f0")
            font_bold = QtGui.QFont()
            font_bold.setBold(True)

            # ✅ 소계 아이템 생성 헬퍼 (기본 우측 정렬 추가)
            def create_subtotal_item(text, color_hex=None, align=Qt.AlignRight | Qt.AlignVCenter):
                item = QtWidgets.QTableWidgetItem(text)
                item.setBackground(bg_color)
                item.setFont(font_bold)
                item.setTextAlignment(align)  # ✅ 정렬 적용
                if color_hex:
                    item.setForeground(QtGui.QBrush(QtGui.QColor(color_hex)))
                return item

            # 0. 라벨 (중앙 정렬)
            self.table.setItem(last_row, 0, create_subtotal_item("소계 (Total)", align=Qt.AlignCenter))

            # 1~7 숫자 (우측 정렬)
            self.table.setItem(last_row, 1, create_subtotal_item(f"{sum_qty:,}"))
            self.table.setItem(last_row, 2, create_subtotal_item("-"))
            self.table.setItem(last_row, 3, create_subtotal_item("-"))
            self.table.setItem(last_row, 4, create_subtotal_item(f"₩{sum_total_rev:,.0f}", "#007bff"))
            self.table.setItem(last_row, 5, create_subtotal_item(f"₩{sum_total_cost:,.0f}"))
            self.table.setItem(last_row, 6, create_subtotal_item("-"))

            margin_color = "#0066cc" if sum_total_margin > 0 else "#dc3545"
            self.table.setItem(last_row, 7, create_subtotal_item(f"₩{sum_total_margin:,.0f}", margin_color))