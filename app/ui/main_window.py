# app/ui/main_window.py
from PySide6 import QtGui
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QHeaderView, QMenu, QSplitter, QTabWidget
from PySide6.QtCore import QLocale, Qt, QSettings, QSignalBlocker
from PySide6.QtGui import QAction
from datetime import datetime

from .color_settings_dialog import ColorSettingsDialog
# ✅ query_all 함수 임포트 추가
from ..db import (get_conn, get_due_change_history, add_due_change_record, update_order_final_due_date,
                  add_or_update_product_master, search_product_master, is_purchase_completed,
                  query_all, init_db)
from .purchase_widget import PurchaseWidget
from .delivery_widget import DeliveryWidget
from .product_widget import ProductWidget
from .product_master_widget import ProductMasterWidget
from .autocomplete_widgets import ProductOrderDialog
from .schedule_dialog import ScheduleDialog
from .money_lineedit import MoneyLineEdit
from .repair_widget import RepairWidget
from .recall_widget import RecallWidget
from .schedule_calendar_widget import ScheduleCalendarWidget
from .bom_widget import BomWidget
from .utils import parse_due_text, apply_table_resize_policy, resource_path, get_icon_path
from .filter_settings_dialog import FilterSettingsDialog
from .analysis_widget import AnalysisWidget
from .profit_widget import ProfitWidget
from .tax_invoice_widget import TaxInvoiceWidget
from .outlook_sync import execute_outlook_operation_sync
from .document_generator import get_next_oa_serial, generate_order_acknowledgement


