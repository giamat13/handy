"""The trail and the coordinates on the video: the logic without a window, and the drawing when OpenCV is available."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import view_aids  # noqa: E402


def test_trail_keeps_recent_points_in_order_and_fades_them():
    t = view_aids.Trail(max_age=1.0)
    t.push((0.1, 0.1), 0.0)
    t.push((0.2, 0.2), 0.5)
    pts = t.points(0.6)
    assert [(x, y) for x, y, _ in pts] == [(0.1, 0.1), (0.2, 0.2)]
    assert pts[0][2] < pts[1][2] <= 1.0                          # the old one is fainter


def test_old_points_expire_and_no_point_just_fades_the_trail():
    t = view_aids.Trail(max_age=1.0)
    t.push((0.1, 0.1), 0.0)
    t.push(None, 0.5)                                             # the hand left: nothing added
    assert len(t.points(0.9)) == 1
    assert t.points(1.2) == []


def test_trail_is_bounded_and_can_be_cleared():
    t = view_aids.Trail(max_age=100, max_points=5)
    for i in range(20):
        t.push((i / 20, 0.5), i * 0.01)
    assert len(t.points(1.0)) == 5
    t.clear()
    assert t.points(1.0) == []


def test_coordinates_text():
    assert view_aids.format_coords((1234.7, 567)) == "X: 1234  Y: 567"
    assert view_aids.format_coords(None) is None


def test_drawing_changes_the_frame_only_when_there_is_something_to_draw():
    pytest.importorskip("cv2")
    img = np.zeros((480, 640, 3), np.uint8)
    view_aids.draw_trail(img, [])
    view_aids.draw_trail(img, [(0.5, 0.5, 1.0)])                  # one point has no segment
    view_aids.draw_coords(img, None)
    assert not img.any()
    view_aids.draw_trail(img, [(0.2, 0.2, 0.2), (0.5, 0.5, 1.0)])
    assert img.any()
    img2 = np.zeros((480, 640, 3), np.uint8)
    view_aids.draw_coords(img2, "X: 1  Y: 2")
    assert img2.any()
