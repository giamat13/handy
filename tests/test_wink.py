"""Wink detection for faces whose normal eye opening is small (the fixed thresholds never saw such an eye as open)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from signs import LEFT_EYE, RIGHT_EYE, WinkDetector, eye_aspect_ratio  # noqa: E402


def face(right_h, left_h):
    """A face whose eyes are open by half-heights right_h / left_h (fractions of the frame height)."""
    f = np.zeros((478, 2), np.float32)
    for idx, half_h in ((RIGHT_EYE, right_h), (LEFT_EYE, left_h)):
        cx = 0.4 if idx is RIGHT_EYE else 0.6
        p1, p2, p3, p4, p5, p6 = idx
        f[p1], f[p4] = (cx - 0.03, 0.4), (cx + 0.03, 0.4)
        f[p2], f[p3] = (cx - 0.01, 0.4 - half_h), (cx + 0.01, 0.4 - half_h)
        f[p6], f[p5] = (cx - 0.01, 0.4 + half_h), (cx + 0.01, 0.4 + half_h)
    return f


def feed(d, f, n):
    out = None
    for _ in range(n):
        out = d.update(f, 640, 480)
    return out


def ear(half_h):
    return eye_aspect_ratio(face(half_h, half_h), RIGHT_EYE, 640, 480)


SMALL_OPEN, CLOSED = 0.0065, 0.002    # a person whose open eye is small (EAR ~0.16, under the old "open" threshold of 0.21)


def test_the_small_eyed_face_really_is_below_the_fixed_thresholds():
    assert ear(SMALL_OPEN) < WinkDetector.OPEN


def test_a_wink_is_found_on_a_face_with_small_eyes_after_it_learns_them():
    d = WinkDetector(3)
    assert feed(d, face(SMALL_OPEN, SMALL_OPEN), 40) is None            # both open: nothing, and the detector learns
    assert feed(d, face(CLOSED, SMALL_OPEN), 4) == "wink_right"
    assert feed(d, face(SMALL_OPEN, SMALL_OPEN), 4) is None
    assert feed(d, face(SMALL_OPEN, CLOSED), 4) == "wink_left"


def test_a_blink_is_still_not_a_wink_after_learning():
    d = WinkDetector(3)
    feed(d, face(SMALL_OPEN, SMALL_OPEN), 40)
    assert feed(d, face(CLOSED, CLOSED), 5) is None


def test_a_slightly_squinting_eye_is_not_a_wink():
    d = WinkDetector(3)
    feed(d, face(0.012, 0.012), 40)
    assert feed(d, face(0.0105, 0.012), 5) is None                       # ~12% narrower: just a squint


def test_eyes_of_different_sizes_do_not_make_a_wink():
    d = WinkDetector(3)
    assert feed(d, face(0.008, 0.012), 60) is None                       # the right eye is naturally smaller


def test_a_wink_on_the_asymmetric_face_is_found_per_eye():
    d = WinkDetector(3)
    feed(d, face(0.008, 0.012), 40)
    assert feed(d, face(0.0015, 0.012), 4) == "wink_right"
    feed(d, face(0.008, 0.012), 4)
    assert feed(d, face(0.008, 0.002), 4) == "wink_left"


def test_a_real_wink_where_the_other_eye_squints_too_is_found():
    d = WinkDetector(3)
    feed(d, face(0.012, 0.012), 40)
    assert feed(d, face(0.002, 0.009), 4) == "wink_right"                 # the open eye narrows to 75%: people cannot wink without it
    feed(d, face(0.012, 0.012), 4)
    assert feed(d, face(0.0085, 0.002), 4) == "wink_left"                 # even to ~70%


def test_a_blink_that_starts_with_one_eye_is_not_a_wink():
    d = WinkDetector(3)
    feed(d, face(0.012, 0.012), 40)
    out = [feed(d, face(0.005, 0.011), 1), feed(d, face(0.003, 0.008), 1)]   # one eye leads by two frames...
    out += [feed(d, face(0.002, 0.002), 1) for _ in range(4)]               # ...then both are shut
    assert set(out) == {None}


def test_readout_shows_how_open_each_eye_is():
    d = WinkDetector(3)
    assert d.readout() == {"right": None, "left": None, "learning": True}
    feed(d, face(0.012, 0.012), 40)
    assert d.readout()["learning"] is False and d.readout()["right"] == pytest.approx(1.0, abs=0.05)
    feed(d, face(0.006, 0.012), 1)
    assert d.readout()["right"] == pytest.approx(0.5, abs=0.1) and d.readout()["left"] == pytest.approx(1.0, abs=0.05)


def test_a_big_eyed_face_still_works():
    d = WinkDetector(3)
    feed(d, face(0.014, 0.014), 40)
    assert feed(d, face(0.002, 0.014), 4) == "wink_right"


def test_before_it_has_learned_the_fixed_thresholds_apply():
    assert feed(WinkDetector(3), face(0.002, 0.012), 4) == "wink_right"  # as in the original test


def test_no_face_gives_nothing():
    d = WinkDetector(3)
    assert d.update(None, 640, 480) is None and feed(d, None, 3) is None


def test_unreliable_tiny_eyes_fall_back_to_the_fixed_thresholds():
    d = WinkDetector(3)
    assert feed(d, face(0.001, 0.001), 50) is None                       # EAR ~0.02: never an "open" eye, no false winks
