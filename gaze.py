"""מבט לפי העיניים: מיקום האישונים בתוך העיניים, ממופה למסך בכיול של תשע נקודות.

לכל עין מודדים את האישון (468 לעין של 33/133, 473 לעין של 263/362, כפי ש-MediaPipe מסדר את הנקודות) ביחס לציר הפינות שלה:
לאורך העין (מבחוץ פנימה) ולניצב לו. כך נטיית הראש במישור לא משנה את המדידה, והיא מנורמלת לרוחב העין, לכן לא תלויה במרחק מהמצלמה.

המדידה לבד לא מספיקה, כי גם סיבוב הראש מזיז את האישון ביחס לפינות. לכן הכיול הוא רגרסיה לינארית על
[1, dx, dy, yaw, pitch] (זוויות במעלות) למצב "הסתכלות", ועל [1, dx, dy] למצב "אישונים" שמתעלם מזווית הראש. שני המיפויים
נוצרים מאותן דגימות, והתוצאה היא נקודה במסך (0..1 לכל ציר). המשתמש מסתכל על תשע נקודות שהממשק מציג."""
import threading

import numpy as np

from eye_gestures import TURNED, openness

# (אישון, (פינה חיצונית, פינה פנימית), (עפעף עליון, עפעף תחתון)) לכל עין. ציר האופק הולך מבחוץ פנימה, וציר האנך מהעפעף העליון לתחתון,
# כך ששתי העיניים מסכימות על הסימן של dx ו-dy (גם כשהן מראות זו של זו)
_EYES = ((468, (33, 133), (159, 145)), (473, (263, 362), (386, 374)))
IRIS_CENTERS = (468, 473)
MIN_OPEN = 0.12      # פתיחות מתחתיה העין סגורה (כמו ב-eye_gestures): האישון מוסתר, ולכן לא מודדים
EYES = (0, 1, 2, 3)  # אילו עמודות של features לקחת: dx, dy, yaw, pitch (מצב "הסתכלות")
PUPILS = (0, 1)      # dx, dy בלבד (מצב "אישונים": הראש לא משפיע על הסמן)
MODELS = {"eyes": EYES, "pupils": PUPILS}   # לכל מצב מיפוי משלו, מאותו כיול

# תשע נקודות במסך (0..1), שורה אחרי שורה: פינות, מרכז ואמצע הצלעות
TARGETS = tuple((x, y) for y in (0.1, 0.5, 0.9) for x in (0.1, 0.5, 0.9))
SETTLE = 0.6         # שניות: זמן להעביר את המבט לנקודה חדשה. בזמן הזה לא אוספים דגימות
SAMPLES = 15         # פריימים לכל נקודה, אחרי ההתייצבות


def _eye_offset(face_px, iris, corners, lids):
    """מיקום האישון בתוך העין: (לאורך העין, לניצב לה), מנורמל לרוחב העין. None אם העין מנוונת."""
    outer, inner = face_px[corners[0]][:2], face_px[corners[1]][:2]
    axis = inner - outer
    width = float(np.linalg.norm(axis))
    if width < 1e-3:
        return None
    u = axis / width
    # הניצב נלקח מהעפעפיים (ולא מסיבוב של u), ולכן הוא תמיד "למטה" ולא הפוך בעין השנייה
    down = face_px[lids[1]][:2] - face_px[lids[0]][:2]
    v = down - u * float(np.dot(down, u))
    n = float(np.linalg.norm(v))
    if n < 1e-3:
        return None
    v = v / n
    rel = face_px[iris][:2] - (outer + inner) / 2
    return float(np.dot(rel, u)) / width, float(np.dot(rel, v)) / width


def features(face_px, pose):
    """[dx, dy, yaw, pitch] לפריים אחד, או None כשאין מבט למדידה: העין סגורה, הפנים לא נמצאו, או הראש מופנה רחוק מדי."""
    if face_px is None or pose is None or abs(pose.yaw) > TURNED:
        return None
    eyes = openness(face_px)
    if eyes is None or min(eyes) < MIN_OPEN:
        return None
    offs = [_eye_offset(face_px, iris, corners, lids) for iris, corners, lids in _EYES]
    if any(o is None for o in offs):
        return None
    dx = sum(o[0] for o in offs) / len(offs)
    dy = sum(o[1] for o in offs) / len(offs)
    return np.array([dx, dy, pose.yaw, pose.pitch], np.float64)


