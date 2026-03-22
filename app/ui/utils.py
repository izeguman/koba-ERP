# utils.py

from datetime import datetime
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
import os
import platform
import unicodedata
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        elif getattr(sys, 'frozen', False):
            # In one-dir mode, the executable directory is the base
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.abspath(".")
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def get_icon_path():
    """
    아이콘 경로를 안전하게 찾습니다.
    1. app/ui/koba_erp_final.ico (개발 환경 및 기본 spec 설정)
    2. koba_erp_final.ico (PyInstaller 루트에 포함된 경우)
    """
    # 1. 기본 경로 시도
    path1 = resource_path('app/ui/koba_erp_final.ico')
    if os.path.exists(path1):
        return path1
        
    # 2. 루트 경로 시도 (spec 파일에서 루트로 복사한 경우)
    path2 = resource_path('koba_erp_final.ico')
    if os.path.exists(path2):
        return path2
        
    return None


class AdjacentColumnResizer(QtCore.QObject):
    """
    컬럼 크기 조절 시 인접한 다음 컬럼의 크기를 반대로 조절하여
    전체 테이블 너비나 다른 컬럼에 영향을 주지 않도록 하는 리사이저.
    """
    def __init__(self, header: QtWidgets.QHeaderView):
        super().__init__(header)
        self.header = header
        self.header.sectionResized.connect(self.on_section_resized)
        self.resizing = False

    def on_section_resized(self, logical_index, old_size, new_size):
        if self.resizing:
            return

        # 1. 마지막 섹션인지 확인 (마지막 섹션은 Stretch이므로 패스)
        # 현재 보이는 순서(visual index) 기준 다음 컬럼 찾기
        visual_index = self.header.visualIndex(logical_index)
        if visual_index >= self.header.count() - 1:
            return

        # 다음 시각적 컬럼의 logical index 찾기 (숨겨진 컬럼 건너뛰기)
        next_logical_index = -1
        for v_idx in range(visual_index + 1, self.header.count()):
            l_idx = self.header.logicalIndex(v_idx)
            if not self.header.isSectionHidden(l_idx):
                next_logical_index = l_idx
                break
        
        if next_logical_index == -1:
            return # 뒤에 더 이상 보이는 컬럼이 없음

        # 2. 크기 변화량 계산
        delta = new_size - old_size
        
        # 3. 제약 조건 확인 및 적용
        current_next_size = self.header.sectionSize(next_logical_index)
        min_width = self.header.minimumSectionSize()
        
        # 다음 컬럼이 줄어들 수 있는 최대 양
        available_shrink = current_next_size - min_width
        
        corrected_delta = delta
        
        # 늘리는 경우 (delta > 0): 다음 컬럼이 그만큼 줄어들어야 함
        if delta > 0:
            if delta > available_shrink:
                corrected_delta = available_shrink
                
        # 줄이는 경우 (delta < 0): 다음 컬럼이 그만큼 늘어나야 함 (제약 없음)
        # 단, 현재 컬럼이 min_width보다 작아지는 것은 QHeaderView가 알아서 막음 (보통)
        
        self.resizing = True
        
        # 만약 delta가 제한되어야 한다면, 현재 컬럼 크기도 강제로 되돌림
        if corrected_delta != delta:
            self.header.resizeSection(logical_index, old_size + corrected_delta)
            
        # 다음 컬럼 리사이즈 (corrected_delta 만큼 반대로)
        new_next_size = current_next_size - corrected_delta
        self.header.resizeSection(next_logical_index, new_next_size)
        
        self.resizing = False


def apply_table_resize_policy(widget: QtWidgets.QTableWidget | QtWidgets.QTreeWidget):
    """
    테이블/트리의 모든 컬럼을 사용자가 크기 조절 가능한 'Interactive' 모드로 설정하고,
    마지막 섹션(컬럼)이 남은 공간을 모두 차지하도록 하여 가로 스크롤바가 생기지 않게 합니다.
    또한, 인접 컬럼 리사이징(Splitter 효과) 로직을 적용합니다.
    """
    if isinstance(widget, QtWidgets.QTreeWidget):
        header = widget.header()
    else:
        header = widget.horizontalHeader()

    # 1. 모든 컬럼을 사용자가 직접 크기를 조절할 수 있는 모드로 변경
    for c in range(header.count()):
        header.setSectionResizeMode(c, QtWidgets.QHeaderView.Interactive)

    # 2. 마지막 컬럼이 남은 공간을 모두 채우도록 설정
    header.setStretchLastSection(True)

    # 3. 가로 스크롤바 비활성화
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    
    # ✅ [추가] 세로 스크롤바 상시 표시 (스크롤바 유무에 따른 너비 흔들림 방지)
    # 내용이 적을 때는 비활성화(회색)되고, 많아지면 활성화됩니다.
    widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
    
    # 4. 인접 컬럼 리사이저 부착 (GC 방지 위해 widget 속성으로 저장)
    resizer = AdjacentColumnResizer(header)
    widget._column_resizer = resizer


