"""הפעלה עם המחשב. Windows: ערך ב-HKCU\\...\\Run. macOS: LaunchAgent. Linux: קובץ ב-~/.config/autostart.
התוכנה מופעלת עם --background: היא עולה במגש המערכת בלי לפתוח חלון (והשליטה בעכבר תמיד מתחילה כבויה).
המקור לאמת הוא המערכת עצמה (לא settings.json), כדי שביטול ידני ב"אפליקציות הפעלה" של Windows יתבטא גם בממשק."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

NAME = "Handy"
MAC_LABEL = "com.handy.app"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def command(frozen=None, executable=None, script=None, platform=None):
    """הפקודה שתרוץ בהפעלת המחשב, כרשימת ארגומנטים. מותקן/ארוז: ה-EXE עצמו. מקוד המקור: האינטרפרטר (pythonw ב-Windows, בלי חלון קונסולה) ו-run.py."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    platform = platform or sys.platform
    if frozen:
        return [executable, "--background"]
    if platform == "win32":
        pythonw = Path(executable).with_name("pythonw.exe")
        if pythonw.is_file():
            executable = str(pythonw)
    return [executable, str(script or Path(__file__).resolve().parent / "run.py"), "--background"]


class _WinRun:
    """הערך שלנו במפתח Run של המשתמש הנוכחי (winreg). מחלקה נפרדת כדי שהבדיקות יוכלו להחליף אותה."""

    def get(self):
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                return winreg.QueryValueEx(k, NAME)[0]
        except FileNotFoundError:
            return None

    def set(self, value):
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, value)

    def delete(self):
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, NAME)
        except FileNotFoundError:
            pass


def _desktop_quote(arg):
    """ציטוט ארגומנט בשורת Exec של קובץ .desktop (מרכאות כפולות, ובתוכן בריחה מ-\\ \" $ `)."""
    if arg and all(c.isalnum() or c in "-_./:=+@%," for c in arg):
        return arg
    return '"' + "".join("\\" + c if c in '\\"$`' else c for c in arg) + '"'


def _file_path(platform, home, env):
    if platform == "darwin":
        return home / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"
    return Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "autostart" / "handy.desktop"


def is_enabled(platform=None, home=None, env=None, registry=None):
    platform = platform or sys.platform
    if platform == "win32":
        return (registry or _WinRun()).get() is not None
    return _file_path(platform, Path(home) if home else Path.home(), os.environ if env is None else env).is_file()


def set_enabled(on, platform=None, home=None, env=None, registry=None, argv=None):
    """מדליק או מכבה. זורק OSError אם המערכת לא מאפשרת (הממשק מציג את ההודעה)."""
    platform = platform or sys.platform
    argv = argv or command(platform=platform)
    if platform == "win32":
        reg = registry or _WinRun()
        if on:
            reg.set(subprocess.list2cmdline(argv))
        else:
            reg.delete()
        return
    path = _file_path(platform, Path(home) if home else Path.home(), os.environ if env is None else env)
    if not on:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if platform == "darwin":
        path.write_bytes(plistlib.dumps({"Label": MAC_LABEL, "ProgramArguments": argv, "RunAtLoad": True}))
    else:
        path.write_text("[Desktop Entry]\nType=Application\nName=Handy\nComment=Hand and head mouse control\n"
                        f"Exec={' '.join(_desktop_quote(a) for a in argv)}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
                        encoding="utf-8")


def refresh(**kwargs):
    """אם ההפעלה עם המחשב דולקת, כותב מחדש את הפקודה: אחרי עדכון או העברת התוכנה לתיקייה אחרת הנתיב הישן כבר לא נכון."""
    if is_enabled(**{k: v for k, v in kwargs.items() if k in ("platform", "home", "env", "registry")}):
        set_enabled(True, **kwargs)
