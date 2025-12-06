@echo off
echo Building koba ERP...
echo.

REM 가상환경이 있다면 활성화 (필요시 경로 수정)
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

REM PyInstaller 실행 (clean: 캐시 삭제, noconfirm: 덮어쓰기 확인 안함)
pyinstaller koba_ERP.spec --clean --noconfirm

echo.
echo Build Complete!
echo Output directory: dist\koba ERP
pause
