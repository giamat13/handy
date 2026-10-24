"""התוכנה: מצלמה, מעקב ושליטה בעכבר רצים בחוטים משלהם; הממשק הוא דף HTML (web/) שמוגש משרת מקומי ונפתח בחלון אפליקציה.
סגירת החלון משאירה את התוכנה רצה ברקע (מגש המערכת) אם ההגדרה דולקת, ואחרת יוצאת."""
import json
import os
import queue
import sys
import threading
import time
import urllib.request
from pathlib import Path

import actions
import settings
import window
from camera import Camera
from custom_gestures import CustomGestureStore
from mouse_control import MouseController
from render import Renderer
from tracker import Tracker
from tray import Tray
from update_service import UpdateService
from webui import Backend, Server

ICON_PATH = Path(__file__).resolve().parent / "icon.png"
INSTANCE_FILE = "instance.json"   # כתובת וטוקן של העותק שרץ, כדי שהפעלה שנייה תפתח חלון אצלו ולא תפתח מצלמה שנייה


def pick_file():
    """בחירת קובץ בחלון המערכת (tkinter מהספרייה הסטנדרטית). מחזיר נתיב או ''."""
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askopenfilename(parent=root) or ""
    finally:
        root.destroy()


def find_running(directory):
    """אם כבר רץ עותק של התוכנה: הכתובת (עם הטוקן) שלו, אחרת None."""
    try:
        info = json.loads((Path(directory) / INSTANCE_FILE).read_text("utf-8"))
        req = urllib.request.Request(f"http://127.0.0.1:{int(info['port'])}/api/ping", headers={"X-Handy-Token": str(info["token"])})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            if json.loads(r.read()).get("app") == "handy":
                return f"http://127.0.0.1:{int(info['port'])}/?t={info['token']}"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


class Application:
    def __init__(self, background_start=False):
        self.cfg = settings.load()
        self.store = CustomGestureStore(settings.CUSTOM_PATH)
        self.stop_event = threading.Event()
        self.commands = queue.SimpleQueue()   # פקודות מהמגש (חוט אחר) ללולאה הראשית
        self.updates = UpdateService(self.cfg, settings.save, self.stop_event.set)
        self.ok = self.updates.startup()      # False: עדכון שנקטע, התוכנה עומדת להיות משוחזרת
        if not self.ok:
            return
        self.camera = Camera().start()
        self.mouse = MouseController(self.cfg)
        self.tracker = Tracker(self.camera, self.mouse, self.store).start()
        self.renderer = Renderer(self.tracker, self.mouse, self.cfg, lambda: {**actions.GESTURES, **self.store.names()}).start()
        self.backend = Backend(self.cfg, self.store, self.tracker, self.mouse, self.renderer, self.updates, settings.save,
                               self.stop_event.set, pick_file=pick_file)
        self.server = Server(self.backend).start()
        self._write_instance()
        self.tray = Tray(self._tray_image(), show=lambda: self.commands.put("show"), toggle=lambda: self.commands.put("toggle"),
                         quit_=lambda: self.commands.put("quit"), is_enabled=lambda: self.cfg["control_enabled"])
        self._hotkeys = None
        self._register_hotkeys()
        self._last_enabled = None
        self.background_start = background_start

    def _tray_image(self):
        from PIL import Image

        try:
            return Image.open(ICON_PATH).convert("RGBA")
        except OSError:
            return Image.new("RGBA", (64, 64), (198, 240, 107, 255))

    def _write_instance(self):
        try:
            settings.DIR.mkdir(parents=True, exist_ok=True)
            (settings.DIR / INSTANCE_FILE).write_text(json.dumps({"port": self.server.port, "token": self.server.token, "pid": os.getpid()}), "utf-8")
        except OSError:
            pass

    def _register_hotkeys(self):
        """F8 מחליף מצב שליטה, F9 מרכז את הראש. ב-Windows דרך ספריית keyboard, בשאר המערכות דרך pynput."""
        try:
            if sys.platform == "win32":
                import keyboard

                keyboard.add_hotkey("f8", self.toggle_control)
                keyboard.add_hotkey("f9", self.mouse.recenter_head)
            else:
                from pynput.keyboard import GlobalHotKeys

                self._hotkeys = GlobalHotKeys({"<f8>": self.toggle_control, "<f9>": self.mouse.recenter_head})
                self._hotkeys.start()
        except Exception:
            pass  # בלי קיצורי מקלדת עדיין אפשר להשתמש בכפתור (ב-Linux/macOS נדרשת הרשאה)

    def toggle_control(self):
        self.cfg["control_enabled"] = not self.cfg["control_enabled"]
        self.backend._changed()

    def open_window(self):
        self.tray.stop()
        window.open_window(self.server.url)

    def _handle(self, cmd):
        if cmd == "show":
            self.open_window()
        elif cmd == "toggle":
            self.toggle_control()
        elif cmd == "quit":
            self.stop_event.set()

    def _ui_closed(self):
        """החלון נסגר: ברקע אם ההגדרה דולקת ויש מגש, אחרת יוצאים."""
        if self.cfg["run_in_background"] and self.tray.start():
            return
        self.stop_event.set()

    def run(self):
        if self.background_start and self.cfg["run_in_background"] and self.tray.start():
            pass
        else:
            self.open_window()
        while not self.stop_event.wait(0.1):
            self.backend.tick()
            self.updates.tick()
            while True:
                try:
                    self._handle(self.commands.get_nowait())
                except queue.Empty:
                    break
            if self._last_enabled != self.cfg["control_enabled"]:
                self._last_enabled = self.cfg["control_enabled"]
                self.tray.refresh()
            if self.backend.ui_gone():
                self._ui_closed()
        self.shutdown()

    def shutdown(self):
        for step in (self.tray.stop, self.mouse.release, self.renderer.stop, self.tracker.stop, self.camera.stop, self.server.stop):
            try:
                step()
            except Exception:
                pass
        if self._hotkeys is not None:
            self._hotkeys.stop()
        try:
            (settings.DIR / INSTANCE_FILE).unlink()
        except OSError:
            pass


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    url = find_running(settings.DIR)
    if url:  # כבר רץ: פותחים חלון אצל העותק הקיים ויוצאים
        window.open_window(url)
        return
    app = Application(background_start="--background" in argv)
    if app.ok:
        app.run()
