"""Head poses: the 3D axes, recording and recognising custom head gestures, hand and head living side by side. Synthetic faces, no camera."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import custom_gestures as cg  # noqa: E402
import head_pose  # noqa: E402
from test_custom_gestures import POSE_A, record  # noqa: E402
from test_mouse_clicks import make, run  # noqa: E402

W, H = 640, 480
RNG = np.random.default_rng(11)

# a canonical face in "face units" (x right, y down, z away from the camera; the eyes are 0.6 apart), only the points the code reads
_CANON = {
    1: (0, 0.10, -0.35), 6: (0, -0.10, -0.15), 168: (0, -0.15, -0.10), 98: (-0.10, 0.15, -0.15), 327: (0.10, 0.15, -0.15),
    33: (-0.30, -0.12, -0.05), 133: (-0.10, -0.12, -0.10), 362: (0.10, -0.12, -0.10), 263: (0.30, -0.12, -0.05),
    159: (-0.20, -0.17, -0.08), 386: (0.20, -0.17, -0.08), 145: (-0.20, -0.08, -0.08), 374: (0.20, -0.08, -0.08),
    70: (-0.30, -0.27, -0.05), 105: (-0.20, -0.30, -0.07), 107: (-0.10, -0.27, -0.09),
    300: (0.30, -0.27, -0.05), 334: (0.20, -0.30, -0.07), 336: (0.10, -0.27, -0.09),
    61: (-0.15, 0.33, -0.10), 291: (0.15, 0.33, -0.10), 13: (0, 0.30, -0.12), 14: (0, 0.34, -0.12), 0: (0, 0.28, -0.13), 17: (0, 0.40, -0.12),
    10: (0, -0.45, -0.07), 152: (0, 0.55, -0.07), 234: (-0.45, 0, 0.15), 454: (0.45, 0, 0.15),
    172: (-0.30, 0.45, 0.0), 397: (0.30, 0.45, 0.0), 127: (-0.42, -0.20, 0.10), 356: (0.42, -0.20, 0.10),
}


def make_face(yaw=0.0, pitch=0.0, roll=0.0, mouth_open=0.0, at=(0.5, 0.5), size=130.0):
    """Normalised (468,3) face like MediaPipe's, turned by yaw (right +), pitch (up +) and roll (clockwise on screen +), degrees."""
    y, p, r = np.radians([yaw, pitch, roll])
    ry = np.array([[np.cos(y), 0, -np.sin(y)], [0, 1, 0], [np.sin(y), 0, np.cos(y)]])
    rx = np.array([[1, 0, 0], [0, np.cos(p), np.sin(p)], [0, -np.sin(p), np.cos(p)]])
    rz = np.array([[np.cos(r), -np.sin(r), 0], [np.sin(r), np.cos(r), 0], [0, 0, 1]])
    rot = rz @ rx @ ry
    face = np.zeros((468, 3), np.float32)
    for i, pt in _CANON.items():
        v = np.array(pt, float)
        if i in (14, 17):
            v[1] += mouth_open
        face[i] = rot @ v * size
    face[:, 0] = face[:, 0] / W + at[0]
    face[:, 1] = face[:, 1] / H + at[1]
    face[:, 2] = face[:, 2] / W
    return face


def pose_px(**kw):
    """What the tracker hands the gesture code: the face in pixels."""
    return head_pose.scaled(make_face(**kw), W, H)


def jitter(pts, sigma=0.25):
    return (pts + RNG.normal(0, sigma, pts.shape)).astype(np.float32)


HEAD_A = pose_px(roll=20)
HEAD_B = pose_px(yaw=-25)
HEAD_C = pose_px(pitch=15)
HEAD_REST = pose_px()


def record_head(name, pose, frames=100, gid=None, sigma=0.25):
    rec = cg.Recorder(name, gid, cg.KIND_HEAD)
    for _ in range(frames):
        rec.add(jitter(pose, sigma), None)
        if rec.done:
            break
    return rec


@pytest.fixture
def store(tmp_path):
    return cg.CustomGestureStore(tmp_path / "custom_gestures.json")


def run_matcher(m, frames):
    return [m.update(f, None) for f in frames]


# --- the axes ---------------------------------------------------------------------

@pytest.mark.parametrize("kw, expect", [({}, (0, 0, 0)), ({"yaw": 25}, (25, 0, 0)), ({"yaw": -25}, (-25, 0, 0)),
                                        ({"pitch": 15}, (0, 15, 0)), ({"pitch": -15}, (0, -15, 0)),
                                        ({"roll": 20}, (0, 0, 20)), ({"roll": -20}, (0, 0, -20))])
