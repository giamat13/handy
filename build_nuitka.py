"""Build Handy using Nuitka.

Produces a standalone native binary — no Python runtime required on the target machine.

Usage:
    python build_nuitka.py
"""

import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from build_config import (
    APP_NAME,
    MODEL_FILENAME,
    MODEL_PATH,
    MODEL_URL,
    PROJECT_ROOT,
    RELEASE_DIR,
)
from build_assets import ensure_windows_icon


def ensure_model_file() -> None:
    if MODEL_PATH.exists():
        return
    print(f"[BUILD] Downloading model to {MODEL_PATH} ...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    except Exception as exc:
        raise SystemExit(
            "[BUILD] Failed to download hand_landmarker.task. "
            "Connect to the internet once or place the file next to main.py."
        ) from exc


def build() -> None:
    ensure_model_file()
    RELEASE_DIR.mkdir(exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--enable-plugin=tk-inter",
        "--include-package=customtkinter",
        "--include-package=mediapipe",
        "--include-package=cv2",
        "--include-package=handy",
        f"--include-data-files={MODEL_PATH}={MODEL_FILENAME}",
        f"--output-filename={APP_NAME}",
        f"--output-dir={RELEASE_DIR}",
        "--assume-yes-for-downloads",
    ]

    if sys.platform == "win32":
        from build_config import BUILD_ROOT, ICON_ICO_PATH
        BUILD_ROOT.mkdir(exist_ok=True)
        ensure_windows_icon()
        cmd += [
            "--standalone",
            "--onefile",
            f"--windows-icon-from-ico={ICON_ICO_PATH}",
            "--windows-disable-console",
        ]
    elif sys.platform == "darwin":
        cmd += [
            "--mode=app",
            "--macos-app-name=Handy",
        ]
    else:
        cmd += [
            "--standalone",
            "--onefile",
        ]

    cmd.append(str(PROJECT_ROOT / "main.py"))

    print("[BUILD] Running Nuitka:\n  " + " \\\n  ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))

    suffix = ".exe" if sys.platform == "win32" else ""
    print(f"\n[BUILD] Done: {RELEASE_DIR / (APP_NAME + suffix)}")


if __name__ == "__main__":
    build()