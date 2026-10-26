"""The tracker end to end with a fake camera that shows an empty room: output shape, no crash, no action fired."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("cv2")
pytest.importorskip("mediapipe")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tracker  # noqa: E402
from custom_gestures import CustomGestureStore  # noqa: E402


class EmptyRoomCamera:
    def __init__(self):
        self.n = 0

    def read(self, last_id, timeout=0.2):
        time.sleep(0.01)
        self.n += 1
        return self.n, np.zeros((240, 320, 3), np.uint8)


def test_a_face_found_near_the_nose_is_mapped_back_to_the_frame():
    class Found:
        def process(self, crop):
            return SimpleNamespace(multi_face_landmarks=[SimpleNamespace(landmark=[SimpleNamespace(x=0.5, y=0.5, z=0.1)])])

    t = tracker.Tracker.__new__(tracker.Tracker)    # only the face search, no models
    t.face_near = Found()
    pts = t._face_near(np.zeros((480, 640, 3), np.uint8), np.array([0.5, 0.5, 1.0], np.float32))
    # the window is centred on the nose at (320, 240): its centre is the frame centre, and z scales with the window width
    assert pts[0, 0] == pytest.approx(0.5) and pts[0, 1] == pytest.approx(0.5) and pts[0, 2] == pytest.approx(0.05)


class FoundHand:
    def __init__(self):
        self.calls = 0

    def process(self, crop):
        self.calls += 1
        return SimpleNamespace(multi_hand_landmarks=[SimpleNamespace(landmark=[SimpleNamespace(x=0.5, y=0.5)] * 21)])


def body_with_left_wrist(wrist=(0.3, 0.5)):
    pts = np.zeros((33, 3), np.float32)
    pts[11], pts[12] = (0.4, 0.3, 1.0), (0.6, 0.3, 1.0)
    pts[15] = (*wrist, 1.0)
    return pts


def bare_tracker():
    t = tracker.Tracker.__new__(tracker.Tracker)    # only the hand logic, no models
    t._hand_checked, t._hand_found = [-1e9, -1e9], {}
    t.hand_near = FoundHand()
    return t


def test_body_hand_bones_are_hidden_where_a_hand_is_drawn():
    t = bare_tracker()
    tracked = [np.full((21, 2), (0.3, 0.5), np.float32)]          # the hand tracker already draws a hand at this wrist
    shown, near = t._body_hands(np.zeros((480, 640, 3), np.uint8), body_with_left_wrist(), tracked, 1.0)
    assert shown[15, 2] == 0 and shown[17, 2] == 0 and shown[11, 2] == 1     # the body's hand bones hidden, the shoulder kept
    assert near == [] and t.hand_near.calls == 0                               # nothing to search for


def test_a_hand_found_near_the_wrist_is_drawn_and_hides_the_body_hand():
    t = bare_tracker()
    rgb = np.zeros((480, 640, 3), np.uint8)
    shown, near = t._body_hands(rgb, body_with_left_wrist(), [], 1.0)
    assert t.hand_near.calls == 1 and len(near) == 1
    assert np.allclose(near[0][0], (0.3, 0.5), atol=1e-3)     # the window's centre is the wrist, mapped back to the frame
    assert shown[15, 2] == 0
    shown, near = t._body_hands(rgb, body_with_left_wrist(), [], 1.2)          # still drawn during the hold, no search yet
    assert t.hand_near.calls == 1 and len(near) == 1
    shown, near = t._body_hands(rgb, body_with_left_wrist(), [], 2.5)          # searched again after the interval
    assert t.hand_near.calls == 2 and len(near) == 1


class RecordingController:
    def __init__(self):
        self.calls = []
        self.point = None

    def allowed_slots(self):
        return {0, 1}

    def update(self, hands, face, signs, labels=None, gaze_feat=None):
        self.calls.append((hands, signs, labels))


def test_tracker_publishes_a_complete_output(tmp_path):
    ctrl = RecordingController()
    t = tracker.Tracker(EmptyRoomCamera(), ctrl, CustomGestureStore(tmp_path / "c.json")).start()
    out, deadline = None, time.time() + 20
    while out is None and time.time() < deadline:
        out = t.latest(0)
        time.sleep(0.05)
    t.stop()
    assert out is not None
    assert out.hands == [] and out.slots == [] and out.signs == [None] * 10 and out.point is None   # left, right, custom head, nod / shake, tilt, lean, eyes, face expressions, hand motions, body
    assert out.pose is None and out.body is None and not any(out.conf.values())   # nothing in the room: the built-in head / hand motions score zero
    assert ctrl.calls and all(c[1] == [None] * 10 for c in ctrl.calls)


def test_a_recorder_silences_the_actions(tmp_path):
    class Rec:
        def __init__(self):
            self.frames = 0

        def add(self, pts, label=None):
            self.frames += 1

    ctrl, rec = RecordingController(), Rec()
    t = tracker.Tracker(EmptyRoomCamera(), ctrl, CustomGestureStore(tmp_path / "c.json"))
    t.recorder = rec
    t.start()
    deadline = time.time() + 20
    while rec.frames < 3 and time.time() < deadline:
        time.sleep(0.05)
    t.stop()
    assert rec.frames >= 3
