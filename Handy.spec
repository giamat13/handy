# -*- mode: python ; coding: utf-8 -*-
import os
import mediapipe
import tempfile

# Bundle the entire mediapipe package (includes .pyd/.so and data files)
mediapipe_path = os.path.dirname(mediapipe.__file__)

build_target = os.environ.get("HANDY_BUILD_TARGET", "portable")

# Write a runtime hook that bakes IS_INSTALLED into the frozen app
_hook_content = f"import handy.state as state; state.IS_INSTALLED = {str(build_target == 'installer')}\n"
_hook_path = os.path.join(tempfile.gettempdir(), "rthook_handy_build.py")
with open(_hook_path, "w") as f:
    f.write(_hook_content)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (mediapipe_path, 'mediapipe'),
        ('icon.png', '.'),
        ('hand_landmarker.task', '.'),
    ],
    hiddenimports=[
        'mediapipe',
        'mediapipe.tasks',
        'mediapipe.tasks.python',
        'mediapipe.tasks.python.vision',
        'mediapipe.tasks.python.core',
        'mediapipe.python',
        'mediapipe.python.solutions',
        'mediapipe.python.solutions.hands',
        'mediapipe.python.solutions.drawing_utils',
        'customtkinter',
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
        'pynput._util',
        'pynput._util.win32',
        'cv2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[_hook_path],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

if build_target == 'installer':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        name='Handy',
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
        icon='icon.png',
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='Handy',
    )
else:
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
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon='icon.png',
    )
