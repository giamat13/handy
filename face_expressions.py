"""פה פתוח, חיוך וגבות מורמות מנקודות הפנים.

כל המדדים מנורמלים לפי המרחק בין זוויות העיניים החיצוניות, כך שהמרחק מהמצלמה לא משנה. חיוך וגבות נמדדים מול ה"רגיל" של
האדם (ממוצע שמסתגל לאט), כי רוחב הפה והמרחק של הגבות מהעיניים שונים מאדם לאדם. פה פתוח נמדד ישירות: פה סגור הוא בערך אפס.
המחוות נשארות מזוהות כל עוד הן מוחזקות, ולכן אפשר לקשור אליהן גם לחיצה ארוכה."""
import math

import numpy as np

MOUTH_OPEN, SMILE, BROWS_UP = "face_mouth_open", "face_smile", "face_brows_up"

_EYE_OUTER = (33, 263)
_LIPS = (13, 14)                 # שפה עליונה ותחתונה (פנימיות)
_MOUTH_CORNERS = (61, 291)
_BROWS = ((105, 159), (334, 386))   # (גבה, עפעף עליון) לכל עין

OPEN_ENTER, OPEN_EXIT, OPEN_HOLD = 0.22, 0.14, 0.25     # פתיחת פה (מרחק השפתיים ביחס למרחק העיניים) ושניות: דיבור רגיל קצר מזה
SMILE_ENTER, SMILE_EXIT, SMILE_HOLD = 0.10, 0.05, 0.3   # הרחבת הפה מול הרגיל
BROWS_ENTER, BROWS_EXIT, BROWS_HOLD = 0.15, 0.07, 0.3   # התרחקות הגבות מהעיניים מול הרגיל
MAX_TURN, MAX_PITCH = 30.0, 25.0   # מעלות: בהפנייה או בהטייה חזקות המרחקים בפריים מתקצרים ולא מעידים על הבעה
DOWN_TAU, UP_TAU = 0.5, 6.0        # שניות: ה"רגיל" יורד מהר (נמצא ערך נמוך יותר) ועולה לאט


def measures(face_px):
    """(פתיחת פה, רוחב פה, גובה גבות) ביחס למרחק העיניים, או None אם הפנים מנוונות."""
    p = face_px[:, :2]
    scale = float(np.linalg.norm(p[_EYE_OUTER[0]] - p[_EYE_OUTER[1]]))
    if scale < 1e-3:
        return None
    opening = float(np.linalg.norm(p[_LIPS[0]] - p[_LIPS[1]]))
    width = float(np.linalg.norm(p[_MOUTH_CORNERS[0]] - p[_MOUTH_CORNERS[1]]))
    brows = sum(float(np.linalg.norm(p[b] - p[e])) for b, e in _BROWS) / len(_BROWS)
    return opening / scale, width / scale, brows / scale


class _Trigger:
    """סף עם היסטרזיס ומשך החזקה. score: 0 עד 0.5 עד שחוצים את הסף, אחר כך 0.5 עד 1 לפי זמן ההחזקה."""

    def __init__(self, enter, exit_, hold):
        self.enter, self.exit, self.hold = enter, exit_, hold
        self.reset()

    def reset(self):
        self.since = None
        self.on = False
        self.score = 0.0

    def update(self, amount, now):
        if amount >= (self.exit if self.on else self.enter):
            if self.since is None:
                self.since = now
            held = now - self.since
            self.score = 0.5 + 0.5 * min(held / self.hold, 1.0)
            self.on = held >= self.hold
        else:
            self.since = None
            self.on = False
            self.score = 0.5 * min(max(amount / self.enter, 0.0), 1.0)
        return self.on


class ExpressionGestures:
    def __init__(self):
        self._open = _Trigger(OPEN_ENTER, OPEN_EXIT, OPEN_HOLD)
        self._smile = _Trigger(SMILE_ENTER, SMILE_EXIT, SMILE_HOLD)
        self._brows = _Trigger(BROWS_ENTER, BROWS_EXIT, BROWS_HOLD)
        self.reset()

    def reset(self):
        self._base = {"width": None, "brows": None}
        self._last = None
        for t in (self._open, self._smile, self._brows):
            t.reset()
        self.scores = {MOUTH_OPEN: 0.0, SMILE: 0.0, BROWS_UP: 0.0}

    def _gauge(self, key, value, now, freeze):
        """ה"רגיל" של מדד, ויחס המדד אליו פחות 1 (חיובי = יותר מהרגיל)."""
        base = self._base[key]
        if base is None:
            base = value
        if not freeze:
            dt = 0.0 if self._last is None else max(now - self._last, 0.0)
            base += (value - base) * (1.0 - math.exp(-dt / (DOWN_TAU if value < base else UP_TAU)))
        self._base[key] = base
        return value / base - 1.0

    def update(self, face_px, pose, now):
        """פריים אחד. מחזיר tuple של מה שפעיל עכשיו (MOUTH_OPEN / SMILE / BROWS_UP), או None."""
        m = measures(face_px) if face_px is not None else None
        if m is None or pose is None:
            self.reset()
            return None
        if abs(pose.yaw) > MAX_TURN or abs(pose.pitch) > MAX_PITCH:
            for t in (self._open, self._smile, self._brows):
                t.reset()
            self.scores = {MOUTH_OPEN: 0.0, SMILE: 0.0, BROWS_UP: 0.0}
            self._last = now
            return None
        opening, width, brows = m
        is_open = self._open.update(opening, now)
        # פה פתוח משנה את רוחב הפה ולא מעיד על חיוך
        wide_open = opening > OPEN_EXIT
        smile_amount = 0.0 if wide_open else self._gauge("width", width, now, self._smile.on or self._smile.since is not None)
        if wide_open:
            self._gauge("width", width, now, True)
        brows_amount = self._gauge("brows", brows, now, self._brows.on or self._brows.since is not None)
        is_smile = self._smile.update(smile_amount, now)
        is_brows = self._brows.update(brows_amount, now)
        self._last = now
        self.scores = {MOUTH_OPEN: self._open.score, SMILE: self._smile.score, BROWS_UP: self._brows.score}
        found = tuple(name for name, on in ((MOUTH_OPEN, is_open), (SMILE, is_smile), (BROWS_UP, is_brows)) if on)
        return found or None
