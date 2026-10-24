"""A flickering gesture must give ONE click, not several; the dominant hand, the on/off gesture and key / script actions
(no camera: the mouse, the keyboard and the launcher are fakes)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mouse_control  # noqa: E402
from actions import DEFAULT_BINDINGS  # noqa: E402

N2 = [None, None]


class FakeMouse:
    def __init__(self):
        self.clicks = []
        self.scrolls = 0
        self.pressed = []
        self.released = []
        self.position = (0, 0)

    def click(self, button, count):
        self.clicks.append((button, count))

    def press(self, button):
        self.pressed.append(button)
        self.clicks.append((button, 1))   # a click is a press: it counts as one click here, and it is let go when the gesture ends

    def release(self, button):
        self.released.append(button)

    def scroll(self, dx, dy):
        self.scrolls += 1


class FakeKeyboard:
    def __init__(self):
        self.log = []

    def press(self, k):
        self.log.append(("down", k))

    def release(self, k):
        self.log.append(("up", k))


def make(monkeypatch, enabled=True, control_hand="both", **bindings):
    t = {"now": 100.0}
    monkeypatch.setattr(mouse_control.time, "perf_counter", lambda: t["now"])
    cfg = {"control_enabled": enabled, "control_source": "hand", "control_hand": control_hand, "sensitivity": 1.0,
           "smoothing": 0.5, "bindings": {**DEFAULT_BINDINGS, **bindings}}
    m = mouse_control.MouseController(cfg, mouse=FakeMouse(), keyboard=FakeKeyboard(), screen=(1000, 800),
                                      launcher=lambda b: m.launched.append(b))
    m.launched = []
    return m, t


def run(m, t, frames, dt=0.04):
    """frames: a list of (signs,) per camera frame, or (signs, hands, labels)."""
    for f in frames:
        signs, *rest = f
        hands, labels = rest if rest else ([], None)
        m.update(hands, None, signs, labels)
        t["now"] += dt


def hand_at(x, y):
    """A hand whose palm center is at (x, y) (all five palm points there)."""
    return np.full((21, 2), (x, y), np.float32)


def test_a_flickering_sign_clicks_once(monkeypatch):
    m, t = make(monkeypatch, pinch="left_click")
    P, N = (["pinch", None],), ([None, None],)
    run(m, t, [P, P, N, P, P, N, N, P, P, P, N, P])        # the sign drops out for a frame or two several times
    assert len(m.mouse.clicks) == 1


def test_two_separate_gestures_click_twice(monkeypatch):
    m, t = make(monkeypatch, pinch="left_click")
    P, N = (["pinch", None],), ([None, None],)
    run(m, t, [P] * 3 + [N] * 25 + [P] * 3)                  # about a second apart
    assert len(m.mouse.clicks) == 2


def test_two_different_gestures_at_once_click_once(monkeypatch):
    m, t = make(monkeypatch, pinch="left_click")
    run(m, t, [(["pinch", "victory"],)] * 3)                 # two left-click gestures together
    assert len(m.mouse.clicks) == 1


def test_scrolling_stops_at_once(monkeypatch):
    m, t = make(monkeypatch)                                 # three fingers -> scroll up by default
    run(m, t, [(["three", None],)] * 5)
    n = m.mouse.scrolls
    run(m, t, [(N2,)] * 5)
    assert n >= 1 and m.mouse.scrolls == n


def test_default_gestures(monkeypatch):
    m, t = make(monkeypatch)
    run(m, t, [(["hang_loose", None],)] * 3)
    assert m.mouse.clicks == [("right", 1)]                  # Hang Loose = right click
    run(m, t, [(N2,)] * 25 + [(["victory", None],)] * 3)
    assert m.mouse.clicks == [("right", 1), ("left", 1)]     # Victory = left click


def test_a_short_gesture_is_a_click_and_a_held_gesture_is_a_long_press(monkeypatch):
    m, t = make(monkeypatch, pinch="left_click")
    P, N = (["pinch", None],), (N2,)
    run(m, t, [P] * 3 + [N] * 25)                                   # a short gesture: pressed, then let go when it ends
    assert m.mouse.pressed == ["left"] and m.mouse.released == ["left"] and m.dragging is None
    run(m, t, [P] * 60)                                             # now the gesture is held for a couple of seconds
    assert m.mouse.pressed == ["left", "left"] and m.mouse.released == ["left"] and m.dragging == "left"   # still pressed: no release yet
    run(m, t, [N] * 12)
    assert m.mouse.released == ["left", "left"] and m.dragging is None


def test_right_and_middle_clicks_hold_the_same_way(monkeypatch):
    m, t = make(monkeypatch, pinch="right_click", fist="middle_click")
    run(m, t, [(["pinch", None],)] * 3 + [(N2,)] * 25 + [(["fist", None],)] * 3 + [(N2,)] * 12)
    assert m.mouse.pressed == ["right", "middle"] and m.mouse.released == ["right", "middle"]


def test_a_double_click_stays_instant(monkeypatch):
    m, t = make(monkeypatch, pinch="double_click")
    run(m, t, [(["pinch", None],)] * 30)
    assert m.mouse.clicks == [("left", 2)] and m.mouse.pressed == []


def test_old_drag_setting_still_holds_left(monkeypatch):
    m, t = make(monkeypatch, pinch="drag")
    run(m, t, [(["pinch", None],)] * 10)
    assert m.dragging == "left"


def test_thumbs_up_no_longer_scrolls(monkeypatch):
    m, t = make(monkeypatch)
    run(m, t, [(["thumbs_up", None],)] * 5)
    assert m.mouse.scrolls == 0


# --- on / off by gesture ---------------------------------------------------

def test_thumbs_up_turns_control_on_and_off(monkeypatch):
    m, t = make(monkeypatch, enabled=False, thumbs_up="toggle_control")
    run(m, t, [(["thumbs_up", None],)] * 4)
    assert m.cfg["control_enabled"] is True
    run(m, t, [(N2,)] * 30 + [(["thumbs_up", None],)] * 4)
    assert m.cfg["control_enabled"] is False


def test_holding_thumbs_up_toggles_only_once(monkeypatch):
    m, t = make(monkeypatch, enabled=False, thumbs_up="toggle_control")
    run(m, t, [(["thumbs_up", None],)] * 80)            # a few seconds of holding it
    assert m.cfg["control_enabled"] is True


def test_other_gestures_do_nothing_while_control_is_off(monkeypatch):
    m, t = make(monkeypatch, enabled=False, thumbs_up="toggle_control")
    run(m, t, [(["hang_loose", None],)] * 4 + [(["three", None],)] * 4)
    assert m.mouse.clicks == [] and m.mouse.scrolls == 0


def test_turning_off_releases_a_drag(monkeypatch):
    m, t = make(monkeypatch, fist="drag", thumbs_up="toggle_control")
    run(m, t, [(["fist", None],)] * 3)
    assert m.dragging == "left"
    run(m, t, [(N2,)] * 10 + [(["thumbs_up", None],)] * 3)
    assert m.dragging is None and m.mouse.released == ["left"]


# --- which hand controls ---------------------------------------------------

def test_right_hand_only_ignores_left_hand_gestures(monkeypatch):
    m, t = make(monkeypatch, control_hand="right")
    run(m, t, [(["hang_loose", None],)] * 3)            # slot 0 = left hand
    assert m.mouse.clicks == []
    run(m, t, [([None, "hang_loose"],)] * 3)            # slot 1 = right hand
    assert m.mouse.clicks == [("right", 1)]


def test_left_hand_only_ignores_right_hand_gestures(monkeypatch):
    m, t = make(monkeypatch, control_hand="left")
    run(m, t, [([None, "victory"],)] * 3)
    assert m.mouse.clicks == []
    run(m, t, [(["victory", None],)] * 3)
    assert m.mouse.clicks == [("left", 1)]


def test_both_hands_work_by_default(monkeypatch):
    m, t = make(monkeypatch)
    run(m, t, [(["victory", None],)] * 3 + [(N2,)] * 25 + [([None, "victory"],)] * 3)
    assert len(m.mouse.clicks) == 2


def test_cursor_follows_only_the_dominant_hand(monkeypatch):
    m, t = make(monkeypatch, control_hand="right")
    left, right = hand_at(0.2, 0.2), hand_at(0.8, 0.6)
    run(m, t, [(N2, [left, right], [0, 1])] * 3)
    assert m.active_slot == 1
    assert np.allclose(m.point, (0.8, 0.6))
    run(m, t, [(N2, [left], [0])] * 3)                 # only the left hand is visible: nothing to follow
    assert m.active_slot is None and m.point is None


def test_with_both_hands_the_cursor_does_not_jump_between_them(monkeypatch):
    m, t = make(monkeypatch)
    left, right = hand_at(0.2, 0.2), hand_at(0.8, 0.6)
    run(m, t, [(N2, [right], [1])] * 3)
    assert m.active_slot == 1
    run(m, t, [(N2, [left, right], [0, 1])] * 3)       # a second hand appears: stay on the first
    assert m.active_slot == 1
    run(m, t, [(N2, [left], [0])] * 3)                 # the first leaves: take the other
    assert m.active_slot == 0


def test_the_point_is_tracked_even_while_control_is_off(monkeypatch):
    m, t = make(monkeypatch, enabled=False, thumbs_up="toggle_control")
    run(m, t, [(N2, [hand_at(0.4, 0.5)], [1])])
    assert np.allclose(m.point, (0.4, 0.5)) and m.mouse.position == (0, 0)   # the cursor itself did not move


# --- keys and scripts ------------------------------------------------------

def test_a_hotkey_binding_presses_the_keys_once(monkeypatch):
    pytest.importorskip("pynput.keyboard")
    from pynput.keyboard import Key
    m, t = make(monkeypatch, fist={"type": "hotkey", "keys": "ctrl+c"})
    run(m, t, [(["fist", None],), (["fist", None],), (N2,), (["fist", None],)])
    assert m._keyboard.log == [("down", Key.ctrl), ("down", "c")]                     # pressed once, and held while the gesture lasts
    run(m, t, [(N2,)] * 12)
    assert m._keyboard.log == [("down", Key.ctrl), ("down", "c"), ("up", "c"), ("up", Key.ctrl)]   # let go when it ends


def test_held_keys_are_let_go_when_the_control_is_switched_off(monkeypatch):
    pytest.importorskip("pynput.keyboard")
    m, t = make(monkeypatch, fist={"type": "hotkey", "keys": "alt+tab"}, thumbs_up="toggle_control")
    run(m, t, [(["fist", None],)] * 3)
    assert len(m._keyboard.log) == 2
    m.release()
    assert len(m._keyboard.log) == 4 and not m.held_keys


def test_an_invalid_hotkey_binding_is_skipped_without_crashing(monkeypatch):
    m, t = make(monkeypatch, fist={"type": "hotkey", "keys": "ctrl+;calc"})
    run(m, t, [(["fist", None],)] * 3)
    assert m._keyboard.log == []


def test_a_script_binding_is_launched_once_per_gesture(monkeypatch):
    binding = {"type": "script", "path": "C:/x/tool.exe", "args": "--go"}
    m, t = make(monkeypatch, rock=binding)
    run(m, t, [(["rock", None],), (N2,), (["rock", None],), (["rock", None],)])
    assert m.launched == [binding]


def test_a_failing_script_does_not_stop_the_tracker(monkeypatch):
    m, t = make(monkeypatch, rock={"type": "script", "path": "C:/x", "args": ""})
    m._launcher = lambda b: (_ for _ in ()).throw(ValueError("gone"))
    run(m, t, [(["rock", None],)] * 3)                   # no exception
    assert m.mouse.clicks == []



def test_the_cursor_glides_in_many_small_steps_so_drawing_is_not_a_polygon(monkeypatch):
    m, t = make(monkeypatch)
    m._glide_thread = object()   # glide mode without a real thread: the test calls glide_step itself
    m.update([hand_at(0.5, 0.45)], None, [None, None], [0])
    m.glide_step(0.008)
    start = m.mouse.position
    m.update([hand_at(0.6, 0.5)], None, [None, None], [0])   # one camera frame later the hand is far away
    seen = []
    for _ in range(60):
        m.glide_step(0.008)
        seen.append(m.mouse.position)
    xs = [p[0] for p in seen]
    assert len(set(seen)) > 25 and xs == sorted(xs) and xs[0] < xs[-1]   # a smooth run, not one jump
    assert max(b[0] - a[0] for a, b in zip([start] + seen, seen)) < 100   # no single big step
    assert abs(seen[-1][0] - m._target[0]) < 5
