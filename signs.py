"""זיהוי סימני יד (מ-21 נקודות)."""
from collections import deque

import numpy as np

# (MCP, PIP, DIP, TIP) לכל אצבע
_FINGERS = {
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}

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
