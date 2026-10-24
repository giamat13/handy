"""תצוגות עזר על הווידאו: שובל זוהר שצבעו לפי מהירות, גלי קליק, צירי הראש, מד הצביטה וקואורדינטות הסמן. הלוגיקה בנפרד מהציור, כדי שאפשר לבדוק אותה."""
import colorsys
import math
from collections import deque

SLOW, FAST = 0.05, 1.6   # מהירויות הקצה של סולם הצבע, בפריימים (רוחב) לשנייה: מתחת ל-SLOW כחול, מעל FAST אדום


def speed_color(speed):
    """צבע (BGR) לפי מהירות: איטי כחול, ובמהירות עולה תכלת, ירוק, צהוב, ועד אדום."""
    t = min(max((speed - SLOW) / (FAST - SLOW), 0.0), 1.0) ** 0.6   # שורש: הטווח האיטי-בינוני מקבל יותר גוונים
    r, g, b = colorsys.hsv_to_rgb((1.0 - t) * 2.0 / 3.0, 1.0, 1.0)
    return int(b * 255), int(g * 255), int(r * 255)


class Trail:
    """נקודות אחרונות (בקואורדינטות מנורמלות של הפריים) שדוהות עם הזמן."""

    def __init__(self, max_age=0.6, max_points=48):
        self.max_age = max_age
        self._pts = deque(maxlen=max_points)

    def push(self, point, now):
        """point: (x, y) או None. בלי נקודה לא מוסיפים כלום והשובל פשוט דוהה."""
        if point is not None:
            self._pts.append((float(point[0]), float(point[1]), now))

    def clear(self):
        self._pts.clear()

    def points(self, now):
        """[(x, y, חיוניות 0..1)] מהישנה לחדשה, בלי נקודות שפג תוקפן."""
        while self._pts and now - self._pts[0][2] > self.max_age:
            self._pts.popleft()
        return [(x, y, 1.0 - (now - t) / self.max_age) for x, y, t in self._pts]

    def segments(self, now):
        """[(x0, y0, x1, y1, חיוניות 0..1, מהירות)] לכל קטע בשובל, מהישן לחדש. המהירות בפריימים לשנייה, מוחלקת כדי שהצבע לא יהבהב."""
        self.points(now)
        pts = list(self._pts)
        out, smooth = [], None
        for (x0, y0, t0), (x1, y1, t1) in zip(pts, pts[1:]):
            v = math.hypot(x1 - x0, y1 - y0) / max(t1 - t0, 1e-3)
            smooth = v if smooth is None else 0.6 * smooth + 0.4 * v
            out.append((x0, y0, x1, y1, 1.0 - (now - t1) / self.max_age, smooth))
        return out


def draw_glow_trail(img, segments):
    """שובל זוהר: קו חד בצבע המהירות ומעליו הילה מטושטשת שמתווספת לתמונה (חיבור, כמו אור)."""
    import cv2
    import numpy as np

    if not segments:
        return
    h, w = img.shape[:2]
    scale = max(w / 640.0, 0.5)
    margin = int(24 * scale)
    xs = [v for s in segments for v in (s[0], s[2])]
    ys = [v for s in segments for v in (s[1], s[3])]
    x0, x1 = max(int(min(xs) * w) - margin, 0), min(int(max(xs) * w) + margin, w)
    y0, y1 = max(int(min(ys) * h) - margin, 0), min(int(max(ys) * h) + margin, h)
    if x1 <= x0 or y1 <= y0:
        return
    glow = np.zeros((y1 - y0, x1 - x0, 3), np.uint8)
    cores = []
    for ax, ay, bx, by, alive, speed in segments:
        col = speed_color(speed)
        fade = 0.35 + 0.65 * alive
        p0, p1 = (int(ax * w) - x0, int(ay * h) - y0), (int(bx * w) - x0, int(by * h) - y0)
        cv2.line(glow, p0, p1, tuple(int(c * fade) for c in col), max(3, round((4 + 9 * alive) * scale)), cv2.LINE_AA)
        cores.append((p0, p1, col, fade, alive))
    glow = cv2.GaussianBlur(glow, (0, 0), 5 * scale)
    roi = img[y0:y1, x0:x1]
    img[y0:y1, x0:x1] = cv2.addWeighted(roi, 1.0, glow, 1.5, 0)
    roi = img[y0:y1, x0:x1].copy()
    for p0, p1, col, fade, alive in cores:
        core = tuple(int((c * 0.55 + 255 * 0.45) * fade) for c in col)   # ליבה בהירה יותר מההילה
        cv2.line(roi, p0, p1, core, max(1, round((1 + 3 * alive) * scale)), cv2.LINE_AA)
    img[y0:y1, x0:x1] = roi


