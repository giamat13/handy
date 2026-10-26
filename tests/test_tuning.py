"""Gesture tuning (tuning.py): the threshold and the hold time of each gesture, the detectors that use them, the saved settings and
the web API. Synthetic inputs only: no camera, no mediapipe."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tuning  # noqa: E402
import webui  # noqa: E402
from body_gestures import CROUCH, JUMP, BodyGestures  # noqa: E402
from face_expressions import SMILE, SMILE_ENTER, SMILE_EXIT, SMILE_HOLD, _Trigger  # noqa: E402
from head_motion import TILT_RIGHT, HeadTilt  # noqa: E402
from test_body_gestures import body, run  # noqa: E402
from test_webui import be  # noqa: E402,F401  (the Backend fixture)
from test_settings import _load_from  # noqa: E402

DT = 1 / 30


def cfg_with(gid, **values):
    return {"tuning": {gid: values}}


# --- the numbers ---------------------------------------------------------------------------

def test_without_a_setting_nothing_changes():
    t = tuning.Tuning({})
    assert t.threshold(CROUCH, 0.2) == 0.2
    assert t.hold_time(CROUCH, 0.5) == 0.5
    assert tuning.Tuning().threshold(TILT_RIGHT, 20.0) == 20.0


def test_sensitivity_divides_the_threshold_and_hold_multiplies_the_time():
    t = tuning.Tuning(cfg_with(CROUCH, sens=2.0, hold=0.5))
    assert t.threshold(CROUCH, 0.2) == pytest.approx(0.1)
    assert t.hold_time(CROUCH, 0.5) == pytest.approx(0.25)


@pytest.mark.parametrize("raw", [True, "2", None, float("nan"), float("inf"), [1]])
def test_a_bad_stored_value_means_the_default(raw):
    assert tuning.Tuning(cfg_with(CROUCH, sens=raw)).threshold(CROUCH, 0.2) == 0.2


def test_stored_values_are_clamped_to_the_limits():
    assert tuning.Tuning(cfg_with(CROUCH, sens=9.0)).value(CROUCH, "sens") == 2.0
    assert tuning.Tuning(cfg_with(CROUCH, sens=0.01)).value(CROUCH, "sens") == 0.5
    assert tuning.Tuning(cfg_with(CROUCH, hold=0.0)).value(CROUCH, "hold") == 0.5


def test_a_broken_table_means_the_defaults():
    assert tuning.Tuning({"tuning": [1, 2]}).threshold(CROUCH, 0.2) == 0.2
    assert tuning.Tuning({"tuning": {CROUCH: 3}}).hold_time(CROUCH, 0.5) == 0.5


def test_a_gesture_ignores_the_values_it_does_not_have():
    t = tuning.Tuning(cfg_with("body_arms_up", sens=2.0, hold=2.0))   # arms up is a yes / no pose: only its hold applies
    assert t.threshold("body_arms_up", 1.0) == 1.0
    assert t.hold_time("body_arms_up", 0.5) == 1.0
    assert tuning.Tuning(cfg_with("nod", hold=2.0)).hold_time("nod", 0.5) == 0.5   # nod has no hold time


def test_clean_value_takes_only_numbers_in_range():
    assert tuning.clean_value("sens", 1) == 1.0
    for bad in (True, "1", 0.4, 2.1, float("nan"), None):
        with pytest.raises(ValueError):
            tuning.clean_value("sens", bad)


# --- the detectors use them ----------------------------------------------------------------

def first_on(det, name, angle, seconds=3.0):
    """The time at which the gesture turns on while the head is held at this roll angle, or None."""
    for i in range(int(seconds / DT)):
        if det.update(SimpleNamespace(roll=angle), i * DT) == name:
            return i * DT
    return None


def test_a_higher_sensitivity_turns_a_tilt_on_at_a_smaller_angle():
    assert first_on(HeadTilt(), TILT_RIGHT, 12.0) is None                              # 12 degrees is under the default 20
    on = first_on(HeadTilt(tuning.Tuning(cfg_with(TILT_RIGHT, sens=2.0))), TILT_RIGHT, 12.0)   # now the limit is 10
    assert on is not None and 0.45 <= on <= 0.6                                         # and the default hold, 0.5 s


def test_a_longer_hold_turns_a_tilt_on_later():
    default = first_on(HeadTilt(), TILT_RIGHT, 25.0)
    longer = first_on(HeadTilt(tuning.Tuning(cfg_with(TILT_RIGHT, hold=2.0))), TILT_RIGHT, 25.0)
    assert 0.45 <= default <= 0.6
    assert 0.95 <= longer <= 1.1


def test_a_smaller_crouch_counts_with_a_higher_sensitivity():
    shallow = [body()] * 30 + [body(cy=240 + 0.15 * 120)] * 90           # the shoulders drop 0.15 of their width: under 0.2
    plain = run(BodyGestures(), shallow)
    assert all(not (s and CROUCH in s) for s in plain)
    eager = run(BodyGestures(tuning.Tuning(cfg_with(CROUCH, sens=2.0))), shallow)   # now the limit is 0.1
    assert any(s and CROUCH in s for s in eager)


def test_a_longer_hold_makes_a_crouch_count_later():
    deep = [body()] * 30 + [body(cy=240 + 0.3 * 120)] * 90              # a deep crouch: far over the threshold
    def first_crouch(tun):
        out = run(BodyGestures(tun), deep)
        return next(i for i, s in enumerate(out) if s and CROUCH in s)
    assert 44 <= first_crouch(None) <= 47                              # the default hold, 0.5 s, from frame 30
    assert 59 <= first_crouch(tuning.Tuning(cfg_with(CROUCH, hold=2.0))) <= 62   # twice as long: 1 s


def jump_frames(width):
    """The shoulders go up `width` widths in 0.3 s, stay up 1/3 s, and come back down."""
    rise = [body(cy=240 - width * 120 * min(i / 9, 1)) for i in range(20)]
    return [body()] * 30 + rise + [body(cy=240 - width * 120)] * 10 + [body()] * 60


def test_a_jump_needs_a_higher_rise_when_sensitivity_is_lower():
    assert any(s and JUMP in s for s in run(BodyGestures(), jump_frames(0.4)))                 # 0.4 widths: over the default 0.25
    strict = tuning.Tuning(cfg_with(JUMP, sens=0.5))                                             # the limit doubles to 0.5 widths
    assert not any(s and JUMP in s for s in run(BodyGestures(strict), jump_frames(0.4)))


def test_the_smile_trigger_follows_the_sensitivity():
    easy = _Trigger(SMILE, SMILE_ENTER, SMILE_EXIT, SMILE_HOLD, tuning.Tuning(cfg_with(SMILE, sens=2.0)))
    plain = _Trigger(SMILE, SMILE_ENTER, SMILE_EXIT, SMILE_HOLD, tuning.Tuning())
    for i in range(30):
        easy.update(0.07, i * DT)
        plain.update(0.07, i * DT)
    assert easy.on and not plain.on


# --- saved settings and the web API --------------------------------------------------------

def test_a_broken_tuning_table_in_the_settings_file_is_reset(monkeypatch, tmp_path):
    assert _load_from(monkeypatch, tmp_path, {"tuning": [1, 2]})["tuning"] == {}


def test_the_page_is_told_what_each_gesture_can_tune(be):
    t = be.config()["tuning"]
    assert t["params"]["nod"] == ["sens"]
    assert t["params"]["body_arms_up"] == ["hold"]
    assert t["limits"]["sens"] == [0.5, 2.0] and t["limits"]["hold"] == [0.5, 2.0]
    assert t["values"] == {}


def test_a_tuning_is_saved_for_a_tunable_gesture(be):
    assert be.set_tuning({"gesture": CROUCH, "sens": 1.5, "hold": 0.75}) == {"ok": True, "values": {"sens": 1.5, "hold": 0.75}}
    assert be.cfg["tuning"][CROUCH] == {"sens": 1.5, "hold": 0.75}
    assert be.saved, "the settings file is written"


def test_a_partial_change_keeps_the_other_value(be):
    be.set_tuning({"gesture": CROUCH, "sens": 1.5, "hold": 0.75})
    be.set_tuning({"gesture": CROUCH, "hold": 1.25})
    assert be.cfg["tuning"][CROUCH] == {"sens": 1.5, "hold": 1.25}


def test_a_value_the_gesture_does_not_have_is_not_stored(be):
    assert be.set_tuning({"gesture": "body_arms_up", "sens": 1.5})["values"] == {}


def test_untunable_gestures_are_refused(be):
    for gid in ("pinch", "swipe_left", "body_nothing", None, ["nod"]):
        with pytest.raises(webui.ApiError):
            be.set_tuning({"gesture": gid, "sens": 1.5})


@pytest.mark.parametrize("bad", [0.1, 3.0, True, "1", None])
def test_out_of_range_values_are_refused(be, bad):
    with pytest.raises(webui.ApiError):
        be.set_tuning({"gesture": CROUCH, "sens": bad})
    assert CROUCH not in be.cfg["tuning"]
