"""Build Handy 2 with Nuitka (compiles the Python code to C) instead of PyInstaller. Works on Windows, macOS and Linux.

    pip install nuitka ordered-set zstandard
    python tools/build_nuitka.py            -> dist_nuitka/run.dist/ (renamed to dist_nuitka/Handy2/)
    python tools/make_platform_archive.py nuitka   -> dist/Handy2-<version>-<platform>-nuitka.zip (or .tar.gz on Linux)

The mediapipe models and the customtkinter themes are data files, so they are included explicitly (same reason as Handy2.spec).
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist_nuitka"


def command(python=sys.executable):
    cmd = [python, "-m", "nuitka", "--standalone", "--assume-yes-for-downloads", "--enable-plugin=tk-inter",
           "--include-package=mediapipe", "--include-package-data=mediapipe",
           "--include-package=pystray",
           # webview is not --include-package'd: that forces every platform module, which clashes with the pywebview plugin
           "--include-package-data=webview",
           f"--include-data-dir={ROOT / 'web'}=web",   # the interface (HTML / CSS / JS), served to the app window
           f"--include-data-files={ROOT / 'icon.png'}=icon.png", f"--include-data-files={ROOT / 'icon.ico'}=icon.ico",
           f"--output-dir={OUT}", "--output-filename=Handy2", "--remove-output"]
    if sys.platform == "win32":
        cmd += ["--windows-console-mode=disable", f"--windows-icon-from-ico={ROOT / 'icon.ico'}",
                "--include-module=keyboard"]
    elif sys.platform == "darwin":
        cmd += ["--macos-create-app-bundle", f"--macos-app-icon={ROOT / 'icon.icns'}", "--macos-app-name=Handy 2",
                "--macos-app-mode=gui"]
    cmd.append(str(ROOT / "run.py"))
    return cmd


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    subprocess.run(command(), cwd=ROOT, check=True)
    built = OUT / "run.dist"
    if built.is_dir():                       # Windows / Linux: a folder; rename it so the archive has a clean name
        shutil.move(str(built), str(OUT / "Handy2"))
    print("built:", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