# --- גלי קליק ---------------------------------------------------------------------
RIPPLE_COLORS = {"left": (255, 170, 40), "right": (60, 120, 255), "middle": (220, 90, 230), "double": (60, 230, 255)}   # BGR
RIPPLE_LIFE = 0.8


class Ripples:
    """קליקים אחרונים (זמן, סוג, נקודת פריים מנורמלת) שמתפשטים כטבעת ונמוגים. הלוגיקה בלי ציור."""

    def __init__(self, life=RIPPLE_LIFE):
        self.life = life
        self._items = []
        self._last = -math.inf

    def feed(self, events):
        """events: הקליקים שהעכבר רשם (deque). מוסיף רק את החדשים מאז הפעם הקודמת."""
        for ev in tuple(events):
            if ev[0] > self._last:
                self._items.append(ev)
                self._last = ev[0]

    def clear(self):
        self._items.clear()

    def active(self, now):
        """[(סוג, נקודה, התקדמות 0..1)] לגלים שעוד חיים."""
        self._items = [e for e in self._items if 0 <= now - e[0] < self.life]
        return [(kind, point, (now - t) / self.life) for t, kind, point in self._items]


def draw_ripples(img, items):
    """טבעת שמתרחבת ונמוגה בנקודת הקליק, בצבע לפי סוג הקליק; קליק כפול מצייר שתי טבעות. מתווספת לתמונה כאור."""
    import cv2
    import numpy as np

    if not items:
        return
    h, w = img.shape[:2]
    scale = max(w / 640.0, 0.5)
    layer = np.zeros_like(img)
    for kind, (px, py), progress in items:
        base = RIPPLE_COLORS.get(kind, RIPPLE_COLORS["left"])
        centre = (int(px * w), int(py * h))
        rings = (0.0, 0.3) if kind == "double" else (0.0,)
        for delay in rings:
            p = (progress - delay) / (1.0 - delay)
            if not 0.0 <= p < 1.0:
                continue
            ease = 1.0 - (1.0 - p) ** 3                    # מתחיל מהר ונרגע
            fade = 1.0 - p
            col = tuple(int(c * fade) for c in base)
            cv2.circle(layer, centre, max(2, round((8 + 52 * ease) * scale)), col, max(1, round((1 + 4 * fade) * scale)), cv2.LINE_AA)
        flash = 1.0 - min(progress * 4.0, 1.0)             # הבזק קטן ומלא ברגע הקליק
        if flash > 0:
            cv2.circle(layer, centre, max(2, round(9 * scale)), tuple(int(c * flash) for c in base), -1, cv2.LINE_AA)
    cv2.add(img, layer, dst=img)


# --- כיוון הראש ---------------------------------------------------------------------
AXIS_COLORS = ((60, 60, 255), (90, 230, 90), (255, 140, 40))   # BGR: ימינה אדום, למטה ירוק, קדימה כחול
AXIS_NAMES = ("X", "Y", "Z")


def axis_tips(pose):
    """הקצוות של שלושת הצירים, בקואורדינטות מנורמלות של הפריים. הציר הקדמי (Z) מוצג בהיטל, ולכן כמעט נקודה כשמסתכלים ישר למצלמה."""
    w, h = pose.frame
    nx, ny = float(pose.nose[0]), float(pose.nose[1])
    return [(nx + float(a[0]) * pose.size / w, ny + float(a[1]) * pose.size / h) for a in pose.axes]


def head_text(pose):
    return f"Yaw {pose.yaw:+.0f}  Pitch {pose.pitch:+.0f}  Roll {pose.roll:+.0f}"


def _shadow_text(img, text, org, scale, color=(255, 255, 255)):
    import cv2

    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), max(3, round(5 * scale)), cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, max(1, round(2 * scale)), cv2.LINE_AA)


