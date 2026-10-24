"""The diagnostics: real rates and timings, the confidence of every built-in sign, and starting with the computer. No camera, no registry."""
import plistlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import autostart  # noqa: E402
import perf  # noqa: E402
from signs import classify_hand, sign_scores  # noqa: E402
from test_signs import make_hand  # noqa: E402


# --- rates and timings ------------------------------------------------------------

class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_the_rate_is_the_real_number_of_events_per_second():
    c = Clock()
    m = perf.RateMeter(window=1.5, clock=c)
    assert m.rate == 0.0
    for _ in range(31):                                           # 30 intervals of 1/30 s
        m.tick()
        c.t += 1 / 30
    assert m.rate == pytest.approx(30.0, rel=0.02)


def test_a_camera_that_gives_15_fps_shows_15_even_when_the_app_could_draw_30():
    c = Clock()
    camera, drawn = perf.RateMeter(clock=c), perf.RateMeter(clock=c)
    for i in range(60):
        if i % 2 == 0:
            camera.tick()
        drawn.tick()
        c.t += 1 / 30
    assert camera.rate == pytest.approx(15.0, rel=0.05) and drawn.rate == pytest.approx(30.0, rel=0.05)


def test_the_rate_falls_to_zero_when_events_stop_and_follows_a_slowdown():
    c = Clock()
    m = perf.RateMeter(window=1.0, clock=c)
    for _ in range(20):
        m.tick()
        c.t += 0.05
    assert m.rate == pytest.approx(20.0, rel=0.05)
    c.t += 5
    assert m.rate == 0.0
    m.tick()
    assert m.rate == 0.0                                          # one event is no rate


def test_the_time_meter_averages_milliseconds_and_works_as_a_context():
    m = perf.TimeMeter(smoothing=0.5)
    assert m.ms == 0.0
    m.add(0.010)
    assert m.ms == pytest.approx(10.0)
    m.add(0.020)
    assert m.ms == pytest.approx(15.0)
    c = Clock()
    timed = perf.TimeMeter(clock=c)
    with timed:
        c.t += 0.004
    assert timed.ms == pytest.approx(4.0)
    timed.add(-1)                                                 # a clock that went backwards must not give a negative time
    assert timed.ms >= 0


# --- confidence of the built-in signs --------------------------------------------------

POSES = {
    "open": make_hand({"index", "middle", "ring", "pinky"}, "out"),
    "fist": make_hand(set(), "in"),
    "point": make_hand({"index"}, "in"),
    "victory": make_hand({"index", "middle"}, "in"),
    "hang_loose": make_hand({"pinky"}, "out"),
    "thumbs_up": make_hand(set(), "up"),
    "thumbs_down": make_hand(set(), "down"),
    "rock": make_hand({"index", "pinky"}, "in"),
    "three": make_hand({"index", "middle", "ring"}, "in"),
    "ok": make_hand({"middle", "ring", "pinky"}, "in", pinch=True),
}


@pytest.mark.parametrize("name", sorted(POSES))
def test_the_recognised_sign_has_a_score_above_half_and_the_others_do_not(name):
    pts = POSES[name]
    assert classify_hand(pts) == name
    s = sign_scores(pts)
    assert s[name] > 0.5
    rivals = {k: v for k, v in s.items() if k != name}
    assert max(rivals.values()) < s[name], (name, rivals)


def test_scores_cover_every_built_in_sign_and_stay_between_0_and_1():
    import actions
    s = sign_scores(POSES["victory"])
    assert set(s) == set(actions.GESTURES)
    assert all(0.0 <= v <= 1.0 for v in s.values())


def test_a_half_made_sign_scores_between_the_two():
    """The point of the bar: a ring finger half way down is neither victory nor three, and the bars show it."""
    victory, three = POSES["victory"].copy(), POSES["three"].copy()
    half = victory.copy()
    half[13:17] = (victory[13:17] + three[13:17]) / 2             # the ring finger half way between folded and extended
    s_v, s_t, s_h = sign_scores(victory), sign_scores(three), sign_scores(half)
    assert s_v["victory"] > s_h["victory"] and s_t["three"] > s_h["three"]
    assert s_h["victory"] > 0.15 and s_h["three"] > 0.15          # it is close to both: that is what the bars should say


def test_pinch_ratio_is_the_distance_between_thumb_and_index():
    from signs import PINCH_LIMIT, pinch_ratio
    assert pinch_ratio(POSES["ok"]) < PINCH_LIMIT < pinch_ratio(POSES["open"])


