"""מחוות סטטיות מותאמות אישית: הקלטה (כמה דגימות של תנוחת היד), שמירה ב-custom_gestures.json וזיהוי בזמן אמת.

תנוחה מיוצגת ב-20 נקודות (בלי פרק היד) יחסית לפרק היד ומנורמלות לגודל כף היד, וביד שמאל מראים את ציר x, כך שמחווה
שהוקלטה ביד אחת מזוהה גם בשנייה. ההתאמה היא שורש ממוצע הריבועים של מרחקי הנקודות מול תבנית (ממוצע הדגימות), עם סף שנלמד מהפיזור של
ההקלטה ובדיקה נוספת למרחק הגדול ביותר בנקודה בודדת, כדי שאצבע אחת שונה לא תספיק להתבלבל."""
import json
import os
import re
import threading
import uuid
from pathlib import Path

import numpy as np

from signs import classify_hand

PREFIX = "custom:"
SAMPLES = 12            # כמה דגימות נאספות בהקלטה
SAMPLE_GAP = 3          # פריימים יציבים בין דגימה לדגימה
MOTION_MAX = 0.06       # תנועה מקסימלית בין שני פריימים (ביחידות כף יד) כדי שהתנוחה תיחשב "עומדת"
DWELL = 6               # פריימים יציבים ברצף עד שמחווה מזוהה: תנוחת מעבר לא מפעילה כלום
RELEASE = 3             # פריימים בלי התאמה עד שהמחווה נגמרת
LOST_MAX = 45           # פריימים בלי יד אחרי שההקלטה מתאפסת
MIN_THRESHOLD, MAX_THRESHOLD = 0.10, 0.25
PEAK_FACTOR = 2.5       # המרחק בנקודה בודדת לא יעלה על הסף כפול זה
AMBIGUOUS_GAP = 0.04    # שתי מחוות מותאמות שהמרחק אליהן קרוב יותר מזה: לא מזהים אף אחת
NAME_MAX = 30


def is_custom(gesture_id):
    return isinstance(gesture_id, str) and gesture_id.startswith(PREFIX)


def features(pts, label=None):
    """(20,2) מנורמל, או None אם היד מנוונת. label == "Left" הופך את ציר x."""
    pts = np.asarray(pts, np.float32)
    scale = float(np.linalg.norm(pts[0] - pts[9]))
    if scale < 1e-4:
        return None
    f = (pts - pts[0]) / scale
    if label == "Left":
        f[:, 0] *= -1
    return f[1:]


def distance(a, b):
    """(rms, max) של מרחקי הנקודות בין שתי תנוחות מנורמלות."""
    d = np.linalg.norm(a - b, axis=1)
    return float(np.sqrt(np.mean(d * d))), float(d.max())


def validate_name(name):
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("הזן שם למחווה")
    if len(name) > NAME_MAX:
        raise ValueError(f"השם ארוך מדי (עד {NAME_MAX} תווים)")
    if not name.isprintable():
        raise ValueError("השם מכיל תווים לא חוקיים")
    return name


class Recorder:
    """אוסף דגימות של תנוחה יציבה. מזינים אותו פריים אחרי פריים (add), וכשהוא done קוראים ל-store.add / store.rerecord."""

    def __init__(self, name, gesture_id=None):
        self.name = name
        self.gesture_id = gesture_id    # מלא כשמקליטים מחדש מחווה קיימת
        self.samples = []
        self.raw = []                   # הנקודות המקוריות, לבדיקה מול המחוות המובנות
        self.hint = "waiting"           # waiting / moving / recording / done
        self._prev = None
        self._steady = 0
        self._lost = 0

    @property
    def progress(self):
        return min(len(self.samples) / SAMPLES, 1.0)

    @property
    def done(self):
        return len(self.samples) >= SAMPLES

    def add(self, pts, label=None):
        """פריים אחד. pts = נקודות היד (21,2) או None אם אין יד. מחזיר True אם נאספה דגימה."""
        if self.done:
            return False
        f = features(pts, label) if pts is not None else None
        if f is None:
            self._lost += 1
            self._prev = None
            self._steady = 0
            if self._lost > LOST_MAX and self.samples:
                self.samples, self.raw = [], []  # היד נעלמה לזמן ארוך: מתחילים מחדש ולא מערבבים שתי הקלטות
            self.hint = "waiting"
            return False
        self._lost = 0
        moving = self._prev is not None and distance(f, self._prev)[0] > MOTION_MAX
        self._prev = f
        if moving:
            self._steady = 0
            self.hint = "moving"
            return False
        self._steady += 1
        self.hint = "recording"
        if self._steady % SAMPLE_GAP:
            return False
        self.samples.append(f)
        self.raw.append(np.asarray(pts, np.float32))
        if self.done:
            self.hint = "done"
        return True

    def build(self):
        """(תבנית, סף) מהדגימות."""
        if not self.done:
            raise ValueError("ההקלטה לא הסתיימה")
        arr = np.stack(self.samples)
        template = arr.mean(axis=0)
        spread = max(distance(s, template)[0] for s in self.samples)
        return template, float(min(max(spread * 1.8 + 0.04, MIN_THRESHOLD), MAX_THRESHOLD))

    def builtin_overlap(self):
        """שם מחווה מובנת אם רוב הדגימות מסווגות כמחווה מובנת אחת, אחרת None."""
        counts = {}
        for pts in self.raw:
            s = classify_hand(pts)
            if s:
                counts[s] = counts.get(s, 0) + 1
        if counts:
            name, n = max(counts.items(), key=lambda kv: kv[1])
            if n >= 0.6 * len(self.raw):
                return name
        return None


