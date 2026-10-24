"""The HTML interface: the backend logic, the HTTP server and its security checks, the update service and the window launcher.
Fakes for the tracker, the mouse and the renderer: no camera, no browser, no window."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import actions  # noqa: E402
import custom_gestures as cg  # noqa: E402
import update_service  # noqa: E402
import webui  # noqa: E402
import window  # noqa: E402
from test_custom_gestures import POSE_A, record  # noqa: E402
from test_head_gestures import HEAD_A  # noqa: E402
from test_mouse_clicks import FakeMouse  # noqa: E402


class FakeCamera:
    opened = True


class FakeTracker:
    fps = 29.6
    recorder = None

    def __init__(self):
        self.camera = FakeCamera()


class FakeMouseCtl:
    active_slot = 1

    def __init__(self):
        self.released = 0

    def release(self):
        self.released += 1


class FakeRenderer:
    detect = "ניצחון (V)"

    def __init__(self):
        self.wanted = 0

    def want(self):
        self.wanted += 1

    def wait_frame(self, seq, timeout=1.0):
        return seq + 1, b"\xff\xd8fakejpeg\xff\xd9"


class FakeUpdates:
    def __init__(self):
        self.calls = []

    def snapshot(self):
        return {"status": "idle", "progress": 0, "message": "", "notice": None, "info": None}

    def check(self, manual=True):
        self.calls.append(("check", manual))

    def install(self):
        self.calls.append("install")

    def skip(self):
        self.calls.append("skip")

    def dismiss(self):
        self.calls.append("dismiss")

    def ack(self):
        self.calls.append("ack")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def be(tmp_path):
    from settings import DEFAULTS
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    saved, quit_calls = [], []
    b = webui.Backend(cfg, cg.CustomGestureStore(tmp_path / "c.json"), FakeTracker(), FakeMouseCtl(), FakeRenderer(), FakeUpdates(),
                      save=lambda c: saved.append(json.dumps(c)), quit_cb=lambda: quit_calls.append(1), pick_file=lambda: "C:/x/tool.exe",
                      clock=Clock())
    b.saved, b.quit_calls = saved, quit_calls
    return b


# --- config and state ----------------------------------------------------------

def test_gestures_are_all_hand_gestures_and_there_are_no_winks(be):
    g = be.config()["groups"]
    hand = {r["id"] for r in g["hand"]}
    assert not any(k.startswith("wink") for k in actions.GESTURES)
    assert {r["id"] for r in g["head"]} == set(actions.HEAD_GESTURES) == {"nod", "shake", "tilt_left", "tilt_right", "lean_forward", "lean_back",
                                                                                    "eye_wink_left", "eye_wink_right", "eye_blink_long",
                                                                                    "face_mouth_open", "face_smile", "face_brows_up"}      # built-in head motions, apart from the hand signs
    assert all(r["kind"] == "head" for r in g["head"])
    assert {r["id"] for r in g["motion"]} == set(actions.HAND_MOTIONS) and len(actions.HAND_MOTIONS) == 7      # hand motions have their own group
    assert not set(actions.HAND_MOTIONS) & (hand | set(actions.HEAD_GESTURES))
    assert not set(actions.HEAD_GESTURES) & hand
    assert {"victory", "hang_loose", "thumbs_up", "fist"} <= hand
    assert hand == set(actions.GESTURES)
    assert next(r for r in g["hand"] if r["id"] == "thumbs_up")["text"] == actions.ACTIONS["none"]


def test_custom_gestures_are_listed_under_custom(be):
    gid = be.store.add("Alpha", record("Alpha", POSE_A))
    assert [r["id"] for r in be.config()["groups"]["custom"]] == [gid]
    assert be.names()[gid] == "Alpha"


def test_state_reports_what_the_ui_needs_and_counts_as_a_visit(be):
    st = be.state()
    assert st["fps"] == 29.6 and st["detect"] == "ניצחון (V)" and st["active_hand"] == "right" and st["enabled"] is False
    assert st["recording"] is None and st["update"]["status"] == "idle" and be.ui_open


# --- settings ----------------------------------------------------------------

def test_set_value_validates_and_saves(be):
    be.set_value({"key": "show_trail", "value": True})
    be.set_value({"key": "control_hand", "value": "left"})
    be.set_value({"key": "sensitivity", "value": 2})
    assert be.cfg["show_trail"] is True and be.cfg["control_hand"] == "left" and be.cfg["sensitivity"] == 2.0 and len(be.saved) == 3
    v = be.config_version
    be.set_value({"key": "smoothing", "value": 0.1})
    assert be.config_version == v + 1


@pytest.mark.parametrize("body", [
    {"key": "show_trail", "value": "yes"}, {"key": "control_hand", "value": "nose"}, {"key": "sensitivity", "value": 99},
    {"key": "sensitivity", "value": True}, {"key": "sensitivity", "value": "1"}, {"key": "bindings", "value": {}},
    {"key": "control_enabled", "value": True}, {"key": "update_skipped", "value": "x"}, {"value": 1}, {},
])
def test_set_value_rejects_bad_input(be, body):
    before = json.dumps(be.cfg)
    with pytest.raises(webui.ApiError):
        be.set_value(body)
    assert json.dumps(be.cfg) == before and not be.saved


def test_control_switch(be):
    be.set_control({"enabled": True})
    assert be.cfg["control_enabled"] is True
    be.set_control({"enabled": False})
    assert be.cfg["control_enabled"] is False and be.mouse.released == 1       # turning it off lets go of anything held
    with pytest.raises(webui.ApiError):
        be.set_control({"enabled": "on"})


# --- bindings ----------------------------------------------------------------

def test_simple_binding(be):
    r = be.set_binding({"gesture": "fist", "action": "right_click"})
    assert r["binding"] == "right_click" and be.cfg["bindings"]["fist"] == "right_click" and be.saved


def test_hotkey_binding_is_normalised(be):
    r = be.set_binding({"gesture": "fist", "action": "hotkey", "keys": "shift+ctrl+t"})
    assert r["binding"] == {"type": "hotkey", "keys": "Ctrl+Shift+T"}
    r = be.set_binding({"gesture": "fist", "action": "hotkey", "keys": "ctrl+c", "hold": True})
    assert r["binding"] == {"type": "hotkey", "keys": "Ctrl+C"}            # no separate long-press option any more


def test_there_is_no_separate_long_press_or_drag_action(be):
    ids = {a["id"] for a in be.config()["actions"]}
    assert not ids & {"drag", "hold_right", "hold_middle"} and {"left_click", "right_click", "middle_click"} <= ids
    assert "hold" not in (ROOT / "web" / "app.js").read_text("utf-8").replace("holder", "")


def test_script_binding_is_validated(be, tmp_path):
    exe = tmp_path / ("t.cmd" if sys.platform == "win32" else "t.sh")
    exe.write_text("x")
    exe.chmod(0o755)
    r = be.set_binding({"gesture": "rock", "action": "script", "path": str(exe), "args": "--go"})
    assert r["binding"] == {"type": "script", "path": str(exe), "args": "--go"}
    for bad in ({"path": "relative.exe"}, {"path": str(tmp_path / "nope.exe")}, {"path": ""}):
        with pytest.raises(webui.ApiError):
            be.set_binding({"gesture": "rock", "action": "script", **bad})
    assert be.cfg["bindings"]["rock"]["path"] == str(exe)                   # the failed ones changed nothing


@pytest.mark.parametrize("body", [
    {"gesture": "nope", "action": "left_click"}, {"gesture": "fist", "action": "format_disk"}, {"gesture": "fist"},
    {"gesture": "fist", "action": "hotkey", "keys": "ctrl+;calc"}, {"gesture": "fist", "action": "hotkey"},
])
def test_binding_rejects_bad_input(be, body):
    before = json.dumps(be.cfg["bindings"])
    with pytest.raises(webui.ApiError):
        be.set_binding(body)
    assert json.dumps(be.cfg["bindings"]) == before


def test_a_custom_gesture_can_be_bound_and_its_binding_goes_with_it(be):
    gid = be.store.add("Alpha", record("Alpha", POSE_A))
    be.set_binding({"gesture": gid, "action": "scroll_up"})
    assert be.cfg["bindings"][gid] == "scroll_up"
    be.custom({"op": "delete", "id": gid})
    assert gid not in be.cfg["bindings"] and be.store.names() == {}


# --- recording custom gestures -------------------------------------------------

def finish(be, pose=POSE_A, mode_name=None):
    rec = be.rec
    for _ in range(100):
        rec.add(pose + 0, "Right")
        if rec.done:
            break
    be.tick()


def test_recording_flow(be):
    be.custom({"op": "record", "name": "Alpha", "mode": "new", "kind": "hand"})
    assert be.tracker.recorder is be.rec and be.state()["recording"]["name"] == "Alpha"
    assert be.state()["recording"]["kind"] == "hand"
    with pytest.raises(webui.ApiError):
        be.custom({"op": "record", "name": "Beta", "mode": "new", "kind": "hand"})   # one at a time
    rec = be.rec
    import numpy as np
    for _ in range(100):
        rec.add(POSE_A + np.random.default_rng(1).normal(0, 0.001, POSE_A.shape).astype(np.float32), "Right")
        if rec.done:
            break
    be.tick()
    assert be.rec is None and be.tracker.recorder is None
    assert be.rec_result["ok"] and "Alpha" in be.rec_result["text"] and list(be.store.names().values()) == ["Alpha"]


def test_recording_errors_and_cancel(be):
    for body in ({"op": "record", "name": "", "mode": "new", "kind": "hand"}, {"op": "record", "name": "x", "mode": "wild"},
                 {"op": "record", "mode": "train", "id": "custom:nope"}):
        with pytest.raises(webui.ApiError):
            be.custom(body)
    assert be.rec is None
    be.tracker.camera.opened = False
    with pytest.raises(webui.ApiError, match="מצלמה"):
        be.custom({"op": "record", "name": "x", "mode": "new", "kind": "hand"})
    be.tracker.camera.opened = True
    be.custom({"op": "record", "name": "x", "mode": "new", "kind": "hand"})
    be.custom({"op": "cancel"})
    assert be.rec is None and be.tracker.recorder is None


def test_rename_and_unknown_ops(be):
    gid = be.store.add("Alpha", record("Alpha", POSE_A))
    be.custom({"op": "rename", "id": gid, "name": "Alef"})
    assert be.store.names()[gid] == "Alef"
    with pytest.raises(webui.ApiError):
        be.custom({"op": "rename", "id": gid, "name": ""})
    with pytest.raises(webui.ApiError):
        be.custom({"op": "rename", "id": "custom:nope", "name": "x"})
    with pytest.raises(webui.ApiError):
        be.custom({"op": "explode", "id": gid})


def test_duplicate_name_is_refused_before_recording(be):
    be.store.add("Alpha", record("Alpha", POSE_A))
    with pytest.raises(webui.ApiError, match="בשם הזה"):
        be.custom({"op": "record", "name": "alpha", "mode": "new", "kind": "hand"})


# --- hand or head: asked on every new gesture ---------------------------------------

def test_every_new_gesture_must_say_whether_it_is_for_the_hand_or_the_head(be):
    for kind in (None, "", "leg", 3):
        with pytest.raises(webui.ApiError, match="יד או ראש"):
            be.custom({"op": "record", "name": "Nodder", "mode": "new", "kind": kind})
    with pytest.raises(webui.ApiError, match="יד או ראש"):
        be.custom({"op": "record", "name": "Nodder", "mode": "new"})
    assert be.rec is None and be.tracker.recorder is None


def test_a_head_gesture_is_recorded_listed_and_keeps_its_kind(be):
    be.custom({"op": "record", "name": "Tilt", "mode": "new", "kind": "head"})
    assert be.rec.kind == "head" and be.state()["recording"]["kind"] == "head"
    rec = be.rec
    for _ in range(100):
        rec.add(HEAD_A, None)
        if rec.done:
            break
    be.tick()
    assert be.rec_result["ok"], be.rec_result
    row = be.config()["groups"]["custom"][0]
    assert row["name"] == "Tilt" and row["kind"] == "head"
    gid = row["id"]
    be.custom({"op": "record", "id": gid, "mode": "train"})              # no kind needed: it is the gesture's own
    assert be.rec.kind == "head"
    be.custom({"op": "cancel"})


def test_state_carries_confidence_and_stage_timings(be):
    be.renderer.conf = {"victory": 0.93, "custom:x": 0.1234}
    st = be.state()
    assert st["conf"] == {"victory": 0.93, "custom:x": 0.12}
    assert set(st["perf"]) == {"camera_fps", "tracker_fps", "hands_ms", "face_ms", "logic_ms", "latency_ms", "draw_fps", "draw_ms",
                               "encode_ms", "cursor_hz"}
    assert all(v is None for v in st["perf"].values())                   # the fakes measure nothing: reported as unknown
    from perf import RateMeter, TimeMeter
    be.tracker.rate, be.tracker.hands_ms = RateMeter(), TimeMeter()
    be.tracker.hands_ms.add(0.0123)
    assert be.state()["perf"]["hands_ms"] == 12.3 and be.state()["perf"]["tracker_fps"] == 0.0


# --- start with the computer ---------------------------------------------------------

def test_autostart_is_read_from_and_written_to_the_system(be, monkeypatch):
    state = {"on": False, "calls": []}
    monkeypatch.setattr(webui.autostart, "is_enabled", lambda: state["on"])
    monkeypatch.setattr(webui.autostart, "set_enabled", lambda on: state.update(on=on, calls=state["calls"] + [on]))
    assert be.config()["settings"]["autostart"] is False
    v = be.config_version
    be.set_value({"key": "autostart", "value": True})
    assert state["on"] and be.config()["settings"]["autostart"] is True and be.config_version > v
    assert "autostart" not in be.cfg and not be.saved                     # the system is the truth, not settings.json
    be.set_value({"key": "autostart", "value": False})
    assert state["calls"] == [True, False]
    with pytest.raises(webui.ApiError):
        be.set_value({"key": "autostart", "value": "yes"})


def test_autostart_failure_is_reported_not_raised(be, monkeypatch):
    def boom(on):
        raise PermissionError("denied")
    monkeypatch.setattr(webui.autostart, "set_enabled", boom)
    with pytest.raises(webui.ApiError, match="denied"):
        be.set_value({"key": "autostart", "value": True})


def test_new_display_options_are_settings(be):
    for key in ("show_head_axes", "show_pinch_gauge", "show_ripples"):
        assert be.config()["settings"][key] is True
        be.set_value({"key": key, "value": False})
        assert be.cfg[key] is False


# --- the window going away -----------------------------------------------------

def test_ui_gone_after_bye_but_a_reload_cancels_it(be):
    assert be.ui_gone() is False                                            # never connected: not "gone"
    be.touch()
    be.bye()
    be.clock.t += 1
    assert be.ui_gone() is False                                            # still inside the grace period
    be.touch()                                                              # the page reloaded
    be.clock.t += webui.BYE_GRACE + 1
    assert be.ui_gone() is False
    be.bye()
    be.clock.t += webui.BYE_GRACE + 0.1
    assert be.ui_gone() is True and be.ui_gone() is False                   # reported once


def test_ui_gone_after_a_long_silence(be):
    be.touch()
    be.clock.t += webui.UI_GONE_AFTER + 1
    assert be.ui_gone() is True


def test_quit_calls_back(be):
    be.quit()
    import time
    for _ in range(50):
        if be.quit_calls:
            break
        time.sleep(0.02)
    assert be.quit_calls == [1]


def test_pick_file_and_update_ops(be):
    assert be.pick_file({}) == {"path": "C:/x/tool.exe"}
    be.update({"op": "check"})
    be.update({"op": "install"})
    assert be.updates.calls == [("check", True), "install"]
    with pytest.raises(webui.ApiError):
        be.update({"op": "format"})


# --- HTTP ----------------------------------------------------------------------

@pytest.fixture
def server(be):
    s = webui.Server(be).start()
    yield s
    s.stop()


def call(server, path, body=None, token=True, headers=None, host=None):
    h = {"Host": host or f"127.0.0.1:{server.port}", **(headers or {})}
    if token:
        h["X-Handy-Token"] = server.token
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}{path}", data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def test_the_index_needs_the_token_and_gets_it_embedded(server):
    assert call(server, "/", token=False)[0] == 401
    status, body, headers = call(server, f"/?t={server.token}", token=False)
    assert status == 200 and server.token in body.decode() and "__TOKEN__" not in body.decode()
    assert headers["Content-Type"].startswith("text/html") and headers["Cache-Control"] == "no-store"
    assert call(server, "/?t=wrong", token=False)[0] == 401


def test_static_files_are_served_and_nothing_else(server):
    assert call(server, "/style.css", token=False)[0] == 200
    assert call(server, "/app.js", token=False)[2]["Content-Type"].startswith("text/javascript")
    assert call(server, "/index.html", token=False)[0] == 404                # the page with the token only via "/?t="
    for evil in ("/../settings.py", "/%2e%2e/settings.py", "/..%5csettings.py", "/web/../app.py", "/nothing.js"):
        assert call(server, evil, token=False)[0] == 404, evil


def test_the_app_icon_is_served_for_the_taskbar(server):
    st, body, headers = call(server, "/icon.ico", token=False)
    assert st == 200 and body[:4] == b"\x00\x00\x01\x00" and "icon" in headers["Content-Type"]      # a real ICO file
    st, body, _ = call(server, "/icon.png", token=False)
    assert st == 200 and body[:8] == b"\x89PNG\r\n\x1a\n"
    html = (ROOT / "web" / "index.html").read_text("utf-8")
    assert 'rel="icon"' in html and "icon.ico" in html and 'src="icon.png"' in html
    for name in ("icon.png", "icon.ico"):                                  # web/ keeps copies so it opens from the folder too (make_icon.py)
        assert (ROOT / "web" / name).read_bytes() == (ROOT / name).read_bytes(), name


def test_api_needs_the_token(server):
    assert call(server, "/api/state", token=False)[0] == 401
    assert call(server, "/api/state", headers={"X-Handy-Token": "nope"}, token=False)[0] == 401
    assert call(server, "/api/set", {"key": "run_in_background", "value": True}, token=False)[0] == 401
    assert call(server, "/video", token=False)[0] == 401
    status, body, _ = call(server, "/api/state")
    assert status == 200 and json.loads(body)["fps"] == 29.6


def test_a_foreign_host_header_is_refused(server):
    assert call(server, "/api/state", host="evil.example")[0] == 403
    assert call(server, f"/?t={server.token}", host="evil.example", token=False)[0] == 403
    assert call(server, "/style.css", host="evil.example", token=False)[0] == 403


def test_a_foreign_origin_cannot_post(server):
    st, _, _ = call(server, "/api/set", {"key": "run_in_background", "value": True}, headers={"Origin": "http://evil.example"})
    assert st == 403 and server.backend.cfg["run_in_background"] is False
    st, _, _ = call(server, "/api/set", {"key": "run_in_background", "value": True}, headers={"Origin": f"http://127.0.0.1:{server.port}"})
    assert st == 200 and server.backend.cfg["run_in_background"] is True


def test_http_errors_and_limits(server):
    st, body, _ = call(server, "/api/set", {"key": "sensitivity", "value": 50})
    assert st == 400 and "error" in json.loads(body)
    assert call(server, "/api/nothing", {})[0] == 404
    try:                                                                    # too big: refused (Windows may also just cut the connection)
        assert call(server, "/api/set", {"pad": "x" * (webui.MAX_BODY + 10)})[0] == 413
    except (ConnectionError, urllib.error.URLError):
        pass
    assert server.backend.cfg["run_in_background"] is False
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}/api/set", data=b"[1,2]", headers={"X-Handy-Token": server.token})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 400


def test_config_and_bye_over_http(server):
    st, body, _ = call(server, "/api/config")
    assert st == 200 and json.loads(body)["groups"]["hand"][0]["id"] == "pinch"
    assert call(server, "/api/bye", {})[0] == 200 and server.backend._bye_at is not None


def test_the_video_stream_sends_multipart_jpeg(server):
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}/video?t={server.token}")
    with urllib.request.urlopen(req, timeout=5) as r:
        assert "multipart/x-mixed-replace" in r.headers["Content-Type"]
        chunk = r.read(120)
    assert b"image/jpeg" in chunk and server.backend.renderer.wanted >= 1


def test_the_server_listens_on_localhost_only(server):
    assert server.server_address[0] == "127.0.0.1"


# --- the web files ---------------------------------------------------------------

def test_the_page_is_separate_files_and_uses_relative_paths():
    html = (ROOT / "web" / "index.html").read_text("utf-8")
    assert 'href="style.css"' in html and 'src="app.js"' in html           # not "/style.css": it must open from a file too
    js = (ROOT / "web" / "app.js").read_text("utf-8")
    assert "__TOKEN__" in html and "<style" not in html                       # the CSS lives in its own file
    assert ".innerHTML" not in js and "insertAdjacentHTML" not in js and "eval(" not in js   # text from the server is only ever shown as text
    for tab in ("hand", "mine", "settings", "diag", "updates"):
        assert f'id="tab-{tab}"' in html and f'data-tab="{tab}"' in html
    assert 'id="rows-hand"' in html and "eye-left" not in html                              # no winks
    # hand and head gestures are separate things: each kind has its own recording card and its own list, both in the "my gestures" tab
    mine = html.split('id="tab-mine"', 1)[1].split('id="tab-settings"', 1)[0]
    assert 'id="rows-hand"' not in mine and 'id="rows-hand"' in html.split('id="tab-mine"', 1)[0]   # the built-in signs stay in their own tab
    for kind in ("hand", "head"):
        assert all(f'id="{p}-{kind}"' in mine for p in ("rows-custom", "rec-name", "rec-start", "rec-cancel", "rec-bar", "rec-msg"))
        for part in ("rows-custom", "rec-name", "rec-start", "rec-cancel", "rec-bar", "rec-msg"):
            assert f'id="{part}-{kind}"' in html, (part, kind)


# --- the update service --------------------------------------------------------

class FakeUpdater:
    CHECK_EVERY = 100
    class BlockedError(Exception):
        pass

    def __init__(self, info=None, **kw):
        self.info = info or {"error": None, "available": True, "skipped": False, "latest": "9.9.9", "prerelease": False,
                             "notes": "n", "page": "https://example.com/r"}
        self.kw = kw
        self.launched = []

    def reconcile(self):
        return {"state": self.kw.get("state", "clean")}

    def pending_notice(self):
        return {"updated": self.kw.get("updated"), "failed": self.kw.get("failed")}

    def ack_notice(self):
        pass

    def check(self, cfg):
        return self.info

    def can_install(self, info):
        return self.kw.get("can_install", True)

    def download(self, info, progress):
        progress(5, 10)
        return {"path": "p"}

    def launch(self, path):
        self.launched.append(path)
        return {"mode": self.kw.get("mode", "installing")}


def wait_for(cond):
    import time
    for _ in range(100):
        if cond():
            return True
        time.sleep(0.02)
    return False


def make_service(**kw):
    quits = []
    u = FakeUpdater(**kw)
    s = update_service.UpdateService({"auto_update_check": True, "update_skipped": ""}, lambda c: None, lambda: quits.append(1), updater_mod=u,
                                     clock=Clock())
    return s, u, quits


def test_startup_stops_when_the_app_is_being_restored_and_reports_notices():
    assert make_service(state="restoring")[0].startup() is False
    s, *_ = make_service(updated={"to": "2.1.0"})
    assert s.startup() and "2.1.0" in s.notice["text"]
    s.ack()
    assert s.notice is None
    s, *_ = make_service(failed={"restored": True})
    s.startup()
    assert s.notice["kind"] == "failed" and "שוחזרה" in s.notice["text"]


def test_a_manual_check_finds_an_update_and_install_quits_the_app():
    s, u, quits = make_service()
    s.check(manual=True)
    assert wait_for(lambda: s.status == "available") and s.snapshot()["info"]["latest"] == "9.9.9"
    s.install()
    assert wait_for(lambda: quits) and u.launched == ["p"] and s.status == "installing"


def test_an_automatic_check_stays_quiet_unless_there_is_something_new():
    s, u, _ = make_service(info={"error": "offline", "available": False, "skipped": False})
    s.check(manual=False)
    assert wait_for(lambda: s.status == "idle") and s.snapshot()["message"] == ""
    s.check(manual=True)
    assert wait_for(lambda: s.status == "error")
    s2, *_ = make_service(info={"error": None, "available": True, "skipped": True, "latest": "9", "prerelease": False, "notes": "", "page": "https://x"})
    s2.check(manual=False)
    assert wait_for(lambda: s2.status == "idle") and s2.info is None         # a skipped version is not offered again


def test_a_portable_or_blocked_install_falls_back_to_the_release_page():
    s, *_ = make_service(mode="page")
    s.check(manual=True)
    wait_for(lambda: s.status == "available")
    s.install()
    assert wait_for(lambda: s.status == "page")
    s, *_ = make_service(can_install=False)
    s.check(manual=True)
    wait_for(lambda: s.status == "available")
    s.install()
    assert s.status == "page"


def test_skip_remembers_the_version():
    s, *_ = make_service()
    s.check(manual=True)
    wait_for(lambda: s.status == "available")
    s.skip()
    assert s.cfg["update_skipped"] == "9.9.9" and s.status == "idle"


# --- the window launcher -------------------------------------------------------

def test_the_window_runs_in_a_child_process_of_the_same_program():
    assert window.command("http://x/", frozen=True, executable="Handy2.exe") == ["Handy2.exe", "--window", "http://x/"]
    src = window.command("http://x/", frozen=False, executable="py")
    assert src[0] == "py" and src[1].endswith("run.py") and src[2:] == ["--window", "http://x/"]


def test_the_window_opens_without_a_shell_and_without_a_browser_profile():
    seen = {}
    ok = window.open_window("http://127.0.0.1:1/?t=x", popen=lambda argv, **kw: seen.update(argv=argv, kw=kw), frozen=True, executable="H.exe")
    assert ok and seen["argv"] == ["H.exe", "--window", "http://127.0.0.1:1/?t=x"] and seen["kw"]["shell"] is False


def test_if_the_child_cannot_start_the_default_browser_is_used(monkeypatch):
    opened = []
    monkeypatch.setattr(window.webbrowser, "open", lambda u: opened.append(u))

    def boom(*a, **k):
        raise OSError

    assert window.open_window("http://127.0.0.1:1/", popen=boom) is False and opened == ["http://127.0.0.1:1/"]


def test_without_pywebview_the_default_browser_is_used(monkeypatch):
    opened = []
    monkeypatch.setitem(sys.modules, "webview", None)   # import webview -> ImportError
    monkeypatch.setattr(window.webbrowser, "open", lambda u: opened.append(u))
    window.show("http://127.0.0.1:1/")
    assert opened == ["http://127.0.0.1:1/"]
