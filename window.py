"""פותח את הממשק (דף HTML מקומי) בחלון "אפליקציה" של Edge / Chrome / Chromium: בלי סרגל כתובת, עם פרופיל נפרד כדי שהחלון
לא יתמזג עם הדפדפן הרגיל של המשתמש. אם אין דפדפן כזה, פותחים בדפדפן ברירת המחדל."""
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

WINDOW_SIZE = "1280,860"


def candidates(platform=None, env=None, which=shutil.which):
    """נתיבים אפשריים לדפדפן מבוסס Chromium, לפי העדפה (Edge קודם ב-Windows: הוא תמיד מותקן שם)."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    if platform == "win32":
        roots = [env.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA") if env.get(k)]
        rel = ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe", "Chromium/Application/chrome.exe")
        return [str(Path(r) / p) for p in rel for r in roots]
    if platform == "darwin":
        return ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    return [p for p in (which(n) for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser")) if p]


def find_browser(exists=os.path.isfile, **kw):
    return next((p for p in candidates(**kw) if exists(p)), None)


def command(browser, url, profile_dir):
    return [browser, f"--app={url}", f"--user-data-dir={profile_dir}", f"--window-size={WINDOW_SIZE}", "--no-first-run",
            "--no-default-browser-check", "--disable-features=Translate"]


def open_window(url, profile_dir, popen=subprocess.Popen, browser=None):
    """פותח את הממשק. מחזיר True אם נפתח חלון אפליקציה, False אם נפתח הדפדפן הרגיל (או כלום)."""
    browser = browser or find_browser()
    if browser:
        try:
            Path(profile_dir).mkdir(parents=True, exist_ok=True)
            popen(command(browser, url, profile_dir), shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL, close_fds=True)
            return True
        except OSError:
            pass
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return False
