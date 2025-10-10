# run.py
import sys
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow
# init_db import 제거

def main():
    # init_db() 제거
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()