class GazeMap:
    """ממפה מדידת מבט לנקודה במסך. cols = העמודות של המדידה (EYES או PUPILS), wx / wy = מקדם לקבוע ולכל עמודה."""

    def __init__(self, wx, wy, cols=EYES):
        self.wx = np.asarray(wx, np.float64)
        self.wy = np.asarray(wy, np.float64)
        self.cols = list(cols)

    @staticmethod
    def fit(feats, targets, cols=EYES):
        """feats: שורה לכל דגימה (מ-features), targets: הנקודה במסך לכל דגימה. None אם הפתרון לא תקין."""
        X = np.hstack([np.ones((len(feats), 1)), np.asarray(feats, np.float64)[:, list(cols)]])
        T = np.asarray(targets, np.float64)
        wx = np.linalg.lstsq(X, T[:, 0], rcond=None)[0]
        wy = np.linalg.lstsq(X, T[:, 1], rcond=None)[0]
        if not (np.all(np.isfinite(wx)) and np.all(np.isfinite(wy))):
            return None
        return GazeMap(wx, wy, cols)

    def apply(self, feat):
        """(x, y) במסך, בין 0 ל-1."""
        x = np.concatenate(([1.0], np.asarray(feat, np.float64)[self.cols]))
        return tuple(min(max(float(v), 0.0), 1.0) for v in (x @ self.wx, x @ self.wy))

    def to_dict(self):
        return {"wx": self.wx.tolist(), "wy": self.wy.tolist()}

    @staticmethod
    def from_dict(d, cols=EYES):
        """מההגדרות השמורות, למצב cols. None אם חסר או לא תקין (אז צריך לכייל שוב)."""
        try:
            wx, wy = (np.asarray(d[k], np.float64) for k in ("wx", "wy"))
        except (KeyError, TypeError, ValueError):
            return None
        n = len(cols) + 1
        if wx.shape != (n,) or wy.shape != (n,) or not (np.all(np.isfinite(wx)) and np.all(np.isfinite(wy))):
            return None
        return GazeMap(wx, wy, cols)


class GazeCalibration:
    """הכיול: הממשק מציג נקודה, המשתמש מסתכל עליה, והמעקב אוסף דגימות. אחרי כל התשע מתאימים GazeMap לכל מצב.
    add נקרא מחוט המעקב בכל פריים; השאר (start / cancel / snapshot / take_result) מהשרת."""

    def __init__(self):
        self._lock = threading.Lock()
        self.status = "idle"            # idle / running / done / failed
        self.index = 0                  # הנקודה הנוכחית
        self._feats, self._targets = [], []   # דגימות של הנקודות שכבר הסתיימו
        self._point = []                # דגימות של הנקודה הנוכחית
        self._settle_until = None       # נקבע בדגימה הראשונה של כל נקודה (שעון של המעקב)
        self._result = None

    def start(self):
        with self._lock:
            self.status, self.index = "running", 0
            self._feats, self._targets, self._point, self._settle_until, self._result = [], [], [], None, None

    def cancel(self):
        with self._lock:
            if self.status == "running":
                self.status = "idle"

    def add(self, feat, now):
        """דגימה מפריים (או None כשאין מבט). now = perf_counter, כמו שאר המעקב."""
        with self._lock:
            if self.status != "running" or feat is None:
                return
            if self._settle_until is None:
                self._settle_until = now + SETTLE
            if now < self._settle_until:
                return
            self._point.append(feat)
            if len(self._point) < SAMPLES:
                return
            self._feats += self._point
            self._targets += [TARGETS[self.index]] * len(self._point)
            self._point, self._settle_until = [], None
            self.index += 1
            if self.index == len(TARGETS):
                self._finish()

    def _finish(self):
        """בתוך הנעילה. מתאים מיפוי לכל מצב מאותן דגימות, ומעדכן את הסטטוס."""
        try:
            maps = {name: GazeMap.fit(self._feats, self._targets, cols) for name, cols in MODELS.items()}
            self._result = maps if all(m is not None for m in maps.values()) else None
        except np.linalg.LinAlgError:
            self._result = None
        self.status = "done" if self._result is not None else "failed"
        self._feats, self._targets = [], []

    def take_result(self):
        """הכיול שהסתיים, פעם אחת: {מצב: GazeMap} או None."""
        with self._lock:
            result, self._result = self._result, None
            return result

    def snapshot(self):
        """המצב לממשק: האם מציגים נקודה, ואיפה (0..1)."""
        with self._lock:
            active = self.status == "running"
            x, y = TARGETS[self.index] if active else (None, None)
            return {"active": active, "status": self.status, "index": self.index, "total": len(TARGETS), "x": x, "y": y}
