# PyInstaller spec -> a program FOLDER (dist/Handy2/Handy2.exe + _internal). Build:  pyinstaller Handy2.spec
# A folder (not one file) so the app does not unpack hundreds of MB into %TEMP% at every start.
# Windows: dist/Handy2/Handy2.exe.  macOS: also dist/Handy2.app (zipped by tools/make_platform_archive.py).  Linux: dist/Handy2/Handy2.
import sys

from PyInstaller.utils.hooks import collect_all

sys.path.insert(0, SPECPATH)  # SPECPATH is provided by PyInstaller: the folder of this file, where version.py is
from version import __version__  # noqa: E402

# the interface is the web/ folder (served to the app window); the icons are the window's taskbar icon and the tray icon
datas = [("web", "web"), ("icon.png", "."), ("icon.ico", ".")]
binaries = []
hiddenimports = ["pystray", "webview"]
# without this the EXE would be broken (the mediapipe models are data files; pywebview ships its own js and dlls)
for pkg in ("mediapipe", "pystray", "webview"):
    try:
        d, b, h = collect_all(pkg)
    except Exception as e:
        raise SystemExit(f"Handy2.spec: required package '{pkg}' is not installed ({e}). Run: pip install -r requirements.txt")
    datas += d; binaries += b; hiddenimports += h
if sys.platform == "win32":
    hiddenimports += ["keyboard"]           # the F8 / F9 hotkeys (other systems use pynput)
else:
    hiddenimports += ["pynput.keyboard", "pynput.mouse"]

a = Analysis(["run.py"], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe_extra = {}
if sys.platform == "win32":
    exe_extra = dict(version="version_info.txt",    # run tools/make_version_info.py first (keeps Explorer's "Details" tab right)
                     icon="icon.ico")               # python tools/make_icon.py makes it from icon.png
elif sys.platform == "darwin":
    exe_extra = dict(icon="icon.icns")
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Handy2",
          console=False, disable_windowed_traceback=False, upx=False,      # UPX makes antivirus false positives more likely
          **exe_extra)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Handy2")

if sys.platform == "darwin":
    # the .app bundle; the camera text is required, macOS refuses camera access to an app without it
    app = BUNDLE(coll, name="Handy2.app", icon="icon.icns", bundle_identifier="com.giamat13.handy2",
                 info_plist={
                     "CFBundleName": "Handy 2", "CFBundleDisplayName": "Handy 2",
                     "CFBundleShortVersionString": __version__, "CFBundleVersion": __version__,
                     "NSCameraUsageDescription": "Handy 2 watches your hands and face to control the mouse. Frames are never saved or sent.",
                     "NSHighResolutionCapable": True,
                 })
