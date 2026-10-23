"""שליטה בעכבר: תנועה לפי יד או ראש, ופעולות לפי מחוות."""
import ctypes
import math
import time

from pynput.mouse import Button, Controller

_CLICKS = {
    "left_click": (Button.left, 1),
    "right_click": (Button.right, 1),
    "double_click": (Button.left, 2),
    "middle_click": (Button.middle, 1),
}
_SCROLL = {"scroll_up": 1, "scroll_down": -1}
_SCROLL_INTERVAL = 0.08
_COOLDOWN = 0.7  # בין כל שני קליקים, מכל מחווה: מונע קליק כפול ממחווה שמהבהבת
_RELEASE_HOLD = 0.3  # מחווה נחשבת כנגמרה רק אחרי כל כך הרבה זמן בלעדיה, כדי שהבהוב לא יספור כמחווה חדשה
_FREEZE = 0.3  # אחרי קליק לא מזיזים את הסמן, כי הראש/היד זזים קצת בזמן המחווה

# טווח התנועה (חצי רוחב, חצי גובה) בקואורדינטות מנורמלות של הפריים, לרגישות 1
_RANGE = {"hand": (0.28, 0.22), "head": (0.10, 0.07)}
_CENTER = {"hand": (0.5, 0.45), "head": (0.5, 0.5)}


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


class MouseController:
    def __init__(self, cfg):
        self.cfg = cfg
        self.mouse = Controller()
        user32 = ctypes.windll.user32
        self.sw, self.sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        self.fx, self.fy = OneEuro(), OneEuro()
        self.prev = set()
        self.last_seen = {}
        self.last_click = -1e9
        self.last_scroll = 0.0
        self.freeze_until = 0.0
        self.dragging = None
        self.head_center = None
        self._last_point = None

    def recenter_head(self):
        """קובע את מיקום הראש הנוכחי כמרכז המסך."""
        if self._last_point is not None:
            self.head_center = tuple(self._last_point)

    def _point(self, hands, face):
        src = self.cfg["control_source"]
        if src == "hand" and hands:
            # מרכז כף היד יציב יותר מקצה האצבע, ולא זז כשמבצעים צביטה
            p = hands[0][[0, 5, 9, 13, 17]].mean(axis=0)
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

    def update(self, hands, face, signs, wink):
        """נקרא מחוט המעקב אחרי כל פריים."""
        now = time.perf_counter()
        if not self.cfg["control_enabled"]:
            self.release()
            self.fx.reset(), self.fy.reset()
            self.prev = set()
            return

        raw = {s for s in signs if s}
        if wink:
            raw.add(wink)
        for g in raw:
            self.last_seen[g] = now
        # הקליקים נקבעים לפי מחוות "מוחזקות" (נשארות פעילות עוד רגע אחרי שנעלמו), הגלילה לפי מה שנראה עכשיו
        active = {g for g, t in self.last_seen.items() if now - t < _RELEASE_HOLD}
        self.last_seen = {g: self.last_seen[g] for g in active}

        p, src = self._point(hands, face)
        # בזמן קריצה הפנים זזים, אז לא מזיזים את הסמן
        if p is not None and not wink and now >= self.freeze_until:
            self._move(p, src, now)
        elif p is None:
            self.fx.reset(), self.fy.reset()

        bindings = self.cfg["bindings"]
        for g in active - self.prev:
            self._fire(bindings.get(g, "none"), g, now)
        for g in self.prev - active:
            if bindings.get(g) == "drag":
                self.release()
        for g in raw:
            action = bindings.get(g, "none")
            if action in _SCROLL and now - self.last_scroll >= _SCROLL_INTERVAL:
                self.mouse.scroll(0, _SCROLL[action])
                self.last_scroll = now
        self.prev = active

    def _fire(self, action, gesture, now):
        if action in _CLICKS:
            if now - self.last_click < _COOLDOWN:
                return
            self.last_click = now
            self.freeze_until = now + _FREEZE
            button, count = _CLICKS[action]
            self.mouse.click(button, count)
        elif action == "drag" and self.dragging is None:
            self.dragging = Button.left
            self.mouse.press(Button.left)

    def release(self):
        if self.dragging is not None:
            self.mouse.release(self.dragging)
            self.dragging = None