def test_the_pose_recovers_yaw_pitch_and_roll(kw, expect):
    pose = head_pose.estimate(make_face(**kw), W, H)
    assert pose.yaw == pytest.approx(expect[0], abs=1.5)
    assert pose.pitch == pytest.approx(expect[1], abs=1.5)
    assert pose.roll == pytest.approx(expect[2], abs=1.5)


def test_pose_axes_are_unit_vectors_at_the_nose():
    pose = head_pose.estimate(make_face(yaw=10, pitch=5, roll=5, at=(0.4, 0.6)), W, H)
    assert np.allclose(np.linalg.norm(pose.axes, axis=1), 1.0, atol=1e-4)
    assert pose.frame == (W, H) and pose.size > 0
    assert np.allclose(pose.nose, make_face(yaw=10, pitch=5, roll=5, at=(0.4, 0.6))[1][:2])


def test_a_degenerate_face_has_no_pose():
    assert head_pose.estimate(np.zeros((468, 3), np.float32), W, H) is None


# --- features: position and distance do not matter, the pose does ---------------------

def test_head_features_ignore_position_and_distance():
    base = cg.head_features(HEAD_A)
    far = pose_px(roll=20, at=(0.3, 0.6), size=65.0)               # the same pose, smaller and elsewhere
    assert np.allclose(base, cg.head_features(far), atol=1e-3)
    assert base.shape == (len(head_pose.HEAD_POINTS), 3)
    assert cg.head_features(np.zeros((468, 3), np.float32)) is None
    assert cg.head_features(np.zeros((21, 2), np.float32)) is None   # not a face


def test_different_poses_are_far_apart_and_jitter_is_close():
    fa, fb, fc, fr = (cg.head_features(p) for p in (HEAD_A, HEAD_B, HEAD_C, HEAD_REST))
    lo = cg.PARAMS["head"].lo
    for x, y in ((fa, fb), (fa, fc), (fb, fc), (fa, fr), (fb, fr), (fc, fr)):
        assert cg.distance(x, y)[0] > 2 * lo
    assert cg.distance(fa, cg.head_features(jitter(HEAD_A)))[0] < lo / 2


def test_an_open_mouth_is_a_different_head_pose():
    assert cg.distance(cg.head_features(HEAD_REST), cg.head_features(pose_px(mouth_open=0.2)))[0] > cg.PARAMS["head"].lo


# --- recording ------------------------------------------------------------------------

def test_recording_a_head_pose_collects_samples_and_ignores_moving():
    rec = record_head("Tilt", HEAD_A)
    assert rec.done and len(rec.samples) == cg.SAMPLES and rec.kind == "head" and rec.raw == []
    assert rec.builtin_overlap() is None                            # there are no built-in head signs
    moving = cg.Recorder("M", None, cg.KIND_HEAD)
    for i in range(30):
        moving.add(HEAD_A if i % 2 else HEAD_B, None)               # flips every frame
    assert not moving.samples and moving.hint == "moving"
    assert cg.Recorder("W", None, cg.KIND_HEAD).add(None, None) is False


def test_a_head_recording_does_not_read_a_hand():
    rec = cg.Recorder("H", None, cg.KIND_HEAD)
    for _ in range(20):
        rec.add(POSE_A, "Right")                                    # (21,2) hand points are not a face
    assert not rec.samples


# --- the store -------------------------------------------------------------------------

def test_head_gestures_are_stored_with_their_kind_and_survive_a_restart(store, tmp_path):
    hand = store.add("Fingers", record("Fingers", POSE_A))
    head = store.add("Tilt", record_head("Tilt", HEAD_A))
    assert store.kinds() == {hand: "hand", head: "head"}
    assert [g for g, _t, _s in store.compiled("head")] == [head] and [g for g, _t, _s in store.compiled("hand")] == [hand]
    data = json.loads((tmp_path / "custom_gestures.json").read_text("utf-8"))
    assert data["gestures"][head]["kind"] == "head" and data["gestures"][hand]["kind"] == "hand"
    again = cg.CustomGestureStore(tmp_path / "custom_gestures.json")
    assert again.kinds() == {hand: "hand", head: "head"}
    assert np.asarray(again.gestures[head]["template"]).shape == (len(head_pose.HEAD_POINTS), 3)


