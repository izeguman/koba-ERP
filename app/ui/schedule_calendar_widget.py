# app/ui/schedule_calendar_widget.py
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QCalendarWidget,
                               QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
                               QHeaderView, QLabel, QSpinBox, QPushButton, QHBoxLayout, QSplitter)
from PySide6.QtCore import Qt, QDate, Signal, QSignalBlocker
from PySide6.QtGui import QPainter, QBrush, QColor

from ..db import get_schedule_for_month, get_schedule_details_for_date, query_all, query_one
from .utils import apply_table_resize_policy
from datetime import datetime


# ── 표시용 포맷 ────────────────────────────────────────
def format_money(val: float | None) -> str:
    if val is None: return ""
    try:
        return f"{val:,.0f} 엔"
    except Exception:
        return str(val)


# ── 1개월 뷰 (커스텀 캘린더) ──────────────────────────────

class MonthlyCalendarWidget(QWidget):
    """1개월 뷰 위젯 (달력 + 상세 목록)"""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QSplitter(Qt.Vertical, self)

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.addWidget(layout)

        self.calendar = CustomCalendarWidget(self)

        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)

        details_label = QLabel("해당 날짜의 납품 일정:")
        self.details_list = QListWidget(self)
        self.details_list.setStyleSheet("QListWidget::item { padding: 5px; }")

        details_layout.addWidget(details_label)
        details_layout.addWidget(self.details_list)

        layout.addWidget(self.calendar)
        layout.addWidget(details_widget)

        # ✅ [수정] 달력(1) : 상세목록(2) 비율로 크기 조절 - 달력을 더 작게
        layout.setSizes([50, 270])

        self.calendar.currentPageChanged.connect(self.calendar.load_month_data)
        self.calendar.selectionChanged.connect(self.load_schedule_details)

        self.privacy_mode = False

    def set_privacy_mode(self, enabled: bool):
        self.privacy_mode = enabled
        self.load_schedule_details()

    def load_schedule_details(self):
        """달력에서 선택된 날짜의 상세 일정을 리스트에 로드"""
        self.details_list.clear()
        selected_date = self.calendar.selectedDate().toString("yyyy-MM-dd")

        details = get_schedule_details_for_date(selected_date)

        if not details:
            item = QListWidgetItem("선택한 날짜에 납품 일정이 없습니다.")
            item.setForeground(QBrush(QColor("#888")))
            self.details_list.addItem(item)
            return

        for row in details:
            order_no, product_name, ship_qty, amount_jpy, order_id, item_code = row

            text = f"[{order_no}] {product_name}\n"
            if self.privacy_mode:
                text += f"    수량: {ship_qty}개"
            else:
                text += f"    수량: {ship_qty}개 (예상 금액: {format_money(amount_jpy)})"

            item = QListWidgetItem(text)
            self.details_list.addItem(item)



