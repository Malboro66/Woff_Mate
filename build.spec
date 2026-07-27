# -*- mode: python ; coding: utf-8 -*-
# build.spec

block_cipher = None

a = Analysis(
    ['woff/woff_watchdog.py'],
    pathex=['woff'], # Adiciona a pasta woff ao path do PyInstaller
    binaries=[],
    datas=[],
    hiddenimports=[
        'watchdog.observers', 
        'watchdog.events', 
        'watchdog.utils.dirsnapshot',
        # Módulos internos locais (Forçar o empacotamento)
        'config', 
        'handler', 
        'database', 
        'discovery', 
        'medal_cataloger', 
        'squadron_cataloger', 
        'campaign_engine',
        'parsers', 
        'parsers.xml_parser', 
        'parsers.mission_log_parser', 
        'parsers.pilot_data_parser', 
        'parsers.dossier_parser'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PySide2', 'tkinter', 'matplotlib', 'numpy', 'pandas'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WoFFWatchdog',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True, # True para vermos os logs a correr
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WoFFWatchdog',
)