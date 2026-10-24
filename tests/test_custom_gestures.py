"""Recording, saving and recognising custom (static) gestures with synthetic landmarks. No camera."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import custom_gestures as cg  # noqa: E402
from signs import classify_hand  # noqa: E402
from test_signs import make_hand  # noqa: E402

# three poses the built-in classifier does NOT know (it returns None), clearly different from each other
POSE_A = make_hand({"ring"}, "out")
POSE_B = make_hand({"middle"}, "out")
POSE_C = make_hand({"middle", "ring"}, "out")
RNG = np.random.default_rng(7)


def jitter(pts, sigma=0.002):
    return (pts + RNG.normal(0, sigma, pts.shape)).astype(np.float32)


def record(name, pose, label="Right", frames=80, gid=None):
    rec = cg.Recorder(name, gid)
    for _ in range(frames):
        rec.add(jitter(pose), label)
        if rec.done:
            break
    return rec


@pytest.fixture
def store(tmp_path):
    return cg.CustomGestureStore(tmp_path / "custom_gestures.json")


def run_matcher(matcher, frames, label="Right"):
    return [matcher.update(f, label) for f in frames]


def test_the_test_poses_are_really_unknown_to_the_builtin_classifier():
    assert classify_hand(POSE_A) is None and classify_hand(POSE_B) is None and classify_hand(POSE_C) is None


def test_features_ignore_position_and_size():
    base = cg.features(POSE_A)
    moved = POSE_A * 0.5 + (0.2, 0.1)
    assert np.allclose(base, cg.features(moved.astype(np.float32)), atol=1e-4)
    assert cg.features(np.zeros((21, 2), np.float32)) is None            # a degenerate hand


def test_a_left_hand_matches_a_gesture_recorded_with_the_right_hand(store):
    gid = store.add("A", record("A", POSE_A, "Right"))
    mirrored = POSE_A.copy()
    mirrored[:, 0] = 1.0 - mirrored[:, 0]
    m = cg.CustomMatcher(store)
    assert run_matcher(m, [jitter(mirrored)] * 10, "Left")[-1] == gid


# --- recording -------------------------------------------------------------

def test_recording_collects_samples_from_a_steady_hand():
    rec = record("A", POSE_A)
    assert rec.done and rec.progress == 1.0 and len(rec.samples) == cg.SAMPLES and rec.hint == "done"


def test_recording_ignores_a_moving_hand_and_waits_for_it_to_settle():
    rec = cg.Recorder("A")
    swing = [POSE_A if i % 2 else POSE_B for i in range(30)]             # flips between two poses every frame
    for f in swing:
        rec.add(f, "Right")
    assert not rec.samples and rec.hint == "moving"
    for _ in range(40):
        rec.add(jitter(POSE_A), "Right")
    assert rec.samples


def test_recording_without_a_hand_waits_and_does_not_mix_two_sessions():
    rec = cg.Recorder("A")
    for _ in range(15):
        rec.add(jitter(POSE_A), "Right")
    assert rec.samples
    for _ in range(cg.LOST_MAX + 2):
        assert rec.add(None) is False
    assert rec.samples == [] and rec.hint == "waiting"


def test_unfinished_recording_cannot_be_saved(store):
    rec = cg.Recorder("A")
    rec.add(jitter(POSE_A), "Right")
    with pytest.raises(ValueError):
        store.add("A", rec)


# --- storing ---------------------------------------------------------------

def test_add_rename_rerecord_delete_and_persist(store, tmp_path):
    a = store.add("Alpha", record("Alpha", POSE_A))
    b = store.add("Beta", record("Beta", POSE_B))
    assert store.names() == {a: "Alpha", b: "Beta"} and cg.is_custom(a)

    store.rename(a, "Alef")
    store.rerecord(b, record("Beta", POSE_C, gid=b))
    again = cg.CustomGestureStore(tmp_path / "custom_gestures.json")     # a fresh start reads the file
    assert again.names() == {a: "Alef", b: "Beta"}
    assert np.allclose(again.gestures[b]["template"], cg.features(POSE_C), atol=0.03)

    store.delete(a)
    assert cg.CustomGestureStore(tmp_path / "custom_gestures.json").names() == {b: "Beta"}


def test_names_are_validated(store):
    store.add("Alpha", record("x", POSE_A))
    for bad in ("", "   ", "x" * 31, "bell\x07name"):
        with pytest.raises(ValueError):
            store.add(bad, record("x", POSE_B))
    with pytest.raises(ValueError):
        store.add("alpha", record("x", POSE_B))                           # same name, any case
    gid = store.add("Beta", record("x", POSE_B))
    with pytest.raises(ValueError):
        store.rename(gid, "ALPHA")
    store.rename(gid, "Beta")                                             # its own name is fine
    assert cg.validate_name("  two   words ") == "two words"


def test_a_pose_that_is_already_builtin_is_refused(store):
    with pytest.raises(ValueError, match="מובנית"):
        store.add("My fist", record("My fist", make_hand(set(), "in")))   # a fist
    with pytest.raises(ValueError, match="מובנית"):
        store.add("V", record("V", make_hand({"index", "middle"}, "in")))
    assert store.names() == {}


def test_a_pose_too_close_to_an_existing_custom_gesture_is_refused(store):
    store.add("Alpha", record("Alpha", POSE_A))
    with pytest.raises(ValueError, match="דומה"):
        store.add("Same again", record("Same again", POSE_A))
    store.add("Different", record("Different", POSE_B))                   # a clearly different pose is fine


def test_a_rerecord_may_overlap_with_itself(store):
    a = store.add("Alpha", record("Alpha", POSE_A))
    store.rerecord(a, record("Alpha", POSE_A, gid=a))


def test_a_damaged_file_is_ignored(tmp_path):
    p = tmp_path / "custom_gestures.json"
    for content in ("not json", "[]", '{"gestures": {"custom:1": {"name": "x", "template": [[1,2]], "threshold": 0.1}}}',
                    '{"gestures": {"evil": {"name": "x", "template": [], "threshold": 1}}}'):
        p.write_text(content, "utf-8")
        assert cg.CustomGestureStore(p).names() == {}
    assert cg.CustomGestureStore(tmp_path / "missing.json").names() == {}


def test_the_file_is_plain_json_beside_the_settings(store, tmp_path):
    store.add("Alpha", record("Alpha", POSE_A))
    data = json.loads((tmp_path / "custom_gestures.json").read_text("utf-8"))
    assert data["version"] == 1 and len(next(iter(data["gestures"].values()))["template"]) == 20


# --- recognising -----------------------------------------------------------

def test_a_recorded_gesture_is_recognised_only_after_a_steady_moment(store):
    gid = store.add("Alpha", record("Alpha", POSE_A))
    out = run_matcher(cg.CustomMatcher(store), [jitter(POSE_A) for _ in range(cg.DWELL + 4)])
    assert out[: cg.DWELL - 1] == [None] * (cg.DWELL - 1)                 # not at the first frames
    assert out[-1] == gid


def test_gestures_are_told_apart(store):
    a = store.add("Alpha", record("Alpha", POSE_A))
    b = store.add("Beta", record("Beta", POSE_B))
    c = store.add("Gamma", record("Gamma", POSE_C))
    for pose, gid in ((POSE_A, a), (POSE_B, b), (POSE_C, c)):
        assert run_matcher(cg.CustomMatcher(store), [jitter(pose)] * 12)[-1] == gid


def test_an_unrelated_pose_matches_nothing(store):
    store.add("Alpha", record("Alpha", POSE_A))
    for other in (POSE_B, make_hand(set(), "in"), make_hand({"index", "middle", "ring", "pinky"}, "out")):
        assert set(run_matcher(cg.CustomMatcher(store), [jitter(other)] * 15)) == {None}


def test_a_transition_between_poses_triggers_nothing_wrong(store):
    a = store.add("Alpha", record("Alpha", POSE_A))
    b = store.add("Beta", record("Beta", POSE_B))
    steps = [POSE_A * (1 - i / 10) + POSE_B * (i / 10) for i in range(1, 10)]
    out = run_matcher(cg.CustomMatcher(store), [jitter(POSE_A)] * 10 + steps + [jitter(POSE_B)] * 10)
    assert out[9] == a                                                    # A was held
    assert set(out[10:19]) <= {a, None}                                   # the way to B never reports B
    assert None in out[10:]                                               # A ended on the way
    assert out[-1] == b                                                   # and B is recognised once it is held


def test_a_short_flicker_does_not_end_a_gesture_but_a_long_loss_does(store):
    a = store.add("Alpha", record("Alpha", POSE_A))
    m = cg.CustomMatcher(store)
    run_matcher(m, [jitter(POSE_A)] * 10)
    assert m.update(None) is None                                         # the hand left the frame: reset
    out = run_matcher(m, [jitter(POSE_A)] * 10)
    assert out[-1] == a
    out = run_matcher(m, [jitter(POSE_B)] * 2 + [jitter(POSE_A)] * 2)     # two odd frames in the middle
    assert out[-1] == a
    assert run_matcher(m, [jitter(POSE_B)] * cg.RELEASE)[-1] is None


def test_deleting_a_gesture_stops_its_recognition_at_once(store):
    a = store.add("Alpha", record("Alpha", POSE_A))
    m = cg.CustomMatcher(store)
    assert run_matcher(m, [jitter(POSE_A)] * 10)[-1] == a
    store.delete(a)
    assert run_matcher(m, [jitter(POSE_A)] * cg.RELEASE + [jitter(POSE_A)] * 3)[-1] is None


def test_two_nearly_identical_gestures_are_not_guessed(store):
    a = store.add("Alpha", record("Alpha", POSE_A))
    twin = dict(store.gestures[a])
    store.gestures = {**store.gestures, "custom:twin0001": {**twin, "name": "Twin"}}   # a hand-edited file
    store.version += 1
    assert set(run_matcher(cg.CustomMatcher(store), [jitter(POSE_A)] * 12)) == {None}
