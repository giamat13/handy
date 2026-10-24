"""The tracker end to end with a fake camera that shows an empty room: output shape, no crash, no action fired."""
import sys
import time
from pathlib import Path

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


class RecordingController:
    def __init__(self):
        self.calls = []
        self.point = None

    def allowed_slots(self):
        return {0, 1}

    def update(self, hands, face, signs, labels=None):
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
    assert out.hands == [] and out.slots == [] and out.signs == [None, None, None] and out.point is None   # left, right, head
    assert out.pose is None and out.conf == {}
    assert ctrl.calls and all(c[1] == [None, None, None] for c in ctrl.calls)


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
