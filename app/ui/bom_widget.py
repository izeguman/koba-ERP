# app/ui/bom_widget.py

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QGroupBox, QListWidget,
                               QTreeWidget, QTreeWidgetItem, QMessageBox, QLabel,
                               QPushButton, QSplitter, QHeaderView, QDoubleSpinBox)
from PySide6.QtCore import Qt
from ..db import get_conn, query_all
from .autocomplete_widgets import AutoCompleteLineEdit


class BomWidget(QtWidgets.QWidget):
    """BOM (자재 명세서) 관리 탭 위젯"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.current_parent_code = None
        self.setup_ui()
        self.load_existing_boms()  # 초기 로드

    def setup_ui(self):
        main_layout = QHBoxLayout(self)

        # ==========================================
        # [좌측 패널] 등록된 BOM 목록 조회
        # ==========================================
        left_panel = QGroupBox("등록된 BOM 목록")
        left_layout = QVBoxLayout(left_panel)

        self.bom_list_widget = QListWidget()
        self.bom_list_widget.itemClicked.connect(self.on_existing_bom_clicked)

        btn_refresh_list = QPushButton("목록 새로고침")
        btn_refresh_list.clicked.connect(self.load_existing_boms)

        left_layout.addWidget(btn_refresh_list)
        left_layout.addWidget(self.bom_list_widget)

        # ==========================================
        # [우측 패널] BOM 편집
        # ==========================================
        right_panel = QtWidgets.QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 1. 부모 품목 선택 영역
        parent_group = QGroupBox("1. BOM 대상 품목 (부모)")
        parent_layout = QVBoxLayout(parent_group)

        self.edt_parent_search = AutoCompleteLineEdit()
        self.edt_parent_search.setPlaceholderText("부모 품목 검색 (코드/명칭)...")
        self.edt_parent_search.product_selected.connect(self.on_parent_selected)

        self.lbl_parent_info = QLabel("BOM을 정의할 '판매/조립품'을 선택하거나, 좌측 목록에서 선택하세요.")
        self.lbl_parent_info.setStyleSheet("font-weight: bold; color: #0066cc; padding: 5px;")

        parent_layout.addWidget(self.edt_parent_search)
        parent_layout.addWidget(self.lbl_parent_info)

        # 2. 하위 부품 구성 영역
        child_group = QGroupBox("2. 하위 부품 구성 (BOM)")
        self.child_group_box = child_group  # 활성/비활성 제어를 위해 저장
        child_group.setEnabled(False)  # 부모 선택 전 비활성화

        child_layout = QVBoxLayout(child_group)

        # 2-1. 자식 추가 폼
        add_layout = QHBoxLayout()
        self.edt_child_search = AutoCompleteLineEdit()
        self.edt_child_search.setPlaceholderText("추가할 자식 부품 검색...")

        self.sp_qty = QDoubleSpinBox()
        self.sp_qty.setDecimals(2)
        self.sp_qty.setRange(0.01, 1000.0)
        self.sp_qty.setValue(1.0)

        btn_add = QPushButton("추가")
        btn_add.clicked.connect(self.add_child_item)

        add_layout.addWidget(self.edt_child_search, 1)
        add_layout.addWidget(QLabel("수량:"))
        add_layout.addWidget(self.sp_qty)
        add_layout.addWidget(btn_add)

        # 2-2. BOM 트리
        self.bom_tree = QTreeWidget()
        self.bom_tree.setHeaderLabels(["품목코드", "Rev", "제품명", "필요수량"])
        self.bom_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bom_tree.customContextMenuRequested.connect(self.show_context_menu)

        header = self.bom_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        child_layout.addLayout(add_layout)
        child_layout.addWidget(self.bom_tree)

        right_layout.addWidget(parent_group)
        right_layout.addWidget(child_group)

        # ==========================================
        # [스플리터] 좌우 패널 배치
        # ==========================================
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 700])

        main_layout.addWidget(splitter)

    def load_existing_boms(self):
        """이미 BOM이 정의된 부모 품목들을 좌측 리스트에 표시"""
        self.bom_list_widget.clear()
        try:
            conn = get_conn()
            cur = conn.cursor()
            # BOM 테이블에 존재하는 distinct parent_item_code 조회
            sql = """
                SELECT DISTINCT b.parent_item_code, p.product_name 
                FROM bom_items b
                LEFT JOIN product_master p ON b.parent_item_code = p.item_code
                ORDER BY p.product_name, b.parent_item_code
            """
            cur.execute(sql)
            rows = cur.fetchall()
            conn.close()

            for code, name in rows:
                display = f"{code} - {name or '품명없음'}"
                item = QtWidgets.QListWidgetItem(display)
                item.setData(Qt.UserRole, code)
                self.bom_list_widget.addItem(item)

        except Exception as e:
            print(f"BOM 목록 로드 실패: {e}")

    def on_existing_bom_clicked(self, item):
        """좌측 목록에서 BOM 선택 시 -> 우측 에디터에 로드"""
        parent_code = item.data(Qt.UserRole)

        # 부모 품목 정보 조회 (이름 등)
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT item_code, product_name, rev FROM product_master WHERE item_code = ?", (parent_code,))
            result = cur.fetchone()
            conn.close()

            if result:
                # on_parent_selected 함수 재사용을 위해 딕셔너리 구성
                product_data = {
                    'item_code': result[0],
                    'product_name': result[1],
                    'rev': result[2]
                }
                self.on_parent_selected(product_data)
            else:
                # 마스터에 없으면 코드만으로 세팅
                product_data = {'item_code': parent_code, 'product_name': '알 수 없음', 'rev': ''}
                self.on_parent_selected(product_data)

        except Exception as e:
            print(f"부모 품목 정보 로드 실패: {e}")

    def on_parent_selected(self, product_data):
        """부모 품목이 선택되었을 때 (검색창 또는 리스트 클릭)"""
        code = product_data.get('item_code')
        name = product_data.get('product_name')
        rev = product_data.get('rev') or ""

        self.current_parent_code = code

        rev_str = f" (Rev: {rev})" if rev else ""
        self.lbl_parent_info.setText(f"<b>{name}</b>{rev_str}\n[{code}]")

        # 입력창 텍스트는 클릭 시에는 업데이트 안하고 라벨만 갱신
        # self.edt_parent_search.setText(code)

        self.child_group_box.setEnabled(True)
        self.child_group_box.setTitle(f"2. [{code}]의 하위 부품 목록 (BOM)")

        self.load_bom_structure(code)

    def load_bom_structure(self, parent_code):
        """DB에서 해당 부모의 BOM 정보를 읽어와 트리에 표시"""
        self.bom_tree.clear()
        try:
            sql = """
                SELECT 
                    b.id, 
                    b.child_item_code, 
                    pm.rev, 
                    pm.product_name, 
                    b.quantity_required
                FROM bom_items b
                LEFT JOIN product_master pm ON b.child_item_code = pm.item_code
                WHERE b.parent_item_code = ?
                -- 동일 품목코드의 여러 Rev 중 하나만 표시되거나 하는 문제 방지
                GROUP BY b.id, b.child_item_code, pm.product_name, b.quantity_required
                ORDER BY pm.product_name
            """
            rows = query_all(sql, (parent_code,))

            for bom_id, child_code, rev, name, qty in rows:
                item = QTreeWidgetItem(self.bom_tree)
                item.setData(0, Qt.UserRole, bom_id)
                item.setText(0, child_code)
                item.setText(1, rev or "")
                item.setText(2, name or " (품목 마스터에 없음)")
                item.setText(3, str(qty))

        except Exception as e:
            QMessageBox.critical(self, "BOM 로드 오류", f"BOM 목록 로드 중 오류가 발생했습니다:\n{e}")

    def add_child_item(self):
        """자식 품목 추가 (즉시 DB 저장)"""
        if not self.current_parent_code:
            QMessageBox.warning(self, "오류", "부모 품목이 선택되지 않았습니다.")
            return

        # 입력창에서 텍스트 가져오기
        # AutoCompleteLineEdit가 선택된 데이터를 내부적으로 가지고 있을 수 있음
        # 여기서는 간단히 텍스트 기준으로 처리하거나, AutoComplete 위젯의 product_data 활용

        # 입력된 텍스트가 'CODE - NAME' 형식이면 코드만 추출
        child_text = self.edt_child_search.text().strip()
        child_code = child_text.split(' - ')[0]

        if not child_code:
            QMessageBox.warning(self, "오류", "추가할 자식 부품을 입력하세요.")
            return

        if child_code == self.current_parent_code:
            QMessageBox.critical(self, "입력 오류", "부모 품목은 자식 부품이 될 수 없습니다.")
            return

        qty = self.sp_qty.value()

        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO bom_items (parent_item_code, child_item_code, quantity_required) VALUES (?, ?, ?)",
                (self.current_parent_code, child_code, qty)
            )
            conn.commit()
            conn.close()

            self.load_bom_structure(self.current_parent_code)
            self.load_existing_boms()  # 좌측 목록 갱신 (신규 생성인 경우)

            self.edt_child_search.clear()
            self.sp_qty.setValue(1.0)
            self.edt_child_search.setFocus()

        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                QMessageBox.warning(self, "중복 오류", f"이미 등록된 하위 부품입니다: {child_code}")
            else:
                QMessageBox.critical(self, "저장 오류", f"BOM 저장 중 오류가 발생했습니다:\n{e}")

    def show_context_menu(self, position):
        item = self.bom_tree.itemAt(position)
        if not item: return

        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("삭제")
        delete_action.triggered.connect(self.delete_child_item)
        menu.exec_(self.bom_tree.mapToGlobal(position))

    def delete_child_item(self):
        item = self.bom_tree.currentItem()
        if not item: return

        bom_id = item.data(0, Qt.UserRole)
        child_code = item.text(0)

        reply = QMessageBox.question(
            self, "BOM 삭제",
            f"'{self.current_parent_code}'의 하위 부품에서\n'{child_code}' 항목을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("DELETE FROM bom_items WHERE id = ?", (bom_id,))
                conn.commit()
                conn.close()

                self.load_bom_structure(self.current_parent_code)
                # 만약 자식이 하나도 없게 되면 BOM 목록에서 사라져야 하는지?
                # 현재 로직상 BOM 항목이 없으면 목록 쿼리에서 자동으로 빠짐
                self.load_existing_boms()

            except Exception as e:
                QMessageBox.critical(self, "삭제 오류", f"BOM 삭제 중 오류가 발생했습니다:\n{e}")

    def load_data_if_needed(self):
        """메인 윈도우 탭 전환 시 호출"""
        self.load_existing_boms()