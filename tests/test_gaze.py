"""Gaze by the irises: the measurement inside each eye, the calibration to the screen, and the cursor it moves.
Synthetic landmarks only (no camera): the face is built in pixels, the way tracker.py hands it to gaze.py."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gaze  # noqa: E402
import head_pose  # noqa: E402
import mouse_control  # noqa: E402
import webui  # noqa: E402

# MediaPipe's eye corners (outer, inner) in pixels. Each eye is 60 px wide, centred at CENTERS. LIDS = the openness pairs of eye_gestures.
CORNERS = {33: (100, 200), 133: (160, 200), 263: (340, 200), 362: (280, 200)}
CENTERS = (130, 310)
LIDS = (((160, 144), (159, 145), (158, 153)), ((385, 380), (386, 374), (387, 373)))


def face(shift=0.0, ratio=0.3, drop=0.0):
    """shift: px the irises move toward the nose. drop: px down. ratio: eye opening / eye width."""
    p = np.zeros((478, 2), np.float64)
    for i, xy in CORNERS.items():
        p[i] = xy
    h = ratio * 60
    for cx, pairs in zip(CENTERS, LIDS):
        for up, down in pairs:
            p[up], p[down] = (cx, 200 - h / 2), (cx, 200 + h / 2)
    p[468] = (130 + shift, 200 + drop)
    p[473] = (310 - shift, 200 + drop)
    return p


def rotated(p, deg):
    """The whole face turned in the image plane (the head rolls): every landmark about (200, 200)."""
    t = np.radians(deg)
    r = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    return (p - 200) @ r.T + 200


def pose(yaw=0.0, pitch=0.0):
    return head_pose.HeadPose(None, yaw, pitch, 0.0, None, 0.0, None)


def test_the_iris_offset_is_measured_per_eye_in_eye_units():
    assert gaze.features(face(0), pose()) == pytest.approx([0, 0, 0, 0], abs=1e-9)
    assert gaze.features(face(6), pose())[:2] == pytest.approx([6 / 60, 0])     # both eyes move toward the nose: same sign
    assert gaze.features(face(0, drop=6), pose())[:2] == pytest.approx([0, 6 / 60])   # down is +dy in both eyes


def test_the_measurement_does_not_change_when_the_head_rolls():
    assert gaze.features(rotated(face(6, drop=3), 20), pose())[:2] == pytest.approx([6 / 60, 3 / 60], abs=1e-6)


def test_closed_eyes_and_a_turned_head_give_no_measurement():
    assert gaze.features(face(ratio=0.05), pose()) is None       # closed: the iris is hidden
    assert gaze.features(face(), pose(yaw=60)) is None           # turned too far to measure
    assert gaze.features(None, pose()) is None                   # no face


def test_the_map_fits_a_linear_relation_and_clips_to_the_screen():
    rng = np.random.default_rng(0)
    feats = rng.uniform(-0.2, 0.2, (40, 4))
    feats[:, 2:] *= 10
    targets = np.column_stack([0.5 + 2 * feats[:, 0] - 0.01 * feats[:, 2], 0.4 + 3 * feats[:, 1] + 0.005 * feats[:, 3]])
    m = gaze.GazeMap.fit(feats, targets)
    assert m.apply(np.array([0.1, -0.05, 4.0, -2.0])) == pytest.approx((0.66, 0.24), abs=1e-6)
    assert m.apply(np.array([1.0, 0.0, 0.0, 0.0])) == (1.0, pytest.approx(0.4))   # off the screen: clipped


def test_a_saved_map_comes_back_and_a_bad_one_is_dropped():
    m = gaze.GazeMap(np.arange(5.0), np.ones(5))
    back = gaze.GazeMap.from_dict(json.loads(json.dumps(m.to_dict())))
    assert np.allclose(back.wx, m.wx) and np.allclose(back.wy, m.wy)
    for bad in (None, {}, {"wx": [1, 2], "wy": [1, 2, 3, 4, 5]}, {"wx": [0, 0, 0, 0, "x"], "wy": [0] * 5}, {"wx": [float("nan")] * 5, "wy": [0] * 5}):
        assert gaze.GazeMap.from_dict(bad) is None


def run_calibration(calib, feature_of, garbage_while_settling=False):
    """Plays the user: looks at each target in turn, one camera frame every 0.1 s. While the gaze moves, the features are garbage."""
    calib.start()
    t, since, last = 0.0, 0.0, None
    while calib.snapshot()["active"]:
        snap = calib.snapshot()
        if snap["index"] != last:
            last, since = snap["index"], t
        if garbage_while_settling and t - since < gaze.SETTLE:
            feat = np.full(4, 9.0)
        else:
            feat = feature_of((snap["x"], snap["y"]))
        calib.add(feat, t)
        t += 0.1
        assert t < 1000, "calibration never finished"


def looks_at(xy):
    """The features of a user who looks at xy on the screen (head still)."""
    x, y = xy
    return np.array([(x - 0.5) * 0.4, (y - 0.5) * 0.2, 0.0, 0.0])


def test_the_calibration_walks_nine_points_and_fits_them():
    calib = gaze.GazeCalibration()
    run_calibration(calib, looks_at, garbage_while_settling=True)     # the settle time is not counted: garbage there must not matter
    snap = calib.snapshot()
    assert snap["active"] is False and snap["status"] == "done" and snap["total"] == 9
    m = calib.take_result()
    assert m is not None and calib.take_result() is None             # handed over once
    for xy in gaze.TARGETS:
        assert m.apply(looks_at(xy)) == pytest.approx(xy, abs=1e-6)


def test_cancel_stops_the_calibration_and_keeps_nothing():
    calib = gaze.GazeCalibration()
    calib.start()
    calib.add(looks_at((0.1, 0.1)), 0.0)
    calib.cancel()
    assert calib.snapshot()["active"] is False and calib.snapshot()["status"] == "idle"
    assert calib.take_result() is None


class FakeMouse:
    def __init__(self):
        self.position = (0, 0)


def controller(gaze_model):
    cfg = {"control_enabled": True, "control_source": "eyes", "control_hand": "both", "sensitivity": 1.0, "smoothing": 0.5,
           "bindings": {}, "gaze_model": gaze_model}
    return mouse_control.MouseController(cfg, mouse=FakeMouse(), screen=(1001, 801), launcher=lambda b: None)


def test_the_cursor_follows_the_calibrated_gaze_and_stops_when_the_eyes_close():
    model = gaze.GazeMap(wx=[0.5, 1, 0, 0, 0], wy=[0.5, 0, 1, 0, 0]).to_dict()
    m = controller(model)
    signs = [None] * 9
    m.update([], face_pts(), signs, None, gaze_feat=np.array([0.2, -0.1, 0.0, 0.0]))
    assert abs(m.mouse.position[0] - 700) <= 1 and abs(m.mouse.position[1] - 320) <= 1
    assert m.point == pytest.approx((0.5, 0.5))   # the display point is the iris centre in the frame
    m.update([], face_pts(), signs, None, gaze_feat=None)   # eyes closed: the cursor stays where it was
    assert abs(m.mouse.position[0] - 700) <= 1


def test_without_a_calibration_the_eyes_do_not_move_the_cursor():
    m = controller(None)
    m.update([], face_pts(), [None] * 9, None, gaze_feat=np.array([0.2, -0.1, 0.0, 0.0]))
    assert m.mouse.position == (0, 0)


def face_pts():
    """The face as tracker.py hands it to the controller: normalised (x, y), 478 points."""
    return np.full((478, 2), 0.5, np.float32)


class FakeTracker:
    def __init__(self):
        self.gaze_calib = gaze.GazeCalibration()


class FakeMouseCtl:
    def __init__(self):
        self.gaze_map = None


def test_the_backend_starts_saves_and_rejects_what_it_does_not_know():
    saved, tracker, mouse = [], FakeTracker(), FakeMouseCtl()
    cfg = {"control_source": "eyes", "gaze_model": None}
    be = webui.Backend(cfg, None, tracker, mouse, None, None, saved.append, lambda: None)
    be.gaze({"action": "start"})
    assert be._gaze_state()["calib"]["active"] is True and be._gaze_state()["calibrated"] is False
    run_calibration(tracker.gaze_calib, looks_at)
    be.tick()
    assert cfg["gaze_model"] is not None and mouse.gaze_map is not None and len(saved) == 1
    assert be._gaze_state()["calibrated"] is True
    with pytest.raises(webui.ApiError):
        be.gaze({"action": "nope"})
