"""Swipes, circles and waving of an open hand. Synthetic hands, no camera."""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hand_motion as hmo  # noqa: E402
from hand_motion import CIRCLE_CCW, CIRCLE_CW, SWIPE_DOWN, SWIPE_LEFT, SWIPE_RIGHT, SWIPE_UP, WAVE, HandMotion, HandMotions  # noqa: E402
from test_mouse_clicks import make, run  # noqa: E402
from test_signs import make_hand  # noqa: E402

DT = 1 / 30
FRAME = (640, 480)
OPEN = {"index", "middle", "ring", "pinky"}


def hand_at(cx, cy, fingers=OPEN):
    """An upright hand whose palm centre is (cx, cy) in normalised coordinates."""
    h = make_hand(fingers, "out")
    palm = h[[0, 5, 9, 13, 17]].mean(axis=0)
    return h + (np.array([cx, cy], np.float32) - palm)


def feed(det, centres, start=0.0, fingers=OPEN):
    return [det.update(hand_at(x, y, fingers), FRAME, start + i * DT) for i, (x, y) in enumerate(centres)]


def line(a, b, n):
    return [(a[0] + (b[0] - a[0]) * i / (n - 1), a[1] + (b[1] - a[1]) * i / (n - 1)) for i in range(n)]


def palm_units():
    """How many normalised x units one palm is across the frame width (the hand is ~0.2 tall; the palm measure is wrist to middle knuckle)."""
    x, y, size = hmo.palm_state(hand_at(0.5, 0.5), *FRAME)[0][0], 0, hmo.palm_state(hand_at(0.5, 0.5), *FRAME)[1]
    return size / FRAME[0]


def test_the_open_hand_is_seen_as_open():
    assert hmo.palm_state(hand_at(0.5, 0.5), *FRAME)[2] is True
    assert hmo.palm_state(hand_at(0.5, 0.5, {"index"}), *FRAME)[2] is False


def test_swipes_in_the_four_directions():
    p = palm_units()
    for name, (dx, dy) in ((SWIPE_RIGHT, (1, 0)), (SWIPE_LEFT, (-1, 0)), (SWIPE_DOWN, (0, 1)), (SWIPE_UP, (0, -1))):
        det = HandMotion()
        feed(det, [(0.5, 0.5)] * 20)
        far = 3.5 * p
        seen = feed(det, line((0.5, 0.5), (0.5 + dx * far, 0.5 + dy * far * 640 / 480), 10), 1.0)
        assert name in seen, name
        assert {s for s in seen if s} == {name}


def test_a_slow_drift_is_not_a_swipe():
    det = HandMotion()
    p = palm_units()
    seen = feed(det, line((0.2, 0.5), (0.2 + 3.5 * p, 0.5), 90))        # the same distance over three seconds
    assert set(seen) == {None}


def test_a_small_move_is_not_a_swipe():
    det = HandMotion()
    p = palm_units()
    assert set(feed(det, line((0.5, 0.5), (0.5 + 1.2 * p, 0.5), 10))) == {None}


def test_a_zigzag_is_not_a_swipe():
    det = HandMotion()
    p = palm_units()
    path = [(0.5 + (i % 2) * 0.01, 0.5 + i * 0.4 * p * 640 / 480 * 0.3) for i in range(12)]
    assert set(feed(det, path)) == {None}


def test_only_an_open_hand_counts():
    det = HandMotion()
    p = palm_units()
    for fingers in ({"index"}, set(), {"index", "middle"}):
        assert set(feed(det, line((0.5, 0.5), (0.5 + 3.5 * p, 0.5), 10), fingers=fingers)) == {None}, fingers


def test_a_circle_either_way():
    p = palm_units()
    r = 1.2 * p
    for name, sign in ((CIRCLE_CW, 1), (CIRCLE_CCW, -1)):
        det = HandMotion()
        feed(det, [(0.5, 0.5)] * 10)
        pts = [(0.5 + r * math.cos(sign * 2 * math.pi * i / 36), 0.5 + r * math.sin(sign * 2 * math.pi * i / 36) * 640 / 480) for i in range(40)]
        seen = feed(det, pts, 0.4)
        assert name in seen, name
        assert {s for s in seen if s} == {name}


