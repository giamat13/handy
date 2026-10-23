"""בדיקות עם נקודות סינתטיות, בלי מצלמה."""
import numpy as np

from signs import (
    LEFT_EYE, RIGHT_EYE, WinkDetector, classify_hand,
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


def test_peace():
    assert classify_hand(make_hand({"index", "middle"}, "in")) == "peace"


def test_thumbs():
    assert classify_hand(make_hand(set(), "up")) == "thumbs_up"
    assert classify_hand(make_hand(set(), "down")) == "thumbs_down"


def test_rock():
    assert classify_hand(make_hand({"index", "pinky"}, "in")) == "rock"


def test_ok():
    assert classify_hand(make_hand({"middle", "ring", "pinky"}, "in", pinch=True)) == "ok"


def _face(right_open, left_open):
    face = np.zeros((478, 2), np.float32)
    for idx, opened in ((RIGHT_EYE, right_open), (LEFT_EYE, left_open)):
        cx = 0.4 if idx is RIGHT_EYE else 0.6
        half_h = 0.012 if opened else 0.002
        p1, p2, p3, p4, p5, p6 = idx
        face[p1], face[p4] = (cx - 0.03, 0.4), (cx + 0.03, 0.4)
        face[p2], face[p3] = (cx - 0.01, 0.4 - half_h), (cx + 0.01, 0.4 - half_h)
        face[p6], face[p5] = (cx - 0.01, 0.4 + half_h), (cx + 0.01, 0.4 + half_h)
    return face


def _run(face, n=4):
    d = WinkDetector(3)
    res = None
    for _ in range(n):
        res = d.update(face, 640, 480)
    return res


def test_wink():
    assert _run(_face(right_open=False, left_open=True)) == "wink_right"
    assert _run(_face(right_open=True, left_open=False)) == "wink_left"


def test_blink_and_open_are_not_winks():
    assert _run(_face(False, False)) is None
    assert _run(_face(True, True)) is None
