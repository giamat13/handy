"""The tray icon logic with a fake pystray: the menu, the state, and the fallback when there is no tray. No window, no camera."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import tray  # noqa: E402


@pytest.fixture(autouse=True)
def windows(monkeypatch):
    """tray.py turns the tray off on macOS on purpose. These tests check the Windows tray, so they run as Windows on every system."""
    monkeypatch.setattr(tray.sys, "platform", "win32")


class FakeItem:
    def __init__(self, text, action, checked=None, default=False):
        self.text, self.action, self.checked, self.default = text, action, checked, default


class FakeMenu:
    def __init__(self, *items):
        self.items = items


class FakeIcon:
    last = None

    def __init__(self, name, image, title, menu):
        self.name, self.image, self.title, self.menu = name, image, title, menu
        self.detached = self.stopped = False
        self.updates = 0
        FakeIcon.last = self

    def run_detached(self):
        self.detached = True

    def update_menu(self):
        self.updates += 1

    def stop(self):
        self.stopped = True


class FakePystray:
    Menu, MenuItem, Icon = FakeMenu, FakeItem, FakeIcon


def make(module=FakePystray):
    calls, state = [], {"on": False}
    t = tray.Tray("img", lambda: calls.append("show"), lambda: calls.append("toggle"), lambda: calls.append("quit"),
                  lambda: state["on"], module=module)
    return t, calls, state


def test_start_shows_an_icon_with_the_three_menu_items():
    t, calls, _ = make()
    assert t.start() and t.visible
    icon = FakeIcon.last
    assert icon.detached and icon.image == "img"
    assert len(icon.menu.items) == 3 and icon.menu.items[0].default        # a click on the icon opens the window
    for item in icon.menu.items:
        item.action(None, item)
    assert calls == ["show", "toggle", "quit"]


def test_the_menu_shows_the_control_state_and_the_title_follows_it():
    t, _, state = make()
    t.start()
    icon = FakeIcon.last
    toggle = icon.menu.items[1]
    assert toggle.checked(toggle) is False
    state["on"] = True
    assert toggle.checked(toggle) is True
    t.refresh()
    assert icon.title == t.title() and icon.updates == 1


def test_start_twice_makes_one_icon_and_stop_removes_it():
    t, _, _ = make()
    t.start()
    first = FakeIcon.last
    assert t.start() and FakeIcon.last is first
    t.stop()
    assert first.stopped and not t.visible
    t.refresh()                                                            # harmless without an icon
    t.stop()


def test_no_pystray_means_no_tray_and_the_caller_falls_back():
    t, _, _ = make()
    t._mod = None
    assert t.start() is False and not t.visible


def test_a_broken_backend_does_not_crash():
    class Broken(FakePystray):
        class Icon(FakeIcon):
            def run_detached(self):
                raise RuntimeError("no display")

    t, _, _ = make(module=Broken)
    assert t.start() is False and not t.visible


def test_macos_has_no_tray(monkeypatch):
    monkeypatch.setattr(tray.sys, "platform", "darwin")
    assert tray.available(FakePystray) is False
    monkeypatch.setattr(tray.sys, "platform", "win32")
    assert tray.available(FakePystray) is True