def parse_due_text(text: str) -> str | None:
    """날짜 형식의 텍스트를 YYYY-MM-DD 로 정규화합니다."""
    s = (text or "").strip()
    if not s:
        return None
    fmts = [
        "%Y-%m-%d", "%Y/%m/%d", "%y-%m-%d", "%y/%m/%d",
        "%d-%b-%y", "%d-%b-%Y", "%d/%m/%Y", "%m/%d/%Y",
    ]
    for f in fmts:
        try:
            dt = datetime.strptime(s, f)
            if dt.year < 2000:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, Exception):
            continue
    return None


def parse_datetime_text(text: str) -> str | None:
    """날짜와 시간 형식의 텍스트를 YYYY-MM-DD HH:MM:SS 로 정규화합니다."""
    s = (text or "").strip()
    if not s:
        return None
    fmts_dt = ["%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"]
    for f in fmts_dt:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, Exception):
            continue
    date_part = parse_due_text(s.split()[0])
    if date_part:
        return f"{date_part} 00:00:00"
    return None


def get_dynamic_onedrive_path(stored_path: str) -> str:
    """
    DB에 저장된 절대 경로를 현재 PC의 OneDrive 경로로 변환하고,
    자소 분리(NFD) 현상을 해결하여(NFC) 유효한 경로를 반환합니다.
    """
    if not stored_path:
        return ""

    # 1. 현재 PC의 OneDrive 루트 경로 찾기
    onedrive_root = os.environ.get("OneDrive")
    if not onedrive_root:
        onedrive_root = os.environ.get("OneDriveConsumer")
    if not onedrive_root:
        onedrive_root = os.environ.get("OneDriveCommercial")

    if not onedrive_root:
        onedrive_root = os.path.join(os.path.expanduser("~"), "OneDrive")

    # 2. 경로 변환 로직
    final_path = stored_path  # 기본값

    if "OneDrive" in stored_path:
        # 경로 정규화 (슬래시/역슬래시 통일)
        norm_stored = os.path.normpath(stored_path)

        try:
            idx = norm_stored.find("OneDrive")
            if idx != -1:
                relative_path = norm_stored[idx + 8:]
                if relative_path.startswith(os.sep):
                    relative_path = relative_path[1:]

                # 현재 PC의 OneDrive 루트와 결합
                new_path = os.path.join(onedrive_root, relative_path)

                # ✅ [핵심 수정 1] 유니코드 정규화 (NFC: 윈도우 표준) 적용
                # (자소가 분리된 'ㅎ+ㅏ+ㄴ'을 '한'으로 합침)
                new_path = unicodedata.normalize('NFC', new_path)

                final_path = new_path

        except Exception as e:
            print(f"경로 변환 중 오류: {e}")

    # ✅ [핵심 수정 2] 파일 존재 여부 최종 확인
    # 그냥 확인해서 있으면 OK
    if os.path.exists(final_path):
        return final_path

    # -------------------------------------------------------
    # [비상 대책] 윈도우 긴 경로(260자) 제한 또는 미세한 불일치 해결 시도
    # -------------------------------------------------------

    # 시도 1: 혹시 NFD(Mac 방식)로 되어 있나? (반대로 변환해서 체크)
    path_nfd = unicodedata.normalize('NFD', final_path)
    if os.path.exists(path_nfd):
        return path_nfd

    # 시도 2: 윈도우 긴 경로 접두사(\\?\) 붙이기 (경로가 너무 길 때)
    if platform.system() == 'Windows' and len(final_path) > 200:
        long_path = "\\\\?\\" + os.path.abspath(final_path)
        if os.path.exists(long_path):
            return long_path

    # 그래도 없으면 어쩔 수 없이 변환된 경로(NFC) 반환 (에러 메시지용)
    return final_path