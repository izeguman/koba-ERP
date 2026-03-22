@echo off
echo Building koba ERP...
echo.

REM 가상환경이 있다면 활성화 (필요시 경로 수정)
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

REM 이전 빌드 폴더 정리
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo Cleaned up previous build artifacts.
echo.

REM 리소스 파일 컴파일 (run.py 실행을 위해 필수)
echo Compiling resources...
if exist .venv\Scripts\pyside6-rcc.exe (
    call .venv\Scripts\pyside6-rcc.exe resources.qrc -o resources_rc.py
) else (
    echo WARNING: pyside6-rcc.exe not found in .venv! Attempting global command...
    pyside6-rcc resources.qrc -o resources_rc.py
)

REM PyInstaller 실행 (clean: 캐시 삭제, noconfirm: 덮어쓰기 확인 안함)
REM koba_MES.spec 파일을 사용하여 빌드 (스플래시 스크린 및 최신 설정 적용)
pyinstaller koba_MES.spec --clean --noconfirm

echo.
echo Build Complete!
echo Output file: dist\koba_MES.exe
pause
