# app/ui/product_master_widget.py
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QHeaderView, QCompleter
from PySide6.QtCore import Qt, QStringListModel, QSignalBlocker
from PySide6.QtGui import QBrush, QColor
from datetime import datetime
from ..db import (get_conn, get_all_product_master, add_or_update_product_master,
                  delete_product_master, search_product_master, update_product_master,
                  update_item_code_references, get_parent_items)
from .money_lineedit import MoneyLineEdit
from .utils import apply_table_resize_policy


def format_money(val: float | None) -> str:
    if val is None:
        return ""
    try:
        return f"{val:,.0f}"
    except Exception:
        return str(val)


class ProductMasterWidget(QtWidgets.QWidget):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings

        # ✅ 저장된 설정 불러오기
        if self.settings:
            self.show_all = self.settings.value("filters/product_master_show_all", False, type=bool)
            # 저장된 필터 로드 (없으면 기본 3가지 모두 선택)
            saved_filters = self.settings.value("filters/product_master_types", ["PRODUCT", "MODULE", "PART"])
            self.selected_types = set(saved_filters)
            
            # ✅ [이동] setup_ui 호출 전에 정렬 변수 초기화 (setup_ui에서 사용함)
            self.current_sort_column = self.settings.value("product_master_table/sort_column", 0, type=int)
            sort_order_val = self.settings.value("product_master_table/sort_order", 0, type=int)
            try:
                self.current_sort_order = Qt.SortOrder(sort_order_val)
            except (ValueError, TypeError):
                self.current_sort_order = Qt.AscendingOrder
        else:
            self.show_all = False
            self.selected_types = {"PRODUCT", "MODULE", "PART"}
            # 기본 정렬 값
            self.current_sort_column = 0
            self.current_sort_order = Qt.AscendingOrder

        self.current_product_code = None
        self.setup_ui()
        
        # ✅ 초기 프라이버시 모드 적용 (UI 생성 후 실행)
        if self.settings and self.settings.value("view/privacy_mode", False, type=bool):
            self.set_privacy_mode(True)
        
        self.load_product_list()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("품목 정보")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")

        # ✅ 유형 필터 버튼 (ToolButton + Menu)
        self.btn_type_filter = QtWidgets.QToolButton()
        self.btn_type_filter.setText("유형 필터")
        self.btn_type_filter.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        
        self.type_filter_menu = QtWidgets.QMenu(self.btn_type_filter)
        
        # 필터 항목 (표시명, 코드)
        self.filter_options = [("완제품 (PRODUCT)", "PRODUCT"), ("모듈 (MODULE)", "MODULE"), ("부품 (PART)", "PART")]
        self.filter_actions = {}
        
        for label, code in self.filter_options:
            action = QtWidgets.QWidgetAction(self.type_filter_menu)
            cb = QtWidgets.QCheckBox(label)
            # 전체 영역 클릭 시 체크되도록
            cb.setStyleSheet("QCheckBox { padding: 5px; }")
            cb.setChecked(code in self.selected_types)
            cb.stateChanged.connect(lambda state, c=code: self.on_filter_changed(c, state))
            
            action.setDefaultWidget(cb)
            self.type_filter_menu.addAction(action)
            self.filter_actions[code] = cb

        self.btn_type_filter.setMenu(self.type_filter_menu)
        self.update_filter_button_text() # ✅ 초기 텍스트 설정 (중요)

        # ✅ 단종 필터 버튼
        self.btn_show_all = QtWidgets.QPushButton("전체보기" if self.show_all else "판매 가능만")
        self.btn_show_all.setCheckable(True)
        self.btn_show_all.setChecked(self.show_all)  # ✅ 저장된 값으로 설정
        self.btn_show_all.toggled.connect(self.toggle_show_all)

        self.btn_new_product = QtWidgets.QPushButton("새 제품")
        self.btn_refresh_product = QtWidgets.QPushButton("새로고침")

        # ✅ [추가] 도구 버튼 (일괄 작업용)
        self.btn_tools = QtWidgets.QToolButton()
        self.btn_tools.setText("도구 (관리)")
        self.btn_tools.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.tools_menu = QtWidgets.QMenu(self.btn_tools)
        
        action_add_prefix = self.tools_menu.addAction("일괄 변경: 품목코드 표준화 (B10000 추가)")
        action_add_prefix.setToolTip("6자리 숫자 코드(예: 123456) 앞에 'B10000'을 붙입니다.")
        action_add_prefix.triggered.connect(self.batch_add_prefix)
        
        action_remove_prefix = self.tools_menu.addAction("일괄 변경: 접두사 제거 (B10000 제거)")
        action_remove_prefix.setToolTip("'B10000'으로 시작하는 코드에서 접두사를 제거합니다.")
        action_remove_prefix.triggered.connect(self.batch_remove_prefix)
        
        self.btn_tools.setMenu(self.tools_menu)


        self.btn_new_product.clicked.connect(self.add_product)
        self.btn_refresh_product.clicked.connect(self.load_product_list)

        title_layout.addWidget(title_label)

        # ✅ [추가] 검색 바
        self.search_bar = QtWidgets.QLineEdit()
        self.search_bar.setPlaceholderText("품목 검색 (코드/명칭)...")
        self.search_bar.setFixedWidth(200)
        self.search_bar.textChanged.connect(self.load_product_list)
        
        title_layout.addStretch()
        title_layout.addWidget(self.search_bar) # 검색 바 배치
        title_layout.addWidget(self.btn_type_filter) # 필터 배치
        
        # title_layout.addStretch() # 스트레치 제거 (위에서 이미 추가)
        # title_layout.addStretch() # 스트레치 제거 (위에서 이미 추가)
        title_layout.addWidget(self.btn_new_product)
        title_layout.addWidget(self.btn_tools) # ✅ 도구 버튼 추가
        title_layout.addWidget(self.btn_refresh_product)
        title_layout.addWidget(self.btn_show_all)
        
        self.table = QtWidgets.QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            ["품목코드", "Rev", "제품명", "약어", "판매단가(엔)", "발주단가(원)", "설명", "생산유형", "판매가능", "등록일"]
        )
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.setShowGrid(True)

        self.table.itemDoubleClicked.connect(self.edit_product)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        self.table.setColumnWidth(0, 120)   # 품목코드
        self.table.setColumnWidth(1, 60)    # Rev
        self.table.setColumnWidth(2, 500)   # 제품명
        self.table.setColumnWidth(3, 120)   # 판매단가(엔)
        self.table.setColumnWidth(4, 120)   # 발주단가(원)
        self.table.setColumnWidth(5, 300)  # 설명
        self.table.setColumnWidth(6, 120)  # ✅ [변경] 생산유형 (너비 조정)
        self.table.setColumnWidth(7, 80)  # ✅ [변경] 생산가능
        self.table.setColumnWidth(8, 100)  # ✅ [변경] 등록일

        if self.settings:
            self.restore_column_widths()
            # ✅ [추가] 초기화 시 프라이버시 모드 적용 상태 확인
            if self.settings.value("view/privacy_mode", False, type=bool):
                self.set_privacy_mode(True)

        header.sectionResized.connect(self.save_column_widths)

        # ✅ [추가] 시그널 연결 및 화살표 강제 표시
        header.sortIndicatorChanged.connect(self.on_header_sort_changed)
        header.setSortIndicatorShown(True)
        # ✅ [추가] 저장된 정렬 상태를 UI 헤더에 반영 (화살표 표시)
        header.setSortIndicator(self.current_sort_column, self.current_sort_order)

        layout.addLayout(title_layout)
        layout.addWidget(self.table)

        apply_table_resize_policy(self.table)
        
        # ✅ [수정] 가로 스크롤바 활성화 (utils 정책 오버라이드)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.horizontalHeader().setStretchLastSection(False)
        
    def set_privacy_mode(self, enabled: bool):
        """재무 정보 숨기기 설정"""
        # 판매단가(엔): 4번 컬럼 (0:코드, 1:Rev, 2:명칭, 3:약어)
        # 발주단가(원): 5번 컬럼
        
        if enabled:
            # 숨기기 전 저장
            if not self.table.isColumnHidden(4) or not self.table.isColumnHidden(5):
                 self._product_temp_widths = [self.table.columnWidth(col) for col in range(self.table.columnCount())]

            self.table.setColumnHidden(4, True)
            self.table.setColumnHidden(5, True)
        else:
            self.table.setColumnHidden(4, False)
            self.table.setColumnHidden(5, False)
            
             # 복원
            if hasattr(self, '_product_temp_widths') and self._product_temp_widths:
                header = self.table.horizontalHeader()
                blocker = QSignalBlocker(header)
                try:
                    for col, width in enumerate(self._product_temp_widths):
                        if col < self.table.columnCount():
                            if (col == 4 or col == 5) and width < 50: width = 120
                            self.table.setColumnWidth(col, width)
                finally:
                    blocker.unblock()

    def on_filter_changed(self, code, state):
        """필터 체크박스 상태 변경 핸들러"""
        # Qt.Checked is 2. Using integer 2 is safer against Enum type mismatches.
        if state == 2:  
            self.selected_types.add(code)
        else:
            self.selected_types.discard(code)
            
        # 버튼 텍스트 갱신
        self.update_filter_button_text()
        
        # 설정 저장
        if self.settings:
            self.settings.setValue("filters/product_master_types", list(self.selected_types))
            
        # 목록 새로고침
        self.load_product_list()

    def update_filter_button_text(self):
        count = len(self.selected_types)
        total = len(self.filter_options)
        self.btn_type_filter.setText(f"유형 필터 ({count}/{total})")

    def toggle_show_all(self, checked: bool):
        """판매 가능 제품만 / 전체보기 토글"""
        self.show_all = checked
        self.btn_show_all.setText("전체보기" if checked else "판매 가능만")
        
        # 설정 저장
        if self.settings:
            self.settings.setValue("filters/product_master_show_all", checked)
            
        self.load_product_list()

    def load_product_list(self):
        """제품 목록 로드 (필터 및 정렬 적용)"""
        try:
            conn = get_conn()
            cur = conn.cursor()

            # 1. Base SQL
            sql = "SELECT id, item_code, rev, product_name, abbreviation, unit_price_jpy, purchase_price_krw, description, item_type, is_active, created_at FROM product_master WHERE 1=1"
            params = []

            # 2. Filter: Active Status
            if not self.show_all:
                sql += " AND is_active = 1"

            # 3. Filter: Item Type
            # 3. Filter: Item Type (Improved)
            if not self.selected_types:
                sql += " AND 1=0"
            else:
                # ✅ [수정] BOM 위젯처럼 다양한 표기법 모두 포함 & 대소문자 무시
                target_types = list(self.selected_types)
                extended_types = []
                
                # 레거시 데이터 및 한글 데이터 호환 확장
                if 'PRODUCT' in self.selected_types: 
                    extended_types.extend(['PRODUCT', 'SELLABLE', '완제품', 'Product'])
                if 'MODULE' in self.selected_types: 
                    extended_types.extend(['MODULE', '모듈', 'Module'])
                if 'PART' in self.selected_types: 
                    extended_types.extend(['PART', 'SUB_COMPONENT', '부품', 'Part'])
                
                # 선택된 게 있지만 매핑이 비었을 경우 (방어 코드)
                if not extended_types:
                    extended_types = target_types

                placeholders = ', '.join(['?'] * len(extended_types))
                # ✅ UPPER()를 사용하여 대소문자 구분 없이 비교
                sql += f" AND UPPER(item_type) IN ({', '.join(['UPPER(?)'] * len(extended_types))})"
                params.extend(extended_types)

            # ✅ 4. Filter: Search Text
            search_text = self.search_bar.text().strip()
            if search_text:
                sql += " AND (item_code LIKE ? OR product_name LIKE ? OR abbreviation LIKE ?)"
                like_pattern = f"%{search_text}%"
                params.append(like_pattern)
                params.append(like_pattern)
                params.append(like_pattern)

            # 4. Sorting
            col_map = {
                0: "item_code",
                1: "rev",
                2: "product_name",
                3: "unit_price_jpy",
                4: "purchase_price_krw",
                5: "description",
                6: "item_type",
                7: "is_active",
                8: "created_at"
            }
            sort_col = col_map.get(self.current_sort_column, "item_code")
            sort_order = "DESC" if self.current_sort_order == Qt.DescendingOrder else "ASC"
            
            sql += f" ORDER BY {sort_col} {sort_order}"

            cur.execute(sql, params)
            rows = cur.fetchall()
            
            self.table.setRowCount(0)
            self.table.setRowCount(len(rows))
            self.table.setSortingEnabled(False) 

            for r, row in enumerate(rows):
                # unpacked tuple (now 12 items?)
                # We need to see the SELECT statement to be sure.
                # Assuming I will update SELECT statement in load_product_list to include abbreviation.
                # SELECT id, item_code, rev, product_name, abbreviation, unit_price_jpy, purchase_price_krw, description, item_type, is_active, created_at
                
                p_id, code, rev, name, abbr, price_jpy, price_krw, desc, p_type, active, created = row

                # 0: Item Code
                item_0 = QtWidgets.QTableWidgetItem(str(code))
                item_0.setData(Qt.UserRole, p_id)
                self.table.setItem(r, 0, item_0)
                
                # 1: Rev
                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(rev or "")))
                
                # 2: Name
                self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(name)))

                # 3: Abbreviation
                self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(abbr or "")))
                
                # 4: Price JPY (Was 3)
                p_jpy = (price_jpy or 0) / 100
                display_jpy = format_money(p_jpy)
                item_4 = QtWidgets.QTableWidgetItem(display_jpy)
                item_4.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, 4, item_4)
                
                # 5: Price KRW (Was 4)
                p_krw = (price_krw or 0) / 100
                display_krw = format_money(p_krw)
                item_5 = QtWidgets.QTableWidgetItem(display_krw)
                item_5.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, 5, item_5)
                
                # 6: Desc (Was 5)
                self.table.setItem(r, 6, QtWidgets.QTableWidgetItem(str(desc or "")))
                
                # 7: Type (Was 6)
                type_map = {"PRODUCT": "완제품", "MODULE": "모듈", "PART": "부품"}
                display_type = type_map.get(p_type, p_type)
                self.table.setItem(r, 7, QtWidgets.QTableWidgetItem(display_type))
                
                # 8: Active (Was 7)
                chk_box = QtWidgets.QCheckBox()
                chk_box.setChecked(bool(active))
                chk_box.stateChanged.connect(lambda state, pid=p_id: self.update_active_status(pid, state))
                cell_widget = QtWidgets.QWidget()
                layout = QtWidgets.QHBoxLayout(cell_widget)
                layout.addWidget(chk_box)
                layout.setAlignment(Qt.AlignCenter)
                layout.setContentsMargins(0,0,0,0)
                self.table.setCellWidget(r, 8, cell_widget)
                
                # 9: Created (Was 8)
                created_str = str(created).split()[0] if created else ""
                self.table.setItem(r, 9, QtWidgets.QTableWidgetItem(created_str))
                
                # Gray out inactive rows based on settings
                if not active:
                    # ✅ [수정] 설정된 색상 사용 (비활성/단종)
                    inactive_fg = self.settings.value("colors/product_master_incomplete_fg", "#999999")
                    inactive_bg = self.settings.value("colors/product_master_incomplete_bg", "#FFFFFF")
                    
                    for c in range(self.table.columnCount()):
                        item = self.table.item(r, c)
                        if item:
                            item.setForeground(QBrush(QColor(inactive_fg)))
                            item.setBackground(QBrush(QColor(inactive_bg)))
                else:
                    # ✅ [추가] 활성(생산) 품목도 설정된 색상 적용
                    active_fg = self.settings.value("colors/product_master_completed_fg", "#000000")
                    # 배경색은 alternatingRowColors와 충돌할 수 있지만 사용자 설정을 우선시
                    # (기본값 #E0F7FA는 옅은 하늘색)
                    active_bg = self.settings.value("colors/product_master_completed_bg", "#FFFFFF") 
                    # 주의: ColorSettingsDialog 기본값은 bg=#E0F7FA 이지만, 
                    # 여기서는 사용자 경험을 위해 기본값이 없을 땐 흰색(투명)으로 두는게 안전할 수 있음.
                    # 하지만 '설정을 따르지 않네'라고 했으므로 Dialog의 기본값과 일치시키는 게 맞음?
                    # ColorSettingsDialog의 Default는 #E0F7FA임.
                    # 하지만 여기서 fallback을 #FFFFFF로 하면, 사용자가 설정을 안 건드렸을 때 그냥 흰색으로 나옴.
                    # 사용자가 "설정의... 색상 기준을 따라야지" 했으니 Dialog의 Default 값과 동일하게 해주는게 맞을 듯.
                    # Dialog Default: completed_bg='#E0F7FA'
                    
                    active_bg = self.settings.value("colors/product_master_completed_bg", "#E0F7FA")

                    for c in range(self.table.columnCount()):
                        item = self.table.item(r, c)
                        if item:
                            item.setForeground(QBrush(QColor(active_fg)))
                            item.setBackground(QBrush(QColor(active_bg)))
                            
            self.table.setSortingEnabled(True)

            # ✅ [추가] current_product_code가 설정되어 있다면 해당 제품 자동 선택
            if self.current_product_code:
                match_found = False
                for r in range(self.table.rowCount()):
                    item = self.table.item(r, 0) # 품목코드 컬럼
                    if item and item.text() == self.current_product_code:
                        self.table.selectRow(r)
                        self.table.scrollToItem(item)
                        match_found = True
                        # 선택 후 해제할지는 정책 결정 필요. 
                        # 여기서는 사용자가 '찾기'를 의도했다고 보고 유지하되, 
                        # 필터 변경 등으로 리로드될 때마다 다시 선택되는 것을 방지하려면 None으로 초기화?
                        # 하지만 탭 이동 후 다시 돌아왔을 때 등 재진입 시나리오를 고려하면
                        # 외부에서 설정해준 값을 리로드 직후에만 쓰고 초기화하는 게 깔끔함.
                        self.current_product_code = None 
                        break
            
            conn.close()

        except Exception as e:
            print(f"제품 목록 로드 오류: {e}")
            import traceback
            traceback.print_exc()
    
    def save_column_widths(self):
        if not self.settings:
            return
        widths = []
        for col in range(self.table.columnCount()):
            widths.append(self.table.columnWidth(col))
        self.settings.setValue("product_master_table/column_widths", widths)

    def restore_column_widths(self):
        if not self.settings:
            return
        widths = self.settings.value("product_master_table/column_widths")
        if widths:
            for col, width in enumerate(widths):
                if col < self.table.columnCount():
                    self.table.setColumnWidth(col, int(width))

    def show_context_menu(self, position):
        if self.table.itemAt(position) is None:
            return

        menu = QtWidgets.QMenu(self)

        edit_action = menu.addAction("수정")
        edit_action.triggered.connect(self.edit_product)

        # ✅ 단종 토글 메뉴 추가
        product_data = self.get_selected_product()
        if product_data:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT is_active FROM product_master WHERE id = ?", (product_data[0],))
            result = cur.fetchone()
            is_active = result[0] if result else 1
            conn.close()

            toggle_text = "판매 불가 처리" if is_active else "판매 가능으로 변경"
            toggle_action = menu.addAction(toggle_text)
            toggle_action.triggered.connect(lambda: self.toggle_product_active(product_data[0]))

        where_used_action = menu.addAction("이 부품이 사용된 곳 보기 (Where Used)")
        where_used_action.triggered.connect(lambda: self.show_where_used(product_data))
        
        menu.addSeparator()

        delete_action = menu.addAction("삭제")
        delete_action.triggered.connect(self.delete_product)

        menu.exec_(self.table.mapToGlobal(position))

    def toggle_product_active(self, product_id: int):
        """제품 생산 가능 상태 토글"""
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT is_active FROM product_master WHERE id = ?", (product_id,))
        result = cur.fetchone()
        if not result:
            conn.close()
            return

        current_active = result[0]
        new_active = 0 if current_active else 1
        
        cur.execute("UPDATE product_master SET is_active = ?, updated_at=datetime('now','localtime') WHERE id = ?", (new_active, product_id))
        conn.commit()
        conn.close()
        
        # 목록 새로고침
        self.load_product_list()
        
    def get_product_master_order_clause(self):
        col_map = {
            0: "item_code",
            1: "rev",
            2: "product_name",
            3: "unit_price_jpy",
            4: "purchase_price_krw",
            5: "description",
            6: "item_type",
            7: "is_active",
            8: "created_at"
        }
        sort_col = col_map.get(self.current_sort_column, "item_code")
        sort_order = "DESC" if self.current_sort_order == Qt.DescendingOrder else "ASC"
        return f" ORDER BY {sort_col} {sort_order}"

    def on_header_sort_changed(self, column_index, order):
        if self.current_sort_column == column_index and self.current_sort_order == order:
            return

        self.current_sort_column = column_index
        self.current_sort_order = order

        if self.settings:
            self.settings.setValue("product_master_table/sort_column", self.current_sort_column)
            self.settings.setValue("product_master_table/sort_order", order.value if hasattr(order, 'value') else int(order))

        self.load_product_list()

    def update_active_status(self, product_id: int, state: int):
        """체크박스 상태 변경 시 DB 업데이트"""
        conn = get_conn()
        try:
            cur = conn.cursor()
            is_active = 1 if state == 2 else 0 # Qt.Checked = 2
            cur.execute("UPDATE product_master SET is_active = ?, updated_at=datetime('now','localtime') WHERE id = ?", (is_active, product_id))
            conn.commit()
            
            # 여기서 즉시 로드하지 않고, 필요한 경우에만 로드
            if not self.show_all and is_active == 0:
                self.load_product_list()
                
        except Exception as e:
            print(f"상태 업데이트 오류: {e}")
        finally:
            conn.close()

    def get_selected_product(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return None
        item = self.table.item(current_row, 0)
        if not item:
            return None
        product_id = item.data(Qt.UserRole)
        
        conn = get_conn()
        cur = conn.cursor()
        # [수정] 포장 정보 컬럼 추가 조회
        cur.execute("""
            SELECT id, item_code, rev, product_name, abbreviation, unit_price_jpy, purchase_price_krw, description, 
                   created_at, updated_at, is_active, item_type,
                   items_per_box, box_l, box_w, box_h, box_weight, max_layer
            FROM product_master WHERE id=?
        """, (product_id,))
        row = cur.fetchone()
        conn.close()
        return row

    def add_product(self):
        # ✅ settings 전달
        dialog = ProductMasterDialog(self, is_edit=False, settings=self.settings)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_product_list()

    def edit_product(self):
        product_data = self.get_selected_product()
        if not product_data:
            QtWidgets.QMessageBox.information(self, "알림", "수정할 제품을 선택해주세요.")
            return

        # ✅ settings 전달
        dialog = ProductMasterDialog(self, is_edit=True, product_data=product_data, settings=self.settings)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.load_product_list()

    def delete_product(self):
        product_data = self.get_selected_product()
        if not product_data:
            QtWidgets.QMessageBox.information(self, "알림", "삭제할 제품을 선택해주세요.")
            return

        product_id = product_data[0]
        item_code = product_data[1]

        reply = QtWidgets.QMessageBox.question(
            self, "삭제 확인", f"정말로 제품 '{item_code}'을(를) 삭제하시겠습니까?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                delete_product_master(product_id)
                self.load_product_list()
                QtWidgets.QMessageBox.information(self, "완료", f"제품 '{item_code}'이 삭제되었습니다.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "오류", f"제품 삭제 중 오류가 발생했습니다:\n{str(e)}")

    def show_where_used(self, product_data):
        if not product_data:
            return
            
        # product_data: id, item_code, rev, product_name, ...
        item_code = product_data[1]
        product_name = product_data[3]
        
        product_name = product_data[3]
        
        # ✅ [수정] 모달리스로 변경
        if hasattr(self, 'current_where_used_dialog') and self.current_where_used_dialog.isVisible():
            self.current_where_used_dialog.close()
            
        self.current_where_used_dialog = WhereUsedDialog(self, child_code=item_code, child_name=product_name, settings=self.settings)
        self.current_where_used_dialog.show()

    def batch_add_prefix(self):
        """일괄 변경: 6자리 숫자 코드에 'B10000' 추가"""
        reply = QtWidgets.QMessageBox.question(
            self, "일괄 변경 확인",
            "6자리 숫자(예: 123456)로 된 품목코드를 찾아 'B10000'을 붙여서\n"
            "표준 형식(예: B10000123456)으로 변경합니다.\n\n"
            "※ 모든 관련 데이터(BOM, 주문, 발주, 납품 등)가 함께 업데이트됩니다.\n"
            "정말로 실행하시겠습니까?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        conn = get_conn()
        try:
            cur = conn.cursor()
            # 1. 대상 조회 (6자리 숫자만)
            # SQLite GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' or REGEX if enabled.
            # Here we fetch all and filter in Python for safety/portability
            cur.execute("SELECT item_code FROM product_master")
            all_codes = [row[0] for row in cur.fetchall()]
            
            targets = []
            for code in all_codes:
                if len(code) == 6 and code.isdigit():
                    targets.append(code)
            
            if not targets:
                QtWidgets.QMessageBox.information(self, "알림", "변경 대상 품목(6자리 숫자)이 없습니다.")
                return

            success_count = 0
            skipped = []

            # 2. 업데이트 실행
            # 트랜잭션 단위: 전체를 하나로 묶음
            for old_code in targets:
                new_code = "B10000" + old_code
                
                # 충돌 체크 (이미 new_code가 존재하는지)
                if new_code in all_codes:
                    skipped.append(f"{old_code} -> {new_code} (이미 존재함)")
                    continue
                
                # DB 업데이트 (헬퍼 함수 사용)
                # 이 함수는 커밋을 하지 않으므로(conn 전달 시), 반복문 후에 커밋해야 함
                # 하지만 현재 구현된 update_item_code_references는 should_close=False일 때 커밋 안함?
                # -> db.py를 보니 conn을 넘기면 should_close=False이고, finally에서 close()만 안함.
                # -> conn.commit()은 should_close일 때만 함.
                # -> 따라서 여기서 명시적으로 커밋해야 함. OK.
                update_item_code_references(old_code, new_code, conn=conn)
                success_count += 1
            
            conn.commit()
            
            msg = f"총 {len(targets)}건 중 {success_count}건 변경 완료."
            if skipped:
                msg += f"\n\n[건너김 - 중복됨 ({len(skipped)}건)]\n" + ", ".join(skipped[:10])
                if len(skipped) > 10: msg += " ..."
            
            QtWidgets.QMessageBox.information(self, "완료", msg)
            self.load_product_list()
            
        except Exception as e:
            conn.rollback()
            QtWidgets.QMessageBox.critical(self, "오류", f"일괄 변경 중 오류가 발생했습니다:\n{e}")
        finally:
            conn.close()

    def batch_remove_prefix(self):
        """일괄 변경: 'B10000' + 6자리 숫자 코드에서 접두사 제거"""
        reply = QtWidgets.QMessageBox.question(
            self, "일괄 변경 확인",
            "'B10000'으로 시작하는 6자리 숫자 코드(예: B10000123456)에서\n"
            "접두사를 제거하여 6자리 숫자(예: 123456)로 변경합니다.\n\n"
            "※ 모든 관련 데이터가 함께 업데이트됩니다.\n"
            "정말로 실행하시겠습니까?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT item_code FROM product_master")
            all_codes = [row[0] for row in cur.fetchall()]
            
            targets = []
            for code in all_codes:
                if code.startswith("B10000") and len(code) == 12 and code[6:].isdigit():
                    targets.append(code)
            
            if not targets:
                QtWidgets.QMessageBox.information(self, "알림", "변경 대상 품목(B10000+6자리)이 없습니다.")
                return

            success_count = 0
            skipped = []

            for old_code in targets:
                new_code = old_code.replace("B10000", "", 1)
                
                if new_code in all_codes:
                    skipped.append(f"{old_code} -> {new_code} (이미 존재함)")
                    continue
                
                update_item_code_references(old_code, new_code, conn=conn)
                success_count += 1
            
            conn.commit()
            
            msg = f"총 {len(targets)}건 중 {success_count}건 변경 완료."
            if skipped:
                msg += f"\n\n[건너김 - 중복됨 ({len(skipped)}건)]\n" + ", ".join(skipped[:10])
                if len(skipped) > 10: msg += " ..."
            
            QtWidgets.QMessageBox.information(self, "완료", msg)
            self.load_product_list()
            
        except Exception as e:
            conn.rollback()
            QtWidgets.QMessageBox.critical(self, "오류", f"일괄 변경 중 오류가 발생했습니다:\n{e}")
        finally:
            conn.close()


class ProductMasterDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, is_edit=False, product_data=None, settings=None):
        super().__init__(parent)
        self.is_edit = is_edit
        self.product_data = product_data
        self.settings = settings # ✅ settings 저장
        self.setup_ui()

        if is_edit and product_data:
            self.load_product_data()

    def setup_ui(self):
        title = "제품 수정" if self.is_edit else "새 제품 추가"
        self.setWindowTitle(title)
        self.setMinimumWidth(600)

        form = QtWidgets.QFormLayout(self)

        self.edt_item_code = QtWidgets.QLineEdit()
        self.edt_item_code.setPlaceholderText("예: B10000805")

        self.edt_rev = QtWidgets.QLineEdit()
        self.edt_rev.setPlaceholderText("예: 055")

        self.edt_product_name = QtWidgets.QLineEdit()
        self.edt_product_name.setMinimumWidth(400)
        self.edt_product_name.setPlaceholderText("예: ASSY-MOD 29,CTRL,HEATER,XTAL,ROHS,TESTED")

        # ✅ [추가] 약어 입력
        self.edt_abbreviation = QtWidgets.QLineEdit()
        self.edt_abbreviation.setPlaceholderText("예: MOD 29")

        self.edt_unit_price_jpy = MoneyLineEdit(max_value=1_000_000_000)
        self.edt_unit_price_jpy.setPlaceholderText("예: 405000")
        self.edt_unit_price_jpy.setMinimumWidth(200)

        self.edt_purchase_price_krw = MoneyLineEdit(max_value=1_000_000_000)
        self.edt_purchase_price_krw.setPlaceholderText("예: 3249333")
        self.edt_purchase_price_krw.setMinimumWidth(200)

        self.edt_description = QtWidgets.QLineEdit()
        self.edt_description.setMinimumWidth(400)
        self.edt_description.setPlaceholderText("제품에 대한 추가 설명")

        self.cmb_item_type = QtWidgets.QComboBox()
        self.cmb_item_type.addItem("완제품 (PRODUCT) - 판매 대상", "PRODUCT")
        self.cmb_item_type.addItem("모듈 (MODULE) - 반제품", "MODULE")
        self.cmb_item_type.addItem("부품 (PART) - 구매/조립 자재", "PART")
        
        # ✅ [추가] 판매 가능 여부 체크박스 (기본값 False)
        self.chk_is_active = QtWidgets.QCheckBox("판매 가능 (체크 해제 시 '내부용' 상태로 등록됩니다)")
        self.chk_is_active.setChecked(False) # 기본값 False

        form.addRow("품목코드*", self.edt_item_code)
        form.addRow("Rev", self.edt_rev)
        form.addRow("제품명*", self.edt_product_name)
        form.addRow("약어", self.edt_abbreviation)
        
        # ✅ 프라이버시 모드 체크
        is_privacy = False
        if self.settings and self.settings.value("view/privacy_mode", False, type=bool):
            is_privacy = True
        
        # 프라이버시 모드가 아닐 때만 표시
        if not is_privacy:
            form.addRow("판매단가(엔)", self.edt_unit_price_jpy)
            form.addRow("발주단가(원)", self.edt_purchase_price_krw)
            
        form.addRow("설명", self.edt_description)
        form.addRow("생산 유형*", self.cmb_item_type)
        form.addRow("상태", self.chk_is_active) 

        # ---------------------------------------------------------------------
        # ✅ [추가] 포장 규격 (Packing Specs) 그룹박스
        # ---------------------------------------------------------------------
        packing_group = QtWidgets.QGroupBox("포장 및 적재 사양")
        packing_layout = QtWidgets.QFormLayout(packing_group)

        self.edt_box_l = QtWidgets.QLineEdit()
        self.edt_box_l.setPlaceholderText("mm")
        self.edt_box_w = QtWidgets.QLineEdit()
        self.edt_box_w.setPlaceholderText("mm")
        self.edt_box_h = QtWidgets.QLineEdit()
        self.edt_box_h.setPlaceholderText("mm")
        
        # 가로배치 (L x W x H)
        size_layout = QtWidgets.QHBoxLayout()
        size_layout.addWidget(QtWidgets.QLabel("L:"))
        size_layout.addWidget(self.edt_box_l)
        size_layout.addWidget(QtWidgets.QLabel("W:"))
        size_layout.addWidget(self.edt_box_w)
        size_layout.addWidget(QtWidgets.QLabel("H:"))
        size_layout.addWidget(self.edt_box_h)
        
        self.edt_box_weight = QtWidgets.QLineEdit()
        self.edt_box_weight.setPlaceholderText("kg (예: 6.8)")
        
        self.edt_items_per_box = QtWidgets.QLineEdit()
        self.edt_items_per_box.setPlaceholderText("박스당 수량 (예: 20)")
        
        self.edt_max_layer = QtWidgets.QLineEdit()
        self.edt_max_layer.setPlaceholderText("팔레트 최대 적재 단수 (예: 4)")

        packing_layout.addRow("박스 크기 (mm)", size_layout)
        packing_layout.addRow("박스 무게 (kg)", self.edt_box_weight)
        packing_layout.addRow("박스당 제품수량", self.edt_items_per_box)
        packing_layout.addRow("최대 적재 단수", self.edt_max_layer)
        
        form.addRow(packing_group)
        # ---------------------------------------------------------------------

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept_dialog)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def load_product_data(self):
        if not self.product_data:
            return

        # unpacked tuple based on get_selected_product query
        # unpacked tuple based on get_selected_product query
        (product_id, item_code, rev, product_name, abbreviation, unit_price_jpy, purchase_price_krw, description, 
         created_at, updated_at, is_active, item_type,
         items_per_box, box_l, box_w, box_h, box_weight, max_layer) = self.product_data

        self.edt_item_code.setText(str(item_code))
        self.edt_rev.setText(str(rev or ""))
        self.edt_product_name.setText(str(product_name))
        self.edt_abbreviation.setText(str(abbreviation or ""))
        self.edt_unit_price_jpy.set_value((unit_price_jpy or 0) // 100)
        self.edt_purchase_price_krw.set_value((purchase_price_krw or 0) // 100)
        self.edt_description.setText(str(description or ""))

        # ✅ [수정] 다양한 표기법 대응 (대소문자, 한글, 레거시)
        safe_type = str(item_type).upper().strip() if item_type else ""
        
        if safe_type in ['PRODUCT', 'SELLABLE', '완제품']:
            target_data = 'PRODUCT'
        elif safe_type in ['MODULE', '모듈']:
            target_data = 'MODULE'
        elif safe_type in ['PART', 'SUB_COMPONENT', '부품']:
            target_data = 'PART'
        else:
            target_data = safe_type # 그 외는 그대로 시도

        index = self.cmb_item_type.findData(target_data)
        self.cmb_item_type.setCurrentIndex(index if index >= 0 else 0)
        
        # ✅ [추가] 상태 로드
        self.chk_is_active.setChecked(bool(is_active))
        
        # ✅ [추가] 포장 정보 로드
        self.edt_items_per_box.setText(str(items_per_box if items_per_box is not None else 1))
        self.edt_box_l.setText(str(box_l if box_l is not None else 0))
        self.edt_box_w.setText(str(box_w if box_w is not None else 0))
        self.edt_box_h.setText(str(box_h if box_h is not None else 0))
        self.edt_box_weight.setText(str(box_weight if box_weight is not None else 0.0))
        self.edt_max_layer.setText(str(max_layer if max_layer is not None else 0))

    def accept_dialog(self):
        item_code = self.edt_item_code.text().strip()
        rev = self.edt_rev.text().strip() or None
        product_name = self.edt_product_name.text().strip()
        abbreviation = self.edt_abbreviation.text().strip() or None

        if not item_code or not product_name:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "품목코드와 제품명은 필수입니다.")
            return

        unit_price_jpy_cents = self.edt_unit_price_jpy.get_value() * 100
        purchase_price_krw_cents = self.edt_purchase_price_krw.get_value() * 100
        description = self.edt_description.text().strip() or None

        item_type = self.cmb_item_type.currentData()
        item_type = self.cmb_item_type.currentData()
        is_active_val = 1 if self.chk_is_active.isChecked() else 0 

        # 포장 정보 값 읽기
        def to_int(s, default=0):
            try: return int(s)
            except: return default
        def to_float(s, default=0.0):
            try: return float(s)
            except: return default
            
        items_per_box = to_int(self.edt_items_per_box.text(), 1)
        box_l = to_int(self.edt_box_l.text(), 0)
        box_w = to_int(self.edt_box_w.text(), 0)
        box_h = to_int(self.edt_box_h.text(), 0)
        box_weight = to_float(self.edt_box_weight.text(), 0.0)
        max_layer = to_int(self.edt_max_layer.text(), 0)

        try:
            if self.is_edit and self.product_data:
                 # 수정 모드: 기존 ID로 업데이트 (키 값 변경 허용)
                 product_id = self.product_data[0]
                 update_product_master(
                     product_id, item_code, rev, product_name,
                     unit_price_jpy_cents, purchase_price_krw_cents, description, item_type,
                     items_per_box=items_per_box, box_l=box_l, box_w=box_w, box_h=box_h,
                     box_weight=box_weight, max_layer=max_layer, abbreviation=abbreviation
                 )
                 
                 conn = get_conn()
                 cur = conn.cursor()
                 cur.execute("UPDATE product_master SET is_active=? WHERE id=?", (is_active_val, product_id))
                 conn.commit()
                 conn.close()

                 action_msg = "수정되었습니다"
                 new_action = False
            else:
                # 추가 모드: 신규 생성 (또는 기존 코드/리비전이 있으면 업데이트)
                result = add_or_update_product_master(
                    item_code, rev, product_name,
                    unit_price_jpy_cents, purchase_price_krw_cents, description, item_type,
                    is_active=is_active_val,
                    items_per_box=items_per_box, box_l=box_l, box_w=box_w, box_h=box_h,
                    box_weight=box_weight, max_layer=max_layer, abbreviation=abbreviation
                )
                
                if result == 'DUPLICATE_INACTIVE':
                    # 사용자가 활성화를 원했을 수 있음.
                    if is_active_val == 1:
                        # 이미 있는데 비활성 상태임. 활성화 할까요? 묻거나, 그냥 경고.
                        # 기획상 "단종된 중복 품목"이라고 경고함.
                        # 여기선 그대로 둠.
                        QtWidgets.QMessageBox.warning(self, "중복 경고", 
                                                      "이미 존재하는 '내부용' 품목입니다.\n목록에서 해당 품목을 찾아 '판매 가능'으로 변경해주세요.")
                        return

                new_action = (result == 'INSERTED')
                action_msg = "추가되었습니다" if new_action else "수정되었습니다"

            QtWidgets.QMessageBox.information(self, "완료", f"제품이 {action_msg}.")
            self.accept()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"제품 저장 중 오류가 발생했습니다:\n{str(e)}")


    def set_privacy_mode(self, enabled: bool):
        """재무 정보 숨기기 설정 (Dialog)"""
        # 이 메소드는 Dialog에서 호출될 일이 없으므로 인터페이스 호환을 위해 둠.
        # 실제는 Dialog가 동적으로 폼을 구성하므로 실시간 변경보다는 열릴 때 결정됨.
        pass


class WhereUsedDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, child_code=None, child_name=None, settings=None):
        super().__init__(parent)
        self.child_code = child_code
        self.child_name = child_name
        self.settings = settings
        self.setWindowTitle(f"역전개 (Where Used) - {child_code}")
        self.resize(750, 400)
        self.setWindowModality(Qt.NonModal)
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        info_bg = QtWidgets.QFrame()
        info_bg.setStyleSheet("background-color: #E3F2FD; border-radius: 5px; padding: 10px;")
        info_layout = QtWidgets.QVBoxLayout(info_bg)
        
        lbl_title = QtWidgets.QLabel(f"부품 '{self.child_name}' ({self.child_code})")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #1565C0;")
        lbl_desc = QtWidgets.QLabel("위 부품을 자재(Child)로 사용하고 있는 상위 모듈/완제품 목록입니다.")
        lbl_desc.setStyleSheet("color: #555;")
        
        info_layout.addWidget(lbl_title)
        info_layout.addWidget(lbl_desc)
        
        layout.addWidget(info_bg)
        
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["No.", "상위 품목코드", "품목명", "소요량", "단위", "유형"])
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        
        # ✅ [수정] 수직 헤더 숨기기 (No. 중복 표시 방지)
        self.table.verticalHeader().setVisible(False)
        
        self.table.setColumnWidth(0, 35)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 350)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 80)

        apply_table_resize_policy(self.table)
        
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        
        layout.addWidget(self.table)
        
        btn_layout = QtWidgets.QHBoxLayout()
        # ✅ [추가] CSV 내보내기 버튼
        btn_export = QtWidgets.QPushButton("CSV 출력")
        btn_export.clicked.connect(self.export_csv)
        btn_export.setStyleSheet("padding: 5px 15px; background-color: #e9ecef;")

        btn_close = QtWidgets.QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        btn_close.setStyleSheet("padding: 5px 15px;")
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_export)
        btn_layout.addWidget(btn_close)
        
        layout.addLayout(btn_layout)

    def load_data(self):
        if not self.child_code:
            return
            
        parents = get_parent_items(self.child_code)
        self.table.setRowCount(0)
        self.table.setRowCount(len(parents))
        
        type_map = {
            'PRODUCT': '완제품', 'MODULE': '모듈', 'PART': '부품',
            'SELLABLE': '완제품(구)', 'SUB_COMPONENT': '부품(구)'
        }
        
        for r, p in enumerate(parents):
            # p: {parent_code, parent_name, qty, remarks, item_type}
            
            # 0: No
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(r + 1)))
            
            # 1: Code
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(p['parent_code'])))
            
            # 2: Name
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(str(p['parent_name'])))
            
            # 3: Qty
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(p['qty'])))

            # 4: Unit
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(p.get('unit', ''))))
            
            # 5: Type
            itype = p.get('item_type', '')
            display_type = type_map.get(itype, itype)
            self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(display_type))

    def showEvent(self, event):
        super().showEvent(event)
        # 다이얼로그가 보인 직후(레이아웃 완료 후)에 컬럼 폭 복원
        QtCore.QTimer.singleShot(0, self.restore_column_widths)

    def done(self, result):
        """다이얼로그가 닫힐 때(OK, Cancel, X 등) 항상 호출됨"""
        self.save_column_widths()
        super().done(result)

    def save_column_widths(self):
        if not self.settings: return
        widths = []
        for col in range(self.table.columnCount()):
            widths.append(self.table.columnWidth(col))
        self.settings.setValue("where_used_dialog/column_widths", widths)

    def restore_column_widths(self):
        if not self.settings: return
        widths = self.settings.value("where_used_dialog/column_widths")
        if widths:
            self.table.horizontalHeader().blockSignals(True)
            try:
                for col, width in enumerate(widths):
                    if col < self.table.columnCount():
                        self.table.setColumnWidth(col, int(width))
            finally:
                self.table.horizontalHeader().blockSignals(False)

    def on_item_double_clicked(self, item):
        """항목 더블클릭 시 부모 창(BOM Widget)의 트리에 해당 품목이 있으면 하이라이트"""
        row = item.row()
        # 1: Code (Parent Items Code)
        parent_code = self.table.item(row, 1).text()
        # 2: Name (Parent Items Name)
        parent_name = self.table.item(row, 2).text()
        
        # 부모가 BOMWidget인 경우 해당 메서드 호출
        if hasattr(self.parent(), 'navigate_to_usage'):
             self.parent().navigate_to_usage(parent_code, parent_name, self.child_code)
        
        # 이전 호환성 (highlight_item_in_tree만 있는 경우 - 거의 없을 예정)
        elif hasattr(self.parent(), 'highlight_item_in_tree'):
             self.parent().highlight_item_in_tree(parent_code) # 구버전 동작 (부모 하이라이트)

    def export_csv(self):
        """결과를 CSV로 저장"""
        if self.table.rowCount() == 0:
            QtWidgets.QMessageBox.information(self, "알림", "저장할 데이터가 없습니다.")
            return

        # Child Info for filename
        child_info = f"{self.child_name}_{self.child_code}"
        # Remove invalid filename characters
        child_info = "".join(c for c in child_info if c.isalnum() or c in (' ', '_', '-')).strip()
        
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "CSV 내보내기", f"WhereUsed_{child_info}.csv", "CSV Files (*.csv)"
        )
        if not filename:
            return

        import csv
        try:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                
                # ✅ 상단에 부품 정보 표기
                writer.writerow(["부품명", self.child_name])
                writer.writerow(["부품코드", self.child_code])
                writer.writerow([]) # 빈 줄
                
                # ✅ 헤더 (단위 포함)
                writer.writerow(["No.", "상위 품목코드", "품목명", "소요량", "단위", "유형"])
                
                # 데이터
                for r in range(self.table.rowCount()):
                    # load_data 순서: 0:No, 1:Code, 2:Name, 3:Qty, 4:Unit, 5:Type
                    no = self.table.item(r, 0).text()
                    code = self.table.item(r, 1).text()
                    name = self.table.item(r, 2).text()
                    qty = self.table.item(r, 3).text()
                    unit = self.table.item(r, 4).text()
                    itype = self.table.item(r, 5).text()
                    writer.writerow([no, code, name, qty, unit, itype])
            
            QtWidgets.QMessageBox.information(self, "완료", "파일이 저장되었습니다.")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다: {e}")
