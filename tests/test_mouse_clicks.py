"""A flickering gesture must give ONE click, not several (no camera: the mouse is a fake)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mouse_control  # noqa: E402
from actions import DEFAULT_BINDINGS  # noqa: E402


class FakeMouse:
    def __init__(self):
        self.clicks = []
        self.scrolls = 0

    def click(self, button, count):
        self.clicks.append((button, count))

    def scroll(self, dx, dy):
        self.scrolls += 1


def make(monkeypatch, **bindings):
    t = {"now": 100.0}
    monkeypatch.setattr(mouse_control.time, "perf_counter", lambda: t["now"])
    cfg = {"control_enabled": True, "control_source": "hand", "sensitivity": 1.0, "smoothing": 0.5,
           "bindings": {**DEFAULT_BINDINGS, **bindings}}
    m = mouse_control.MouseController(cfg)
    m.mouse = FakeMouse()
    return m, t


def run(m, t, frames, dt=0.04):
    """frames: a list of (signs, wink) per camera frame."""
    for signs, wink in frames:
        m.update([], None, signs, wink)
        t["now"] += dt


def test_a_flickering_sign_clicks_once(monkeypatch):
    m, t = make(monkeypatch, pinch="left_click")
    P, N = (["pinch", None], None), ([None, None], None)
    run(m, t, [P, P, N, P, P, N, N, P, P, P, N, P])        # the sign drops out for a frame or two several times
    assert len(m.mouse.clicks) == 1


def test_a_flickering_wink_clicks_once(monkeypatch):
    m, t = make(monkeypatch)                                 # wink_left -> left click by default
    W, N = ([None, None], "wink_left"), ([None, None], None)
    run(m, t, [W, W, N, W, W, W, N, W])
    assert len(m.mouse.clicks) == 1


def test_two_separate_gestures_click_twice(monkeypatch):
    m, t = make(monkeypatch, pinch="left_click")
    P, N = (["pinch", None], None), ([None, None], None)
    run(m, t, [P] * 3 + [N] * 25 + [P] * 3)                  # about a second apart
    assert len(m.mouse.clicks) == 2


def test_two_different_gestures_at_once_click_once(monkeypatch):
    m, t = make(monkeypatch, pinch="left_click")
    run(m, t, [(["pinch", None], "wink_left")] * 3)          # pinch + wink together
    assert len(m.mouse.clicks) == 1


def test_scrolling_stops_at_once(monkeypatch):
    m, t = make(monkeypatch)                                 # thumbs_up -> scroll up
    run(m, t, [(["thumbs_up", None], None)] * 5)
    n = m.mouse.scrolls
    run(m, t, [([None, None], None)] * 5)
    assert n >= 1 and m.mouse.scrolls == n
