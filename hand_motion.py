"""תנועות יד דינמיות: החלקה (ארבעה כיוונים), עיגול (עם כיוון השעון ונגדו) ונפנוף.

מזהים רק כשהיד פתוחה (כל חמש האצבעות פשוטות). היד גם מזיזה את הסמן כשהשליטה בעכבר פועלת, ותנועות קטנות ואיטיות הן שימוש רגיל, ולכן
דורשים כף יד פתוחה (שאין לה פעולה כברירת מחדל) ותנועה גדולה ביחס לגודל כף היד: המדידה כולה ביחידות של כף היד (שורש עד בסיס האמצעית),
כך שהמרחק מהמצלמה לא משנה. הכיוונים כפי שרואים על המסך (הווידאו הפוך כמו מראה).
כמו הנהון: התנועה היא אירוע, והיא מוצגת רגע קצר אחרי הזיהוי."""
import math
from collections import deque

import numpy as np

from head_motion import swings
from signs import classify_hand

SWIPE_LEFT, SWIPE_RIGHT, SWIPE_UP, SWIPE_DOWN = "swipe_left", "swipe_right", "swipe_up", "swipe_down"
CIRCLE_CW, CIRCLE_CCW, WAVE = "circle_cw", "circle_ccw", "wave"
ALL = (SWIPE_LEFT, SWIPE_RIGHT, SWIPE_UP, SWIPE_DOWN, CIRCLE_CW, CIRCLE_CCW, WAVE)

HISTORY = 2.2          # שניות של היסטוריה
OPEN_WINDOW = 0.8      # בחלון הזה היד צריכה להיות פתוחה ברוב הפריימים
OPEN_FRACTION = 0.5

SWIPE_WINDOW = 0.6     # שניות
SWIPE_DISTANCE = 1.5   # יחידות כף יד: כמה צריך לנוע
SWIPE_STRAIGHT = 0.7   # התזוזה בציר השני חייבת להיות קטנה מזה (כיחס לתזוזה העיקרית)
SWIPE_PATH = 2.0       # ואורך המסלול לא יותר מזה (כיחס לתזוזה), כלומר בקו ישר ולא בזיגזג

CIRCLE_WINDOW = 2.0    # שניות שבהן צריך להשלים סיבוב
CIRCLE_MIN_TIME = 0.7
CIRCLE_TURN = 2 * math.pi * 0.7    # כשלושה רבעים מסיבוב (העיגול לא חייב להיסגר)
CIRCLE_RADIUS = 0.4    # יחידות כף יד: רדיוס מינימלי
CIRCLE_ROUND = 0.6    # סטיית התקן של הרדיוס חלקי הרדיוס: עיגול ולא קו או זיגזג
CIRCLE_ONE_WAY = 0.7   # שיעור הצעדים שמסתובבים באותו כיוון

WAVE_WINDOW = 1.4
WAVE_SWING = 0.45       # יחידות כף יד לכל תנודה
WAVE_SWINGS = 3
WAVE_FLAT = 0.9        # טווח ה-y חייב להיות קטן מזה (כיחס לטווח ה-x)

HOLD = 0.5             # שניות שהתנועה מוצגת אחרי הזיהוי
QUIET = 0.9            # שניות אחרי זיהוי שבהן לא מחפשים חדש


def palm_state(pts, w, h):
    """((x, y) מרכז כף היד בפיקסלים, גודל כף היד בפיקסלים, האם היד פתוחה). pts: (21,2) מנורמל."""
    px = np.asarray(pts, np.float32) * np.array([w, h], np.float32)
    centre = px[[0, 5, 9, 13, 17]].mean(axis=0)
    size = float(np.linalg.norm(px[0] - px[9]))
    return (float(centre[0]), float(centre[1])), size, classify_hand(pts) == "open"