class CustomCalendarWidget(QCalendarWidget):
    """'납품 일정'이 있는 날짜에 배경색을 칠하는 커스텀 캘린더"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.schedule_data = {}  # {'2025-10-15': 2, ...}

        # 기본 UI 설정
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setGridVisible(True)

        # ✅ [수정] 1. 스플리터가 달력을 줄일 수 있도록 최소 높이를 0으로 설정
        self.setMinimumHeight(0)
        # ✅ [추가] 2. 최소 너비도 0으로 설정하여 가로 크기도 줄일 수 있게 함
        self.setMinimumWidth(0)

        # ✅ [수정] 2. 크기 정책을 '확장'이 아닌 '선호'로 변경
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)

    def load_month_data(self, year=None, month=None):
        """표시된 월이 변경될 때 DB에서 일정 데이터를 새로고침"""
        if year is None or month is None:
            today = QDate.currentDate()
            year = today.year()
            month = today.month()

        self.schedule_data = get_schedule_for_month(year, month)

        # ✅ [수정] db.py의 파라미터가 2개로 변경됨
        try:
            self.schedule_data = get_schedule_for_month(year, month)
        except Exception as e:
            print(f"월별 납품 일정 조회 오류 (파라미터 확인): {e}")
            self.schedule_data = {}  # 오류 시 초기화

        # 데이터가 변경되었으므로 캘린더 UI를 강제로 다시 그리도록 요청
        self.updateCells()


    def paintCell(self, painter: QPainter, rect: QtCore.QRect, date: QDate):
        """캘린더의 각 날짜(셀)를 그릴 때 호출됨"""

        # 1. Qt의 기본 날짜 그리기를 먼저 실행
        super().paintCell(painter, rect, date)

        # 2. 이 날짜에 일정이 있는지 확인
        date_str = date.toString("yyyy-MM-dd")
        if date_str in self.schedule_data:
            # 3. ✅ [수정] 배경색 칠하기 (빨간 점 로직 삭제)
            painter.save()

            # 연한 노란색 (#FFFACD), 반투명(150)
            bg_color = QColor("#FFFACD")
            bg_color.setAlpha(150)
            painter.fillRect(rect, QBrush(bg_color))

            painter.restore()

class TimelineWidget(QWidget):
    """
    N개월 뷰 위젯 (트리 타임라인)
    [수정됨] 가장 먼 납기일부터 역순으로 N개월 데이터를 자동 조회
    """

    # ✅ [추가] 컬럼 폭이 변경되었음을 알리는 시그널
    widths_changed_signal = Signal(list)

    def __init__(self, months_to_load: int, parent=None, settings=None):
        super().__init__(parent)
        self.months_to_load = months_to_load

        self.settings = settings  # ✅ settings 저장
        # ✅ 3m, 6m, 12m 뷰별로 설정을 다르게 저장하기 위한 고유 이름
        self.table_name = "schedule_timeline_shared"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["날짜", "주문번호", "제품명", "수량", "예상 금액(엔)"])
        layout.addWidget(self.tree)

        self.setup_ui()
        # ✅ __init__ 시점에 load_data()를 호출하지 않음
        #    (메인 위젯의 on_tab_changed에서 호출됨)

    def setup_ui(self):
        # 0. 메인 레이아웃
        layout = self.layout()

        # 1. ✅ [수정] 컨트롤 레이아웃 (스핀박스, 조회 버튼 부활)
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(0, 5, 0, 5)

        today = datetime.now()

        self.lbl_year = QLabel("기준 연:")
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2020, 2040)
        self.year_spin.setValue(today.year)

        self.lbl_month = QLabel("기준 월:")
        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 12)
        self.month_spin.setValue(today.month)

        self.search_btn = QPushButton("조회")  # ✅ '조회' 버튼

        # ✅ [수정] '조회' 버튼은 'manual' 모드로 load_data 호출
        self.search_btn.clicked.connect(lambda: self.load_data(mode='manual'))

        self.info_label = QLabel("데이터 로드 중...")
        self.info_label.setStyleSheet("color: #333; font-style: italic;")

        control_layout.addWidget(self.lbl_year)
        control_layout.addWidget(self.year_spin)
        control_layout.addWidget(self.lbl_month)
        control_layout.addWidget(self.month_spin)
        control_layout.addSpacing(10)
        control_layout.addWidget(self.search_btn)
        control_layout.addStretch()
        control_layout.addWidget(self.info_label)  # ✅ info_label을 맨 뒤로

        # 2. 컨트롤 레이아웃을 메인 레이아웃의 맨 위에 추가
        layout.insertLayout(0, control_layout)

        # 3. 헤더 설정 (이전과 동일)
        # header = self.tree.header()
        # header.setSectionResizeMode(0, QHeaderView.Interactive)
        # header.setSectionResizeMode(1, QHeaderView.Interactive)
        # header.setSectionResizeMode(2, QHeaderView.Interactive)
        # header.setSectionResizeMode(3, QHeaderView.Interactive)
        # header.setSectionResizeMode(4, QHeaderView.Interactive)
        # header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.setAlternatingRowColors(True)

        apply_table_resize_policy(self.tree)
        
        # ✅ [수정] 가로 스크롤바 활성화 (utils 정책 오버라이드)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree.header().setStretchLastSection(False)

        # 4. 컬럼 폭 저장/복원 (이전과 동일)
        header = self.tree.header()
        header.sectionResized.connect(self.save_column_widths)
        self.restore_column_widths()

    def set_privacy_mode(self, enabled: bool):
        self.privacy_mode = enabled
        # 컬럼 숨김/보임 (예상 금액: 4번)
        if hasattr(self, 'tree'):
            if enabled:
                # 숨기기 전 저장
                if not self.tree.isColumnHidden(4):
                    self._timeline_temp_widths = [self.tree.columnWidth(col) for col in range(self.tree.columnCount())]
                self.tree.setColumnHidden(4, True)
            else:
                self.tree.setColumnHidden(4, False)
                # 복원
                if hasattr(self, '_timeline_temp_widths') and self._timeline_temp_widths:
                    # 복원 시에는 시그널 차단 (apply_column_widths 재사용 불가하므로 직접 구현)
                    header = self.tree.header()
                    blocker = QSignalBlocker(header)
                    try:
                        for col, width in enumerate(self._timeline_temp_widths):
                            if col < self.tree.columnCount():
                                if col == 4 and width < 50: width = 100
                                header.resizeSection(col, width)
                    finally:
                        blocker.unblock()

        # 데이터 다시 로드 (상단 합계 텍스트 갱신 위해)
        self.load_data(mode='auto') # 기본적으로 auto로 리로드

    def load_data(self, mode='auto'):  # ✅ [수정] 'mode' 인자 추가
        """
        [수정됨] 데이터 로드 (자동/수동 모드)
        - mode='auto': 오늘 기준 1/2/3개월 전 ~ N개월치
        - mode='manual': 스핀박스 기준 0개월 전 ~ N개월치
        - 정렬 순서: 오름차순 (과거 -> 미래)
        - 현재 월 하이라이트, 월별 총 매출/원가 계산
        """
        self.tree.clear()

        # 프라이버시 모드 확인 (속성이 없으면 False로 초기화)
        if not hasattr(self, 'privacy_mode'):
            self.privacy_mode = False

        try:
            from dateutil.relativedelta import relativedelta

            # --- [수정] 기준 날짜 계산: 자동/수동 모드 분기 ---

            today_dt_obj = datetime.now()
            self.today_month_str = today_dt_obj.strftime("%Y-%m")

            base_dt_obj = None  # 기준 날짜
            months_to_go_back = 0  # 과거로 몇 달 이동할지

            if mode == 'manual':
                # --- 1. 수동 '조회' 모드 ---
                selected_year = self.year_spin.value()
                selected_month = self.month_spin.value()
                # 기준일 = 선택한 연/월의 1일
                base_dt_obj = datetime(selected_year, selected_month, 1)
                months_to_go_back = 0  # 수동 조회는 과거로 이동하지 않음

            else:  # 'auto' 모드 (기본값)
                # --- 2. 자동 '탭 클릭' 모드 ---
                base_dt_obj = today_dt_obj  # 기준일 = 오늘

                if self.months_to_load == 3:
                    months_to_go_back = 1
                elif self.months_to_load == 6:
                    months_to_go_back = 2
                elif self.months_to_load == 12:
                    months_to_go_back = 3

            # 3. 공통 계산 로직
            start_dt_obj = base_dt_obj - relativedelta(months=months_to_go_back)
            end_dt_obj = start_dt_obj + relativedelta(months=self.months_to_load)

            start_date = start_dt_obj.strftime("%Y-%m-%d")
            end_date = end_dt_obj.strftime("%Y-%m-%d")

            # 4. 라벨 업데이트
            if mode == 'manual':
                self.info_label.setText(f"기간: {start_date} ~ {end_date} (수동 조회)")
            else:
                self.info_label.setText(f"기간: {start_date} ~ {end_date} (자동 조회)")
            # --- [수정] 끝 ---

            # 5. 원가 맵 (이전과 동일)
            cost_map_cents = {}
            try:
                rows_cost = query_all(
                    "SELECT item_code, purchase_price_krw FROM product_master WHERE purchase_price_krw > 0")
                for item_code, purchase_price_krw_cents in rows_cost:
                    if item_code: cost_map_cents[item_code] = purchase_price_krw_cents
            except Exception as e:
                print(f"원가 맵 생성 오류: {e}")

            # 6. DB 조회 SQL (이전과 동일)
            sql = """
                SELECT * FROM (
                    -- 쿼리 A: '분할 납기'가 설정된 건 (order_shipments)
                    SELECT
                        os.due_date, o.order_no, oi.product_name, os.ship_qty,
                        (oi.unit_price_cents * os.ship_qty) / 100.0 as amount_jpy,
                        oi.item_code
                    FROM order_shipments os
                    JOIN order_items oi ON os.order_item_id = oi.id
                    JOIN orders o ON oi.order_id = o.id
                    WHERE os.due_date BETWEEN ? AND ?

                    UNION ALL

                    -- 쿼리 B: '단순 납기' 건 (orders.final_due 또는 req_due)
                    SELECT 
                        COALESCE(o.final_due, o.req_due) as due_date, o.order_no, oi.product_name, oi.qty as ship_qty,
                        (oi.unit_price_cents * oi.qty) / 100.0 as amount_jpy,
                        oi.item_code
                    FROM orders o
                    JOIN order_items oi ON o.id = oi.order_id
                    WHERE 
                        oi.id NOT IN (SELECT DISTINCT order_item_id FROM order_shipments)
                        AND COALESCE(o.final_due, o.req_due) BETWEEN ? AND ?
                )
                ORDER BY due_date ASC, order_no ASC
            """
            rows = query_all(sql, (start_date, end_date, start_date, end_date))

            # 7. 루프 및 UI 렌더링 (이전과 동일)
            if not rows:
                item = QTreeWidgetItem(self.tree, ["해당 기간에 납품 일정이 없습니다."])
                return

            current_month_group = None
            current_date_group = None
            last_month = "";
            last_date = ""
            month_total_amount = 0;
            month_total_cost = 0

            for row in rows:
                due_date, order_no, product_name, ship_qty, amount_jpy, item_code = row

                month_str = due_date[:7]
                if month_str != last_month:
                    if current_month_group:
                        old_text = current_month_group.text(0)
                        if self.privacy_mode:
                            current_month_group.setText(0, f"{old_text}")
                        else:
                            current_month_group.setText(0,
                                                        f"{old_text}  |  총매출: {month_total_amount:,.0f} 엔  |  총원가: {month_total_cost:,.0f} 원")

                    month_total_amount = 0;
                    month_total_cost = 0
                    current_month_group = QTreeWidgetItem(self.tree, [f"{month_str} (월별)"])
                    current_month_group.setExpanded(True)
                    font = current_month_group.font(0);
                    font.setBold(True);
                    current_month_group.setFont(0, font)

                    if month_str == self.today_month_str:
                        current_month_group.setBackground(0, QBrush(QColor("#FFFACD")))
                    else:
                        current_month_group.setBackground(0, QBrush(QColor("#f0f0f0")))

                    last_month = month_str;
                    last_date = ""

                if due_date != last_date:
                    current_date_group = QTreeWidgetItem(current_month_group, [due_date])
                    current_date_group.setExpanded(True)
                    last_date = due_date

                amount_float = amount_jpy or 0
                month_total_amount += amount_float

                cost_in_cents = cost_map_cents.get(item_code, 0)
                item_cost_krw = (cost_in_cents / 100.0) * (ship_qty or 0)
                month_total_cost += item_cost_krw

                item = QTreeWidgetItem(current_date_group)
                item.setText(1, order_no);
                item.setText(2, product_name)
                item.setText(3, f"{ship_qty:,} 개");
                item.setText(4, f"{amount_float:,.0f}")

            # 8. 마지막 월 총액 업데이트 (이전과 동일)
            if current_month_group:
                old_text = current_month_group.text(0)
                if self.privacy_mode:
                     current_month_group.setText(0, f"{old_text}")
                else:
                    current_month_group.setText(0,
                                            f"{old_text}  |  총매출: {month_total_amount:,.0f} 엔  |  총원가: {month_total_cost:,.0f} 원")

        except ImportError:
            QTreeWidgetItem(self.tree, [f"오류: 'dateutil' 라이브러리가 필요합니다. (pip install python-dateutil)"])
        except Exception as e:
            QTreeWidgetItem(self.tree, [f"데이터 로드 중 오류 발생: {e}"])
            print(f"타임라인 로드 오류: {e}")
            import traceback
            traceback.print_exc()

    def apply_column_widths(self, widths: list):

        """(새 함수) 외부에서 전달받은 컬럼 폭을 트리에 적용"""
        header = self.tree.header()
        # [핵심] 시그널을 차단하여, 이 함수가 save_column_widths를 다시 호출하지 않도록 함
        blocker = QSignalBlocker(header)
        try:
            for i, width in enumerate(widths):
                if i < header.count():
                    header.resizeSection(i, int(width))
        finally:
            blocker.unblock()  # PySide6 에서는 unblock()

    def save_column_widths(self):
        """(수정) 컬럼 폭 저장 및 시그널 방출"""
        if not self.settings: return
        widths = []
        for i in range(self.tree.columnCount()):
            widths.append(self.tree.columnWidth(i))

        self.settings.setValue(f"{self.table_name}/column_widths", widths)

        # ✅ [추가] 다른 탭에 변경 사항을 알리는 시그널 방출
        self.widths_changed_signal.emit(widths)

    def restore_column_widths(self):
        """(수정) 컬럼 폭 복원 (apply_column_widths 사용)"""
        if not self.settings: return
        widths = self.settings.value(f"{self.table_name}/column_widths")

        if widths:
            # ✅ [수정] apply_column_widths 함수를 호출하여 적용
            self.apply_column_widths(widths)
        else:
            # 기본값 설정 (QSignalBlocker 불필요, header.resizeSection 사용)
            header = self.tree.header()
            header.resizeSection(0, 100)  # 날짜
            header.resizeSection(1, 100)  # 주문번호
            # 2 (제품명) is stretch
            header.resizeSection(3, 80)  # 수량
            header.resizeSection(4, 100)  # 예상 금액


class ScheduleCalendarWidget(QWidget):
    """'납품 달력' 메인 탭 위젯"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings

        # ✅ [수정] QVBoxLayout -> QHBoxLayout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ✅ [수정] 메인 레이아웃을 QSplitter로 변경
        main_splitter = QSplitter(Qt.Horizontal, self)
        layout.addWidget(main_splitter)

        # --- 1. 왼쪽 패널 (달력 + 상세 목록) ---
        # (MonthlyCalendarWidget가 이미 이 구조를 가지고 있음)
        self.month_view = MonthlyCalendarWidget(self)
        main_splitter.addWidget(self.month_view)

        # --- 2. 오른쪽 패널 (3/6/12개월 탭) ---
        right_pane = QWidget()
        right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.timeline_tabs = QTabWidget()  # ✅ '목록형 일정'용 새 탭 위젯
        right_layout.addWidget(self.timeline_tabs)
        right_pane.setLayout(right_layout)

        # 3/6/12개월 뷰 생성
        self.timeline_3m = TimelineWidget(months_to_load=3, parent=self, settings=self.settings)
        self.timeline_6m = TimelineWidget(months_to_load=6, parent=self, settings=self.settings)
        self.timeline_12m = TimelineWidget(months_to_load=12, parent=self, settings=self.settings)

        # ✅ [수정] 새 탭 위젯(timeline_tabs)에 탭 추가
        self.timeline_tabs.addTab(self.timeline_3m, "3개월 (목록)")
        self.timeline_tabs.addTab(self.timeline_6m, "6개월 (목록)")
        self.timeline_tabs.addTab(self.timeline_12m, "1년 (목록)")

        main_splitter.addWidget(right_pane)

        # ✅ [수정] 좌우 스플리터 초기 크기 설정 (왼쪽 25%, 오른쪽 75%)
        main_splitter.setSizes([250, 750])

        # --- 3. 시그널 연결 ---
        # [수정] 탭 전환 시그널을 timeline_tabs에 연결
        self.timeline_tabs.currentChanged.connect(self.on_timeline_tab_changed)

        # [유지] 컬럼 폭 동기화 시그널 연결
        self.timeline_3m.widths_changed_signal.connect(self.on_timeline_widths_changed)
        self.timeline_6m.widths_changed_signal.connect(self.on_timeline_widths_changed)
        self.timeline_12m.widths_changed_signal.connect(self.on_timeline_widths_changed)

        self.timeline_tabs.setCurrentIndex(1)

    def refresh_all_views(self):
        # 1. 왼쪽 (달력) 새로고침
        if hasattr(self, 'month_view'):
            self.month_view.calendar.load_month_data()
            self.month_view.load_schedule_details()

        # 2. 오른쪽 (목록)의 *현재 탭* 새로고침
        if hasattr(self, 'timeline_tabs'):
            current_widget = self.timeline_tabs.currentWidget()
            if isinstance(current_widget, TimelineWidget):
                current_widget.load_data()

    # ✅ on_timeline_widths_changed 슬롯
    def on_timeline_widths_changed(self, widths_list):
        """(새 함수) 한 탭에서 컬럼 폭이 변경되면 나머지 탭에도 적용"""
        sender = self.sender()  # 시그널을 보낸 위젯

        if sender != self.timeline_3m:
            self.timeline_3m.apply_column_widths(widths_list)

        if sender != self.timeline_6m:
            self.timeline_6m.apply_column_widths(widths_list)

        if sender != self.timeline_12m:
            self.timeline_12m.apply_column_widths(widths_list)

    def on_timeline_tab_changed(self, index):
        """'목록형 일정' 탭이 변경될 때 해당 탭의 데이터를 새로고침"""
        current_widget = self.timeline_tabs.widget(index)

    def set_privacy_mode(self, enabled: bool):
        """재무 정보 숨기기 설정"""
        # 1. 왼쪽 패널 (MonthlyCalendarWidget) - 상세 리스트 갱신 필요
        #    (달력 자체엔 금액이 없으나, 하단 리스트엔 금액이 있음)
        if hasattr(self, 'month_view'):
             # 강제 리로드하여 format_money 등에서 숨김 처리?
             # 하지만 format_money는 전역 함수이므로, 여기서 제어하기 어려움.
             # 대신 month_view 내부에 플래그를 심거나, load_schedule_details를 수정해야 함.
             self.month_view.set_privacy_mode(enabled)

        # 2. 오른쪽 패널 (TimelineWidget들)
        #    예상 금액(엔): 4번 컬럼, 총매출/총원가 숨김
        if hasattr(self, 'timeline_3m'): self.timeline_3m.set_privacy_mode(enabled)
        if hasattr(self, 'timeline_6m'): self.timeline_6m.set_privacy_mode(enabled)
        if hasattr(self, 'timeline_12m'): self.timeline_12m.set_privacy_mode(enabled)
