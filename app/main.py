# app/main.py
import sys
from PySide6 import QtWidgets
from .db import get_conn  # 스키마 자동 생성 트리거
from .ui.main_window import MainWindow

def main():
    app = QtWidgets.QApplication(sys.argv)  # 앱 객체 생성 (이벤트 루프 준비)
    _ = get_conn()                          # db.py 모듈의 get_conn을 실행. return 값은 안 받음
    win = MainWindow()                      # 메인 윈도우 생성
    win.show()                              # 창 띄우기
    sys.exit(app.exec())                    # 이벤트 루프 실행(여기서 프로그램이 멈춰 있음)

if __name__ == "__main__":
    main()