# --- starting with the computer -----------------------------------------------------------

class FakeRegistry:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def delete(self):
        self.value = None


def test_command_for_the_installed_program_is_the_exe_with_background():
    assert autostart.command(frozen=True, executable=r"C:\Program Files\Handy\Handy2.exe") == [r"C:\Program Files\Handy\Handy2.exe", "--background"]


def test_command_from_source_runs_run_py_with_background(tmp_path):
    (tmp_path / "python.exe").write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    cmd = autostart.command(frozen=False, executable=str(tmp_path / "python.exe"), script="C:/h/run.py", platform="win32")
    assert cmd[0].endswith("pythonw.exe") and cmd[1:] == ["C:/h/run.py", "--background"]      # no console window at logon
    assert autostart.command(frozen=False, executable="/usr/bin/python3", script="/h/run.py", platform="linux") == ["/usr/bin/python3", "/h/run.py", "--background"]


def test_windows_autostart_is_a_run_value_with_a_quoted_command():
    reg = FakeRegistry()
    assert autostart.is_enabled("win32", registry=reg) is False
    autostart.set_enabled(True, "win32", registry=reg, argv=[r"C:\Program Files\Handy\Handy2.exe", "--background"])
    assert reg.value == '"C:\\Program Files\\Handy\\Handy2.exe" --background'                 # spaces in the path are quoted
    assert autostart.is_enabled("win32", registry=reg) is True
    autostart.set_enabled(False, "win32", registry=reg)
    assert reg.value is None and autostart.is_enabled("win32", registry=reg) is False
    autostart.set_enabled(False, "win32", registry=reg)                                        # off twice is fine


def test_linux_autostart_is_a_desktop_file(tmp_path):
    kw = dict(platform="linux", home=tmp_path, env={})
    assert autostart.is_enabled(**kw) is False
    autostart.set_enabled(True, argv=["/opt/my apps/handy", "--background"], **kw)
    f = tmp_path / ".config" / "autostart" / "handy.desktop"
    text = f.read_text("utf-8")
    assert autostart.is_enabled(**kw) and 'Exec="/opt/my apps/handy" --background' in text and "Type=Application" in text
    autostart.set_enabled(False, **kw)
    assert not f.exists() and autostart.is_enabled(**kw) is False
    autostart.set_enabled(False, **kw)


def test_linux_autostart_honours_xdg_config_home(tmp_path):
    autostart.set_enabled(True, platform="linux", home=tmp_path, env={"XDG_CONFIG_HOME": str(tmp_path / "cfg")}, argv=["/x/handy", "--background"])
    assert (tmp_path / "cfg" / "autostart" / "handy.desktop").is_file()


def test_macos_autostart_is_a_launch_agent(tmp_path):
    kw = dict(platform="darwin", home=tmp_path, env={})
    autostart.set_enabled(True, argv=["/Applications/Handy.app/Contents/MacOS/Handy", "--background"], **kw)
    f = tmp_path / "Library" / "LaunchAgents" / "com.handy.app.plist"
    data = plistlib.loads(f.read_bytes())
    assert data["RunAtLoad"] is True and data["ProgramArguments"][-1] == "--background" and autostart.is_enabled(**kw)
    autostart.set_enabled(False, **kw)
    assert not f.exists()


def test_desktop_quoting_protects_special_characters():
    assert autostart._desktop_quote("plain-arg_1") == "plain-arg_1"
    assert autostart._desktop_quote('a "b" $c') == '"a \\"b\\" \\$c"'
    assert autostart._desktop_quote("") == '""'


def test_refresh_rewrites_a_stale_command_but_never_turns_autostart_on(tmp_path):
    kw = dict(platform="linux", home=tmp_path, env={})
    autostart.refresh(argv=["/new/handy", "--background"], **kw)
    assert autostart.is_enabled(**kw) is False                    # it was off: stays off
    autostart.set_enabled(True, argv=["/old/handy", "--background"], **kw)
    autostart.refresh(argv=["/new/handy", "--background"], **kw)
    assert "Exec=/new/handy --background" in (tmp_path / ".config" / "autostart" / "handy.desktop").read_text("utf-8")
    reg = FakeRegistry()
    autostart.refresh(platform="win32", registry=reg, argv=["x"])
    assert reg.value is None