def test_old_files_without_a_kind_are_hand_gestures_and_broken_heads_are_dropped(tmp_path):
    p = tmp_path / "c.json"
    s = cg.CustomGestureStore(p)
    gid = s.add("Old", record("Old", POSE_A))
    raw = json.loads(p.read_text("utf-8"))
    del raw["gestures"][gid]["kind"]                                # a file written before head gestures existed
    raw["gestures"]["custom:bad00001"] = {"name": "Bad", "kind": "head", "template": [[0, 0]] * 20, "threshold": 0.1}   # wrong shape
    raw["gestures"]["custom:bad00002"] = {"name": "Bad2", "kind": "leg", "template": [[0, 0]] * 20, "threshold": 0.1}
    p.write_text(json.dumps(raw), "utf-8")
    again = cg.CustomGestureStore(p)
    assert again.kinds() == {gid: "hand"}


def test_hand_and_head_do_not_block_each_other_and_do_not_share_names(store):
    store.add("Alpha", record("Alpha", POSE_A))
    store.add("Beta", record_head("Beta", HEAD_A))                  # a different kind: never "too similar" to the hand pose
    with pytest.raises(ValueError, match="בשם הזה"):
        store.add("alpha", record_head("alpha", HEAD_B))           # but the names are one list
    store.add("Gamma", record_head("Gamma", HEAD_B))
    with pytest.raises(ValueError, match="דומה מדי"):
        store.add("Delta", record_head("Delta", HEAD_A))           # the same head pose twice


def test_different_head_poses_are_not_called_too_similar_even_with_noisy_landmarks(store):
    """Real face points are noisier than the synthetic ones, which widens the learned threshold. Poses that really differ (a tilt, a
    smaller tilt, a nod, a turn) must still all be accepted, one after the other."""
    poses = {"Tilt": HEAD_A, "Half tilt": pose_px(roll=10), "Nod": HEAD_C, "Turn": HEAD_B, "Left tilt": pose_px(roll=-15)}
    for name, pose in poses.items():
        store.add(name, record_head(name, pose, sigma=0.8))
    assert sorted(store.names().values()) == sorted(poses)


def test_retraining_with_the_wrong_kind_is_refused(store):
    head = store.add("Tilt", record_head("Tilt", HEAD_A))
    with pytest.raises(ValueError, match="יד / ראש"):
        store.train(head, record("Tilt", POSE_A, gid=head))
    with pytest.raises(ValueError, match="יד / ראש"):
        store.rerecord(head, record("Tilt", POSE_A, gid=head))
    assert store.train(head, record_head("Tilt", HEAD_A, gid=head)) == 2 * cg.SAMPLES


# --- recognising -----------------------------------------------------------------------

def test_a_head_gesture_is_recognised_after_a_steady_moment_and_released(store):
    gid = store.add("Tilt", record_head("Tilt", HEAD_A))
    m = cg.CustomMatcher(store, cg.KIND_HEAD)
    out = run_matcher(m, [jitter(HEAD_A) for _ in range(cg.DWELL + 4)])
    assert out[: cg.DWELL - 1] == [None] * (cg.DWELL - 1) and out[-1] == gid
    assert run_matcher(m, [jitter(HEAD_REST)] * cg.RELEASE)[-1] is None


def test_other_head_poses_do_not_trigger_it_and_each_gesture_is_told_apart(store):
    a = store.add("Tilt", record_head("Tilt", HEAD_A))
    b = store.add("Turn", record_head("Turn", HEAD_B))
    c = store.add("Nod", record_head("Nod", HEAD_C))
    assert set(run_matcher(cg.CustomMatcher(store, cg.KIND_HEAD), [jitter(HEAD_REST)] * 15)) == {None}
    for pose, gid in ((HEAD_A, a), (HEAD_B, b), (HEAD_C, c)):
        assert run_matcher(cg.CustomMatcher(store, cg.KIND_HEAD), [jitter(pose)] * 12)[-1] == gid


def test_moving_the_whole_head_does_not_break_recognition(store):
    gid = store.add("Tilt", record_head("Tilt", HEAD_A))
    m = cg.CustomMatcher(store, cg.KIND_HEAD)
    frames = [jitter(pose_px(roll=20, at=(0.5 + 0.004 * i, 0.5))) for i in range(12)]   # the head drifts across the picture
    assert run_matcher(m, frames)[-1] == gid