def draw_head_axes(img, pose):
    """צירי הראש התלת-ממדיים מקצה האף, ומתחתיהם הזוויות במעלות."""
    import cv2

    if pose is None:
        return
    h, w = img.shape[:2]
    scale = max(w / 640.0, 0.5)
    nose = (int(pose.nose[0] * w), int(pose.nose[1] * h))
    for tip, col, name in zip(axis_tips(pose), AXIS_COLORS, AXIS_NAMES):
        end = (int(tip[0] * w), int(tip[1] * h))
        cv2.arrowedLine(img, nose, end, (0, 0, 0), max(3, round(5 * scale)), cv2.LINE_AA, tipLength=0.25)
        cv2.arrowedLine(img, nose, end, col, max(2, round(3 * scale)), cv2.LINE_AA, tipLength=0.25)
        if math.hypot(end[0] - nose[0], end[1] - nose[1]) > 12 * scale:
            _shadow_text(img, name, (end[0] + int(5 * scale), end[1] + int(5 * scale)), 0.5 * scale, col)
    cv2.circle(img, nose, max(3, round(4 * scale)), (255, 255, 255), -1, cv2.LINE_AA)
    _shadow_text(img, head_text(pose), (int(10 * scale), int(24 * scale)), 0.55 * scale)


# --- מד הצביטה ----------------------------------------------------------------------
PINCH_FULL = 1.0   # מרחק (ביחידות כף יד) שבו המד ריק


def pinch_amount(ratio):
    """כמה האגודל והאצבע קרובים, 0 (רחוקים) עד 1 (נוגעים), ממרחק ביחידות כף יד (signs.pinch_ratio)."""
    return min(max(1.0 - ratio / PINCH_FULL, 0.0), 1.0)


def draw_pinch(img, pts):
    """קו בין קצה האגודל לקצה האצבע שהופך מאדום לירוק ככל שהם מתקרבים, ומד עם סימון איפה צביטה נספרת."""
    import cv2

    from signs import PINCH_LIMIT, pinch_ratio

    h, w = img.shape[:2]
    scale = max(w / 640.0, 0.5)
    amount = pinch_amount(pinch_ratio(pts))
    limit = pinch_amount(PINCH_LIMIT)
    on = amount >= limit
    col = (90, 255, 120) if on else (60, int(120 + 135 * amount / max(limit, 1e-6)), 255 - int(155 * amount / max(limit, 1e-6)))
    a, b = (int(pts[4][0] * w), int(pts[4][1] * h)), (int(pts[8][0] * w), int(pts[8][1] * h))
    cv2.line(img, a, b, (0, 0, 0), max(3, round(4 * scale)), cv2.LINE_AA)
    cv2.line(img, a, b, col, max(2, round(2 * scale)), cv2.LINE_AA)
    bw, bh = int(70 * scale), int(9 * scale)
    mx, my = (a[0] + b[0]) // 2 - bw // 2, max((a[1] + b[1]) // 2 + int(22 * scale), 0)
    mx = min(max(mx, 2), max(w - bw - 2, 2))
    my = min(my, h - bh - int(8 * scale))
    cv2.rectangle(img, (mx - 1, my - 1), (mx + bw + 1, my + bh + 1), (0, 0, 0), -1)
    cv2.rectangle(img, (mx, my), (mx + int(bw * amount), my + bh), col, -1)
    tick = mx + int(bw * limit)
    cv2.line(img, (tick, my - 3), (tick, my + bh + 3), (255, 255, 255), 1, cv2.LINE_AA)
    _shadow_text(img, f"PINCH {amount * 100:.0f}%", (mx, my - int(6 * scale)), 0.42 * scale, col)


def format_coords(pos):
    """"X: 1234  Y: 567", או None אם אין מיקום."""
    if pos is None:
        return None
    return f"X: {int(pos[0])}  Y: {int(pos[1])}"


def draw_coords(img, text):
    """כתובת בפינה השמאלית התחתונה (ASCII בלבד, כי cv2 לא מצייר עברית), עם צל לקריאות על כל רקע."""
    import cv2

    if not text:
        return
    h, w = img.shape[:2]
    scale = max(w / 1000.0, 0.5)
    org = (int(10 * scale), h - int(12 * scale))
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.9 * scale, (0, 0, 0), max(3, round(4 * scale)), cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.9 * scale, (255, 255, 255), max(1, round(2 * scale)), cv2.LINE_AA)
