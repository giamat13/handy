"""פותח את הממשק (דף HTML מקומי) בחלון מקורי של pywebview (ב-Windows: WebView2): בלי סרגל כתובת, בלי פרופיל דפדפן ובלי חלונות
של Edge. pywebview חייב לרוץ בחוט הראשי של תהליך משלו, ולכן החלון נפתח בתהליך בן (אותה תוכנה עם --window) שמסתיים כשהחלון נסגר.
אם pywebview לא זמין, פותחים בדפדפן ברירת המחדל."""
import subprocess
import sys
import webbrowser
from pathlib import Path

WINDOW_FLAG = "--window"
WINDOW_SIZE = (1280, 860)
TITLE = "Handy 2"
_ENTRY = Path(__file__).resolve().parent / "run.py"


def command(url, frozen=None, executable=None):
    """פקודת התהליך שמציג את החלון: ב-EXE (PyInstaller / Nuitka) הקובץ עצמו, מהמקור run.py."""
    frozen = ("__compiled__" in globals() or getattr(sys, "frozen", False)) if frozen is None else frozen
    exe = executable or sys.executable
    return [exe, WINDOW_FLAG, url] if frozen else [exe, str(_ENTRY), WINDOW_FLAG, url]


def open_window(url, popen=subprocess.Popen, **kw):
    """פותח את הממשק. מחזיר True אם נפתח חלון אפליקציה, False אם נפתח הדפדפן הרגיל (או כלום)."""
    try:
        popen(command(url, **kw), shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return True
    except OSError:
        _browser(url)
        return False


def _browser(url):
    try:
        webbrowser.open(url)
    except Exception:
        pass


def show(url):
    """רץ בתהליך הבן: חלון pywebview עד שסוגרים אותו (חוסם). בלי pywebview או אם הוא נכשל: דפדפן ברירת המחדל."""
    try:
        import webview

        webview.create_window(TITLE, url, width=WINDOW_SIZE[0], height=WINDOW_SIZE[1])
        webview.start()   # private_mode: בלי אחסון קבוע, אז גם אין פרופיל על הדיסק
    except Exception:
        _browser(url)