# ── 표시용 포맷 ──────────────────────────────────────────────────────────────
def format_money(val: float | None) -> str:
    if val is None:
        return ""
    try:
        return f"{val:,.0f}"
    except Exception:
        return str(val)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
        # ✅ DB 초기화 (테이블 생성 등)
        try:
             init_db()
        except Exception as e:
             print(f"DB Init Warning: {e}")

        self.setWindowTitle("KOBATECH 생산 관리 시스템")
        # self.resize(1600, 900)

        # 설정 저장을 위한 QSettings 초기화
        self.settings = QSettings("KOBATECH", "ProductionManagement")

        # ✅ [저장된 창 크기가 없으면 기본값(1600x900) 사용
        if self.settings.contains("MainWindow/geometry"):
            try:
                self.restoreGeometry(self.settings.value("MainWindow/geometry"))
            except Exception as e:
                print(f"윈도우 크기 복원 실패: {e}")
        else:
            self.resize(1600, 900)

        # ✅ 윈도우 상태(툴바 위치 등)도 복원
        if self.settings.contains("MainWindow/state"):
            self.restoreState(self.settings.value("MainWindow/state"))

        self.only_future = False
        self.show_all_billed = True
        self.show_all_inventory = False

        # ✅ 상호작용 선택 시 무한 루프 방지용 플래그
        self.is_selecting = False

        # ✅ 저장된 필터 설정 불러오기
        self.show_all_billed = self.settings.value("filters/orders_show_all", False, type=bool)
        self.show_all_inventory = self.settings.value("filters/inventory_show_all", False, type=bool)

        # ✅ 활성화된 주문 다이얼로그 추적용 리스트 (모달리스 지원)
        self.active_order_dialogs = []

        # ✅ 윈도우 아이콘 설정
        icon_path = get_icon_path()
        if icon_path:
            self.setWindowIcon(QtGui.QIcon(icon_path))

        # ✅ 로고 툴바를 먼저 생성
        self.setup_logo_toolbar()

        # ✅ 메뉴바 추가
        self.setup_menubar()

        self.main_tabs = QTabWidget()

        # 각 탭 위젯 생성 및 저장
        self.order_purchase_delivery_widget = self.create_order_purchase_delivery_widget()
        self.main_tabs.addTab(self.order_purchase_delivery_widget, "주문/발주/납품")

        self.product_master_widget = ProductMasterWidget(settings=self.settings)
        self.main_tabs.addTab(self.product_master_widget, "품목 관리")

        # ✅ [추가] 1. BOM 관리 위젯 생성
        self.bom_widget = BomWidget(settings=self.settings)
        # ✅ [추가] 2. 메인 탭에 "BOM 관리" 탭 추가
        self.main_tabs.addTab(self.bom_widget, "BOM 관리")

        self.product_production_widget = ProductWidget(settings=self.settings)
        self.main_tabs.addTab(self.product_production_widget, "제품 생산")

        # ✅ [추가] 재고 현황 테이블의 정렬 상태 불러오기
        self.current_inventory_sort_column = self.settings.value("inventory_table/sort_column", 0, type=int)
        sort_order_val = self.settings.value("inventory_table/sort_order", Qt.DescendingOrder)
        self.current_inventory_sort_order = Qt.SortOrder(sort_order_val)

        self.inventory_widget = self.create_inventory_widget()
        self.main_tabs.addTab(self.inventory_widget, "재고 현황")

        self.repair_widget = RepairWidget(settings=self.settings)
        self.main_tabs.addTab(self.repair_widget, "수리 관리")

        self.recall_widget = RecallWidget(settings=self.settings)
        self.main_tabs.addTab(self.recall_widget, "리콜 관리")

        # ✅ [추가] 1. 납품 달력 위젯 생성
        self.schedule_calendar_widget = ScheduleCalendarWidget(settings=self.settings)
        # ✅ [추가] 2. 메인 탭에 "납품 달력" 탭 추가
        self.main_tabs.addTab(self.schedule_calendar_widget, "납품 달력")

        # ✅ [추가] 품질 분석 탭 추가
        self.analysis_widget = AnalysisWidget()
        self.main_tabs.addTab(self.analysis_widget, "품질 분석")

        # ✅ [추가] 수익 분석 탭
        self.profit_widget = ProfitWidget(settings=self.settings)
        self.main_tabs.addTab(self.profit_widget, "수익 분석")

        # ✅ [추가] 세금계산서 관리 탭
        self.tax_invoice_widget = TaxInvoiceWidget(settings=self.settings)
        self.main_tabs.addTab(self.tax_invoice_widget, "세금계산서 관리")

        # 🆕 탭 전환 시 자동 새로고침 연결
        self.main_tabs.currentChanged.connect(self.on_tab_changed)

        self.setCentralWidget(self.main_tabs)

        # ✅ 선택된 아이템의 텍스트 색상을 흰색으로 변경하는 스타일시트 추가
        # QTableWidget, QListWidget 등에서 선택된 아이템의 전경색을 흰색으로 설정
        self.setStyleSheet("""
                            /* 1. 기본 스타일 정의 (글자색, 배경색) */
                            QTableWidget::item,
                            QListWidget::item,
                            QTreeView::item {
                                outline: none; /* 기본적으로 모든 아이템의 아웃라인 제거 */
                            }
                            QTableView {
                                outline: 0; /* 테이블 뷰 자체의 포커스 아웃라인 제거 */
                            }

                            /* 2. '선택된' 아이템의 스타일 */
                            QTableWidget::item:selected,
                            QListWidget::item:selected,
                            QTreeView::item:selected {
                                background-color: #0078d4; 
                                color: white;             
                                border: none;
                            }

                            /* 3. 포커스를 얻었을 때의 테두리 강제 제거 (최대 우선순위) */
                            QTableWidget::item:focus,
                            QListWidget::item:focus,
                            QTreeView::item:focus,
                            QTableWidget::item:selected:focus { /* 선택 + 포커스 상태 */
                                border: none;
                                outline: none; 
                            }

                            /* 4. 콤보박스 드롭다운 리스트의 선택된 아이템 스타일 */
                            QComboBox QAbstractItemView::item:selected {
                                background-color: #0078d4; 
                                color: white;             
                            }

                            /* 5. 마우스 오버 시 스타일 (테두리 제거) */
                            QTableWidget::item:hover,
                            QListWidget::item:hover,
                            QTreeView::item:hover {
                                border: none;
                                outline: none;
                            }
                        """)
        self.statusBar().showMessage("준비됨")

        # ✅ 저장된 정렬 상태 불러오기 (기본값: 7-최초납기, 0-오름차순)
        self.current_sort_column = self.settings.value("orders_table/sort_column", 7, type=int)
        # [수정] type=int를 제거하여 QSettings가 Enum 객체를 직접 읽도록 함
        sort_order_val = self.settings.value("orders_table/sort_order", Qt.AscendingOrder)
        self.current_sort_order = Qt.SortOrder(sort_order_val)

        self.load_due_list(only_future=False)
        self.refresh_order_purchase_delivery()

        # ✅ [추가] 초기 프라이버시 모드 적용
        is_privacy = self.settings.value("view/privacy_mode", False, type=bool)
        self.apply_privacy_mode(is_privacy)

        # ✅ [핵심] 3개 테이블의 *선택 집합 변경* 시그널을 핸들러에 연결
        self.table.itemSelectionChanged.connect(self.on_order_selected)
        if hasattr(self, 'purchase_widget') and self.purchase_widget:
            self.purchase_widget.table.itemSelectionChanged.connect(self.on_purchase_selected)
        if hasattr(self, 'delivery_widget') and self.delivery_widget:
            self.delivery_widget.table.itemSelectionChanged.connect(self.on_delivery_selected)


    def setup_logo_toolbar(self):
        """로고 전용 툴바 생성"""
        try:
            from pathlib import Path
            logo_path = Path(__file__).parent / "logo.png"

            if logo_path.exists():
                logo_toolbar = self.addToolBar("Logo")
                logo_toolbar.setMovable(False)
                logo_toolbar.setFloatable(False)

                # ✅ 툴바 구분선 제거
                logo_toolbar.setStyleSheet("""
                    QToolBar {
                        border: none;
                        spacing: 0px;
                    }
                """)

                '''# 왼쪽: 시스템 정보
                info_label = QtWidgets.QLabel("KOBATECH 생산 관리 시스템 v1.0")
                info_label.setStyleSheet("color: #666; font-size: 11px; padding-left: 15px;")
                logo_toolbar.addWidget(info_label)'''

                # 스페이서
                spacer = QtWidgets.QWidget()
                spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
                logo_toolbar.addWidget(spacer)

                # 오른쪽: 로고
                logo_label = QtWidgets.QLabel()
                pixmap = QtGui.QPixmap(str(logo_path))
                scaled_pixmap = pixmap.scaledToHeight(35, Qt.SmoothTransformation)
                logo_label.setPixmap(scaled_pixmap)
                logo_label.setStyleSheet("padding: 5px 15px;")

                logo_toolbar.addWidget(logo_label)

        except Exception as e:
            print(f"로고 툴바 생성 오류: {e}")

    def setup_menubar(self):
        """메뉴바 설정 (로고 제외)"""
        menubar = self.menuBar()

        # 설정 메뉴
        settings_menu = menubar.addMenu("설정")

        # 보기 메뉴
        view_menu = menubar.addMenu("보기")
        
        # ✅ [추가] 재무 정보 숨기기 (프라이버시 모드)
        self.privacy_mode_action = QAction("재무 정보 숨기기 (프라이버시 모드)", self)
        self.privacy_mode_action.setCheckable(True)
        self.privacy_mode_action.setChecked(self.settings.value("view/privacy_mode", False, type=bool))
        self.privacy_mode_action.triggered.connect(self.toggle_privacy_mode)
        view_menu.addAction(self.privacy_mode_action)

        # 필터 초기값 설정 (설정 메뉴에 계속)
        filter_settings_action = QAction("필터 초기값 설정", self)
        filter_settings_action.triggered.connect(self.open_filter_settings)
        settings_menu.addAction(filter_settings_action)

        # ✅ [추가] 환율 관리 메뉴
        exchange_rate_action = QAction("환율 관리 (기준 환율)", self)
        exchange_rate_action.setStatusTip("수익 분석을 위한 월별 기준 환율을 설정합니다")
        exchange_rate_action.triggered.connect(self.open_exchange_rate_settings)
        settings_menu.addAction(exchange_rate_action)

        # ✅ [추가] 계산 설정 메뉴
        calc_settings_action = QAction("계산 및 자동화 설정", self)
        calc_settings_action.setStatusTip("금액 계산 방식을 설정합니다 (e.g., 반올림)")
        calc_settings_action.triggered.connect(self.open_calculation_settings)
        settings_menu.addAction(calc_settings_action)

        # ✅ 색상 설정 추가
        color_settings_action = QAction("색상 설정", self)
        color_settings_action.setStatusTip("데이터 상태별 색상을 설정합니다")
        color_settings_action.triggered.connect(self.open_color_settings)
        settings_menu.addAction(color_settings_action)

        # ✅ [추가] 로그 설정
        log_settings_action = QAction("로그 설정", self)
        log_settings_action.setStatusTip("로그 파일 보관 기간을 설정합니다")
        log_settings_action.triggered.connect(self.open_log_settings)
        settings_menu.addAction(log_settings_action)

        # 디스플레이 초기화 액션
        reset_display_action = QAction("디스플레이 초기화", self)
        reset_display_action.setStatusTip("모든 테이블 컬럼 폭과 트리 확장 상태를 기본값으로 되돌립니다")
        reset_display_action.triggered.connect(self.reset_display_settings)
        settings_menu.addAction(reset_display_action)

        # 도구 메뉴
        tools_menu = self.menuBar().addMenu("도구(&T)")

        # 1. 미래 일정 동기화 (기본/빠름)
        sync_future_action = QAction("Outlook 동기화 (오늘 이후)", self)
        sync_future_action.setShortcut("F5")
        sync_future_action.setStatusTip("오늘 이후 납품 예정인 건만 Outlook과 동기화합니다.")
        sync_future_action.triggered.connect(self.run_outlook_sync_future)  # ✅ 연결
        tools_menu.addAction(sync_future_action)

        # 2. 전체 동기화 (느림/완전)
        sync_all_action = QAction("Outlook 전체 동기화 (모든 일정)", self)
        sync_all_action.setStatusTip("과거 데이터를 포함한 모든 주문을 Outlook과 동기화합니다.")
        sync_all_action.triggered.connect(self.run_outlook_sync_all)  # ✅ 연결
        tools_menu.addAction(sync_all_action)

        tools_menu.addSeparator()

        # 3. 완료된 일정 삭제
        cleanup_action = QAction("Outlook 완료된 일정 삭제", self)
        cleanup_action.triggered.connect(self.run_outlook_cleanup)
        tools_menu.addAction(cleanup_action)

        # 4. 전체 일정 삭제 (NEW)
        delete_all_action = QAction("Outlook 일정 전체 삭제 (초기화)", self)
        delete_all_action.setStatusTip("Outlook의 모든 작업을 삭제합니다. (주의!)")
        delete_all_action.triggered.connect(self.run_outlook_delete_all)  # ✅ 연결
        tools_menu.addAction(delete_all_action)

        # 도움말 메뉴
        help_menu = menubar.addMenu("도움말")

        about_action = QAction("정보", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def open_log_settings(self):
        """로그 설정 다이얼로그 열기"""
        try:
            from .log_settings_dialog import LogSettingsDialog
            dialog = LogSettingsDialog(self, settings=self.settings)
            dialog.exec()
        except ImportError:
             QtWidgets.QMessageBox.critical(self, "오류", "로그 설정 파일을 찾을 수 없습니다 (log_settings_dialog.py)")


    def open_color_settings(self):
        """색상 변경 다이얼로그를 엽니다."""
        # ✅ 다이얼로그를 생성할 때 self.settings 객체를 전달합니다.
        dialog = ColorSettingsDialog(self, settings=self.settings)

        # ✅ 사용자가 '저장'을 눌렀을 때만 목록을 새로고침하도록 수정
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_due_list()


    def open_calculation_settings(self):
        """(새 함수) 계산 설정 다이얼로그 열기"""
        # calculation_settings_dialog.py 파일이 필요합니다.
        try:
            from .calculation_settings_dialog import CalculationSettingsDialog
            dialog = CalculationSettingsDialog(self, settings=self.settings)
            dialog.exec()
        except ImportError:
            QtWidgets.QMessageBox.critical(
                self, "오류",
                "계산 설정 파일을 찾을 수 없습니다 (calculation_settings_dialog.py)"
            )


    def open_exchange_rate_settings(self):
        """환율 관리 다이얼로그 열기"""
        try:
            from .exchange_rate_dialog import ExchangeRateDialog
            dialog = ExchangeRateDialog(self)
            dialog.exec()
        except ImportError:
            QtWidgets.QMessageBox.critical(self, "오류", "환율 설정 파일(exchange_rate_dialog.py)을 찾을 수 없습니다.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"환율 설정 창 열기 실패: {e}")


    def refresh_order_purchase_delivery(self):
        """
        주문/발주/납품을 한 번에 새로고침한다.
        - 주문: self.load_due_list(self.only_future)
        - 발주: self.purchase_widget.load_purchase_list()
        - 납품: self.delivery_widget.load_delivery_list()
        """
        try:
            # 1) 주문
            #   MainWindow 내부에 이미 존재하는 주문 새로고침 함수입니다.
            #   기존 코드에서도 self.load_due_list(...)를 여러 곳에서 사용합니다.
            self.load_due_list(self.only_future)

            # 2) 발주
            #   PurchaseWidget 인스턴스가 만들어져 있다면 테이블 새로고침
            if hasattr(self, 'purchase_widget') and self.purchase_widget:
                self.purchase_widget.load_purchase_list()

            # 3) 납품
            #   DeliveryWidget 인스턴스가 만들어져 있다면 테이블 새로고침
            if hasattr(self, 'delivery_widget') and self.delivery_widget:
                self.delivery_widget.load_delivery_list()

        except Exception as e:
            # 예외 시 사용자에게 알림
            QtWidgets.QMessageBox.warning(self, "오류", f"새로고침 중 오류가 발생했습니다:\n{e}")


    def refresh_current_tab(self):
        """✅ 현재 선택된 탭 새로고침"""
        current_index = self.main_tabs.currentIndex()
        tab_name = self.main_tabs.tabText(current_index)

        if "주문/발주/납품" in tab_name:
            self.load_due_list()
            if hasattr(self, 'purchase_widget'):
                self.purchase_widget.load_purchase_list()
            if hasattr(self, 'delivery_widget'):
                self.delivery_widget.load_delivery_list()
        elif "제품 생산" in tab_name:
            if hasattr(self, 'product_production_widget'):
                self.product_production_widget.load_product_list()
        elif "제품 마스터" in tab_name:
            if hasattr(self, 'product_master_widget'):
                self.product_master_widget.load_product_list()
        elif "재고 현황" in tab_name:
            self.load_inventory_list()

    def open_filter_settings(self):
        """필터 설정 대화상자 열기"""
        from .filter_settings_dialog import FilterSettingsDialog
        dialog = FilterSettingsDialog(self)
        dialog.exec()


    def reset_display_settings(self):
        """디스플레이 설정 초기화 (데이터는 안전합니다)"""
        reply = QtWidgets.QMessageBox.question(
            self,
            "디스플레이 초기화",
            "테이블 컬럼 폭과 트리 확장 상태를 기본값으로 되돌리시겠습니까?\n\n"
            "✓ 초기화 항목:\n"
            "  • 주문/발주/납품 테이블 컬럼 폭\n"
            "  • 제품 마스터/생산 테이블 컬럼 폭\n"
            "  • 재고 현황 테이블 컬럼 폭\n"
            "  • 납품 품목 입력창 컬럼 폭\n"
            "  • 제품 트리 확장 상태\n\n"
            "✓ 안전:\n"
            "  • 데이터베이스 내용은 변경되지 않습니다\n"
            "  • 모든 업무 데이터는 그대로 유지됩니다",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            # 1. 초기화할 모든 컬럼 폭 설정 키(이름) 목록을 직접 정의합니다.
            column_width_keys = [
                "order_table/column_widths",
                "purchase_table/column_widths",
                "delivery_main_table/column_widths",
                "delivery_item_table/column_widths",
                "product_table/column_widths",
                "product_master_table/column_widths",
                "inventory_table/column_widths",
                "repair_table/column_widths"
            ]

            # 2. 목록에 있는 설정들을 하나씩 명시적으로 삭제합니다.
            for key in column_width_keys:
                self.settings.remove(key)

            # 3. 트리 확장 상태도 초기화
            self.settings.remove("product_tree/expanded_state")

            # 4. 창 크기/위치 관련 설정도 명시적으로 삭제합니다.
            self.settings.remove("MainWindow/geometry")
            self.settings.remove("MainWindow/state")

            QtWidgets.QMessageBox.information(
                self,
                "완료",
                "디스플레이 설정이 초기화되었습니다.\n\n"
                "프로그램을 다시 시작하면 기본 레이아웃이 적용됩니다.\n\n"
                "⚠️ 초기화 후에는 컬럼을 조정하지 말고 바로 프로그램을 종료하세요.\n"
                "컬럼을 조정하면 다시 설정이 저장됩니다.\n\n"
                "✓ 모든 데이터는 안전하게 보존되었습니다."
            )
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "오류", f"초기화 중 오류 발생: {e}")

    def show_about(self):
        """프로그램 정보 표시"""
        QtWidgets.QMessageBox.about(
            self,
            "KOBATECH 생산 관리 시스템",
            "<h3>KOBATECH 생산 관리 시스템</h3>"
            "<p>버전: 1.25.02</p>"
            "<p>제품 생산 및 재고 관리를 위한 통합 시스템</p>"
            "<br>"
            "<p><b>주요 기능:</b></p>"
            "<ul>"
            "<li>주문/발주/납품 관리</li>"
            "<li>아웃룩 일정 동기화 기능</li>"
            "<li>품목 관리</li>"
            "<li>BOM 관리</li>"
            "<li>제품 생산 관리</li>"
            "<li>재고 현황 추적</li>"
            "<li>수리 이력 관리</li>"
            "<li>납품 이력 및 계획 관리</li>"
            "<li>품질 분석</li>"
            "<li>수익 분석</li>"
            "<li>리콜 관리</li>"
            "<li>OA, 발주서, 납품서, 송장, 청구서 자동 생성</li>"
            "</ul>"
            "<br>"
            "<p>© 2025 KOBATECH. All rights reserved.</p>"
        )



    def toggle_privacy_mode(self, checked):
        """재무 정보 숨기기 (프라이버시 모드) 토글"""
        self.settings.setValue("view/privacy_mode", checked)
        self.apply_privacy_mode(checked)
        
        state_text = "활성화" if checked else "비활성화"
        QtWidgets.QMessageBox.information(self, "설정 변경", f"프라이버시 모드가 {state_text}되었습니다.")

    def apply_privacy_mode(self, enabled: bool):
        """모든 위젯에 프라이버시 모드 적용"""
        
        # 1. ProductMasterWidget
        if hasattr(self, 'product_master_widget'):
            if hasattr(self.product_master_widget, 'set_privacy_mode'):
                self.product_master_widget.set_privacy_mode(enabled)
                
        # 2. PurchaseWidget
        if hasattr(self, 'purchase_widget'):
            if hasattr(self.purchase_widget, 'set_privacy_mode'):
                self.purchase_widget.set_privacy_mode(enabled)
                
        # 3. DeliveryWidget
        if hasattr(self, 'delivery_widget'):
            if hasattr(self.delivery_widget, 'set_privacy_mode'):
                self.delivery_widget.set_privacy_mode(enabled)
                
        # 4. ScheduleCalendarWidget
        if hasattr(self, 'schedule_calendar_widget'):
            if hasattr(self.schedule_calendar_widget, 'set_privacy_mode'):
                self.schedule_calendar_widget.set_privacy_mode(enabled)
                
        # 5. InventoryWidget (Inventory Table in MainWindow)
        if hasattr(self, 'inv_value_label') and hasattr(self, 'inv_revenue_label'):
            if enabled:
                self.inv_value_label.setText("총 재고금액: ****")
                self.inv_revenue_label.setText("예상 매출액: ****")
            else:
                # 프라이버시 모드 해제 시, 현재 탭이 재고 현황이면 데이터를 다시 로드하여 금액 복구
                # (단순 텍스트 복구가 아니라 최신 데이터 기준 재계산)
                if self.main_tabs.tabText(self.main_tabs.currentIndex()) == "재고 현황":
                    self.load_inventory_data()
        
        # 6. ProfitWidget (탭 접근 제어 또는 내용 숨김)
        # ... (Existing logic) ...
        # 탭 인덱스 찾기
        profit_tab_index = -1
        for i in range(self.main_tabs.count()):
            if self.main_tabs.tabText(i) == "수익 분석":
                profit_tab_index = i
                break
        
        if profit_tab_index != -1:
            if enabled:
                if hasattr(self, 'profit_widget'):
                     if hasattr(self.profit_widget, 'set_privacy_mode'):
                        self.profit_widget.set_privacy_mode(enabled)
            else:
                if hasattr(self, 'profit_widget'):
                     if hasattr(self.profit_widget, 'set_privacy_mode'):
                        self.profit_widget.set_privacy_mode(enabled)

        # 7. MainWindow Order Table (주문금액 컬럼: 6번)
        # 7. MainWindow Order Table (주문금액 컬럼: 6번)
        # 테이블 컬럼 숨기기/보이기
        if enabled:
            # 숨기기 전 현재 폭 저장
            if not self.table.isColumnHidden(6):
                 self._order_table_temp_widths = [self.table.columnWidth(col) for col in range(self.table.columnCount())]
            self.table.setColumnHidden(6, True)
        else:
            self.table.setColumnHidden(6, False)
            
            # 저장된 폭 복원
            if hasattr(self, '_order_table_temp_widths') and self._order_table_temp_widths:
                 # 리사이즈 시그널을 차단하여 AdjacentColumnResizer에 의한 연쇄 작용 방지
                 header = self.table.horizontalHeader()
                 blocker = QSignalBlocker(header)
                 try:
                     for col, width in enumerate(self._order_table_temp_widths):
                         if col < self.table.columnCount():
                             if col == 6 and width < 50: width = 100 # 안전장치
                             self.table.setColumnWidth(col, width)
                 finally:
                     blocker.unblock()


    def on_tab_changed(self, index):
        """탭 전환 시 해당 탭의 데이터를 새로고침"""
        # 현재 선택된 탭의 이름을 가져옵니다.
        tab_name = self.main_tabs.tabText(index)

        # 각 탭의 이름에 맞는 새로고침 함수를 호출합니다.
        if tab_name == "주문/발주/납품":
            # ✅ 단일 진입점
            self.refresh_order_purchase_delivery()

        elif tab_name == "품목 관리":
            if hasattr(self, 'product_master_widget'):
                self.product_master_widget.load_product_list()

        elif tab_name == "BOM 관리":  # ✅ [추가 시작]
            if hasattr(self, 'bom_widget'):
                self.bom_widget.load_data_if_needed()
            # ✅ [추가 끝]

        elif tab_name == "제품 생산":
            if hasattr(self, 'product_production_widget'):
                self.product_production_widget.load_product_list()

        elif tab_name == "수리 관리":
            if hasattr(self, 'repair_widget'):
                self.repair_widget.load_repair_list()

        elif tab_name == "리콜 관리":
            if hasattr(self, 'recall_widget'):
                self.recall_widget.load_recall_list()

        elif tab_name == "세금계산서 관리":
            if hasattr(self, 'tax_invoice_widget'):
                self.tax_invoice_widget.load_data()
            if hasattr(self, 'recall_widget'):
                self.recall_widget.load_recall_list()

        elif tab_name == "재고 현황":
            self.load_inventory_data()

        elif tab_name == "납품 달력":
            if hasattr(self, 'schedule_calendar_widget'):
                self.schedule_calendar_widget.refresh_all_views()

        # ✅ [추가] 품질 분석 탭 선택 시 데이터 로드
        elif tab_name == "품질 분석":
            self.analysis_widget.load_data()

        # ✅ [추가] 탭 선택 시 데이터 로드
        elif tab_name == "수익 분석":
            if hasattr(self, 'profit_widget'):
                self.profit_widget.load_data()

    def save_column_widths(self, table: QtWidgets.QTableWidget, table_name: str):
        """🆕 테이블의 컬럼 크기 저장"""
        widths = []
        for col in range(table.columnCount()):
            widths.append(table.columnWidth(col))
        self.settings.setValue(f"{table_name}/column_widths", widths)


    def restore_column_widths(self, table: QtWidgets.QTableWidget, table_name: str):
        """🆕 테이블의 컬럼 크기 복원"""
        widths = self.settings.value(f"{table_name}/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < table.columnCount():
                    table.setColumnWidth(col, int(width))


    def save_all_column_widths(self):
        """🆕 모든 테이블의 컬럼 크기 저장"""
        self.save_column_widths(self.table, "orders_table")
        self.save_column_widths(self.inventory_table, "inventory_table")


    def create_order_purchase_delivery_widget(self):
        # 1) 래퍼 위젯 + 수직 레이아웃
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 2) 상단 바: 제목 + 통합 새로고침 버튼
        topbar = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("주문 / 발주 / 납품")
        title_label.setStyleSheet("font-weight: bold; color: #333;")

        btn_refresh_all = QtWidgets.QPushButton("새로고침")
        btn_refresh_all.setToolTip("주문/발주/납품 데이터를 한 번에 새로고침합니다.")
        btn_refresh_all.clicked.connect(self.refresh_order_purchase_delivery)  # ← #1 단계에서 만든 메서드

        topbar.addWidget(title_label)
        topbar.addStretch()
        topbar.addWidget(btn_refresh_all)
        layout.addLayout(topbar)

        # 3) 기존 메인 스플리터 구성 (원래 코드 유지)
        self.main_splitter = QSplitter(Qt.Vertical)

        order_widget = self.create_order_widget()

        # 1. 위젯을 먼저 생성합니다.
        self.purchase_widget = PurchaseWidget(settings=self.settings)  # 🆕 self.purchase_widget로 저장
        # 2. 생성된 위젯의 속성을 설정합니다.
        self.purchase_widget.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        # 1. 위젯을 먼저 생성합니다.
        self.delivery_widget = DeliveryWidget(self, settings=self.settings)  # ✅ settings 전달
        # 2. 생성된 위젯의 속성을 설정합니다.
        self.delivery_widget.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.delivery_widget.layout().setContentsMargins(10, 10, 10, 10)

        # ── 개별 새로고침 버튼 숨김 (통합 버튼만 노출)
        try:
            # 발주 탭 새로고침 버튼 (이미 self 속성으로 제공됨)
            if hasattr(self.purchase_widget, "btn_refresh_purchase"):
                self.purchase_widget.btn_refresh_purchase.setVisible(False)  # OK
            # 납품 탭 새로고침 버튼 (3-1 단계에서 self.btn_refresh로 승격 완료)
            if hasattr(self.delivery_widget, "btn_refresh"):
                self.delivery_widget.btn_refresh.setVisible(False)  # OK
            # 주문(직접 속성 접근)
            btn = order_widget.findChild(QtWidgets.QPushButton, "orders_refresh_button")
            if btn:
                btn.setVisible(False)
            else:
            # (대안) 직접 속성 접근: self.btn_refresh
                if hasattr(self, "btn_refresh"):
                    self.btn_refresh.setVisible(False)

        except Exception as e:
            print(f"하위 새로고침 버튼 숨김 실패: {e}")

        self.main_splitter.addWidget(order_widget)
        self.main_splitter.addWidget(self.purchase_widget)
        self.main_splitter.addWidget(self.delivery_widget)
        self.main_splitter.setSizes([300, 300, 300])

        # ✅ 스플리터 상태 복원
        if self.settings.contains("MainWindow/splitter_state"):
            self.main_splitter.restoreState(self.settings.value("MainWindow/splitter_state"))

        # 4) 스플리터를 레이아웃에 추가하고 래퍼 위젯 반환
        layout.addWidget(self.main_splitter)
        return widget

    def create_inventory_widget(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("재고 현황")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")

        refresh_btn = QtWidgets.QPushButton("새로고침")
        refresh_btn.clicked.connect(lambda: self.load_inventory_data())

        # 전체보기 버튼 추가
        self.btn_show_all_inventory = QtWidgets.QPushButton("전체보기" if self.show_all_inventory else "미완료만")
        self.btn_show_all_inventory.setCheckable(True)
        self.btn_show_all_inventory.setChecked(self.show_all_inventory)
        self.btn_show_all_inventory.toggled.connect(self.toggle_show_all_inventory)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        # ✅ [추가] 연간 재고 리포트 UI
        self.inv_year_spin = QtWidgets.QSpinBox()
        self.inv_year_spin.setRange(2020, 2030)
        self.inv_year_spin.setValue(datetime.now().year)
        self.inv_year_spin.setSuffix("년")
        self.inv_year_spin.valueChanged.connect(self.update_inventory_report_value)
        
        # ✅ [추가] 소모품 포함 체크박스
        self.inv_include_consumed_check = QtWidgets.QCheckBox("조립 소모품 포함(미판매분)")
        self.inv_include_consumed_check.setChecked(True)
        self.inv_include_consumed_check.toggled.connect(self.update_inventory_report_value)
        
        self.inv_value_label = QtWidgets.QLabel("총 재고금액: - 원")
        self.inv_value_label.setStyleSheet("font-weight: bold; color: #0d6efd;")
        
        self.inv_revenue_label = QtWidgets.QLabel("예상 매출액: - JPY")
        self.inv_revenue_label.setStyleSheet("font-weight: bold; color: #198754;")

        btn_export_report = QtWidgets.QPushButton("재고 보고서 내보내기")
        btn_export_report.clicked.connect(self.export_inventory_report)
        
        title_layout.addWidget(QtWidgets.QLabel("보고서 기준:"))
        title_layout.addWidget(self.inv_year_spin)
        title_layout.addWidget(self.inv_include_consumed_check)
        title_layout.addWidget(self.inv_value_label)
        title_layout.addWidget(self.inv_revenue_label)
        title_layout.addWidget(btn_export_report)
        
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.VLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        
        # [수정] 초기값 계산 호출
        self.update_inventory_report_value()
        title_layout.addWidget(line)
        
        
        title_layout.addWidget(refresh_btn)
        title_layout.addSpacing(12)
        title_layout.addWidget(self.btn_show_all_inventory)

        # ✅ 컬럼 개수 및 헤더 변경 (품목별로 표시하기 위함)
        self.inventory_table = QtWidgets.QTableWidget(0, 10)
        self.inventory_table.setHorizontalHeaderLabels(
            ["발주번호", "품목코드", "발주내용(품목)", "발주량", "생산량", "납품완료", "재고수량", "소모량", "할당량", "상태"]
        )
        self.inventory_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.inventory_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.inventory_table.setAlternatingRowColors(True)
        self.inventory_table.setSortingEnabled(True)

        # ✅ [추가] 우클릭 메뉴(컨텍스트 메뉴) 정책 설정
        self.inventory_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.inventory_table.customContextMenuRequested.connect(self.show_inventory_context_menu)

        self.inventory_table.verticalHeader().setDefaultSectionSize(25)
        self.inventory_table.setShowGrid(True)

        header = self.inventory_table.horizontalHeader()
        for col in range(self.inventory_table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        # ✅ 컬럼 폭 재설정
        self.inventory_table.setColumnWidth(0, 120)  # 발주번호
        self.inventory_table.setColumnWidth(1, 120)  # 품목코드
        self.inventory_table.setColumnWidth(2, 300)  # 발주내용(품목)
        self.inventory_table.setColumnWidth(3, 80)  # 발주량
        self.inventory_table.setColumnWidth(4, 80)  # 생산량
        self.inventory_table.setColumnWidth(5, 80)  # 납품완료
        self.inventory_table.setColumnWidth(6, 80)  # 재고수량
        self.inventory_table.setColumnWidth(7, 80)  # ✅ [추가] 소모량
        self.inventory_table.setColumnWidth(8, 80)  # ✅ [변경] 할당량 (7->8)
        self.inventory_table.setColumnWidth(9, 120)  # ✅ [변경] 상태 (8->9)

        self.restore_column_widths(self.inventory_table, "inventory_table")
        header.sectionResized.connect(lambda: self.save_column_widths(self.inventory_table, "inventory_table"))

        # ✅ [추가] 재고 현황 테이블 헤더에 시그널 연결 및 화살표 표시
        header.sortIndicatorChanged.connect(self.on_inventory_sort_changed)
        header.setSortIndicatorShown(True)

        layout.addLayout(title_layout)
        layout.addWidget(self.inventory_table)

        self.load_inventory_data()

        apply_table_resize_policy(self.inventory_table)
        
        # ✅ [수정] 가로 스크롤바 활성화 (utils 정책 오버라이드)
        self.inventory_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.inventory_table.horizontalHeader().setStretchLastSection(False)

        return widget


    def create_order_widget(self):
        """주문 위젯 생성"""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("주문 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        self.btn_new = QtWidgets.QPushButton("새 주문")
        self.btn_refresh = QtWidgets.QPushButton("새로고침")
        self.btn_refresh.setObjectName("orders_refresh_button")  # ← 식별자 부여
        self.btn_show_all = QtWidgets.QPushButton("전체보기" if self.show_all_billed else "미청구만")

        self.btn_new.clicked.connect(self.add_order_with_autocomplete)
        self.btn_refresh.clicked.connect(lambda: self.load_due_list(self.only_future))
        self.btn_show_all.setCheckable(True)
        self.btn_show_all.setChecked(self.show_all_billed)
        self.btn_show_all.toggled.connect(self.toggle_show_all_billed)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.btn_new)
        title_layout.addSpacing(12)
        title_layout.addWidget(self.btn_refresh)
        title_layout.addWidget(self.btn_show_all)

        # 테이블 컬럼: "품목수" → "품목/수량"으로 변경
        self.table = QtWidgets.QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            ["주문일", "주문번호", "품목코드", "Rev", "품목 / 수량", "제품명", "주문금액(엔)",
             "최초납기", "최종납기", "OA 발송", "완료처리"]
        )
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        # ✅ [수정] 다중 선택 모드로 변경 (연관 항목 다중 표시에 필수)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        # ✅ [수정] QTableWidget의 자체 정렬을 다시 켭니다. (화살표 표시용)
        self.table.setSortingEnabled(True)

        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.setShowGrid(True)

        self.table.itemDoubleClicked.connect(self.edit_order)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.table.setColumnWidth(0, 90)  # 주문일
        self.table.setColumnWidth(1, 80)  # 주문번호
        self.table.setColumnWidth(2, 210)  # 품목코드
        self.table.setColumnWidth(3, 40)  # Rev
        self.table.setColumnWidth(4, 90)  # 품목/수량 (폭 조정)
        self.table.setColumnWidth(5, 530)  # 제품명
        self.table.setColumnWidth(6, 80)  # 주문금액
        self.table.setColumnWidth(7, 80)  # 최초납기
        self.table.setColumnWidth(8, 110)  # 최종납기
        self.table.setColumnWidth(9, 80)  # OA 발송
        self.table.setColumnWidth(10, 90)  # 청구 완료

        if self.settings:
            self.restore_column_widths(self.table, "order_table")

        header.sectionResized.connect(lambda: self.save_column_widths(self.table, "order_table"))
        # ✅ [수정] 'sectionClicked' 대신 'sortIndicatorChanged' 시그널을 사용합니다.
        header.sortIndicatorChanged.connect(self.on_order_sort_changed)

        layout.addLayout(title_layout)
        layout.addWidget(self.table)

        self.order_data = []

        apply_table_resize_policy(self.table)
        
        # ✅ [수정] 가로 스크롤바 활성화 (utils 정책 오버라이드)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.horizontalHeader().setStretchLastSection(False)

        return widget

    def closeEvent(self, event):
        """프로그램 종료 시 모든 설정을 저장합니다."""
        try:
            # ✅ [추가] 1. 메인 윈도우의 현재 크기 및 위치를 저장
            self.settings.setValue("MainWindow/geometry", self.saveGeometry())
            # ✅ [추가] 2. 메인 윈도우의 상태(툴바 위치 등) 저장
            self.settings.setValue("MainWindow/state", self.saveState())

            # ✅ [추가] 3. 주문/발주/납품 탭의 스플리터(높낮이) 상태 저장
            if hasattr(self, 'main_splitter'):
                self.settings.setValue("MainWindow/splitter_state", self.main_splitter.saveState())

            # 4. 메인 윈도우의 테이블들 너비 저장
            self.save_column_widths(self.table, "order_table")
            self.save_column_widths(self.inventory_table, "inventory_table")

            # 5. 각 탭에 있는 위젯의 테이블 너비 저장
            if hasattr(self, 'purchase_widget'):
                self.purchase_widget.save_column_widths()
            if hasattr(self, 'delivery_widget'):
                self.delivery_widget.save_column_widths()
            if hasattr(self, 'product_master_widget'):
                self.product_master_widget.save_column_widths()
            if hasattr(self, 'product_production_widget'):
                self.product_production_widget.save_column_widths()
            if hasattr(self, 'repair_widget'):
                self.repair_widget.save_column_widths()

            # 6. 제품 생산 탭의 트리 확장 상태 저장
            if hasattr(self, 'product_production_widget'):
                self.product_production_widget.save_expanded_state()

        except Exception as e:
            print(f"설정 저장 중 오류 발생: {e}")

        event.accept()  # 창 닫기를 수락합니다.


    def toggle_show_all_billed(self, checked: bool):
        self.show_all_billed = checked
        self.btn_show_all.setText("전체보기" if checked else "미청구만")
        self.load_due_list(self.only_future)

    def on_order_sort_changed(self, column_index, order):
        """(새 함수) 주문 테이블 헤더의 정렬 표시기가 변경될 때 호출됩니다."""

        # 1. 현재 상태와 동일하면 (load_due_list에 의한 프로그래밍 방식 호출), 무시
        if self.current_sort_column == column_index and self.current_sort_order == order:
            return

        # 2. 사용자 클릭에 의한 변경이므로, 새 정렬 상태를 저장
        self.current_sort_column = column_index
        self.current_sort_order = order

        # 3. 새 정렬 상태를 QSettings에 저장
        self.settings.setValue("orders_table/sort_column", self.current_sort_column)
        self.settings.setValue("orders_table/sort_order", self.current_sort_order)  # enum도 int로 자동 저장됨

        # 4. 새 정렬 기준으로 데이터 목록을 다시 로드 (SQL 정렬)
        self.load_due_list(self.only_future)

    def show_context_menu(self, position):
        if self.table.itemAt(position) is None:
            return

        menu = QMenu(self)

        # [NEW] Order Acknowledgement 작성 메뉴 추가
        oa_action = menu.addAction("Order Acknowledgement 작성")
        oa_action.triggered.connect(self.create_oa_document)

        menu.addSeparator()

        edit_action = menu.addAction("수정")
        edit_action.triggered.connect(self.edit_order)

        delete_action = menu.addAction("삭제")
        delete_action.triggered.connect(self.delete_order)

        # ✅ '납기 변경' 메뉴를 다시 추가합니다.
        menu.addSeparator()
        due_change_action = menu.addAction("납기 일정 관리")
        due_change_action.triggered.connect(self.change_due_date)

        menu.exec_(self.table.mapToGlobal(position))

    def add_order_with_autocomplete(self):
        """새 주문 추가 (모달리스)"""
        dialog = ProductOrderDialog(self, is_edit=False, settings=self.settings)
        # ✅ 데이터 변경 후(Accepted) 목록 새로고침
        dialog.accepted.connect(lambda: self.load_due_list(self.only_future))
        # ✅ 창이 닫히면(Finished) 참조 목록에서 제거
        dialog.finished.connect(lambda: self.cleanup_order_dialog(dialog))
        
        dialog.show()
        self.active_order_dialogs.append(dialog)

    def cleanup_order_dialog(self, dialog):
        """닫힌 주문 다이얼로그를 참조 목록에서 제거"""
        if dialog in self.active_order_dialogs:
            self.active_order_dialogs.remove(dialog)

    def update_invoice_status(self, order_id: int, state: int):
        """청구 완료 상태 업데이트"""
        invoice_done = 1 if state == QtCore.Qt.CheckState.Checked.value else 0

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE orders SET invoice_done=?, updated_at=datetime('now','localtime') WHERE id=?",
                        (invoice_done, order_id))
            conn.commit()

            if invoice_done == 1 and not self.show_all_billed:
                self.load_due_list(self.only_future)
                self.statusBar().showMessage("강제 완료 처리되었습니다. (미청구 목록에서 제거됨)", 3000)
            else:
                self.statusBar().showMessage("강제 완료 상태가 변경되었습니다.", 2000)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"청구 상태 업데이트 중 오류:\n{str(e)}")
        finally:
            conn.close()

        self.refresh_order_purchase_delivery()


    def update_oa_status(self, order_id: int, state: int):
        """OA 발송 상태 업데이트"""
        oa_sent = 1 if state == QtCore.Qt.CheckState.Checked.value else 0

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE orders SET oa_sent = ?, updated_at=datetime('now','localtime') WHERE id = ?",
                        (oa_sent, order_id))

            if cur.rowcount > 0:
                conn.commit()
                status_text = "발송됨" if oa_sent else "미발송"
                self.statusBar().showMessage(f"OA 발송 상태가 '{status_text}'으로 변경되었습니다.", 2000)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"OA 상태 업데이트 중 오류 발생:\n{str(e)}")
        finally:
            conn.close()

    def get_order_clause(self):
        """정렬 조건 반환"""
        column_names = [
            "o.order_dt",  # 0: 주문일
            "o.order_no",  # 1: 주문번호
            "item_codes",  # 2: 품목코드
            "revs",  # 3: Rev
            "item_count",  # 4: 품목수
            "product_names",  # 5: 제품명
            "amount_jpy",  # 6: 주문금액
            "o.req_due",  # 7: 최초납기
            "o.final_due",  # 8: 최종납기
            "o.oa_sent",  # 9: OA 발송
            "o.invoice_done"  # 10: 청구 완료
        ]

        if 0 <= self.current_sort_column < len(column_names):
            column = column_names[self.current_sort_column]
            direction = "DESC" if self.current_sort_order == Qt.DescendingOrder else "ASC"
            if self.current_sort_column in [7, 8]:  # 납기일 컬럼
                return f"date({column}) {direction}, o.order_no ASC"
            else:
                return f"{column} {direction}, date(COALESCE(o.final_due, o.req_due)) ASC, o.order_no ASC"
        else:
            return "date(COALESCE(o.final_due, o.req_due)) ASC, o.order_no ASC"

    def get_selected_order(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return None

        item = self.table.item(current_row, 0)
        if not item:
            return None

        order_id = item.data(Qt.UserRole)
        if not order_id:
            return None

        for row in self.order_data:
            if row[0] == order_id:
                return row

        return None

    def change_due_date(self):
        """새로운 '납기 일정 관리' 창을 여는 기능"""
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QtWidgets.QMessageBox.information(self, "알림", "납기 일정을 관리할 주문을 선택해주세요.")
            return

        item = self.table.item(selected_row, 0)
        if not item: return

        order_id = item.data(Qt.UserRole)
        order_no = self.table.item(selected_row, 1).text()

        if not order_id:
            QtWidgets.QMessageBox.warning(self, "오류", "선택된 주문의 ID를 찾을 수 없습니다.")
            return

        # 새로운 ScheduleDialog를 실행합니다.
        dialog = ScheduleDialog(order_id=order_id, order_no=order_no, parent=self)
        dialog.exec()

        # 창이 닫힌 후, 변경사항이 있을 수 있으므로 주문 목록을 새로고침합니다.
        self.load_due_list()

    def edit_order(self):
        """주문 수정 (모달리스)"""
        order_data = self.get_selected_order()
        if not order_data:
            QtWidgets.QMessageBox.information(self, "알림", "수정할 주문을 선택해주세요.")
            return

        order_id = order_data[0]

        # ✅ 이미 열려있는 창이 있으면 활성화만 하고 중복 열기 방지
        for dlg in self.active_order_dialogs:
            if getattr(dlg, 'order_id', None) == order_id:
                dlg.raise_()
                dlg.activateWindow()
                return

        dialog = ProductOrderDialog(self, is_edit=True, order_id=order_id, settings=self.settings)
        # ✅ 데이터 변경 후 목록 새로고침
        dialog.accepted.connect(lambda: self.load_due_list(self.only_future))
        # ✅ 창 닫히면 정리
        dialog.finished.connect(lambda: self.cleanup_order_dialog(dialog))
        
        dialog.show()
        self.active_order_dialogs.append(dialog)

        '''order_id, order_dt, order_no, item_code, rev, order_desc, qty, amount_jpy, oa_sent, req_due, final_due, unit_price_cents, invoice_done = order_data

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"주문 수정 - {order_no}")
        form = QtWidgets.QFormLayout(dlg)

        edt_order_dt = QtWidgets.QLineEdit(order_dt or "")
        edt_order_dt.setPlaceholderText("예: 2025-08-27 / 2025/8/27")
        edt_no = QtWidgets.QLineEdit(order_no or "")
        edt_item = QtWidgets.QLineEdit(item_code or "")
        edt_rev = QtWidgets.QLineEdit(rev or "")
        edt_desc = QtWidgets.QLineEdit(order_desc or "")
        edt_desc.setMinimumWidth(560)

        sp_qty = QtWidgets.QSpinBox()
        sp_qty.setRange(1, 1_000_000)
        sp_qty.setValue(qty or 1)
        sp_qty.setGroupSeparatorShown(True)

        # ✅ 변경 전: sp_price_jpy = QtWidgets.QSpinBox()
        # ✅ 변경 후:
        edt_price_jpy = MoneyLineEdit(max_value=1_000_000_000)
        edt_price_jpy.set_value((unit_price_cents or 0) // 100)
        edt_price_jpy.setMinimumWidth(200)

        edt_initial_due = QtWidgets.QLineEdit(req_due or "")
        edt_initial_due.setPlaceholderText("예: 2025-09-03 / 2025/9/3 / 30-Jul-25")

        edt_final_due = QtWidgets.QLineEdit(final_due or "")
        edt_final_due.setPlaceholderText("예: 2025-09-03 / 2025/9/3 / 30-Jul-25")

        form.addRow("주문일", edt_order_dt)
        form.addRow("주문번호*", edt_no)
        form.addRow("품목코드", edt_item)
        form.addRow("Rev", edt_rev)
        form.addRow("주문제품명*", edt_desc)
        form.addRow("주문대수", sp_qty)
        form.addRow("단가(엔)", edt_price_jpy)  # ✅ 변경됨
        form.addRow("최초 납기일", edt_initial_due)
        form.addRow("최종 납기일", edt_final_due)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        new_order_dt_raw = edt_order_dt.text().strip()
        new_order_dt = parse_due_text(new_order_dt_raw) if new_order_dt_raw else None
        new_order_no = edt_no.text().strip()
        new_item_code = edt_item.text().strip() or None
        new_rev = edt_rev.text().strip() or None
        new_order_desc = edt_desc.text().strip()

        if not new_order_no or not new_order_desc:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "주문번호와 주문제품명은 필수입니다.")
            return

        if new_order_dt_raw and not new_order_dt:
            QtWidgets.QMessageBox.warning(self, "주문일", "주문일 형식이 올바르지 않습니다. 예: 2025-08-27 / 30-Jul-25")
            return

        new_qty = sp_qty.value()
        new_unit_price_cents = edt_price_jpy.get_value() * 100  # ✅ 변경됨

        initial_due_raw = edt_initial_due.text().strip()
        new_initial_due = parse_due_text(initial_due_raw) if initial_due_raw else None

        final_due_raw = edt_final_due.text().strip()
        new_final_due = parse_due_text(final_due_raw) if final_due_raw else None

        if initial_due_raw and not new_initial_due:
            QtWidgets.QMessageBox.warning(self, "최초 납기일", "최초 납기일 형식이 올바르지 않습니다. 예: 2025-09-03 / 30-Jul-25")
            return

        if final_due_raw and not new_final_due:
            QtWidgets.QMessageBox.warning(self, "최종 납기일", "최종 납기일 형식이 올바르지 않습니다. 예: 2025-09-03 / 30-Jul-25")
            return

        conn = get_conn()
        cur = conn.cursor()

        if new_order_no != order_no:
            cur.execute("SELECT 1 FROM orders WHERE order_no=? AND id!=?", (new_order_no, order_id))
            if cur.fetchone():
                reply = QtWidgets.QMessageBox.question(
                    self, "주문번호 중복",
                    f"주문번호 '{new_order_no}'가 이미 존재합니다.\n"
                    f"동일한 주문번호로 여러 항목을 주문하는 경우가 있습니다.\n\n"
                    f"계속 진행하시겠습니까?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No
                )
                if reply != QtWidgets.QMessageBox.Yes:
                    return

        cur.execute("""
            UPDATE orders 
            SET order_dt=?, order_no=?, item_code=?, rev=?, order_desc=?, qty=?, req_due=?, final_due=?, unit_price_cents=?
            WHERE id=?
        """, (new_order_dt, new_order_no, new_item_code, new_rev, new_order_desc, new_qty, new_initial_due,
              new_final_due, new_unit_price_cents, order_id))
        conn.commit()

        self.load_due_list(self.only_future)
        QtWidgets.QMessageBox.information(self, "완료", "주문이 수정되었습니다.")'''

    def delete_order(self):
        """주문 삭제"""
        order_data = self.get_selected_order()
        if not order_data:
            QtWidgets.QMessageBox.information(self, "알림", "삭제할 주문을 선택해주세요.")
            return

        order_id = order_data[0]
        order_no = order_data[2]
        item_count = order_data[7]
        amount_jpy = order_data[10]
        final_due = order_data[4]
        req_due = order_data[3]

        reply = QtWidgets.QMessageBox.question(
            self,
            "주문 삭제",
            f"정말로 다음 주문을 삭제하시겠습니까?\n\n"
            f"주문번호: {order_no}\n"
            f"품목 수: {item_count}개\n"
            f"금액: {format_money(amount_jpy)}엔\n"
            f"최종납기: {final_due or req_due}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        from ..db import delete_order

        try:
            delete_order(order_id)
            self.load_due_list(self.only_future)
            QtWidgets.QMessageBox.information(self, "완료", f"주문 '{order_no}'이 삭제되었습니다.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"주문 삭제 중 오류가 발생했습니다:\n{str(e)}")

    def toggle_show_all_inventory(self, checked: bool):
        """재고 현황 전체보기 토글"""
        self.show_all_inventory = checked
        self.btn_show_all_inventory.setText("전체보기" if checked else "미완료만")
        self.load_inventory_data()


    def create_oa_document(self):
        """Order Acknowledgement 문서 생성 및 OA 발송 상태 업데이트"""
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QtWidgets.QMessageBox.information(self, "알림", "문서를 생성할 주문을 선택해주세요.")
            return

        item = self.table.item(selected_row, 0)
        if not item: return

        order_id = item.data(Qt.UserRole)
        # item(row, 1)은 주문번호
        order_no_item = self.table.item(selected_row, 1)
        order_no = order_no_item.text() if order_no_item else "Unknown"

        if not order_id:
            return

        try:
            # 1. 일련번호 추천값 조회
            today = datetime.now()
            year_str = today.strftime("%Y")
            suggested_serial = get_next_oa_serial(year_str, order_id)

            # 2. 사용자 입력 (일련번호 수정 가능)
            serial, ok = QtWidgets.QInputDialog.getText(
                self, 
                "Order Acknowledgement 작성", 
                f"OA 일련번호를 입력하세요 (연도: {year_str})\n"
                f"예: 001, 002...", 
                QtWidgets.QLineEdit.Normal, 
                suggested_serial
            )

            if not ok or not serial:
                return

            # 3. 엑셀 생성
            # 템플릿 경로 설정 (app/templete/Order Acknowledgement_.xlsx)
            # 실행 환경(빌드 등) 고려하여 resource_path 사용
            from .utils import resource_path
            template_path = resource_path("app/templete/Order Acknowledgement_.xlsx")
            
            # (옵션) 템플릿이 없으면 알림
            import os
            if not os.path.exists(template_path):
                 # 개발 환경 or 다른 위치 확인 (CWD 기준)
                 fallback = "Order Acknowledgement_.xlsx"
                 if os.path.exists(fallback):
                     template_path = fallback
                 else:
                     QtWidgets.QMessageBox.critical(self, "오류", f"템플릿 파일을 찾을 수 없습니다:\n{template_path}\n\n'app/templete/' 폴더에 'Order Acknowledgement_.xlsx' 파일이 있는지 확인해주세요.")
                     return

            output_path = generate_order_acknowledgement(order_id, serial, template_path)

            # 4. DB 상태 업데이트 (oa_sent = 1)
            self.update_oa_status_in_db(order_id, 1)

            # 5. 성공 알림 및 폴더 열기
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setWindowTitle("완료")
            msg_box.setText(f"Order Acknowledgement 파일이 생성되었습니다.\n\n저장 경로: {output_path}")
            
            open_folder_btn = msg_box.addButton("폴더 열기", QtWidgets.QMessageBox.ActionRole)
            ok_btn = msg_box.addButton("확인", QtWidgets.QMessageBox.AcceptRole)
            
            msg_box.exec()
            
            if msg_box.clickedButton() == open_folder_btn:
                # 폴더 열기 (Windows Explorer)
                folder_path = os.path.dirname(output_path)
                os.startfile(folder_path)

            # 6. 목록 새로고침 (상태 반영)
            self.load_due_list(self.only_future)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"문서 생성 중 오류가 발생했습니다:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def update_oa_status_in_db(self, order_id, status_val):
        """DB만 조용히 업데이트하는 헬퍼 함수"""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE orders SET oa_sent = ?, updated_at=datetime('now','localtime') WHERE id = ?",
                        (status_val, order_id))
            conn.commit()
        except Exception as e:
            print(f"OA Status Update Fail: {e}")
        finally:
            conn.close()

    # app/main_window.py (896라인 함수 교체)

    def load_inventory_data(self):
        """재고 현황 로드 (주문 수요 기반 부족 수량 표시)"""
        try:
            from PySide6.QtGui import QBrush, QColor
            conn = get_conn()
            cur = conn.cursor()

            # 1) 색상 팔레트 읽기
            comp_fg = QColor(self.settings.value("colors/inventory_completed_fg", "#000000"))
            comp_bg = QColor(self.settings.value("colors/inventory_completed_bg", "#E8F5E9"))
            incomp_fg = QColor(self.settings.value("colors/inventory_incomplete_fg", "#000000"))
            incomp_bg = QColor(self.settings.value("colors/inventory_incomplete_bg", "#FFFFFF"))
            repair_fg = QColor(self.settings.value("colors/product_repaired_fg", "#006633"))
            repair_bg = QColor(self.settings.value("colors/product_repaired_bg", "#E8F5E9"))
            recall_fg = QColor(self.settings.value("colors/product_recalled_fg", "#D35400")) # 주황색
            recall_bg = QColor(self.settings.value("colors/product_recalled_bg", "#FFF3E0")) # 연한 주황색

            # 1. 일반 발주 제품
            sql = """
                /* 1. 일반 발주 재고 */
                SELECT 
                    pi.purchase_id, p.status, p.purchase_no,
                    pi.item_code, pi.product_name,
                    EXISTS (SELECT 1 FROM bom_items b WHERE b.parent_item_code = pi.item_code),
                    pi.qty,
                    COUNT(pr.id), 
                    SUM(CASE WHEN pr.delivery_id IS NOT NULL THEN 1 ELSE 0 END),
                    SUM(CASE WHEN pr.consumed_by_product_id IS NOT NULL THEN 1 ELSE 0 END),
                    SUM(CASE WHEN pr.id IS NOT NULL 
                              AND pr.delivery_id IS NULL 
                              AND pr.consumed_by_product_id IS NULL 
                              AND pr.reserved_order_id IS NULL 
                        THEN 1 ELSE 0 END),
                    MIN(CASE WHEN pr.id IS NOT NULL 
                                  AND pr.delivery_id IS NULL 
                                  AND pr.consumed_by_product_id IS NULL 
                                  AND pr.reserved_order_id IS NULL 
                             THEN pr.serial_no ELSE NULL END),
                    (
                       SELECT COALESCE(SUM(oi.qty - COALESCE(osc.shipped_qty, 0)), 0)
                       FROM order_items oi
                       LEFT JOIN (
                           SELECT order_item_id, SUM(ship_qty) as shipped_qty 
                           FROM order_shipments 
                           GROUP BY order_item_id
                       ) osc ON oi.id = osc.order_item_id
                       JOIN orders o ON oi.order_id = o.id
                       WHERE oi.item_code = pi.item_code
                         AND o.invoice_done = 0 
                    ),
                    MAX(pm.purchase_price_krw), -- 같은 item_code라도 rev 다를 수 있으니 Max
                    MAX(pm.unit_price_jpy),
                    MAX(CASE WHEN EXISTS (SELECT 1 FROM recall_items ri WHERE ri.product_id = pr.id) THEN 1 ELSE 0 END) as is_recall
                
                FROM purchase_items pi
                JOIN purchases p ON pi.purchase_id = p.id
                LEFT JOIN products pr ON pi.purchase_id = pr.purchase_id AND pr.part_no = pi.item_code
                LEFT JOIN product_master pm ON pi.item_code = pm.item_code AND pm.rev = pi.rev
                
                GROUP BY pi.purchase_id, pi.item_code, pi.product_name, p.status, p.purchase_no

                UNION ALL

                /* 2. 조립 생산 제품 */
                SELECT
                    NULL, '조립품', ' (조립 재고)',
                    pr.part_no, pr.product_name,
                    EXISTS (SELECT 1 FROM bom_items b WHERE b.parent_item_code = pr.part_no),
                    0, COUNT(pr.id),
                    SUM(CASE WHEN pr.delivery_id IS NOT NULL THEN 1 ELSE 0 END),
                    SUM(CASE WHEN pr.consumed_by_product_id IS NOT NULL THEN 1 ELSE 0 END),
                    SUM(CASE WHEN pr.delivery_id IS NULL AND pr.consumed_by_product_id IS NULL AND pr.reserved_order_id IS NULL THEN 1 ELSE 0 END),
                    NULL,
                    0,
                    MAX(pm.purchase_price_krw),
                    MAX(pm.unit_price_jpy),
                    0 as is_recall
                FROM products pr
                LEFT JOIN product_master pm ON pr.part_no = pm.item_code 
                WHERE pr.purchase_id IS NULL
                GROUP BY pr.part_no, pr.product_name
                HAVING (COUNT(pr.id) - SUM(CASE WHEN pr.delivery_id IS NOT NULL THEN 1 ELSE 0 END) - SUM(CASE WHEN pr.consumed_by_product_id IS NOT NULL THEN 1 ELSE 0 END)) > 0

                UNION ALL

                /* 3. 수리 완료 재고 */
                SELECT
                    NULL, '수리품', ' (수리 재고)',
                    pr.part_no, pr.product_name,
                    EXISTS (SELECT 1 FROM bom_items b WHERE b.parent_item_code = pr.part_no),
                    0, COUNT(pr.id),
                    0, 0, 
                    SUM(CASE WHEN pr.delivery_id IS NULL AND pr.consumed_by_product_id IS NULL AND pr.reserved_order_id IS NULL THEN 1 ELSE 0 END),
                    MIN(pr.serial_no),
                    0,
                    0, -- 수리품 단가 0
                    0,
                    0 as is_recall
                FROM products pr
                WHERE 
                    pr.delivery_id IS NULL
                    AND pr.consumed_by_product_id IS NULL
                    AND (
                        SELECT TRIM(r.status)
                        FROM product_repairs r 
                        WHERE r.product_id = pr.id 
                        ORDER BY r.receipt_date DESC, r.id DESC 
                        LIMIT 1
                    ) LIKE '%%수리완료%%'
                GROUP BY pr.part_no, pr.product_name
            """
            
            # Note: For Assembly/Repair, converting strict group by to allow MAX on metadata is standard practice in SQLite.
            
            cur.execute(sql)

            rows = cur.fetchall()
            _pcache = {}

            if not self.show_all_inventory:
                filtered_rows = []
                for r, row in enumerate(rows):
                    (purchase_id, purchase_status, *rest) = row
                    if purchase_id is None:
                        is_completed_for_filter = False
                    else:
                        is_completed_for_filter = is_purchase_completed(purchase_id)
                    if not is_completed_for_filter:
                        filtered_rows.append(row)
                rows = filtered_rows

            self.inventory_table.setRowCount(len(rows))
            self.inventory_table.setSortingEnabled(False)
            self.inventory_table.setColumnCount(10) # 컬럼 수 복구 (12 -> 10)
            self.inventory_table.setHorizontalHeaderLabels(
                ["발주번호", "품목코드", "발주내용(품목)", "발주량", "생산량", "납품완료", "재고수량", "소모량", "할당가능", "상태"]
            )

            status_col = 9 # Adjusted status_col back to 9
            
            total_inventory_value = 0
            total_expected_revenue = 0

            for r, row in enumerate(rows):
                (purchase_id, purchase_status, purchase_no,
                 item_code, product_name, is_assembly, ordered_qty,
                 produced_qty, delivered_qty, consumed_qty,
                 free_stock_qty, next_serial_no, demand_qty,
                 purchase_price_krw, unit_price_jpy, is_recall) = row

                ordered_qty = ordered_qty or 0
                produced_qty = produced_qty or 0
                delivered_qty = delivered_qty or 0
                consumed_qty = consumed_qty or 0
                free_stock_qty = free_stock_qty or 0
                demand_qty = demand_qty or 0
                is_recall = (is_recall == 1)
                
                purchase_price_krw = purchase_price_krw or 0
                unit_price_jpy = unit_price_jpy or 0

                inventory_qty_raw = produced_qty - delivered_qty - consumed_qty
                inventory_qty_disp = max(inventory_qty_raw, 0)
                
                # 금액 누적 (개별 컬럼 표시는 안 함)
                total_inventory_value += (inventory_qty_disp * purchase_price_krw)
                total_expected_revenue += (inventory_qty_disp * unit_price_jpy)

                is_repair_stock = (purchase_status == '수리품')
                is_assembly_stock = (purchase_status == '조립품')
                is_completed_for_palette = False
                logical_completed = False

                if purchase_id:
                    purchase_completed = _pcache.get(purchase_id)
                    if purchase_completed is None:
                        manual = (str(purchase_status).strip() == "완료")
                        _pcache[purchase_id] = manual
                        purchase_completed = manual
                    logical_completed = (ordered_qty > 0 and (delivered_qty + consumed_qty) >= ordered_qty)
                    is_completed_for_palette = purchase_completed or logical_completed

                # --- [상태 텍스트 로직 수정] ---
                # --- [상태 텍스트 로직 수정] ---
                if is_repair_stock:
                    status_text, status_color = f"수리 재고 {inventory_qty_disp}개", "#006633"
                elif is_recall:
                    status_text, status_color = f"리콜 재고 {inventory_qty_disp}개", "#D35400"
                elif is_assembly_stock:
                    status_text, status_color = f"조립 재고 {inventory_qty_disp}개", "#0d6efd"
                elif delivered_qty > ordered_qty:
                    status_text, status_color = "납품 초과", "#dc3545"
                elif purchase_id and _pcache.get(purchase_id) and (produced_qty == 0):
                    status_text, status_color = "강제 종료", "#6f42c1"
                elif logical_completed:
                    status_text, status_color = "납품 완료", "#888888"

                # ✅ [핵심] 생산 부족 판단 기준 변경: 발주량(ordered)이 아니라 주문요구량(demand) 기준
                # 단, 해당 발주가 아직 생산 여력이 있을 때만(produced_qty < ordered_qty) 표시
                elif produced_qty < ordered_qty and produced_qty < demand_qty:
                    shortage = min(demand_qty, ordered_qty) - produced_qty
                    status_text, status_color = f"생산필요 {shortage}개", "#ff7f27"  # 주황색 (주문 대응 필요)

                elif produced_qty == 0:
                    status_text, status_color = "미생산", "#6c757d"
                elif produced_qty < ordered_qty:
                    # 주문 요구량은 채웠지만, 발주량보다는 적은 경우 (여유분 미생산)
                    status_text, status_color = "생산중 (주문충족)", "#007bff"
                elif inventory_qty_raw <= 0 and produced_qty == ordered_qty:
                    status_text, status_color = "재고 없음", "#007bff"
                else:
                    status_text, status_color = f"재고 {inventory_qty_disp}개", "#28a745"
                        
                # --- 테이블 아이템 채우기 ---
                # 0 ~ 8 : 기존 로직 유지
                # 9 : 재고금액 (New)
                # 10: 예상매출 (New)
                # 11: 상태 (Moved)

                item_0 = QtWidgets.QTableWidgetItem(purchase_no or "")
                item_0.setData(Qt.UserRole, purchase_id)
                item_0.setData(Qt.UserRole + 1, item_code)
                item_0.setData(Qt.UserRole + 2, product_name)
                item_0.setData(Qt.UserRole + 3, next_serial_no)
                self.inventory_table.setItem(r, 0, item_0)

                self.inventory_table.setItem(r, 1, QtWidgets.QTableWidgetItem(item_code or ""))
                display_name = product_name or ""
                if is_assembly: display_name += " (조립품)"
                if is_repair_stock: display_name += " (수리품)"
                self.inventory_table.setItem(r, 2, QtWidgets.QTableWidgetItem(display_name))

                self.inventory_table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(ordered_qty)))
                self.inventory_table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(produced_qty)))
                self.inventory_table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(delivered_qty)))
                self.inventory_table.setItem(r, 6, QtWidgets.QTableWidgetItem(str(inventory_qty_disp)))
                self.inventory_table.setItem(r, 7, QtWidgets.QTableWidgetItem(str(consumed_qty)))

                # 할당가능
                free_item = QtWidgets.QTableWidgetItem(str(free_stock_qty))
                free_item.setForeground(QBrush(QColor("#0066cc")))
                free_item.setFont(sfont := free_item.font())
                sfont.setBold(True)
                self.inventory_table.setItem(r, 8, free_item)

                # 상태 (9열)
                status_item = QtWidgets.QTableWidgetItem(status_text)
                status_item.setTextAlignment(Qt.AlignCenter)
                status_item.setFont(sfont)
                self.inventory_table.setItem(r, 9, status_item)

                # 색상 적용
                fg = incomp_fg;
                bg = incomp_bg
                if is_repair_stock:
                    fg, bg = repair_fg, repair_bg
                elif is_recall:
                    fg, bg = recall_fg, recall_bg
                elif is_assembly_stock:
                    fg, bg = incomp_fg, incomp_bg
                elif is_completed_for_palette:
                    fg, bg = comp_fg, comp_bg

                st_q = QColor(status_color)
                for c in range(self.inventory_table.columnCount()):
                    cell = self.inventory_table.item(r, c)
                    if not cell: continue
                    cell.setBackground(QBrush(bg))
                    if c != status_col and c != 8: cell.setForeground(QBrush(fg))

                status_cell = self.inventory_table.item(r, status_col)
                if status_cell:
                    status_cell.setForeground(QBrush(st_q))
                    status_cell.setBackground(QBrush(bg))

            self.inventory_table.setSortingEnabled(True)
            with QSignalBlocker(self.inventory_table.horizontalHeader()):
                self.inventory_table.horizontalHeader().setSortIndicator(
                    self.current_inventory_sort_column, self.current_inventory_sort_order)
            for i in range(self.inventory_table.rowCount()):
                self.inventory_table.setRowHeight(i, 25)

            conn.close()
            
            # ✅ [수정] 상단 라벨에 총계 업데이트 (프라이버시 모드 적용)
            is_privacy = self.settings.value("view/privacy_mode", False, type=bool)
            if hasattr(self, 'inv_value_label') and hasattr(self, 'inv_revenue_label'):
                if is_privacy:
                    self.inv_value_label.setText("총 재고금액: ****")
                    self.inv_revenue_label.setText("예상 매출액: ****")
                else:
                    self.inv_value_label.setText(f"총 재고금액: {format_money(total_inventory_value)} 원")
                    self.inv_revenue_label.setText(f"예상 매출액: {format_money(total_expected_revenue)} JPY")

        except Exception as e:
            print(f"재고 현황 로드 중 오류: {e}")
            import traceback;
            traceback.print_exc()
            self.inventory_table.setRowCount(0)

        # ✅ [추가] 중요: 로드 후 상단 라벨 금액을 최신 로직(v2)으로 덮어씌움
        self.update_inventory_report_value()



    def update_inventory_report_value(self):
        """선택된 연도의 재고 총액만 계산하여 라벨 업데이트 (테이블 변경 X)"""
        year = self.inv_year_spin.value()
        include_consumed = self.inv_include_consumed_check.isChecked()
        try:
            from ..db import get_yearly_inventory_status_v2
            items = get_yearly_inventory_status_v2(year, include_consumed)
            total_val = sum(item['total_value'] for item in items)
            total_revenue_jpy = sum(item.get('potential_revenue', 0) for item in items)
            
            self.inv_value_label.setText(f"총 재고금액: {format_money(total_val)} 원")
            self.inv_revenue_label.setText(f"예상 매출액: {format_money(total_revenue_jpy)} JPY")
            
        except Exception as e:
            print(f"재고 리포트 계산 오류: {e}")
            self.inv_value_label.setText("계산 오류")
            self.inv_revenue_label.setText("-")

    def export_inventory_report(self):
        """선택된 연도의 재고 현황을 CSV로 내보내기"""
        year = self.inv_year_spin.value()
        include_consumed = self.inv_include_consumed_check.isChecked()
        
        # 1. 파일 저장 경로 선택
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 
            f"{year}년 재고 현황 내보내기", 
            f"Inventory_Report_{year}.csv", 
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not filename:
            return

        try:
            import csv
            from ..db import get_yearly_inventory_status_v2
            
            # 2. 데이터 조회
            items = get_yearly_inventory_status_v2(year, include_consumed)
            
            if not items:
                QtWidgets.QMessageBox.information(self, "알림", "해당 연도에 해당하는 재고 데이터가 없습니다.")
                return

            # 3. CSV 쓰기 (utf-8-sig for Excel compatibility)
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                # 헤더
                writer.writerow(["발주연도", "발주번호", "발주날짜", "품목코드", "품목명", "재고수량", "단가(KRW)", "재고평가액(KRW)", "판매단가(JPY)", "예상매출액(JPY)"])
                
                total_val = 0
                total_rev = 0
                for item in items:
                    writer.writerow([
                        year,
                        item.get('purchase_no', ''),
                        item.get('purchase_dt', ''),
                        item.get('item_code', ''),
                        item.get('product_name', ''),
                        item.get('qty', 0),
                        item.get('unit_price', 0),
                        item.get('total_value', 0),
                        item.get('sales_price_jpy', 0),
                        item.get('potential_revenue', 0)
                    ])
                    total_val += item.get('total_value', 0)
                    total_rev += item.get('potential_revenue', 0)
                
                # 합계 행
                writer.writerow([])
                writer.writerow(["", "", "", "", "총계", "", "", total_val, "", total_rev])

            QtWidgets.QMessageBox.information(self, "완료", f"파일이 성공적으로 저장되었습니다.\n{filename}")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"내보내기 중 오류가 발생했습니다:\n{e}")


    def load_due_list(self, only_future: bool = True):
        """주문 목록 로드 (분할 납기 반영)"""
        self.only_future = only_future
        try:
            from PySide6.QtGui import QBrush, QColor

            # ✅ 1. 설정에서 사용자 지정 색상 불러오기
            comp_fg = self.settings.value("colors/order_completed_fg", "#000000")
            comp_bg = self.settings.value("colors/order_completed_bg", "#C8E6C9")
            incomp_fg = self.settings.value("colors/order_incomplete_fg", "#000000")
            incomp_bg = self.settings.value("colors/order_incomplete_bg", "#FFFFFF")

            conn = get_conn()
            cur = conn.cursor()

            sql = """
                SELECT 
                    o.id, o.order_dt, o.order_no, o.req_due, o.final_due,
                    o.oa_sent, o.invoice_done, COUNT(oi.id) as item_count, SUM(oi.qty) as total_qty,
                    GROUP_CONCAT(oi.item_code, ', ') as item_codes, GROUP_CONCAT(oi.rev, ', ') as revs,
                    GROUP_CONCAT(oi.product_name, ' | ') as product_names,
                    oa.total_cents / 100.0 as amount_jpy,
                    (SELECT MAX(s.due_date) FROM order_shipments s JOIN order_items oi_s ON s.order_item_id = oi_s.id WHERE oi_s.order_id = o.id) as split_final_due,
                    (SELECT COUNT(s.id) FROM order_shipments s JOIN order_items oi_s ON s.order_item_id = oi_s.id WHERE oi_s.order_id = o.id) as split_count
                FROM orders o
                LEFT JOIN order_items oi ON o.id = oi.order_id
                LEFT JOIN order_amounts oa ON o.id = oa.order_id
            """

            conds = []
            if not self.show_all_billed:
                conds.append("COALESCE(o.invoice_done, 0) = 0")

            if conds:
                sql += " WHERE " + " AND ".join(conds)

            sql += " GROUP BY o.id"
            order_clause = self.get_order_clause()
            sql += f" ORDER BY {order_clause}"

            cur.execute(sql)
            rows = cur.fetchall()

            self.order_data = rows
            self.table.setRowCount(len(rows))
            self.table.setSortingEnabled(False)

            for r, row in enumerate(rows):
                (order_id, order_dt, order_no, req_due, final_due,
                 oa_sent, invoice_done, item_count, total_qty, item_codes, revs,
                 product_names, amount_jpy, split_final_due, split_count) = row

                # Col 0: 주문일 + order_id 저장 (가운데 정렬)
                item_0 = QtWidgets.QTableWidgetItem(str(order_dt or ""))
                item_0.setData(Qt.UserRole, order_id)
                item_0.setTextAlignment(Qt.AlignCenter)  # ✅ 가운데 정렬
                self.table.setItem(r, 0, item_0)

                # Col 1: 주문번호 (왼쪽 정렬)
                item_1 = QtWidgets.QTableWidgetItem(str(order_no or ""))
                item_1.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # ✅ 왼쪽 정렬
                self.table.setItem(r, 1, item_1)

                # Col 2: 품목코드 (왼쪽 정렬)
                item_2 = QtWidgets.QTableWidgetItem(str(item_codes or ""))
                item_2.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # ✅ 왼쪽 정렬
                self.table.setItem(r, 2, item_2)

                # Col 3: Rev (가운데 정렬)
                item_3 = QtWidgets.QTableWidgetItem(str(revs or ""))
                item_3.setTextAlignment(Qt.AlignCenter)  # ✅ 가운데 정렬
                self.table.setItem(r, 3, item_3)

                # Col 4: 품목/수량 (가운데 정렬)
                item_4 = QtWidgets.QTableWidgetItem(f"{item_count}종 / {total_qty or 0}개")
                item_4.setTextAlignment(Qt.AlignCenter)  # ✅ 가운데 정렬
                self.table.setItem(r, 4, item_4)

                # Col 5: 제품명 (왼쪽 정렬)
                display_names = product_names or ""
                if len(display_names) > 80:
                    display_names = display_names[:77] + "..."
                item_5 = QtWidgets.QTableWidgetItem(display_names)
                item_5.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # ✅ 왼쪽 정렬
                self.table.setItem(r, 5, item_5)

                # Col 6: 주문금액(엔) (오른쪽 정렬)
                item_6 = QtWidgets.QTableWidgetItem(format_money(amount_jpy))
                item_6.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)  # ✅ 오른쪽 정렬
                self.table.setItem(r, 6, item_6)

                # Col 7: 최초납기 (가운데 정렬)
                item_7 = QtWidgets.QTableWidgetItem(str(req_due or ""))
                item_7.setTextAlignment(Qt.AlignCenter)  # ✅ 가운데 정렬
                self.table.setItem(r, 7, item_7)

                # Col 8: 최종납기 (가운데 정렬)
                date_to_display = split_final_due or final_due or req_due or ""
                suffix = ""

                # 1. 분할 납기인지 확인 (분할 납기 항목이 2개 이상일 경우)
                if split_count and split_count > 1:
                    suffix = " (분할)"
                # 2. 분할 납기가 아닐 때, '납기 일정 관리'를 통해 날짜가 변경되었는지 확인
                #    (분할 납기 테이블의 날짜(split_final_due)가 최초납기(req_due)와 다를 경우)
                elif split_final_due and req_due and split_final_due != req_due:
                    suffix = " (변경)"
                # 3. (구 방식 데이터 호환용) 최종납기 필드가 직접 수정된 경우
                elif final_due and req_due and final_due != req_due:
                    suffix = " (변경)"

                display_text = f"{date_to_display}{suffix}"

                item_8 = QtWidgets.QTableWidgetItem(display_text)
                item_8.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, 8, item_8)

                # Col 9: OA 발송 (Checkbox - 이미 중앙 정렬됨)
                oa_checkbox = QtWidgets.QCheckBox()
                oa_checkbox.setChecked(bool(oa_sent))
                oa_checkbox.setStyleSheet("QCheckBox { margin-left: 20px; }")
                oa_checkbox.stateChanged.connect(
                    lambda state, oid=order_id: self.update_oa_status(oid, state)
                )
                oa_widget = QtWidgets.QWidget()
                oa_layout = QtWidgets.QHBoxLayout(oa_widget)
                oa_layout.addWidget(oa_checkbox)
                oa_layout.setAlignment(Qt.AlignCenter)
                oa_layout.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(r, 9, oa_widget)

                # Col 10: 청구 완료 (Checkbox - 이미 중앙 정렬됨)
                invoice_checkbox = QtWidgets.QCheckBox()
                with QSignalBlocker(invoice_checkbox):  # 🔸초기 세팅 시 신호 차단
                    invoice_checkbox.setChecked(bool(invoice_done))
                invoice_checkbox.setStyleSheet("QCheckBox { margin-left: 20px; }")
                invoice_checkbox.stateChanged.connect(
                    lambda state, oid=order_id: self.update_invoice_status(oid, state)
                )
                invoice_widget = QtWidgets.QWidget()
                invoice_layout = QtWidgets.QHBoxLayout(invoice_widget)
                invoice_layout.addWidget(invoice_checkbox)
                invoice_layout.setAlignment(Qt.AlignCenter)
                invoice_layout.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(r, 10, invoice_widget)

                # ✅ 2. invoice_done 상태에 따라 적용할 색상 결정
                fg_color = QColor(comp_fg if invoice_done else incomp_fg)
                bg_color = QColor(comp_bg if invoice_done else incomp_bg)

                # ✅ 3. 결정된 색상을 모든 컬럼의 글자색으로 적용
                for col in range(self.table.columnCount()):
                    # CellWidget이 아닌 일반 아이템에만 색상 적용
                    item = self.table.item(r, col)
                    if item:
                        item.setForeground(QBrush(fg_color))
                        item.setBackground(QBrush(bg_color))

            # ✅ [수정] QSignalBlocker를 사용하여 setSortIndicator가
            #    on_order_sort_changed를 다시 호출하지 않도록 합니다. (무한 루프 방지)
            self.table.setSortingEnabled(True)

            # 2. 정렬 화살표 표시 (시그널 차단으로 무한 루프 방지)
            with QSignalBlocker(self.table.horizontalHeader()):
                self.table.horizontalHeader().setSortIndicator(
                    self.current_sort_column,
                    self.current_sort_order
                )

            # 3. 행 높이 설정
            for i in range(self.table.rowCount()):
                self.table.setRowHeight(i, 25)

        except Exception as e:
            print(f"주문 목록 로드 중 오류: {e}")
            import traceback
            traceback.print_exc()
            self.order_data = []
            self.table.setRowCount(0)
        finally:
            if 'conn' in locals() and conn:
                conn.close()

    # ✅ [핵심] 추가된 헬퍼 및 핸들러 함수 4개
    def _select_related_rows(self, table: QtWidgets.QTableWidget, ids_to_select: list):
        """
        다른 테이블에서 관련 ID 목록을 받아, 해당 테이블에서 일치하는 모든 행을 선택합니다.
        """
        # 1. 시그널을 차단하여 무한 루프 방지
        table.blockSignals(True)
        # 2. 기존 선택 해제
        table.clearSelection()

        id_set = set(ids_to_select)
        if not id_set:
            table.blockSignals(False)
            return

        first_found_item = None

        # 3. 테이블을 순회하며 일치하는 *모든* ID 찾기
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if not item:
                continue

            row_id = item.data(Qt.UserRole)
            if row_id in id_set:
                # 4. [수정] 'selectRow' 대신 'setSelected'를 사용해
                #    기존 선택에 행을 '추가'합니다.
                table.setRangeSelected(
                    QtWidgets.QTableWidgetSelectionRange(row, 0, row, table.columnCount() - 1),
                    True  # True: 선택 영역에 추가 (False: 선택 해제)
                )

                # 5. 첫 번째로 찾은 항목을 저장 (스크롤용)
                if first_found_item is None:
                    first_found_item = item

        # 6. 첫 번째로 찾은 항목으로 스크롤 (반복문 종료 후 1회 실행)
        if first_found_item:
            table.scrollToItem(first_found_item, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)

        # 7. 시그널 차단 해제
        table.blockSignals(False)

    def on_order_selected(self):
        """주문 테이블에서 항목 선택 시 호출될 핸들러 (다중 선택 지원)"""
        if self.is_selecting:  # 프로그램에 의한 선택이면 무시
            return

        # 1. 선택된 모든 '행'의 인덱스를 집계 (중복 제거)
        selected_rows = set(item.row() for item in self.table.selectedItems())

        if not selected_rows:
            # 2. 선택이 해제된 경우, 다른 테이블의 선택도 해제
            self.is_selecting = True
            self._select_related_rows(self.purchase_widget.table, [])
            self._select_related_rows(self.delivery_widget.table, [])
            self.is_selecting = False
            return

        # 3. 선택된 모든 행에서 고유한 Order ID를 수집
        source_order_ids = set()
        for row in selected_rows:
            item = self.table.item(row, 0)
            if item:
                source_order_ids.add(item.data(Qt.UserRole))

        if not source_order_ids:
            return

        # 4. 수집된 *모든* ID를 사용하여 관련 ID를 한 번에 조회
        placeholders = ', '.join('?' for _ in source_order_ids)
        params = tuple(source_order_ids)

        purchase_ids = [row[0] for row in query_all(
            f"SELECT DISTINCT purchase_id FROM purchase_order_links WHERE order_id IN ({placeholders})", params
        )]
        delivery_ids = [row[0] for row in query_all(
            f"SELECT DISTINCT delivery_id FROM delivery_order_links WHERE order_id IN ({placeholders})", params
        )]

        # 5. 다른 테이블 선택 실행
        self.is_selecting = True
        self._select_related_rows(self.purchase_widget.table, purchase_ids)
        self._select_related_rows(self.delivery_widget.table, delivery_ids)
        self.is_selecting = False

    def on_purchase_selected(self):
        """발주 테이블에서 항목 선택 시 호출될 핸들러 (다중 선택 지원)"""
        if self.is_selecting:
            return

        selected_rows = set(item.row() for item in self.purchase_widget.table.selectedItems())

        if not selected_rows:
            self.is_selecting = True
            self._select_related_rows(self.table, [])
            self._select_related_rows(self.delivery_widget.table, [])
            self.is_selecting = False
            return

        source_purchase_ids = set()
        for row in selected_rows:
            item = self.purchase_widget.table.item(row, 0)
            if item:
                source_purchase_ids.add(item.data(Qt.UserRole))

        if not source_purchase_ids:
            return

        placeholders = ', '.join('?' for _ in source_purchase_ids)
        params = tuple(source_purchase_ids)

        order_ids = [row[0] for row in query_all(
            f"SELECT DISTINCT order_id FROM purchase_order_links WHERE purchase_id IN ({placeholders})", params
        )]
        delivery_ids = [row[0] for row in query_all(
            f"SELECT DISTINCT delivery_id FROM delivery_purchase_links WHERE purchase_id IN ({placeholders})", params
        )]

        self.is_selecting = True
        self._select_related_rows(self.table, order_ids)
        self._select_related_rows(self.delivery_widget.table, delivery_ids)
        self.is_selecting = False

    def on_delivery_selected(self):
        """납품 테이블에서 항목 선택 시 호출될 핸들러 (다중 선택 지원)"""
        if self.is_selecting:
            return

        selected_rows = set(item.row() for item in self.delivery_widget.table.selectedItems())

        if not selected_rows:
            self.is_selecting = True
            self._select_related_rows(self.table, [])
            self._select_related_rows(self.purchase_widget.table, [])
            self.is_selecting = False
            return

        source_delivery_ids = set()
        for row in selected_rows:
            item = self.delivery_widget.table.item(row, 0)
            if item:
                source_delivery_ids.add(item.data(Qt.UserRole))

        if not source_delivery_ids:
            return

        placeholders = ', '.join('?' for _ in source_delivery_ids)
        params = tuple(source_delivery_ids)

        order_ids = [row[0] for row in query_all(
            f"SELECT DISTINCT order_id FROM delivery_order_links WHERE delivery_id IN ({placeholders})", params
        )]
        purchase_ids = [row[0] for row in query_all(
            f"SELECT DISTINCT purchase_id FROM delivery_purchase_links WHERE delivery_id IN ({placeholders})", params
        )]

        self.is_selecting = True
        self._select_related_rows(self.table, order_ids)
        self._select_related_rows(self.purchase_widget.table, purchase_ids)
        self.is_selecting = False

    def get_inventory_order_clause(self):
        """(새 함수) 재고 현황 테이블의 정렬 기준을 SQL ORDER BY 절로 변환"""
        # [참고] SQL은 9개 컬럼을 반환하지만, UI 테이블은 8개임
        column_names = [
            "purchase_no",      # 0 ✅ (p. 및 pi. 접두사 제거 - UNION 호환)
            "item_code",        # 1 ✅
            "product_name",     # 2 ✅
            "ordered_qty",      # 3
            "produced_qty",     # 4
            "delivered_qty",    # 5
            "(produced_qty - delivered_qty - consumed_qty)", # 6 (재고수량)
            "consumed_qty",     # 7 (소모량) ✅ [추가]
            "linked_order_qty", # 8 (할당량) ✅ [변경]
            "NULL"              # 9 (상태) ✅ [변경]
        ]

        if self.current_inventory_sort_column == 7:  # '상태' 컬럼은 SQL 정렬 불가
            # ✅ [수정] 발주일 대신 발주번호로 기본 정렬
            column = "purchase_no"
            direction = "DESC" if self.current_inventory_sort_order == Qt.DescendingOrder else "ASC"
        elif 0 <= self.current_inventory_sort_column < len(column_names):
            column = column_names[self.current_inventory_sort_column]
            direction = "DESC" if self.current_inventory_sort_order == Qt.DescendingOrder else "ASC"
        else:  # 기본값
            column = "purchase_no"
            direction = "DESC"

        # 2차 정렬 기준으로 발주번호, 품목코드 사용
        return f"{column} {direction}, purchase_no {direction}, item_code {direction}"

    def on_inventory_sort_changed(self, column_index, order):
        """(새 함수) 재고 현황 테이블 헤더의 정렬 표시기가 변경될 때 호출됩니다."""

        if self.current_inventory_sort_column == column_index and self.current_inventory_sort_order == order:
            return

        if column_index == 9:  # '상태' 컬럼은 정렬 비활성화
            # 현재 정렬 상태를 유지하고, 화살표만 이전 상태로 되돌림
            with QSignalBlocker(self.inventory_table.horizontalHeader()):
                self.inventory_table.horizontalHeader().setSortIndicator(
                    self.current_inventory_sort_column,
                    self.current_inventory_sort_order
                )
            return

        self.current_inventory_sort_column = column_index
        self.current_inventory_sort_order = order

        self.settings.setValue("inventory_table/sort_column", self.current_inventory_sort_column)
        self.settings.setValue("inventory_table/sort_order", self.current_inventory_sort_order)

        self.load_inventory_data()

    def show_inventory_context_menu(self, position):
        """(새 함수) 재고 현황 테이블 우클릭 메뉴"""
        row = self.inventory_table.rowAt(position.y())
        if row < 0:
            return

        # ✅ [수정] 메뉴를 먼저 생성
        menu = QtWidgets.QMenu(self)
        action = menu.addAction("➡️ 이 발주로 생산하기")

        status_item = self.inventory_table.item(row, 9)  # 9번 컬럼 (상태)
        is_producible = False

        if status_item:
            status_text = status_item.text()
            # '미생산' 또는 '생산 n개 부족' 상태일 때만 '생산하기' 활성화
            if status_text == "미생산" or "부족" in status_text or "생산필요" in status_text:
                is_producible = True

        if is_producible:
            # ✅ 활성화 상태면, 기능 연결
            action.triggered.connect(self.start_production_from_inventory)
        else:
            # ✅ 비활성화 상태면, 메뉴를 끄고 툴팁 표시
            action.setEnabled(False)
            action.setToolTip("'미생산' 또는 '생산 부족' 상태인 항목만 생산할 수 있습니다.")

        # ✅ [수정] 메뉴를 항상 표시
        menu.exec_(self.inventory_table.mapToGlobal(position))

    def start_production_from_inventory(self):
        """(새 함수) 재고 현황 메뉴에서 '생산하기'를 실행"""
        current_row = self.inventory_table.currentRow()
        if current_row < 0:
            return

        item_col_0 = self.inventory_table.item(current_row, 0)  # 0번 컬럼
        if not item_col_0:
            return

        purchase_id = item_col_0.data(Qt.UserRole)
        item_code = item_col_0.data(Qt.UserRole + 1)
        product_name = item_col_0.data(Qt.UserRole + 2)
        next_serial_no = item_col_0.data(Qt.UserRole + 3)  # ✅ [추가]

        if not purchase_id or not item_code:
            QtWidgets.QMessageBox.warning(self, "오류", "생산에 필요한 발주 ID 또는 품목코드를 찾을 수 없습니다.")
            return

        # 1. '제품 생산' 탭의 인덱스를 찾아 강제 이동
        for i in range(self.main_tabs.count()):
            if self.main_tabs.tabText(i) == "제품 생산":
                self.main_tabs.setCurrentIndex(i)
                break

        # 2. '제품 생산' 탭의 add_product_from_inventory 함수 호출
        if hasattr(self, 'product_production_widget'):
            self.product_production_widget.add_product_from_inventory(
                purchase_id, item_code, product_name, next_serial_no  # ✅ [수정]
            )
        else:
            QtWidgets.QMessageBox.warning(self, "오류", "제품 생산 위젯을 찾을 수 없습니다.")

    # ✅ [수정] 스레드 방식 폐기 -> 동기 실행 방식 적용
    def _run_outlook_worker(self, mode, title, label_text):
        """Outlook 작업을 동기적으로 실행합니다 (UI Blocking + processEvents)"""
        # execute_outlook_operation_sync 함수가 내부적으로 QProgressDialog를 띄우고
        # 작업이 완료될 때까지 메인 스레드를 점유하며 UI를 갱신합니다.
        msg = execute_outlook_operation_sync(self, mode)
        
        # 완료 후 결과 처리
        self.on_sync_finished(msg)


    def run_outlook_sync_future(self):
        """오늘 이후 일정만 동기화"""
        self._run_outlook_worker("future", "Outlook 동기화", "미래 일정을 동기화 중입니다...")

    def run_outlook_sync_all(self):
        """전체 일정 동기화"""
        self._run_outlook_worker("all", "Outlook 전체 동기화", "모든 일정을 동기화 중입니다... (시간이 걸릴 수 있습니다)")

    def run_outlook_delete_all(self):
        """모든 일정 삭제 (주의 필요)"""
        reply = QtWidgets.QMessageBox.warning(
            self, "전체 삭제 경고",
            "정말로 Outlook의 '모든' 작업(ToDo)을 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없으며, 완료 여부와 상관없이 싹 지워집니다.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self._run_outlook_worker("delete_all", "일정 삭제 중", "Outlook의 모든 일정을 삭제하고 있습니다...")


    def run_outlook_cleanup(self):
        """Outlook 완료된 일정 삭제 실행"""
        reply = QtWidgets.QMessageBox.question(
            self, "일괄 삭제 확인",
            "Outlook에서 '완료' 상태인 모든 작업을 삭제하시겠습니까?\n(이 작업은 되돌릴 수 없습니다.)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self._run_outlook_worker("cleanup", "완료 일정 정리", "완료된 일정을 삭제하고 있습니다...")

    def on_sync_finished(self, msg):
        """Outlook 동기화 완료 핸들러"""
        self.statusBar().showMessage(msg, 5000)
        
        if "오류" in msg or "실패" in msg:
            QtWidgets.QMessageBox.warning(self, "동기화 알림", msg)
        else:
            QtWidgets.QMessageBox.information(self, "완료", msg)