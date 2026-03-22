import sys
import ctypes
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
# from app.ui.utils import resource_path, get_icon_path # 더 이상 파일 경로에 의존하지 않음
import resources_rc  # ✅ 리소스 파일 임포트 (아이콘이 메모리에 내장됨)

# MainWindow import는 main() 내부로 이동하여 지연 로딩 (Lazy Import)
# 초기 구동 속도를 높이고 아이콘을 먼저 표시하기 위함

def main():
    # 윈도우 작업표시줄 아이콘 분리를 위한 AppUserModelID 설정
    # ID를 변경하여 윈도우 캐시 초기화 유도 (v1.8.3 -> v1.9.0)
    try:
        myappid = 'kobatech.production_management_system.v1.9.0' 
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except ImportError:
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # ✅ 퓨전 스타일 적용

    # ✅ 어플리케이션 아이콘 즉시 설정 (리소스에서 로드)
    # 파일 시스템 I/O 없이 즉시 로드되므로 누락될 확률이 현저히 낮음
    app.setWindowIcon(QIcon(":/icon.ico"))

    # ---------------------------------------------------------

    # ✅ [지연 로딩] 무거운 라이브러리 및 메인 윈도우는 아이콘 설정 후 로딩
    # ---------------------------------------------------------
    print("Loading Main Window...")
    
    # 여기서 로깅 등 무거운 작업 수행
    import logging
    import logging.handlers
    import os
    import traceback
    from PySide6.QtCore import QSettings

    # 1. 로그 디렉토리 생성
    log_dir = os.path.join(os.getcwd(), "log")
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except Exception as e:
            print(f"로그 폴더 생성 실패: {e}")

    # 2. 설정에서 보관 기간 로드 (기본 30일)
    # QSettings는 가볍지만 안전하게 여기서 로드
    settings = QSettings("KOBATECH", "ProductionManagement")
    retention_days = settings.value("logging/retention_days", 30, type=int)

    # 3. 로거 설정
    logger = logging.getLogger("App")
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    
    log_file = os.path.join(log_dir, "app.log")
    try:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file, when='midnight', interval=1, backupCount=retention_days, encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.suffix = "%Y-%m-%d"
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"로그 핸들러 설정 실패: {e}")

    # 4. 예외 훅
    def exception_hook(exctype, value, tb):
        error_msg = "".join(traceback.format_exception(exctype, value, tb))
        logger.critical(f"Uncaught exception:\n{error_msg}")
        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = exception_hook
    logger.info(f"=== Application Started (Retention: {retention_days} days) ===")

    # MainWindow 임포트 및 실행
    # 이 부분에서 시간이 소요될 수 있음 -> 필요시 Splash Screen 도입 고려
    from app.ui.main_window import MainWindow
    
    win = MainWindow()
    
    # ✅ [중요] 메인 윈도우에 아이콘 강제 적용 (MainWindow 내부 로직 덮어쓰기)
    icon = QIcon(":/icon.ico")
    if not icon.isNull():
        win.setWindowIcon(icon)
        logger.info("Main Window icon explicitly set from resource.")
    else:
        logger.error("Failed to load icon from resource ':/icon.ico'")

    win.show()

    # ✅ 스플래시 스크린 닫기 (빌드된 상태에서만 작동)
    try:
        import pyi_splash
        pyi_splash.close()
    except ImportError:
        pass

    sys.exit(app.exec())

if __name__ == "__main__":
    main()