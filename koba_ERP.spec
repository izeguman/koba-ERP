# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/ui/logo.png', 'app/ui'),           # ✅ 로고 추가
        ('app/ui/koba_erp_final.ico', 'app/ui'), # ✅ 아이콘 추가 (기본)
        ('app/ui/koba_erp_final.ico', '.'),      # ✅ 아이콘 추가 (루트 - 안전장치)
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='koba ERP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app/ui/koba_erp_final.ico'  # ✅ exe 아이콘
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='koba ERP',
)