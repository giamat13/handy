"""Body gestures from synthetic upper-body points: jump, crouch, lean left / right, both arms up. No camera, no mediapipe."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import body_pose  # noqa: E402
import view_aids  # noqa: E402
from body_gestures import ARMS_UP, CROUCH, JUMP, LEAN_LEFT, LEAN_RIGHT, BodyGestures  # noqa: E402

W, H = 640, 480
DT = 1 / 30


def body(cy=240.0, width=120.0, roll=0.0, nose_y=200.0, wrists=(None, None)):
    """33 points of MediaPipe Pose for a 640x480 frame, normalized like MediaPipe. roll in degrees (positive = to the right, like the head).
    wrists: the height of the left and right wrist, or None when it is not visible."""
    pts = np.zeros((33, 3), np.float32)
    ax = width / 2 * math.cos(math.radians(roll))
    ay = width / 2 * math.sin(math.radians(roll))
    for i, x, y in ((11, W / 2 + ax, cy + ay), (12, W / 2 - ax, cy - ay), (0, W / 2, nose_y)):
        pts[i] = (x / W, y / H, 1.0)
    for i, x, y in ((15, W / 2 + ax, wrists[0]), (16, W / 2 - ax, wrists[1])):
        if y is not None:
            pts[i] = (x / W, y / H, 1.0)
    return pts


def run(g, frames, start=0.0):
    """frames: the points of each frame, or None when there is no body. Returns what the gestures said on each frame."""
    return [g.update(None if pts is None else body_pose.estimate(pts, W, H), start + i * DT) for i, pts in enumerate(frames)]


def runs(out, name):
    """How many times the gesture started: a run of frames where it is seen, after a frame where it is not."""
    flags = [name in (s or ()) for s in out]
    return sum(1 for i, f in enumerate(flags) if f and (i == 0 or not flags[i - 1]))


def test_a_still_body_gives_nothing():
    rng = np.random.default_rng(1)
    frames = [body(cy=240 + rng.normal(0, 1), roll=rng.normal(0, 1), nose_y=200 + rng.normal(0, 1)) for _ in range(300)]   # 10 s of noise
    assert set(run(BodyGestures(), frames)) == {None}


def test_a_jump_is_counted_once():
    rise = [body(cy=240 - 60 * min(i / 9, 1)) for i in range(20)]     # the shoulders go up half a width in 0.3 s
    out = run(BodyGestures(), [body()] * 30 + rise + [body(cy=180)] * 10 + [body()] * 60)
    assert runs(out, JUMP) == 1
    assert JUMP in out[60]     # the shoulders came back down within JUMP_LAND of the peak: this is when the jump counts


def test_a_slow_rise_is_not_a_jump():
    up = [body(cy=240 - i / 3) for i in range(1, 181)]                 # standing up from a chair: 6 s, half a width
    assert runs(run(BodyGestures(), [body()] * 30 + up + [body()] * 30), JUMP) == 0


def test_lifting_and_staying_up_is_not_a_jump():
    up = [body(cy=240 - 36)] * 90           # sitting up straight: the shoulders go up 0.3 widths and stay for 3 s
    assert runs(run(BodyGestures(), [body()] * 30 + up + [body()] * 30), JUMP) == 0


def test_a_small_lean_counts():
    out = run(BodyGestures(), [body()] * 30 + [body(roll=9)] * 45)
    assert runs(out, LEAN_RIGHT) == 1


def test_a_lean_that_never_ends_is_accepted_as_the_posture():
    out = run(BodyGestures(), [body()] * 30 + [body(roll=9)] * 300)     # 10 s sideways, longer than LEAN_MAX
    assert runs(out, LEAN_RIGHT) == 1          # it counted once, and did not start again
    assert LEAN_RIGHT not in (out[-1] or ())   # and it is no longer stuck on


def test_a_jump_counts_the_same_at_any_distance():
    rise = [body(cy=240 - 30 * min(i / 9, 1), width=60) for i in range(20)]   # the same jump, the body half as big
    assert runs(run(BodyGestures(), [body(width=60)] * 30 + rise + [body(width=60)] * 30), JUMP) == 1


def test_a_crouch_is_recognised_after_it_is_held():
    out = run(BodyGestures(), [body()] * 30 + [body(cy=312)] * 60 + [body()] * 30)     # the shoulders drop 0.6 widths
    first = next(i for i, s in enumerate(out) if s and CROUCH in s)
    assert 30 + 14 <= first <= 30 + 17          # about CROUCH_HOLD (0.5 s, 15 frames) after the drop
    assert runs(out, CROUCH) == 1


def test_leaning_right_and_left():
    right = run(BodyGestures(), [body()] * 30 + [body(roll=20)] * 45)
    assert runs(right, LEAN_RIGHT) == 1 and runs(right, LEAN_LEFT) == 0
    left = run(BodyGestures(), [body()] * 30 + [body(roll=-20)] * 45)
    assert runs(left, LEAN_LEFT) == 1 and runs(left, LEAN_RIGHT) == 0


def test_a_tilt_that_was_always_there_is_not_a_lean():
    drift = [body(roll=8 * i / 300) for i in range(300)]              # 10 s: the shoulders slowly sink to one side
    assert set(run(BodyGestures(), drift)) == {None}


def test_both_arms_up_is_held_and_one_arm_is_not():
    both = run(BodyGestures(), [body()] * 30 + [body(wrists=(150, 150))] * 30)
    assert runs(both, ARMS_UP) == 1
    one = run(BodyGestures(), [body()] * 30 + [body(wrists=(150, None))] * 60)
    assert runs(one, ARMS_UP) == 0


def test_losing_the_body_starts_the_hold_again():
    frames = [body()] * 30 + [body(cy=312)] * 10 + [None] + [body(cy=312)] * 10 + [body()] * 30    # 0.33 s, nothing, 0.33 s
    assert runs(run(BodyGestures(), frames), CROUCH) == 0


def test_the_roll_has_the_head_sign():
    assert body_pose.estimate(body(roll=15), W, H).roll == pytest.approx(15, abs=0.01)


def test_hidden_shoulders_give_no_pose():
    pts = body()
    pts[11, 2] = 0.1
    assert body_pose.estimate(pts, W, H) is None


def test_the_skeleton_draws_only_the_joints_it_sees():
    img = np.zeros((480, 640, 3), np.uint8)
    view_aids.draw_body(img, np.zeros((33, 3), np.float32))
    assert not img.any()                     # nothing seen, nothing drawn
    pts = np.zeros((33, 3), np.float32)
    pts[11] = (0.3, 0.4, 1.0)
    pts[12] = (0.7, 0.4, 1.0)
    pts[23] = (0.4, 0.8, 0.1)                # the hip is hidden
    view_aids.draw_body(img, pts)
    assert img[192, 320].any()               # the line between the shoulders
    assert not img[384, 256].any()           # the hidden hip is not drawn


def test_the_nose_is_not_drawn_when_the_face_mesh_is_shown():
    pts = np.zeros((33, 3), np.float32)
    pts[0] = (0.5, 0.4, 1.0)                 # the nose, at (320, 192)
    img = np.zeros((480, 640, 3), np.uint8)
    view_aids.draw_body(img, pts, with_face=True)
    assert not img.any()
    view_aids.draw_body(img, pts)
    assert img[192, 320].any()


def test_the_skeleton_draws_whatever_part_is_seen():
    img = np.zeros((480, 640, 3), np.uint8)
    pts = np.zeros((33, 3), np.float32)
    pts[25] = (0.4, 0.6, 0.9)                # only the legs are in the frame: knee and ankle
    pts[27] = (0.4, 0.9, 0.9)
    view_aids.draw_body(img, pts)
    assert img[360, 256].any()               # the line between the knee and the ankle
    img[:] = 0
    pts = np.zeros((33, 3), np.float32)
    pts[15] = (0.2, 0.5, 0.4)                # one wrist seen with a lower score
    view_aids.draw_body(img, pts)
    assert img[240, 128].any()               # the wrist's dot
