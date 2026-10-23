import numpy as np

from core.tracker import TrackResult
from tests.test_gestures import hand
from ui.overlay import HAND_CONNECTIONS, LandmarkSmoother, draw_overlay


def blank():
    return np.zeros((480, 640, 3), dtype=np.uint8)


def test_connections_cover_all_21_points():
    assert {i for c in HAND_CONNECTIONS for i in c} == set(range(21))


def test_hand_is_drawn_and_toggle_off_draws_nothing():
    res = TrackResult(hands={"Right": hand()})
    on, off = blank(), blank()
    draw_overlay(on, res, True, True, LandmarkSmoother())
    draw_overlay(off, res, False, False, LandmarkSmoother())
    assert on.any() and not off.any()


def test_face_dots_drawn_only_when_enabled():
    res = TrackResult(face=[(0.3 + 0.001 * i, 0.5, 0) for i in range(478)])
    a, b = blank(), blank()
    draw_overlay(a, res, True, True, LandmarkSmoother())
    draw_overlay(b, res, True, False, LandmarkSmoother())
    assert a.any() and not b.any()


def test_empty_result_is_fine():
    img = blank()
    draw_overlay(img, TrackResult(), True, True, LandmarkSmoother())
    assert not img.any()


def test_smoother_blends_and_forgets():
    s = LandmarkSmoother(alpha=0.5)
    s.update("Right", [(0.0, 0.0, 0.0)])
    assert s.update("Right", [(1.0, 1.0, 0.0)]) == [(0.5, 0.5, 0.0)]
    s.keep(set())
    assert s.update("Right", [(1.0, 1.0, 0.0)]) == [(1.0, 1.0, 0.0)]  # no glide after the hand was lost
