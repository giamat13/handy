"""בדיקות עם נקודות סינתטיות, בלי מצלמה."""
import numpy as np

from signs import (
    assign_slots, classify_hand,
)

# בסיס כל אצבע (MCP) ומיקום רוחבי
_BASES = {"index": (5, -0.06), "middle": (9, -0.02), "ring": (13, 0.02), "pinky": (17, 0.06)}


def make_hand(extended, thumb="in", pinch=False):
    """יד זקופה, שורש בתחתית. extended: קבוצת שמות אצבעות פשוטות."""
    pts = np.zeros((21, 2), np.float32)
    pts[0] = (0.5, 0.8)
    for name, (mcp, dx) in _BASES.items():
        x = 0.5 + dx
        pts[mcp] = (x, 0.62)
        if name in extended:
            pts[mcp + 1], pts[mcp + 2], pts[mcp + 3] = (x, 0.55), (x, 0.49), (x, 0.43)
        else:  # מקופלת: הקצה חוזר לכיוון כף היד
            pts[mcp + 1], pts[mcp + 2], pts[mcp + 3] = (x, 0.57), (x, 0.62), (x, 0.66)
    if thumb == "in":
        pts[1], pts[2], pts[3], pts[4] = (0.46, 0.74), (0.45, 0.70), (0.46, 0.68), (0.48, 0.66)
    elif thumb == "up":
        pts[1], pts[2], pts[3], pts[4] = (0.44, 0.74), (0.40, 0.66), (0.38, 0.58), (0.37, 0.48)
    elif thumb == "down":
        pts[1], pts[2], pts[3], pts[4] = (0.44, 0.76), (0.40, 0.84), (0.38, 0.92), (0.37, 1.02)
    elif thumb == "out":
        pts[1], pts[2], pts[3], pts[4] = (0.44, 0.74), (0.38, 0.70), (0.33, 0.67), (0.28, 0.64)
    if pinch:
        pts[4] = pts[8] + (0.005, 0.005)
    return pts


def test_open():
    assert classify_hand(make_hand({"index", "middle", "ring", "pinky"}, "out")) == "open"


def test_fist():
    assert classify_hand(make_hand(set(), "in")) == "fist"


def test_point():
    assert classify_hand(make_hand({"index"}, "in")) == "point"


def test_victory():
    assert classify_hand(make_hand({"index", "middle"}, "in")) == "victory"
    assert classify_hand(make_hand({"index", "middle"}, "out")) == "victory"  # האגודל לא משנה


def test_hang_loose():
    assert classify_hand(make_hand({"pinky"}, "out")) == "hang_loose"


def test_hang_loose_is_not_confused_with_its_neighbours():
    assert classify_hand(make_hand({"pinky"}, "in")) != "hang_loose"              # בלי אגודל פשוט זו לא שאקה
    assert classify_hand(make_hand({"index", "pinky"}, "out")) == "rock"          # רוק, גם עם אגודל
    assert classify_hand(make_hand(set(), "out")) != "hang_loose"
    assert classify_hand(make_hand({"index"}, "out")) == "point"


def test_assign_slots():
    assert assign_slots(["Left", "Right"]) == [0, 1]
    assert assign_slots(["Right", "Left"]) == [1, 0]
    assert assign_slots(["Right", "Right"]) == [1, 0]   # אותה תווית פעמיים: השנייה עוברת למשבצת הפנויה
    assert assign_slots(["Left", "Left", "Right"]) == [0, 1, None]
    assert assign_slots([]) == []


def test_thumbs():
    assert classify_hand(make_hand(set(), "up")) == "thumbs_up"
    assert classify_hand(make_hand(set(), "down")) == "thumbs_down"


def test_rock():
    assert classify_hand(make_hand({"index", "pinky"}, "in")) == "rock"


def test_ok():
    assert classify_hand(make_hand({"middle", "ring", "pinky"}, "in", pinch=True)) == "ok"
