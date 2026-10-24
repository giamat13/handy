"""זיהוי סימני יד (מ-21 נקודות) וקריצות (מנקודות הפנים)."""
from collections import deque  # noqa: F401  (Stabilizer and WinkDetector)

import numpy as np

# (MCP, PIP, DIP, TIP) לכל אצבע
_FINGERS = {
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}

# עיניים לפי אנטומיה של הנבדק: p1, p2, p3, p4, p5, p6 לחישוב EAR
RIGHT_EYE = (33, 160, 158, 133, 153, 144)
LEFT_EYE = (362, 385, 387, 263, 373, 380)


def _d(a, b):
    return float(np.linalg.norm(a - b))


def finger_states(pts):
    """מחזיר מילון של אצבעות פשוטות. אינבריאנטי לגודל ולסיבוב היד."""
    wrist = pts[0]
    ext = {}
    for name, (mcp, pip, _dip, tip) in _FINGERS.items():
        ext[name] = _d(pts[tip], wrist) > _d(pts[pip], wrist) * 1.08
    # אגודל: הקצה רחוק מבסיס הזרת יותר מהמפרק שלו
    ext["thumb"] = _d(pts[4], pts[17]) > _d(pts[3], pts[17]) * 1.12 and _d(pts[4], pts[5]) > 0.35 * _d(
        pts[0], pts[9]
    )
    return ext


def classify_hand(pts):
    """מחזיר שם סימן או None. pts: מערך (21,2) בקואורדינטות מנורמלות."""
    e = finger_states(pts)
    scale = _d(pts[0], pts[9]) + 1e-6
    pinch = _d(pts[4], pts[8]) / scale
    others_up = e["middle"] and e["ring"] and e["pinky"]
    four_down = not (e["index"] or e["middle"] or e["ring"] or e["pinky"])

    if pinch < 0.25 and others_up:
        return "ok"
    # באגרוף קצה האגודל קרוב לאצבע המקופלת, אז צביטה דורשת לפחות אצבע אחת פשוטה
    if pinch < 0.25 and (e["middle"] or e["ring"] or e["pinky"]):
        return "pinch"
    if e["thumb"] and four_down:
        # כיוון האגודל ביחס לשורש כף היד (y גדל כלפי מטה)
        dy = (pts[4][1] - pts[0][1]) / scale
        if dy < -0.6:
            return "thumbs_up"
        if dy > 0.6:
            return "thumbs_down"
        return "fist"
    if four_down:
        return "fist"
    if e["index"] and e["middle"] and e["ring"] and e["pinky"]:
        return "open"
    if e["index"] and not (e["middle"] or e["ring"] or e["pinky"]):
        return "point"
    if e["index"] and e["middle"] and not (e["ring"] or e["pinky"]):
        return "victory"
    if e["index"] and e["middle"] and e["ring"] and not e["pinky"]:
        return "three"
    if e["index"] and e["pinky"] and not (e["middle"] or e["ring"]):
        return "rock"
    # אגודל ואזרת פשוטים, שלוש האצבעות האחרות מקופלות
    if e["thumb"] and e["pinky"] and not (e["index"] or e["middle"] or e["ring"]):
        return "hang_loose"
    return None


def assign_slots(labels):
    """משבץ כל יד למשבצת: 0 = שמאל, 1 = ימין. אם MediaPipe נתן לשתי ידיים אותה תווית, השנייה עוברת למשבצת הפנויה.
    מחזיר רשימת משבצות באותו סדר של הידיים (None ליד שלישית, שלא אמורה להיות)."""
    taken, slots = set(), []
    for label in labels:
        slot = 0 if label == "Left" else 1
        if slot in taken:
            slot = 1 - slot
        if slot in taken:
            slots.append(None)
            continue
        taken.add(slot)
        slots.append(slot)
    return slots


def eye_aspect_ratio(face, idx, w, h):
    """EAR בפיקסלים, כדי שיחס הפריים לא ישבש את החישוב."""
    p = face[list(idx)] * (w, h)
    return (_d(p[1], p[5]) + _d(p[2], p[4])) / (2.0 * _d(p[0], p[3]) + 1e-6)


class Stabilizer:
    """מחזיר ערך רק אחרי שהוא חוזר על עצמו n פריימים רצופים (נגד הבהובים)."""

    def __init__(self, n=3):
        self.hist = deque(maxlen=n)
        self.value = None

    def update(self, v):
        self.hist.append(v)
        if len(self.hist) == self.hist.maxlen and len(set(self.hist)) == 1:
            self.value = v
        return self.value


class WinkDetector:
    """קריצה = עין אחת סגורה והשנייה פתוחה, כמה פריימים ברצף. מצמוץ (שתיהן) לא נחשב.

    הספים הקבועים (CLOSED / OPEN) טובים לעין גדולה ומצלמה ישרה, אבל בעיניים קטנות, עם משקפיים או מזווית ה-EAR הרגיל נמוך
    והעין לעולם לא "פתוחה" מספיק, ואז אף קריצה לא מזוהה. לכן אחרי כמה פריימים הגלאי לומד את ה-EAR הרגיל (האחוזון ה-85 בחלון
    אחרון) של כל עין בנפרד, ועין נחשבת סגורה כשהיא יורדת מתחת ל-70% ממנו ופתוחה מעל 85%. עד שלמד משתמשים בספים הקבועים."""

    CLOSED = 0.17
    OPEN = 0.21
    CLOSE_RATIO = 0.70
    OPEN_RATIO = 0.85
    WARMUP = 20      # פריימים עד שיש בסיס
    WINDOW = 120     # כמה פריימים אחרונים מרכיבים את הבסיס
    MIN_BASE = 0.12  # בסיס נמוך מזה = העין לא נמדדת באמינות (פנים רחוקות / מוסתרות), אז לא סומכים עליו

    def __init__(self, frames=3):
        self.stab = Stabilizer(frames)
        self._hist = (deque(maxlen=self.WINDOW), deque(maxlen=self.WINDOW))  # (ימין, שמאל)
        self.ears = None  # (ימין, שמאל) האחרונים, לאבחון

    def _base(self, hist):
        return float(np.percentile(hist, 85)) if len(hist) >= self.WARMUP else None

    def update(self, face, w, h):
        if face is None:
            return self.stab.update(None)
        r = eye_aspect_ratio(face, RIGHT_EYE, w, h)
        l = eye_aspect_ratio(face, LEFT_EYE, w, h)
        self.ears = (r, l)
        self._hist[0].append(r)
        self._hist[1].append(l)
        br, bl = self._base(self._hist[0]), self._base(self._hist[1])
        if br is not None and bl is not None and min(br, bl) >= self.MIN_BASE:
            r_closed, r_open = r < br * self.CLOSE_RATIO, r > br * self.OPEN_RATIO
            l_closed, l_open = l < bl * self.CLOSE_RATIO, l > bl * self.OPEN_RATIO
        else:
            r_closed, r_open = r < self.CLOSED, r > self.OPEN
            l_closed, l_open = l < self.CLOSED, l > self.OPEN
        state = None
        if r_closed and l_open:
            state = "wink_right"
        elif l_closed and r_open:
            state = "wink_left"
        return self.stab.update(state)
