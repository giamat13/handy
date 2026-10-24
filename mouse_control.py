"""שליטה בעכבר: תנועה לפי יד או ראש, ופעולות לפי מחוות (קליקים, גלילה, גרירה, קיצורי מקשים, הרצת תוכנה)."""
import logging
import math
import sys
import time

import actions
import commands

log = logging.getLogger(__name__)

_CLICKS = {
    "left_click": ("left", 1),
    "right_click": ("right", 1),
    "double_click": ("left", 2),
    "middle_click": ("middle", 1),
}
# לחיצה ארוכה: הכפתור נלחץ כשהמחווה מתחילה ומשתחרר כשהיא נגמרת ("drag" היא אותה לחיצה ארוכה שמאלית)
_HOLDS = {"drag": "left", "hold_right": "right", "hold_middle": "middle"}
_SCROLL = {"scroll_up": 1, "scroll_down": -1}
_SCROLL_INTERVAL = 0.08
_COOLDOWN = 0.7  # בין כל שני קליקים, מכל מחווה: מונע קליק כפול ממחווה שמהבהבת
_COMMAND_COOLDOWN = 1.0  # בין שתי הרצות של קיצור מקשים / תוכנה: מחווה מהבהבת לא תפתח עשר חלונות
_TOGGLE_COOLDOWN = 1.0  # בין שתי החלפות של מצב השליטה
_RELEASE_HOLD = 0.3  # מחווה נחשבת כנגמרה רק אחרי כל כך הרבה זמן בלעדיה, כדי שהבהוב לא יספור כמחווה חדשה
_FREEZE = 0.3  # אחרי קליק לא מזיזים את הסמן, כי הראש/היד זזים קצת בזמן המחווה

# טווח התנועה (חצי רוחב, חצי גובה) בקואורדינטות מנורמלות של הפריים, לרגישות 1
_RANGE = {"hand": (0.28, 0.22), "head": (0.10, 0.07)}
_CENTER = {"hand": (0.5, 0.45), "head": (0.5, 0.5)}

# משבצות הידיים כפי שה-Tracker מפרסם (signs[0] = שמאל, signs[1] = ימין)
_SLOTS = {"left": {0}, "right": {1}, "both": {0, 1}}
SLOT_NAMES = {0: "Left", 1: "Right"}


class OneEuro:
    """מסנן החלקה: חלק כשהתנועה איטית, מהיר כשהתנועה מהירה."""

    def __init__(self, min_cutoff=1.0, beta=0.02):
        self.min_cutoff, self.beta = min_cutoff, beta
        self.x = self.dx = self.t = None

    @staticmethod
    def _alpha(cutoff, dt):
        return 1.0 / (1.0 + 1.0 / (2 * math.pi * cutoff * dt))

    def __call__(self, x, t):
        if self.x is None:
            self.x, self.dx, self.t = x, 0.0, t
            return x
        dt = max(t - self.t, 1e-3)
        self.t = t
        dx = (x - self.x) / dt
        self.dx += self._alpha(1.0, dt) * (dx - self.dx)
        cutoff = self.min_cutoff + self.beta * abs(self.dx)
        self.x += self._alpha(cutoff, dt) * (x - self.x)
        return self.x

    def reset(self):
        self.x = None


class PynputMouse:
    """עטיפה דקה ל-pynput (עובד ב-Windows, macOS ו-Linux/X11). שמות הכפתורים הם מחרוזות, כדי שהלוגיקה והבדיקות לא יצטרכו pynput."""

    def __init__(self):
        from pynput.mouse import Button, Controller

        self._c = Controller()
        self._b = {"left": Button.left, "right": Button.right, "middle": Button.middle}

    def click(self, name, count=1):
        self._c.click(self._b[name], count)

    def press(self, name):
        self._c.press(self._b[name])

    def release(self, name):
        self._c.release(self._b[name])

    def scroll(self, dx, dy):
        self._c.scroll(dx, dy)

    @property
    def position(self):
        return self._c.position

    @position.setter
    def position(self, xy):
        self._c.position = xy


def screen_size(widget=None):
    """גודל המסך בפיקסלים. ב-Windows מ-user32 (כמו תמיד), בשאר המערכות מ-Tk (widget קיים, או חלון זמני)."""
    if sys.platform == "win32":
        import ctypes

        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    try:
        if widget is not None:
            return widget.winfo_screenwidth(), widget.winfo_screenheight()
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        size = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return size
    except Exception:
        return 1920, 1080


