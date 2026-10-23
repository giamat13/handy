# PyInstaller spec -> a program FOLDER (dist/Handy2/Handy2.exe + _internal). Build:  pyinstaller Handy2.spec
# A folder (not one file) so the app does not unpack hundreds of MB into %TEMP% at every start.
from PyInstaller.utils.hooks import collect_all

datas = [("icon.png", ".")]
binaries = []
hiddenimports = []
# without these the EXE would be broken (the mediapipe models and customtkinter themes are data files)
for pkg in ("mediapipe", "customtkinter"):
    try:
        d, b, h = collect_all(pkg)
    except Exception as e:
        raise SystemExit(f"Handy2.spec: required package '{pkg}' is not installed ({e}). Run: pip install -r requirements.txt")
    datas += d; binaries += b; hiddenimports += h

a = Analysis(["run.py"], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Handy2",
          console=False, disable_windowed_traceback=False, upx=False,      # UPX makes antivirus false positives more likely
          version="version_info.txt",    # run tools/make_version_info.py first (keeps Explorer's "Details" tab right)
          icon="icon.ico")               # python tools/make_icon.py makes it from icon.png
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Handy2")