class HandMotion:
    """גלאי לתנועות של יד אחת."""

    def __init__(self):
        self._hist = deque()   # (זמן, x, y, גודל, פתוחה)
        self._quiet_until = 0.0
        self._shown = None
        self.scores = {g: 0.0 for g in ALL}

    def reset(self):
        self._hist.clear()
        self.scores = {g: 0.0 for g in ALL}

    def update(self, pts, frame, now):
        """פריים אחד. pts = (21,2) מנורמל או None, frame = (רוחב, גובה). מחזיר שם תנועה כל עוד היא מוצגת, אחרת None."""
        if self._shown is not None and now >= self._shown[1]:
            self._shown = None
        shown = lambda: self._shown[0] if self._shown else None
        if pts is None:
            self.reset()
            return shown()
        (x, y), size, is_open = palm_state(pts, *frame)
        if size < 1e-3:
            self.reset()
            return shown()
        if now < self._quiet_until:
            return shown()
        self._hist.append((now, x, y, size, is_open))
        while self._hist and now - self._hist[0][0] > HISTORY:
            self._hist.popleft()
        recent = [s for s in self._hist if now - s[0] <= OPEN_WINDOW]
        if sum(1 for s in recent if s[4]) < OPEN_FRACTION * len(recent):
            self.scores = {g: 0.0 for g in ALL}
            return shown()
        unit = float(np.median([s[3] for s in self._hist]))
        t = np.array([s[0] for s in self._hist])
        xs = np.array([s[1] for s in self._hist]) / unit
        ys = np.array([s[2] for s in self._hist]) / unit
        self.scores = {g: 0.0 for g in ALL}
        found = self._circle(t, xs, ys, now) or self._wave(t, xs, ys, now) or self._swipe(t, xs, ys, now)
        if found:
            self._shown = (found, now + HOLD)
            self._quiet_until = now + QUIET
            self.reset()
            self.scores[found] = 1.0
        return shown()

    # --- הגלאים: כל אחד מקבל זמנים ומיקומים (ביחידות כף יד) ומחזיר שם או None, ומעדכן scores ---

    def _circle(self, t, xs, ys, now):
        m = t >= now - CIRCLE_WINDOW
        if m.sum() < 8 or t[m][-1] - t[m][0] < CIRCLE_MIN_TIME:
            return None
        x, y = xs[m], ys[m]
        dx, dy = x - x.mean(), y - y.mean()
        r = np.hypot(dx, dy)
        if r.mean() < CIRCLE_RADIUS or r.std() > CIRCLE_ROUND * r.mean():
            return None
        a = np.unwrap(np.arctan2(dy, dx))
        steps = np.diff(a)
        steps = steps[np.abs(steps) > 1e-3]
        if len(steps) < 5:
            return None
        total = float(a[-1] - a[0])
        # בציר y כלפי מטה, זווית שגדלה היא סיבוב עם כיוון השעון על המסך
        name = CIRCLE_CW if total > 0 else CIRCLE_CCW
        self.scores[name] = 0.5 * min(abs(total) / CIRCLE_TURN, 1.0)
        one_way = float(np.mean(np.sign(steps) == np.sign(total)))
        return name if abs(total) >= CIRCLE_TURN and one_way >= CIRCLE_ONE_WAY else None

    def _wave(self, t, xs, ys, now):
        m = t >= now - WAVE_WINDOW
        if m.sum() < 6:
            return None
        x, y = xs[m], ys[m]
        n = len(swings(list(x), WAVE_SWING))
        flat = (y.max() - y.min()) < WAVE_FLAT * (x.max() - x.min()) if n else False
        self.scores[WAVE] = 0.5 * min(n, WAVE_SWINGS) / WAVE_SWINGS if flat else 0.0
        return WAVE if flat and n >= WAVE_SWINGS else None

    def _swipe(self, t, xs, ys, now):
        m = t >= now - SWIPE_WINDOW
        if m.sum() < 4:
            return None
        x, y = xs[m], ys[m]
        dx, dy = float(x[-1] - x[0]), float(y[-1] - y[0])
        horizontal = abs(dx) >= abs(dy)
        main, other = (dx, dy) if horizontal else (dy, dx)
        if horizontal:
            name = SWIPE_RIGHT if dx > 0 else SWIPE_LEFT
        else:
            name = SWIPE_DOWN if dy > 0 else SWIPE_UP
        path = float(np.hypot(np.diff(x), np.diff(y)).sum())
        # נפנוף בתנועה (שתי תנודות לפחות) הוא לא החלקה
        waving = len(swings(list(xs[t >= now - WAVE_WINDOW]), WAVE_SWING)) >= 2
        straight = abs(other) <= SWIPE_STRAIGHT * abs(main) and path <= SWIPE_PATH * abs(main)
        if not straight or (horizontal and waving):
            return None
        self.scores[name] = 0.5 * min(abs(main) / SWIPE_DISTANCE, 1.0)
        return name if abs(main) >= SWIPE_DISTANCE else None


class HandMotions:
    """גלאי לכל יד (0 שמאל, 1 ימין). update מחזיר tuple של התנועות שמוצגות ממי שמותר לה לשלוט, או None."""

    def __init__(self):
        self._by_slot = {0: HandMotion(), 1: HandMotion()}

    def reset(self):
        for d in self._by_slot.values():
            d.reset()

    def update(self, by_slot, allowed, frame, now):
        found, scores = [], {g: 0.0 for g in ALL}
        for slot, det in self._by_slot.items():
            pts = by_slot.get(slot) if slot in allowed else None
            g = det.update(pts, frame, now)
            if g:
                found.append(g)
            for k, v in det.scores.items():
                scores[k] = max(scores[k], v)
        self.scores = scores
        return tuple(dict.fromkeys(found)) or None

    scores = {g: 0.0 for g in ALL}
