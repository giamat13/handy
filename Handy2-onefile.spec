# PyInstaller spec -> ONE self-contained file: dist_onefile/Handy2.exe. Build:
#   pyinstaller --noconfirm --distpath dist_onefile --workpath build_onefile Handy2-onefile.spec
# Slower to start than the folder build (Handy2.spec): at every start it unpacks itself into %TEMP%. The folder build is the
# one that is released; this file is for quickly handing someone a single EXE. Windows only.
import sys

from PyInstaller.utils.hooks import collect_all

datas = [("web", "web"), ("icon.png", "."), ("icon.ico", ".")]
binaries = []
hiddenimports = ["keyboard", "pystray"]
for pkg in ("mediapipe", "pystray"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

a = Analysis(["run.py"], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="Handy2",
          console=False, disable_windowed_traceback=False, upx=False,
          version="version_info.txt", icon="icon.ico")
