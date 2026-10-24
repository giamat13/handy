"""Winks and a long blink from the eyelid distances (EAR). Synthetic eyes, no camera."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import eye_gestures as eg  # noqa: E402
from eye_gestures import BLINK_LONG, WINK_LEFT, WINK_RIGHT, EyeGestures  # noqa: E402
from test_head_gestures import make_face  # noqa: E402
from test_mouse_clicks import make, run  # noqa: E402

DT = 1 / 30
POSE = SimpleNamespace(yaw=0.0, pitch=0.0)
OPEN_EAR = 0.30
LEFT = ((33, 133), ((160, 144), (159, 145), (158, 153)))
RIGHT = ((362, 263), ((385, 380), (386, 374), (387, 373)))


def eyes_px(left=OPEN_EAR, right=OPEN_EAR, width=40.0):
    """468 points where only the eyes matter: each eye `width` pixels wide and `ear * width` tall."""
    p = np.zeros((468, 3), np.float32)
    for (a, b), pairs in (LEFT, RIGHT):
        ear = left if (a, b) == LEFT[0] else right
        x0 = 100.0 if (a, b) == LEFT[0] else 300.0
        p[a], p[b] = (x0, 200.0, 0), (x0 + width, 200.0, 0)
        for k, (u, d) in enumerate(pairs):
            p[u] = (x0 + 10 * (k + 1), 200.0 - ear * width / 2, 0)
            p[d] = (x0 + 10 * (k + 1), 200.0 + ear * width / 2, 0)
    return p


def feed(g, frames, start=0.0, pose=POSE):
    """frames: (left_ear, right_ear) per frame."""
    return [g.update(eyes_px(l, r), pose, start + i * DT) for i, (l, r) in enumerate(frames)]


def settled(n=60):
    g = EyeGestures()
    feed(g, [(OPEN_EAR, OPEN_EAR)] * n)
    return g, n * DT


def test_openness_reads_both_eyes():
    left, right = eg.openness(eyes_px(0.30, 0.12))
    assert abs(left - 0.30) < 1e-3 and abs(right - 0.12) < 1e-3


def test_a_held_wink_is_recognised_on_the_right_side():
    g, t = settled()
    seen = feed(g, [(0.08, OPEN_EAR)] * 15, t)                 # left eye shut for half a second
    assert seen[-1] == WINK_LEFT and seen[0] is None           # not at once
    g, t = settled()
    seen = feed(g, [(OPEN_EAR, 0.08)] * 15, t)
    assert seen[-1] == WINK_RIGHT


def test_a_wink_is_let_go_when_the_eye_opens():
    g, t = settled()
    feed(g, [(0.08, OPEN_EAR)] * 15, t)
    seen = feed(g, [(OPEN_EAR, OPEN_EAR)] * 3, t + 1.0)
    assert seen[-1] is None


def test_a_normal_blink_is_nothing():
    g, t = settled()
    seen = feed(g, [(0.08, 0.08)] * 4 + [(OPEN_EAR, OPEN_EAR)] * 10, t)      # 130 ms with both eyes
    assert set(seen) == {None}


def test_a_blink_where_one_eye_lags_is_not_a_wink():
    g, t = settled()
    frames = [(0.08, OPEN_EAR)] * 2 + [(0.08, 0.08)] * 4 + [(0.08, OPEN_EAR)] * 8 + [(OPEN_EAR, OPEN_EAR)] * 5
    assert set(feed(g, frames, t)) == {None}                   # the other eye was shut during it: a blink, and one eye reopening slowly is not a wink


def test_a_short_wink_does_not_count():
    g, t = settled()
    assert set(feed(g, [(0.08, OPEN_EAR)] * 5 + [(OPEN_EAR, OPEN_EAR)] * 5, t)) == {None}     # 170 ms


def test_both_eyes_closed_for_half_a_second_is_a_long_blink():
    g, t = settled()
    seen = feed(g, [(0.08, 0.08)] * 20, t)
    assert seen[0] is None and seen[-1] == BLINK_LONG and WINK_LEFT not in seen and WINK_RIGHT not in seen


def test_a_small_squint_is_not_a_wink():
    g, t = settled()
    assert set(feed(g, [(0.24, OPEN_EAR)] * 30, t)) == {None}   # 80% open


def test_wide_eyes_or_a_different_person_adapt():
    """An eye that is naturally 0.2 open is the 'open' of that person: a wink is still a wink, steady 0.2 is not."""
    g = EyeGestures()
    feed(g, [(0.20, 0.20)] * 90)
    assert set(feed(g, [(0.20, 0.20)] * 30, 3.0)) == {None}
    assert feed(g, [(0.05, 0.20)] * 15, 4.0)[-1] == WINK_LEFT


def test_looking_down_or_turning_away_is_ignored():
    g, t = settled()
    assert set(feed(g, [(0.08, 0.08)] * 30, t, pose=SimpleNamespace(yaw=0.0, pitch=-30.0))) == {None}
    g, t = settled()
    assert set(feed(g, [(0.08, OPEN_EAR)] * 30, t, pose=SimpleNamespace(yaw=50.0, pitch=0.0))) == {None}


def test_a_lost_face_forgets_everything():
    g, t = settled()
    feed(g, [(0.08, OPEN_EAR)] * 15, t)
    assert g.update(None, POSE, t + 1.0) is None and g.scores[WINK_LEFT] == 0.0


def test_scores_grow_as_the_eye_closes():
    g, t = settled()
    feed(g, [(0.26, OPEN_EAR)], t)
    assert 0.0 < g.scores[WINK_LEFT] < 0.5
    feed(g, [(0.08, OPEN_EAR)] * 15, t + 0.1)
    assert g.scores[WINK_LEFT] == 1.0 and g.scores[WINK_RIGHT] == 0.0


def test_works_with_a_real_synthetic_face_pose():
    import head_pose

    pose = head_pose.estimate(make_face(), 640, 480)
    g = EyeGestures()
    for i in range(60):
        g.update(eyes_px(), pose, i * DT)
    seen = [g.update(eyes_px(0.08, OPEN_EAR), pose, 2.0 + i * DT) for i in range(15)]
    assert seen[-1] == WINK_LEFT


def test_a_wink_clicks_and_holds_like_a_pose(monkeypatch):
    m, t = make(monkeypatch, eye_wink_left="left_click")
    run(m, t, [([None] * 6 + [WINK_LEFT],)] * 12)
    assert m.mouse.clicks == [("left", 1)] and m.mouse.pressed == ["left"]
    run(m, t, [([None] * 7,)] * 12)
    assert m.mouse.released == ["left"]


def test_a_wink_is_found_even_when_the_other_eye_narrows_with_it():
    """Shutting one eye pulls the other down a little (muscles, tracker coupling): 70% open on the open side still reads as a wink."""
    g, t = settled()
    seen = feed(g, [(0.07, 0.22)] * 15, t)
    assert seen[-1] == WINK_LEFT


def test_two_eyes_equally_narrowed_is_not_a_wink():
    g, t = settled()
    seen = feed(g, [(0.12, 0.14)] * 30, t)
    assert WINK_LEFT not in seen and WINK_RIGHT not in seen


def test_the_ratios_are_exposed_for_tuning():
    g, t = settled()
    feed(g, [(0.15, OPEN_EAR)], t)
    assert abs(g.ratios[0] - 0.5) < 0.05 and abs(g.ratios[1] - 1.0) < 0.05