def test_a_head_matcher_never_sees_hand_gestures_and_the_hand_matcher_never_sees_heads(store):
    hand = store.add("Fingers", record("Fingers", POSE_A))
    store.add("Tilt", record_head("Tilt", HEAD_A))
    assert run_matcher(cg.CustomMatcher(store, cg.KIND_HEAD), [jitter(HEAD_A)] * 12)[-1] != hand
    assert run_matcher(cg.CustomMatcher(store), [POSE_A] * 12)[-1] == hand
    assert cg.CustomMatcher(store).update(None) is None            # no hand: nothing, and no crash
    assert cg.CustomMatcher(store, cg.KIND_HEAD).update(None) is None


def test_no_face_means_no_head_gesture(store):
    store.add("Tilt", record_head("Tilt", HEAD_A))
    m = cg.CustomMatcher(store, cg.KIND_HEAD)
    run_matcher(m, [jitter(HEAD_A)] * 12)
    assert m.update(None, None) is None and m.scores == {}


# --- the confidence bar ---------------------------------------------------------------------

def test_confidence_is_half_at_the_recognition_limit_and_full_when_identical():
    assert cg.confidence(0.0, 0.0, 0.1) == pytest.approx(1.0)
    assert cg.confidence(0.1, 0.0, 0.1) == pytest.approx(0.5)                  # exactly on the rms limit
    assert cg.confidence(0.0, 0.1 * cg.PEAK_FACTOR, 0.1) == pytest.approx(0.5)  # exactly on the single-point limit
    assert cg.confidence(0.3, 0.3, 0.1) < 0.1


def test_matcher_scores_say_how_close_each_gesture_is(store):
    a = store.add("Tilt", record_head("Tilt", HEAD_A))
    b = store.add("Turn", record_head("Turn", HEAD_B))
    m = cg.CustomMatcher(store, cg.KIND_HEAD)
    m.update(jitter(HEAD_A), None)
    assert m.scores[a] > 0.5 > m.scores[b]
    m.update(jitter(HEAD_B), None)
    assert m.scores[b] > 0.5 > m.scores[a]
    m.update(jitter(HEAD_REST), None)
    assert max(m.scores.values()) < 0.5                                        # neutral: neither


def test_a_hand_gesture_gets_scores_too(store):
    gid = store.add("Fingers", record("Fingers", POSE_A))
    m = cg.CustomMatcher(store)
    m.update(POSE_A, "Right")
    assert m.scores[gid] > 0.5
    assert cg.CustomMatcher(store).scores == {}


# --- the mouse: a head gesture acts like a hand gesture, whichever hand is the dominant one -------------

def test_a_head_gesture_fires_its_action_even_with_only_the_left_hand_allowed(monkeypatch):
    m, t = make(monkeypatch, control_hand="left", **{"custom:head1": "right_click"})
    run(m, t, [([None, None, "custom:head1"],)] * 3)
    assert m.mouse.clicks == [("right", 1)]


def test_a_hand_gesture_of_the_other_hand_is_still_ignored(monkeypatch):
    m, t = make(monkeypatch, control_hand="left", pinch="left_click")
    run(m, t, [([None, "pinch", None],)] * 3)                      # the right hand while only the left is allowed
    assert m.mouse.clicks == []


def test_a_head_gesture_can_toggle_the_control(monkeypatch):
    m, t = make(monkeypatch, enabled=False, **{"custom:head1": "toggle_control"})
    run(m, t, [([None, None, "custom:head1"],)] * 2)
    assert m.cfg["control_enabled"] is True


def test_clicks_are_noted_for_the_ripples(monkeypatch):
    import numpy as np
    m, t = make(monkeypatch, pinch="left_click", ok="double_click", hang_loose="right_click", rock="middle_click")
    hand = np.full((21, 2), (0.4, 0.6), np.float32)
    for sign, kind in (("pinch", "left"), ("ok", "double"), ("hang_loose", "right"), ("rock", "middle")):
        run(m, t, [([None, sign], [hand], [1])] * 3 + [([None, None], [hand], [1])] * 20)
        when, what, where = m.click_events[-1]
        assert what == kind and where == pytest.approx((0.4, 0.6))
    assert [e[1] for e in m.click_events] == ["left", "double", "right", "middle"]
    assert [e[0] for e in m.click_events] == sorted(e[0] for e in m.click_events)


def test_a_click_without_a_tracked_point_is_not_noted(monkeypatch):
    m, t = make(monkeypatch, pinch="left_click")
    run(m, t, [(["pinch", None],)] * 3)                           # no hand points: nothing to draw a ripple on
    assert m.mouse.clicks and not m.click_events
