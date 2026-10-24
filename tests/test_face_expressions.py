"""Open mouth, smile and raised brows from the face points. Synthetic faces, no camera."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import face_expressions as fx  # noqa: E402
from face_expressions import BROWS_UP, MOUTH_OPEN, SMILE, ExpressionGestures  # noqa: E402
from test_head_gestures import make_face  # noqa: E402
from test_mouse_clicks import make, run  # noqa: E402

DT = 1 / 30
POSE = SimpleNamespace(yaw=0.0, pitch=0.0)


def face(opening=0.0, width=0.55, brows=0.20):
    """468 points, only those the code reads. The outer eye corners are 100 px apart; opening / width / brows are in those units."""
    p = np.zeros((468, 3), np.float32)
    p[33], p[263] = (0, 0, 0), (100, 0, 0)
    p[13], p[14] = (50, 100 - opening * 50, 0), (50, 100 + opening * 50, 0)
    p[61], p[291] = (50 - width * 50, 100, 0), (50 + width * 50, 100, 0)
    p[159], p[386] = (20, 0, 0), (80, 0, 0)
    p[105], p[334] = (20, -brows * 100, 0), (80, -brows * 100, 0)
    return p


def feed(g, faces, start=0.0, pose=POSE):
    return [g.update(f, pose, start + i * DT) for i, f in enumerate(faces)]


def settled(n=90):
    g = ExpressionGestures()
    feed(g, [face()] * n)
    return g, n * DT


def test_measures_are_in_eye_distance_units():
    o, w, b = fx.measures(face(opening=0.3, width=0.6, brows=0.25))
    assert abs(o - 0.3) < 1e-3 and abs(w - 0.6) < 1e-3 and abs(b - 0.25) < 1e-3
    o2, w2, b2 = fx.measures(face(opening=0.3, width=0.6, brows=0.25) * 2.0)      # twice as close: the same numbers
    assert abs(o2 - o) < 1e-3 and abs(w2 - w) < 1e-3 and abs(b2 - b) < 1e-3


def test_an_open_mouth_is_recognised_and_let_go():
    g, t = settled()
    seen = feed(g, [face(opening=0.4)] * 15, t)
    assert seen[0] is None and seen[-1] == (MOUTH_OPEN,)
    assert feed(g, [face()] * 3, t + 1.0)[-1] is None


def test_talking_does_not_open_the_mouth():
    g, t = settled()
    syllables = [face(opening=0.3)] * 3 + [face(opening=0.05)] * 3          # ~100 ms open, ~100 ms shut
    assert set(feed(g, syllables * 10, t)) == {None}


def test_a_smile_is_recognised():
    g, t = settled()
    seen = feed(g, [face(width=0.55 * 1.18)] * 15, t)
    assert seen[0] is None and seen[-1] == (SMILE,)


def test_a_small_change_in_the_mouth_is_not_a_smile():
    g, t = settled()
    assert set(feed(g, [face(width=0.55 * 1.05)] * 60, t)) == {None}


def test_a_wide_open_mouth_is_not_also_a_smile():
    g, t = settled()
    seen = feed(g, [face(opening=0.4, width=0.55 * 1.2)] * 20, t)
    assert seen[-1] == (MOUTH_OPEN,)


def test_raised_brows_are_recognised():
    g, t = settled()
    seen = feed(g, [face(brows=0.20 * 1.3)] * 15, t)
    assert seen[0] is None and seen[-1] == (BROWS_UP,)


def test_smile_and_brows_can_be_active_together():
    g, t = settled()
    seen = feed(g, [face(width=0.55 * 1.2, brows=0.20 * 1.3)] * 15, t)
    assert set(seen[-1]) == {SMILE, BROWS_UP}


def test_a_person_with_a_wide_mouth_or_high_brows_by_nature_is_normal():
    g = ExpressionGestures()
    seen = feed(g, [face(width=0.80, brows=0.35)] * 120)
    assert set(seen) == {None}
    assert feed(g, [face(width=0.80 * 1.2, brows=0.35)] * 15, 4.0)[-1] == (SMILE,)


def test_a_held_expression_does_not_become_the_new_normal():
    g, t = settled()
    seen = feed(g, [face(width=0.55 * 1.2)] * 300, t)               # a ten second smile
    assert seen[-1] == (SMILE,)


def test_turning_or_tilting_the_head_is_ignored():
    g, t = settled()
    assert set(feed(g, [face(brows=0.3)] * 20, t, pose=SimpleNamespace(yaw=0.0, pitch=40.0))) == {None}
    g, t = settled()
    assert set(feed(g, [face(opening=0.5)] * 20, t, pose=SimpleNamespace(yaw=50.0, pitch=0.0))) == {None}


def test_a_lost_face_forgets_everything():
    g, t = settled()
    feed(g, [face(opening=0.4)] * 15, t)
    assert g.update(None, POSE, t + 1.0) is None and g.scores[MOUTH_OPEN] == 0.0


def test_scores_grow_towards_recognition():
    g, t = settled()
    feed(g, [face(opening=0.1)], t)
    assert 0.0 < g.scores[MOUTH_OPEN] < 0.5
    feed(g, [face(opening=0.4)] * 15, t + 0.1)
    assert g.scores[MOUTH_OPEN] == 1.0


def test_works_on_a_synthetic_face_pose():
    import head_pose

    pose = head_pose.estimate(make_face(), 640, 480)
    g = ExpressionGestures()
    for i in range(60):
        g.update(face(), pose, i * DT)
    seen = [g.update(face(opening=0.4), pose, 2.0 + i * DT) for i in range(15)]
    assert seen[-1] == (MOUTH_OPEN,)


def test_two_signs_in_one_slot_are_both_acted_on_and_shown(monkeypatch):
    m, t = make(monkeypatch, face_smile="left_click", face_brows_up="scroll_up")
    run(m, t, [([None] * 7 + [(SMILE, BROWS_UP)],)] * 8)
    assert m.mouse.pressed == ["left"] and m.mouse.scrolls >= 1      # a click and a scroll from the same slot; two clicks are limited by the click cooldown
    try:
        from render import detect_text
    except (AttributeError, ImportError):   # no mediapipe at all (the other-platform CI jobs) or one without the legacy `solutions` API
        pytest.skip("mediapipe solutions not available")
    names = {"face_smile": "חיוך", "face_brows_up": "גבות מורמות"}
    assert detect_text([None, None, None, None, None, None, None, (SMILE, BROWS_UP)], names) == "חיוך + גבות מורמות"
