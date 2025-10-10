# app/ui/money_lineedit.py
from PySide6 import QtWidgets, QtGui, QtCore


class MoneyLineEdit(QtWidgets.QLineEdit):
    """
    가격 입력용 LineEdit
    - 숫자만 입력 가능
    - 천 단위 구분 기호 자동 표시
    - 붙여넣기 가능 (쉼표 자동 제거)
    - 최대값 제한
    - ✅ 포커스 시 전체 선택 (새 값 바로 입력 가능)
    """

    def __init__(self, parent=None, max_value=1_000_000_000, locale_type='Korean'):
        super().__init__(parent)
        self.max_value = max_value
        self.locale_type = locale_type

        # 오른쪽 정렬
        self.setAlignment(QtCore.Qt.AlignRight)

        # 텍스트 변경 시 포맷팅
        self.textChanged.connect(self.format_number)

        # 초기값 0
        self.setText("0")

    def focusInEvent(self, event):
        """✅ 포커스 받을 때 전체 선택 (새 값 바로 입력 가능)"""
        super().focusInEvent(event)
        # 약간의 지연 후 전체 선택 (Qt의 기본 동작 이후에 실행)
        QtCore.QTimer.singleShot(0, self.selectAll)

    def format_number(self):
        """입력된 숫자를 천 단위 구분 기호로 포맷팅"""
        # ✅ 수정: 커서 위치 계산 로직 변경
        original_text = self.text()
        original_pos = self.cursorPosition()

        # 커서의 위치를 끝에서부터 계산
        offset_from_end = len(original_text) - original_pos

        # 현재 텍스트에서 쉼표 제거
        text = self.text().replace(',', '').replace(' ', '')

        if not text:
            text = "0"

        # 숫자가 아닌 문자 제거
        text = ''.join(c for c in text if c.isdigit())

        if not text:
            text = "0"

        try:
            value = int(text)

            # 최대값 체크
            if value > self.max_value:
                value = self.max_value

            # 천 단위 구분 기호 추가
            formatted = f"{value:,}"

            # 텍스트 변경 이벤트를 일시적으로 차단
            self.blockSignals(True)
            self.setText(formatted)
            self.blockSignals(False)

            # ✅ 수정: 끝에서부터 계산한 offset을 사용하여 새 커서 위치 설정
            new_pos = len(formatted) - offset_from_end

            # 커서 위치가 텍스트 길이를 벗어나지 않도록 보정
            if new_pos < 0:
                new_pos = 0

            self.setCursorPosition(new_pos)

        except ValueError:
            self.blockSignals(True)
            self.setText("0")
            self.blockSignals(False)

    def get_value(self):
        """쉼표 제거한 정수값 반환"""
        text = self.text().replace(',', '')
        try:
            return int(text)
        except ValueError:
            return 0

    def set_value(self, value):
        """값 설정"""
        if value is None:
            value = 0
        self.setText(str(value))

    def keyPressEvent(self, event):
        """키 입력 처리"""
        # Ctrl+V, Ctrl+C, Ctrl+X, Ctrl+A 허용
        if event.matches(QtGui.QKeySequence.Paste) or \
                event.matches(QtGui.QKeySequence.Copy) or \
                event.matches(QtGui.QKeySequence.Cut) or \
                event.matches(QtGui.QKeySequence.SelectAll):
            super().keyPressEvent(event)
            return

        # 숫자와 백스페이스, Delete, 방향키만 허용
        if event.key() in (QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Delete,
                           QtCore.Qt.Key_Left, QtCore.Qt.Key_Right,
                           QtCore.Qt.Key_Home, QtCore.Qt.Key_End,
                           QtCore.Qt.Key_Tab):
            super().keyPressEvent(event)
            return

        # 숫자만 허용
        if event.text().isdigit():
            super().keyPressEvent(event)
        else:
            # 그 외 키는 무시 (경고음)
            QtWidgets.QApplication.beep()