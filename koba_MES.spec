# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/ui/logo.png', 'app/ui'),
        ('app/ui/koba_erp_final.ico', 'app/ui'),
        ('app/ui/koba_erp_final.ico', '.'),
        ('app/templete/Order Acknowledgement_.xlsx', 'app/templete'), # ✅ 엑셀 템플릿 추가
        ('app/templete/발주서.xlsx', 'app/templete'), # ✅ 발주서 템플릿 추가
        ('app/templete/ULVAC-PHI_Invoice_.xlsx', 'app/templete'), # ✅ 청구서 템플릿 추가
        ('app/templete/납품 인보이스.xlsx', 'app/templete'), # ✅ 납품 인보이스 템플릿 추가
    ],
    hiddenimports=['pandas', 'openpyxl', 'pyodbc', 'babel.numbers', 'win32timezone'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

splash = Splash(
    'app/ui/splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    text_size=12,
    minify_script=True,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles, 
    a.datas,
    splash, 
    splash.binaries,
    [],
    name='koba_MES',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app/ui/koba_erp_final.ico'
)