class MouseController:
    def __init__(self, cfg, mouse=None, keyboard=None, screen=None, launcher=None):
        """mouse / keyboard / launcher מוזרקים בבדיקות; screen = (רוחב, גובה), ברירת מחדל מהמערכת."""
        self.cfg = cfg
        self.mouse = mouse if mouse is not None else PynputMouse()
        self._keyboard = keyboard
        self._launcher = launcher or commands.run_script
        self.sw, self.sh = screen or screen_size()
        self.fx, self.fy = OneEuro(), OneEuro()
        self.prev = set()
        self.last_seen = {}
        self.last_click = -1e9
        self.last_command = -1e9
        self.last_toggle = -1e9
        self.last_scroll = 0.0
        self.freeze_until = 0.0
        self.held = {}             # מחווה -> כפתור עכבר שהיא מחזיקה לחוץ
        self.held_keys = {}        # מחווה -> מקשים שהיא מחזיקה לחוצים (קיצור בלחיצה ארוכה)
        self.head_center = None
        self._last_point = None
        self.point = None          # הנקודה השולטת בקואורדינטות הפריים (לשובל), או None
        self.active_slot = None    # איזו יד מזיזה את הסמן עכשיו (0 שמאל, 1 ימין), או None
        self.active_slot_prev = None

    def recenter_head(self):
        """קובע את מיקום הראש הנוכחי כמרכז המסך."""
        if self._last_point is not None:
            self.head_center = tuple(self._last_point)

    def allowed_slots(self):
        """אילו ידיים שולטות לפי ההגדרה: ימין, שמאל או שתיהן."""
        return _SLOTS.get(self.cfg.get("control_hand", "both"), _SLOTS["both"])

    def cursor_position(self):
        """מיקום הסמן האמיתי במסך, או None."""
        try:
            x, y = self.mouse.position
            return int(x), int(y)
        except Exception:
            return None

    def _keyboard_controller(self):
        if self._keyboard is None:
            from pynput.keyboard import Controller

            self._keyboard = Controller()
        return self._keyboard

    def _point(self, hands, face, labels):
        src = self.cfg["control_source"]
        self.active_slot = None
        if src == "hand":
            allowed = self.allowed_slots()
            slots = labels if labels is not None else list(range(len(hands)))
            cands = [(s, h) for s, h in zip(slots, hands) if s in allowed]
            if not cands:
                return None, src
            # נשארים עם אותה יד כל עוד היא נראית, כדי שהסמן לא יקפוץ בין שתי ידיים
            cands.sort(key=lambda c: c[0] != self.active_slot_prev)
            slot, hand = cands[0]
            self.active_slot = self.active_slot_prev = slot
            # מרכז כף היד יציב יותר מקצה האצבע, ולא זז כשמבצעים צביטה
            p = hand[[0, 5, 9, 13, 17]].mean(axis=0)
        elif src == "head" and face is not None:
            p = face[1]  # קצה האף
        else:
            return None, src
        self._last_point = p
        return p, src

    def _move(self, p, src, now):
        sens = max(self.cfg["sensitivity"], 0.1)
        rx, ry = _RANGE[src]
        cx, cy = (self.head_center if src == "head" and self.head_center else _CENTER[src])
        nx = (p[0] - cx) / (rx / sens) * 0.5 + 0.5
        ny = (p[1] - cy) / (ry / sens) * 0.5 + 0.5
        nx, ny = min(max(nx, 0.0), 1.0), min(max(ny, 0.0), 1.0)
        # smoothing 0..1 -> min_cutoff 4..0.4
        cutoff = 4.0 - 3.6 * min(max(self.cfg["smoothing"], 0.0), 1.0)
        self.fx.min_cutoff = self.fy.min_cutoff = cutoff
        x = self.fx(nx, now) * (self.sw - 1)
        y = self.fy(ny, now) * (self.sh - 1)
        self.mouse.position = (int(x), int(y))

    def update(self, hands, face, signs, wink, labels=None):
        """נקרא מחוט המעקב אחרי כל פריים. signs לפי משבצות (0 שמאל, 1 ימין); labels = משבצת לכל יד ב-hands (אם חסר: לפי הסדר)."""
        now = time.perf_counter()
        allowed = self.allowed_slots()
        # רק מחוות של היד השולטת נחשבות. קריצה לא קשורה ליד
        raw = {s for i, s in enumerate(signs) if s and i in allowed}
        if wink:
            raw.add(wink)

        p, src = self._point(hands, face, labels)
        self.point = p

        if not self.cfg["control_enabled"]:
            self.release()
            self.fx.reset(), self.fy.reset()
            self._gestures(raw, now, only_toggle=True)  # מחוות ההפעלה חייבת לעבוד גם כשהשליטה כבויה
            return

        # בזמן קריצה הפנים זזים, אז לא מזיזים את הסמן
        if p is not None and not wink and now >= self.freeze_until:
            self._move(p, src, now)
        elif p is None:
            self.fx.reset(), self.fy.reset()
        self._gestures(raw, now, only_toggle=False)

    def _gestures(self, raw, now, only_toggle):
        for g in raw:
            self.last_seen[g] = now
        # הפעולות נקבעות לפי מחוות "מוחזקות" (נשארות פעילות עוד רגע אחרי שנעלמו), הגלילה לפי מה שנראה עכשיו
        active = {g for g, t in self.last_seen.items() if now - t < _RELEASE_HOLD}
        self.last_seen = {g: self.last_seen[g] for g in active}

        bindings = self.cfg["bindings"]
        for g in active - self.prev:
            self._fire(bindings.get(g, "none"), g, now, only_toggle)
        if not only_toggle:
            for g in self.prev - active:
                self._release_gesture(g)  # המחווה נגמרה: מה שהיא החזיקה לחוץ משתחרר
            for g in raw:
                action = actions.binding_kind(bindings.get(g, "none"))
                if action in _SCROLL and now - self.last_scroll >= _SCROLL_INTERVAL and self.cfg["control_enabled"]:
                    self.mouse.scroll(0, _SCROLL[action])
                    self.last_scroll = now
        self.prev = active

    def _fire(self, binding, gesture, now, only_toggle=False):
        action = actions.binding_kind(binding)
        if action == "toggle_control":
            if now - self.last_toggle < _TOGGLE_COOLDOWN:
                return
            self.last_toggle = now
            self.cfg["control_enabled"] = not self.cfg["control_enabled"]
            self.release()
            self.fx.reset(), self.fy.reset()
            self.freeze_until = now + _FREEZE
            return
        if only_toggle:
            return
        if action in _CLICKS:
            if now - self.last_click < _COOLDOWN:
                return
            self.last_click = now
            self.freeze_until = now + _FREEZE
            button, count = _CLICKS[action]
            self.mouse.click(button, count)
        elif action in _HOLDS:
            button = _HOLDS[action]
            if gesture not in self.held and button not in self.held.values():
                self.held[gesture] = button
                self.mouse.press(button)
        elif action in ("hotkey", "script"):
            if now - self.last_command < _COMMAND_COOLDOWN:
                return
            self.last_command = now
            self._run_command(binding, gesture)

    @property
    def dragging(self):
        """כפתור העכבר שמוחזק לחוץ עכשיו (או None)."""
        return next(iter(self.held.values()), None)

    def _run_command(self, binding, gesture=None):
        """קיצור מקשים או תוכנה. מאמתים שוב בכל הרצה, וכשל לא מפיל את חוט המעקב."""
        try:
            if binding["type"] == "hotkey":
                tokens = commands.parse_hotkey(binding.get("keys"))
                if binding.get("hold") is True and gesture is not None:
                    if gesture not in self.held_keys:  # לחיצה ארוכה: נשארים לחוצים עד שהמחווה נגמרת
                        self.held_keys[gesture] = commands.hold_hotkey(self._keyboard_controller(), tokens)
                else:
                    commands.press_hotkey(self._keyboard_controller(), tokens)
            else:
                self._launcher(binding)
        except Exception as e:  # קובץ שנמחק, מקש לא תקין, אין הרשאה: מדלגים ולא קורסים
            log.warning("gesture command skipped: %s", e)

    def _release_gesture(self, gesture):
        button = self.held.pop(gesture, None)
        if button is not None:
            self.mouse.release(button)
        keys = self.held_keys.pop(gesture, None)
        if keys:
            commands.release_keys(self._keyboard_controller(), keys)

    def release(self):
        """משחרר כל מה שמוחזק לחוץ (כשהשליטה נכבית, בסגירה, ובכל מקרה שבו מחווה נעלמה)."""
        for g in list(self.held) + [g for g in self.held_keys if g not in self.held]:
            self._release_gesture(g)