def test_half_a_circle_is_not_enough_and_a_line_is_not_a_circle():
    p = palm_units()
    det = HandMotion()
    half = [(0.5 + 1.2 * p * math.cos(math.pi * i / 20), 0.5 + 1.2 * p * math.sin(math.pi * i / 20) * 640 / 480) for i in range(21)]
    assert not {CIRCLE_CW, CIRCLE_CCW} & set(feed(det, half))
    det = HandMotion()
    assert not {CIRCLE_CW, CIRCLE_CCW} & set(feed(det, line((0.2, 0.5), (0.2 + 2 * p, 0.5), 20)))


def test_waving():
    p = palm_units()
    det = HandMotion()
    pts = [(0.5 + 1.5 * p * math.sin(2 * math.pi * 2.5 * i / 45), 0.5) for i in range(45)]       # 2.5 waves in 1.5 s
    seen = feed(det, pts)
    assert WAVE in seen and not {SWIPE_LEFT, SWIPE_RIGHT} & set(seen)


def test_once_per_motion_and_the_name_is_held_briefly():
    p = palm_units()
    det = HandMotion()
    feed(det, [(0.5, 0.5)] * 20)
    seen = feed(det, line((0.5, 0.5), (0.5 + 4 * p, 0.5), 10) + [(0.5 + 4 * p, 0.5)] * 30, 1.0)
    first = seen.index(SWIPE_RIGHT)
    assert sum(1 for a, b in zip([None] + seen, seen) if b and not a) == 1
    assert seen[-1] is None and sum(1 for s in seen[first:] if s) >= int(hmo.HOLD / DT) - 2


def test_a_lost_hand_forgets_the_motion():
    p = palm_units()
    det = HandMotion()
    feed(det, line((0.5, 0.5), (0.5 + 1.0 * p, 0.5), 6))
    assert det.update(None, FRAME, 0.2) is None
    # the two halves together would be a swipe; with the hand lost in between the second half alone is too short
    assert set(feed(det, line((0.5 + 1.0 * p, 0.5), (0.5 + 2.0 * p, 0.5), 6), 0.23)) == {None}


def test_only_the_hands_that_may_control_count():
    p = palm_units()
    motions = HandMotions()
    left, right = hand_at(0.3, 0.5), hand_at(0.7, 0.5)
    for i in range(20):
        motions.update({0: left, 1: right}, (0, 1), FRAME, i * DT)
    out = None
    for i in range(10):
        x = 0.7 + 3.5 * p * i / 9
        out = motions.update({0: left, 1: hand_at(x, 0.5)}, (0, 1), FRAME, 1.0 + i * DT) or out
    assert out == (SWIPE_RIGHT,)
    motions = HandMotions()                                     # the right hand is not allowed to control (only the left one)
    for i in range(20):
        motions.update({0: left, 1: right}, (0,), FRAME, i * DT)
    out = None
    for i in range(10):
        out = motions.update({0: left, 1: hand_at(0.7 + 3.5 * p * i / 9, 0.5)}, (0,), FRAME, 1.0 + i * DT) or out
    assert out is None


def test_scores_grow_with_the_motion():
    p = palm_units()
    det = HandMotion()
    feed(det, [(0.5, 0.5)] * 20)
    feed(det, line((0.5, 0.5), (0.5 + 1.0 * p, 0.5), 5), 1.0)
    assert 0.0 < det.scores[SWIPE_RIGHT] < 0.5


def test_a_swipe_runs_its_binding(monkeypatch):
    m, t = make(monkeypatch, swipe_left={"type": "hotkey", "keys": "alt+left"}, wave="toggle_control", enabled=True)
    run(m, t, [([None] * 8 + [(SWIPE_LEFT,)],)] * 6)
    assert [d for d, _ in m._keyboard.log if d == "down"]
