# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['Handy.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('utils', 'utils'),
    ],
    hiddenimports=[
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
        'keyboard',
        'mouse',
        'PIL',
        'PIL.Image',
        'PIL.ImageGrab',
        'pyperclip',
        'win32gui',
        'win32con',
        'win32api',
        'pywintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='Handy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # שנה ל-False אם אתה רוצה בלי חלון קונסול
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,  # דורש הרשאות אדמין בהרצה
    icon=None,
)
