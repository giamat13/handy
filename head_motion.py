"""מחוות ראש דינמיות: הנהון (כן) וניעור ראש (לא), מתוך הזוויות pitch ו-yaw לאורך זמן (head_pose.py).

מחווה כזו היא תנועה ולא תנוחה, ולכן היא לא נלמדת מהקלטה. מחפשים תנודה: כמה תנועות חזרה לסירוגין בציר אחד (למעלה ולמטה, או ימינה ושמאלה)
בחלון זמן קצר, כשהציר השני כמעט לא זז."""
from collections import deque

NOD, SHAKE = "nod", "shake"

WINDOW = 1.6         # שניות: כל התנועות חייבות להיכנס בחלון הזה (תנועה איטית או הסתכלות חד־פעמית למטה לא נחשבות)
MIN_SWING = 7.0      # מעלות: כמה צריך לנוע בכיוון אחד כדי שייספר כתנועה (רעש מעקב הוא סביב 1-2 מעלות)
MIN_SWINGS = 3       # כמה תנועות לסירוגין: למטה-למעלה-למטה, או שמאלה-ימינה-שמאלה
DOMINANCE = 0.6      # טווח הציר השני חייב להיות קטן מזה (כיחס לטווח הציר הראשי), אחרת זו תנועה אלכסונית ולא כן / לא
HOLD = 0.5           # שניות: כמה זמן המחווה נשארת מזוהה אחרי שזוהתה
QUIET = 1.0          # שניות אחרי זיהוי שלא מחפשים חדש, כדי שסוף אותה תנועה לא ייספר שוב


TILT_LEFT, TILT_RIGHT = "tilt_left", "tilt_right"
TILT_ENTER = 20.0    # מעלות: הטיה גדולה מזה (לכיוון כתף) מתחילה את הספירה. הטיה רגילה בישיבה היא עד כ-8 מעלות
TILT_EXIT = 12.0     # מעלות: המחווה נגמרת רק כשהזווית יורדת מתחת לזה (היסטרזיס, כדי שרעד סביב הגבול לא יפעיל ויכבה)
TILT_HOLD = 0.5      # שניות שצריך להחזיק את ההטיה לפני שהיא נחשבת: עוברים דרך הזווית הזו גם בתנועות רגילות


class HeadTilt:
    """הטיית ראש לכתף (roll): תנוחה שמחזיקים, ולא תנועה. נשארת מזוהה כל עוד הראש מוטה, ואפשר לקשור אליה גלילה או קיצור מקשים."""

    def __init__(self):
        self._since = {TILT_LEFT: None, TILT_RIGHT: None}   # מתי הזווית עברה את הסף
        self._on = None
        self.scores = {TILT_LEFT: 0.0, TILT_RIGHT: 0.0}      # 0.5 = הזווית הדרושה, 1 = גם הוחזקה מספיק זמן

    def reset(self):
        self._since = {TILT_LEFT: None, TILT_RIGHT: None}
        self._on = None
        self.scores = {TILT_LEFT: 0.0, TILT_RIGHT: 0.0}

    def update(self, pose, now):
        """פריים אחד. pose = HeadPose או None. מחזיר TILT_LEFT / TILT_RIGHT כל עוד ההטיה פעילה, אחרת None."""
        if pose is None:
            self.reset()
            return None
        roll = pose.roll
        for name, angle in ((TILT_RIGHT, roll), (TILT_LEFT, -roll)):
            limit = TILT_EXIT if self._on == name else TILT_ENTER
            if angle >= limit:
                if self._since[name] is None:
                    self._since[name] = now
                held = now - self._since[name]
                self.scores[name] = 0.5 + 0.5 * min(held / TILT_HOLD, 1.0)
                if held >= TILT_HOLD:
                    self._on = name
            else:
                self._since[name] = None
                self._on = None if self._on == name else self._on
                self.scores[name] = 0.5 * max(angle, 0.0) / TILT_ENTER
        if self._on is not None:
            other = TILT_LEFT if self._on == TILT_RIGHT else TILT_RIGHT
            self._since[other] = None
        return self._on


def swings(values, size):
    """גודל כל תנועה בין שני קצוות מתחלפים ברצף, כשכל תנועה היא לפחות size. התנועה האחרונה נספרת גם אם עוד לא חזרה."""
    if len(values) < 2:
        return []
    out = []
    pivot = ext = values[0]
    direction = 0
    for v in values[1:]:
        if direction == 0:
            if abs(v - pivot) >= size:
                direction, ext = (1 if v > pivot else -1), v
        elif (v - ext) * direction > 0:
            ext = v
        elif abs(v - ext) >= size:
            out.append(abs(ext - pivot))
            pivot, direction, ext = ext, -direction, v
    if direction:
        out.append(abs(ext - pivot))
    return out


class HeadMotion:
    def __init__(self):
        self._samples = deque()      # (זמן, yaw, pitch)
        self._quiet_until = 0.0
        self._shown = None           # (שם המחווה, עד מתי מציגים אותה)
        self.scores = {NOD: 0.0, SHAKE: 0.0}   # 0.5 = חצי מהתנועות הדרושות, 1 = זוהתה (לתצוגת האבחון)

    def reset(self):
        self._samples.clear()
        self.scores = {NOD: 0.0, SHAKE: 0.0}

    def update(self, pose, now):
        """פריים אחד. pose = HeadPose או None. מחזיר NOD / SHAKE כל עוד המחווה מוצגת, אחרת None."""
        if self._shown is not None and now >= self._shown[1]:
            self._shown = None
        if pose is None:
            self.reset()
            return self._shown[0] if self._shown else None
        if now < self._quiet_until:
            if self._shown is None:
                self.scores = {NOD: 0.0, SHAKE: 0.0}
            return self._shown[0] if self._shown else None
        self._samples.append((now, pose.yaw, pose.pitch))
        while self._samples and now - self._samples[0][0] > WINDOW:
            self._samples.popleft()
        yaw = [s[1] for s in self._samples]
        pitch = [s[2] for s in self._samples]
        found = None
        for name, main, other in ((NOD, pitch, yaw), (SHAKE, yaw, pitch)):
            n = len(swings(main, MIN_SWING))
            steady = max(other) - min(other) < DOMINANCE * (max(main) - min(main)) if n else False
            self.scores[name] = 0.5 * min(n, MIN_SWINGS) / MIN_SWINGS if steady else 0.0
            if steady and n >= MIN_SWINGS:
                found = found or name
        if found is not None:
            self._shown = (found, now + HOLD)
            self._quiet_until = now + QUIET
            self.reset()
            self.scores[found] = 1.0
        return self._shown[0] if self._shown else None
