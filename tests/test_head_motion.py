"""Nod (yes) and shake (no) from the head angles over time. Synthetic angles, no camera."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import head_motion as hm  # noqa: E402
from head_motion import NOD, SHAKE, HeadMotion, swings  # noqa: E402
from test_head_gestures import make_face  # noqa: E402
from test_mouse_clicks import make, run  # noqa: E402

DT = 1 / 30


def feed(motion, angles, start=0.0, dt=DT):
    """angles: (yaw, pitch) per frame. Returns the sign seen on every frame."""
    seen = []
    for i, (yaw, pitch) in enumerate(angles):
        seen.append(motion.update(SimpleNamespace(yaw=yaw, pitch=pitch), start + i * dt))
    return seen


def wave(frames, amp, cycles, axis):
    """cycles full oscillations of amplitude amp (degrees) on one axis, the other still, with a little tracker noise."""
    rng = np.random.default_rng(3)
    out = []
    for i in range(frames):
        v = amp * math.sin(2 * math.pi * cycles * i / frames) + rng.normal(0, 0.5)
        out.append((0.0, v) if axis == "pitch" else (v, 0.0))
    return out


def test_swings_counts_alternating_moves():
    assert swings([0, 10, 0, 10], 7) == [10, 10, 10]
    assert swings([0, 3, 0, 3, 0], 7) == []                      # below the noise floor
    assert swings([0, 10, 12, 20, 5], 7) == [20, 15]              # a longer move in one direction is one swing
    assert swings([5], 7) == []


def test_nodding_is_recognised():
    m = HeadMotion()
    seen = feed(m, wave(45, 12, 2, "pitch"))                      # ~1.5 s, two nods
    assert NOD in seen and SHAKE not in seen


def test_shaking_is_recognised():
    m = HeadMotion()
    seen = feed(m, wave(45, 15, 2, "yaw"))
    assert SHAKE in seen and NOD not in seen


def test_a_still_head_gives_nothing():
    m = HeadMotion()
    rng = np.random.default_rng(1)
    seen = feed(m, [(rng.normal(0, 0.7), rng.normal(0, 0.7)) for _ in range(300)])      # 10 s of tracker noise
    assert set(seen) == {None}


def test_one_glance_down_and_back_is_not_a_nod():
    m = HeadMotion()
    angles = [(0, 0)] * 10 + [(0, -12 * min(i, 10) / 10) for i in range(15)] + [(0, -12 + 12 * min(i, 10) / 10) for i in range(15)]
    assert set(feed(m, angles)) == {None}


def test_a_slow_drift_is_not_a_nod():
    """The same swings, but spread over many seconds: the window forgets the early ones."""
    m = HeadMotion()
    seen = feed(m, wave(300, 12, 3, "pitch"))                     # 10 s, three slow nods
    assert set(seen) == {None}


def test_a_diagonal_move_is_neither():
    m = HeadMotion()
    seen = feed(m, [(a, p) for (_, p), (a, _) in zip(wave(45, 12, 2, "pitch"), wave(45, 12, 2, "yaw"))])
    assert set(seen) == {None}


def test_one_recognition_per_motion_and_the_sign_is_held_briefly():
    m = HeadMotion()
    seen = feed(m, wave(90, 12, 4, "pitch") + [(0.0, 0.0)] * 60)   # keeps nodding for 3 s, then stops
    runs = sum(1 for a, b in zip([None] + seen, seen) if b == NOD and a != NOD)
    assert runs <= 2                                              # the quiet period stops the tail of the motion counting again
    assert seen[-1] is None                                       # and it is let go
    first = seen.index(NOD)
    held = sum(1 for s in seen[first:first + 30] if s == NOD)
    assert held >= int(hm.HOLD / DT) - 2


def test_a_lost_face_forgets_the_motion():
    m = HeadMotion()
    angles = wave(45, 12, 2, "pitch")
    feed(m, angles[:20])
    assert m.update(None, 20 * DT) is None
    seen = feed(m, angles[20:34], start=21 * DT)                  # what is left after the gap alone is not enough
    assert NOD not in seen


def test_scores_grow_towards_recognition():
    m = HeadMotion()
    feed(m, [(0, 0)] * 5)
    assert m.scores[NOD] == 0.0
    feed(m, [(0, -10)], start=1.0)
    first = m.scores[NOD]
    assert 0 < first < 0.5
    feed(m, [(0, 0), (0, -10), (0, 0)], start=1.05)
    assert m.scores[NOD] >= first and m.scores[SHAKE] == 0.0


def test_works_with_the_real_pose_estimate():
    """A synthetic face nodding goes through head_pose.estimate and is recognised."""
    import head_pose

    m = HeadMotion()
    seen = []
    for i in range(45):
        pitch = 12 * math.sin(2 * math.pi * 2 * i / 45)
        pose = head_pose.estimate(make_face(pitch=pitch), 640, 480)
        seen.append(m.update(pose, i * DT))
    assert NOD in seen


def test_nod_triggers_its_binding_once_even_when_the_hand_is_not_the_dominant_one(monkeypatch):
    m, t = make(monkeypatch, control_hand="left", nod="left_click")
    run(m, t, [([None, None, None, NOD],)] * 8)                   # signs: left, right, custom head, nod / shake
    assert m.mouse.clicks == [("left", 1)]


def test_shake_runs_a_hotkey(monkeypatch):
    m, t = make(monkeypatch, shake={"type": "hotkey", "keys": "ctrl+z"})
    run(m, t, [([None, None, None, SHAKE],)] * 3)
    assert ("down", "z") in [(d, getattr(k, "char", k)) for d, k in m._keyboard.log]
