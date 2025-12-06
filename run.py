# run.py
import sys
import ctypes
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from app.ui.main_window import MainWindow
from app.ui.utils import resource_path, get_icon_path

def main():
    # 윈도우 작업표시줄 아이콘 분리를 위한 AppUserModelID 설정
    try:
        myappid = 'kobatech.production_management_system.v1.8.3' # 임의의 고유 ID
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except ImportError:
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # ✅ 퓨전 스타일 적용 (검은 테두리 제거 및 모던한 룩)

    # ✅ 어플리케이션 아이콘 설정 (Taskbar 아이콘 해결)
    # get_icon_path()는 여러 경로를 시도하여 유효한 아이콘 경로를 반환합니다.
    icon_path = get_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    else:
        print("⚠️ 아이콘을 찾을 수 없습니다.")
    
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()