class CustomGestureStore:
    """הרשימה השמורה. נטענת מהקובץ, ושינוי שומר מיד. הקריאה מחוט המעקב בטוחה: הרשימה המהודרת מוחלפת בבת אחת."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.gestures = {}      # id -> {"name", "template" (20x2 כרשימה), "threshold"}
        self.version = 0
        self._compiled = (-1, [])
        self.load()

    # --- קובץ ---
    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            raw = data["gestures"]
            loaded = {}
            for gid, g in raw.items():
                tpl = np.asarray(g["template"], np.float32)
                if not is_custom(gid) or tpl.shape != (20, 2) or not np.isfinite(tpl).all():
                    continue
                loaded[gid] = {"name": validate_name(g["name"]), "template": tpl.tolist(),
                               "threshold": float(min(max(g["threshold"], MIN_THRESHOLD), MAX_THRESHOLD))}
            self.gestures = loaded
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            self.gestures = {}
        self.version += 1

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps({"version": 1, "gestures": self.gestures}, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)  # כתיבה אטומית: הפסקת חשמל באמצע לא משאירה קובץ חצי

    # --- קריאה ---
    def names(self):
        return {gid: g["name"] for gid, g in self.gestures.items()}

    def compiled(self):
        """[(id, תבנית np, סף)] לזיהוי. נבנה מחדש רק אחרי שינוי."""
        if self._compiled[0] != self.version:
            items = [(gid, np.asarray(g["template"], np.float32), g["threshold"]) for gid, g in self.gestures.items()]
            self._compiled = (self.version, items)
        return self._compiled[1]

    # --- שינוי ---
    def _unique(self, name, except_id=None):
        for gid, g in self.gestures.items():
            if gid != except_id and g["name"].casefold() == name.casefold():
                raise ValueError("כבר יש מחווה בשם הזה")

    def _check_recording(self, rec, except_id=None):
        """דוחה הקלטה שתתבלבל: תנוחה שכבר מוגדרת כמחווה מובנת, או קרובה מדי למחווה מותאמת אחרת."""
        template, threshold = rec.build()
        overlap = rec.builtin_overlap()
        if overlap:
            from actions import GESTURES
            raise ValueError(f"התנוחה הזו כבר מוגדרת כמחווה מובנית ({GESTURES.get(overlap, overlap)}). בחר תנוחה אחרת")
        for gid, g in self.gestures.items():
            if gid == except_id:
                continue
            rms, _ = distance(template, np.asarray(g["template"], np.float32))
            if rms < max(threshold, g["threshold"]) * 1.5:
                raise ValueError(f"התנוחה דומה מדי למחווה '{g['name']}'. בחר תנוחה שונה")
        return template, threshold

    def add(self, name, rec):
        with self._lock:
            name = validate_name(name)
            self._unique(name)
            template, threshold = self._check_recording(rec)
            gid = PREFIX + uuid.uuid4().hex[:8]
            self.gestures = {**self.gestures, gid: {"name": name, "template": template.tolist(), "threshold": threshold}}
            self.version += 1
            self.save()
            return gid

    def rerecord(self, gid, rec):
        with self._lock:
            if gid not in self.gestures:
                raise KeyError(gid)
            template, threshold = self._check_recording(rec, except_id=gid)
            self.gestures = {**self.gestures, gid: {**self.gestures[gid], "template": template.tolist(), "threshold": threshold}}
            self.version += 1
            self.save()

    def rename(self, gid, name):
        with self._lock:
            if gid not in self.gestures:
                raise KeyError(gid)
            name = validate_name(name)
            self._unique(name, except_id=gid)
            self.gestures = {**self.gestures, gid: {**self.gestures[gid], "name": name}}
            self.version += 1
            self.save()

    def delete(self, gid):
        with self._lock:
            self.gestures = {k: v for k, v in self.gestures.items() if k != gid}
            self.version += 1
            self.save()


class CustomMatcher:
    """זיהוי של יד אחת (משבצת אחת) לאורך פריימים. מחווה מזוהה רק אחרי DWELL פריימים יציבים באותה תנוחה, נשארת עד RELEASE פריימים
    בלעדיה, ובמעבר בין תנוחות (יד זזה) לא מזהה כלום."""

    def __init__(self, store):
        self.store = store
        self.reset()

    def reset(self):
        self.current = None
        self._cand = None
        self._streak = 0
        self._miss = 0
        self._prev = None

    def best(self, f):
        """id של המחווה המותאמת הקרובה ביותר אם היא עומדת בסף ובבדיקת הנקודה הבודדת, ואין מתחרה קרוב מדי. אחרת None."""
        scored = []
        for gid, tpl, thr in self.store.compiled():
            rms, peak = distance(f, tpl)
            if rms <= thr and peak <= thr * PEAK_FACTOR:
                scored.append((rms, gid))
        if not scored:
            return None
        scored.sort()
        if len(scored) > 1 and scored[1][0] - scored[0][0] < AMBIGUOUS_GAP:
            return None
        return scored[0][1]

    def update(self, pts, label=None):
        f = features(pts, label) if pts is not None else None
        if f is None:
            self.reset()
            return None
        steady = self._prev is not None and distance(f, self._prev)[0] <= MOTION_MAX
        self._prev = f
        match = self.best(f)
        if match is not None and match == self.current:
            self._miss = 0
            return self.current
        if match is not None and steady:
            self._streak = self._streak + 1 if match == self._cand else 1
            self._cand = match
            if self._streak >= DWELL:
                self.current, self._miss = match, 0
                return self.current
        else:
            self._streak, self._cand = 0, None
        if self.current is not None:
            self._miss += 1
            if self._miss >= RELEASE:
                self.current = None
        return self.current
