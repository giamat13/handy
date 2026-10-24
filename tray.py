"""אייקון במגש המערכת: כשסוגרים את החלון התוכנה ממשיכה לרוץ ברקע (מצלמה, מעקב ושליטה בעכבר), ומהאייקון אפשר לפתוח אותה,
להחליף את מצב השליטה או לצאת. ב-macOS pystray חייבת לרוץ בחוט הראשי, שתפוס ע"י חלון התוכנה, ולכן שם אין מגש והחלון רק ממוזער."""
import sys


def _pystray():
    try:
        import pystray
        return pystray
    except Exception:  # לא מותקנת, או אין סביבה גרפית: אין מגש
        return None


def available(module=None):
    """האם אפשר להציג אייקון במגש במערכת הזו."""
    if sys.platform == "darwin":
        return False
    return (module or _pystray()) is not None


class Tray:
    """callbacks: show / toggle / quit (נקראים מחוט המגש: מי שמקבל אותם אחראי להעביר לחוט הממשק); is_enabled() למצב הסימון."""

    def __init__(self, image, show, toggle, quit_, is_enabled, module=None):
        self._mod = module or _pystray()
        self._image, self._show, self._toggle, self._quit, self._enabled = image, show, toggle, quit_, is_enabled
        self._icon = None

    def start(self):
        """מציג את האייקון. מחזיר False אם אי אפשר (אז הקורא ממזער את החלון במקום)."""
        if self._icon is not None:
            return True
        if self._mod is None or not available(self._mod):
            return False
        p = self._mod
        try:
            menu = p.Menu(
                p.MenuItem("פתח את Handy 2", lambda *_: self._show(), default=True),
                p.MenuItem("שליטה בעכבר", lambda *_: self._toggle(), checked=lambda _item: bool(self._enabled())),
                p.MenuItem("יציאה", lambda *_: self._quit()),
            )
            self._icon = p.Icon("Handy2", self._image, self.title(), menu)
            self._icon.run_detached()
            return True
        except Exception:
            self._icon = None
            return False

    def title(self):
        return "Handy 2 - " + ("שליטה בעכבר פעילה" if self._enabled() else "שליטה בעכבר כבויה")

    def refresh(self):
        """מעדכן את הכותרת והסימון אחרי שמצב השליטה השתנה (ממחווה, מ-F8 או מהתפריט)."""
        if self._icon is not None:
            try:
                self._icon.title = self.title()
                self._icon.update_menu()
            except Exception:
                pass

    @property
    def visible(self):
        return self._icon is not None

    def stop(self):
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
