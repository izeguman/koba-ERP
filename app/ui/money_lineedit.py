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

        # 음수 부호 처리
        is_negative = text.startswith('-')
        
        # 숫자가 아닌 문자 제거 (부호 제외)
        text = ''.join(c for c in text if c.isdigit())

        if not text:
            text = "0"
            if is_negative:
                # 부호만 있는 경우 필드에 표시할 수 있도록 함 (전담 처리 필요 시)
                pass

        try:
            value = int(text)

            # 최대값 체크
            if value > self.max_value:
                value = self.max_value

            # 천 단위 구분 기호 추가
            formatted = f"{value:,}"
            if is_negative and value > 0:
                formatted = "-" + formatted
            elif is_negative and value == 0:
                # 0인데 마이너스 부호가 입력된 경우 필드에 부호만 남길 수 있게 하거나
                # 일단 "-"로 표시하여 다음 숫자 입력을 기다림
                if original_text == "-":
                    formatted = "-"

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
            self.setText("-" if is_negative and original_text == "-" else "0")
            self.blockSignals(False)

    def get_value(self):
        """쉼표 제거한 정수값(원) 반환"""
        text = self.text().replace(',', '')
        try:
            return int(text)
        except ValueError:
            return 0

    def get_value_cents(self):
        """센트 단위 정수값 반환 (원 * 100)"""
        return self.get_value() * 100

    def set_value(self, value):
        """값(원) 설정"""
        if value is None:
            value = 0
        self.setText(str(value))

    def set_value_from_cents(self, value_cents):
        """센트 단위 정수값으로부터 원 단위 설정 (센트 / 100)"""
        if value_cents is None:
            value_cents = 0
        self.set_value(int(value_cents / 100))

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

        # 숫자 및 마이너스 부호 허용
        # 커서가 맨 앞이거나, 텍스트가 전체 선택된 상태라면 마이너스 부호를 허용함
        is_minus_key = (event.text() == '-')
        can_insert_minus = is_minus_key and (self.cursorPosition() == 0 or self.hasSelectedText())
        
        if event.text().isdigit() or can_insert_minus:
            # 이미 부호가 있는데 또 입력하려는 경우는 무시 (전체 선택된 경우는 제외)
            if is_minus_key and '-' in self.text() and not self.hasSelectedText():
                QtWidgets.QApplication.beep()
                return
            super().keyPressEvent(event)
        else:
            # 그 외 키는 무시 (경고음)
            QtWidgets.QApplication.beep()