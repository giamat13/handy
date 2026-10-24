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
    t = view_aids.Trail(max_age=1.0)
    view_aids.draw_glow_trail(img, t.segments(0.0))                # an empty trail
    t.push((0.5, 0.5), 0.0)
    view_aids.draw_glow_trail(img, t.segments(0.0))                # one point has no segment
    view_aids.draw_coords(img, None)
    view_aids.draw_ripples(img, [])
    view_aids.draw_head_axes(img, None)
    assert not img.any()
    t.push((0.7, 0.5), 0.05)
    view_aids.draw_glow_trail(img, t.segments(0.05))
    assert img.any()
    img2 = np.zeros((480, 640, 3), np.uint8)
    view_aids.draw_coords(img2, "X: 1  Y: 2")
    assert img2.any()


# --- the glow trail: colour by speed ------------------------------------------------

def test_speed_colour_runs_from_blue_to_red():
    slow, mid, fast = (view_aids.speed_color(v) for v in (0.0, 0.5, 5.0))
    assert slow == (255, 0, 0)                                    # BGR: blue
    assert fast == (0, 0, 255)                                    # BGR: red
    assert mid not in (slow, fast) and mid[1] > 100               # in between there is green
    assert view_aids.speed_color(0.2)[0] > view_aids.speed_color(0.9)[0]   # less blue as it gets faster


def test_trail_segments_carry_the_speed_of_the_movement():
    t = view_aids.Trail(max_age=10.0)
    for i in range(6):                                            # 0.01 per 0.05 s = 0.2 per second
        t.push((0.1 + 0.01 * i, 0.5), 0.05 * i)
    slow = t.segments(0.3)
    assert len(slow) == 5 and all(abs(s[5] - 0.2) < 0.02 for s in slow)
    t.clear()
    for i in range(6):                                            # 0.1 per 0.05 s = 2 per second
        t.push((0.1 + 0.1 * i, 0.5), 0.05 * i)
    assert all(abs(s[5] - 2.0) < 0.1 for s in t.segments(0.3))
    assert all(0.0 <= s[4] <= 1.0 for s in t.segments(0.3))


def test_a_fast_trail_is_drawn_redder_than_a_slow_one():
    pytest.importorskip("cv2")

    def painted(step):
        t = view_aids.Trail(max_age=10.0)
        for i in range(6):
            t.push((0.2 + step * i, 0.5), 0.05 * i)
        img = np.zeros((480, 640, 3), np.uint8)
        view_aids.draw_glow_trail(img, t.segments(0.3))
        return img.astype(int).sum(axis=(0, 1))                   # B, G, R totals

    slow, fast = painted(0.002), painted(0.1)
    assert slow[0] > slow[2] and fast[2] > fast[0]


# --- click ripples ------------------------------------------------------------------

def test_ripples_take_only_new_clicks_and_expire():
    r = view_aids.Ripples(life=1.0)
    events = [(10.0, "left", (0.2, 0.2)), (10.5, "right", (0.6, 0.6))]
    r.feed(events)
    r.feed(events)                                                # the same events again add nothing
    assert [(k, p) for k, p, _ in r.active(10.6)] == [("left", (0.2, 0.2)), ("right", (0.6, 0.6))]
    assert [k for k, _, _ in r.active(11.2)] == ["right"]         # the first one is over
    assert r.active(12.0) == []
    r.feed(events + [(12.5, "double", (0.1, 0.1))])
    assert [k for k, _, _ in r.active(12.6)] == ["double"]


def test_each_click_kind_has_its_own_colour_and_ripples_are_drawn():
    pytest.importorskip("cv2")
    colours = {view_aids.RIPPLE_COLORS[k] for k in ("left", "right", "middle", "double")}
    assert len(colours) == 4
    for kind in ("left", "right", "middle", "double"):
        img = np.zeros((480, 640, 3), np.uint8)
        view_aids.draw_ripples(img, [(kind, (0.5, 0.5), 0.3)])
        assert img.any(), kind
    late = np.zeros((480, 640, 3), np.uint8)
    view_aids.draw_ripples(late, [("left", (0.5, 0.5), 0.95)])
    early = np.zeros((480, 640, 3), np.uint8)
    view_aids.draw_ripples(early, [("left", (0.5, 0.5), 0.1)])
    assert late.sum() < early.sum()                               # it fades out


# --- head axes and the pinch gauge --------------------------------------------------

def test_axis_tips_follow_the_pose():
    import head_pose
    pose = head_pose.HeadPose(np.eye(3, dtype=np.float32), 0.0, 0.0, 0.0, np.array([0.5, 0.5], np.float32), 100.0, (640, 480))
    right, down, forward = view_aids.axis_tips(pose)
    assert right[0] > 0.5 and abs(right[1] - 0.5) < 1e-6          # to the right
    assert down[1] > 0.5 and abs(down[0] - 0.5) < 1e-6            # downward
    assert view_aids.head_text(pose) == "Yaw +0  Pitch +0  Roll +0"


def test_head_axes_and_pinch_gauge_draw_something():
    pytest.importorskip("cv2")
    import head_pose
    from test_signs import make_hand
    pose = head_pose.HeadPose(np.eye(3, dtype=np.float32), 12.0, -3.0, 5.0, np.array([0.5, 0.5], np.float32), 100.0, (640, 480))
    img = np.zeros((480, 640, 3), np.uint8)
    view_aids.draw_head_axes(img, pose)
    assert img.any()
    hand = make_hand({"middle", "ring", "pinky"}, "in", pinch=True)
    img2 = np.zeros((480, 640, 3), np.uint8)
    view_aids.draw_pinch(img2, hand)
    assert img2.any()


def test_pinch_amount_grows_as_the_fingers_close():
    assert view_aids.pinch_amount(0.0) == 1.0 and view_aids.pinch_amount(5.0) == 0.0
    assert view_aids.pinch_amount(0.2) > view_aids.pinch_amount(0.6)
    from signs import PINCH_LIMIT
    assert 0.0 < view_aids.pinch_amount(PINCH_LIMIT) < 1.0       # the click limit is a tick inside the gauge
