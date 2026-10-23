"""The automatic update, against a mock GitHub on localhost: checking, the download and its SHA-256 check, and the journal /
rollback logic for an interrupted update (dry run: no installer is started). No camera, no real network."""
import hashlib
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import updater  # noqa: E402
from version import REPO  # noqa: E402

INSTALLER = b"MZ fake installer bytes" * 1000
DIGEST = hashlib.sha256(INSTALLER).hexdigest()


class Mock(BaseHTTPRequestHandler):
    state = {}

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        s, path = self.state, self.path.split("?", 1)[0].rstrip("/")
        if path == "/dl/Handy2Setup.exe":
            return self._send(200, s.get("file", INSTALLER), "application/octet-stream")
        if s.get("none"):
            return self._send(404, b"{}")
        base = f"http://127.0.0.1:{self.server.server_port}"
        rel = {"tag_name": s["tag"], "body": "## Features\n- something new", "html_url": "https://example.invalid/r", "prerelease": s.get("pre", False),
               "assets": [{"name": "Handy2Setup.exe", "browser_download_url": s.get("url", f"{base}/dl/Handy2Setup.exe"),
                           "size": len(INSTALLER), "digest": s.get("digest", "sha256:" + DIGEST)}]}
        if path.endswith("/releases"):
            return self._send(200, json.dumps([rel]).encode())
        if path.endswith("/releases/latest"):
            return self._send(200, json.dumps(rel).encode())
        self._send(404, b"{}")


@pytest.fixture()
def mock(tmp_path, monkeypatch):
    Mock.state = {"tag": "v2.1.0"}
    srv = HTTPServer(("127.0.0.1", 0), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_port
    monkeypatch.setenv("HANDY_UPDATE_API", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("HANDY_UPDATE_ALLOW_PREFIX", f"http://127.0.0.1:{port}/dl/")
    monkeypatch.setenv("HANDY_UPDATE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    yield Mock.state
    srv.shutdown()


def test_version_order():
    nw = updater.is_newer
    assert nw("2.1.0", "2.0.0") and nw("2.0.1", "2.0.0") and nw("2.10.0", "2.9.0")
    assert not nw("2.0.0", "2.0.0") and not nw("2.0.0", "2.1.0")
    assert nw("2.1.0", "2.1.0-beta.2") and not nw("2.1.0-beta.2", "2.1.0")      # a pre-release is older than its release
    assert nw("2.1.0-beta.2", "2.1.0-beta.1") and nw("2.1.0-beta.1", "2.0.5")
    assert nw("v2.1.0", "2.0.0")
    assert not nw("nonsense", "2.0.0")


def test_check_finds_a_newer_release(mock):
    info = updater.check({})
    assert info["available"] and info["latest"] == "2.1.0" and "something new" in info["notes"]
    assert info["asset"]["sha256"] == DIGEST and updater.can_install(info)


def test_check_same_version_is_not_an_update(mock):
    mock["tag"] = "v2.0.0"
    assert not updater.check({})["available"]


def test_check_with_no_releases_does_not_raise(mock):
    mock["none"] = True
    info = updater.check({})
    assert not info["available"] and "404" in info["error"]


def test_skipped_version_is_marked(mock):
    assert updater.check({"update_skipped": "2.1.0"})["skipped"]
    assert not updater.check({"update_skipped": "2.0.5"})["skipped"]


def test_a_prerelease_is_offered_only_in_tester_mode(mock):
    mock.update(tag="v2.1.0-beta.1", pre=True)
    assert updater.check({"beta_channel": True})["available"]


def test_download_verifies_and_saves(mock):
    got = updater.download(updater.check({}))
    assert Path(got["path"]).read_bytes() == INSTALLER and got["sha256"] == DIGEST


def test_download_with_wrong_checksum_is_deleted(mock):
    mock["digest"] = "sha256:" + "0" * 64
    with pytest.raises(updater.UpdateError, match="SHA-256"):
        updater.download(updater.check({}))
    assert not list(updater.download_dir().glob("Handy2Setup-*"))


def test_download_from_another_host_is_refused(mock):
    mock["url"] = "https://evil.example/Handy2Setup.exe"
    info = updater.check({})
    assert not updater.can_install(info)
    with pytest.raises(updater.UpdateError):
        updater.download(info)


def test_asset_without_checksum_is_never_installed_automatically(mock):
    mock["digest"] = ""
    assert not updater.can_install(updater.check({}))


@pytest.fixture()
def fake_install(tmp_path, monkeypatch, mock):
    app_dir = tmp_path / "app"
    (app_dir / "_internal").mkdir(parents=True)
    exe = app_dir / "Handy2.exe"
    exe.write_bytes(b"old program")
    (app_dir / "_internal" / "lib.dll").write_bytes(b"old lib")
    monkeypatch.setenv("HANDY_UPDATE_DRY_RUN", "1")
    monkeypatch.setenv("HANDY_UPDATE_FAKE_EXE", str(exe))
    got = updater.download(updater.check({}))
    return app_dir, got


def test_launch_saves_a_rollback_copy_and_a_journal(fake_install):
    app_dir, got = fake_install
    res = updater.launch(got["path"])
    d = updater.state_dir()
    assert res["mode"] == "dry-run" and (d / "pending.json").exists()
    assert (d / "rollback" / "app" / "Handy2.exe").read_bytes() == b"old program"
    assert (d / "recover.ps1").exists()


def test_launch_refuses_a_file_that_was_not_downloaded_by_the_updater(fake_install, tmp_path):
    other = tmp_path / "x.exe"
    other.write_bytes(b"x")
    with pytest.raises(updater.UpdateError):
        updater.launch(str(other))


def _age(d, seconds):
    j = json.loads((d / "pending.json").read_text("utf-8"))
    j["started"] = time.time() - seconds
    (d / "pending.json").write_text(json.dumps(j), "utf-8")


def test_reconcile_nothing_pending(mock):
    assert updater.reconcile()["state"] == "none"


def test_reconcile_update_in_progress_is_left_alone(fake_install):
    updater.launch(fake_install[1]["path"])
    assert updater.reconcile()["state"] == "in_progress"


def test_reconcile_failed_but_untouched_needs_no_restore(fake_install):
    updater.launch(fake_install[1]["path"])
    d = updater.state_dir()
    _age(d, updater.STALE_AFTER + 60)
    assert updater.reconcile()["state"] == "failed_intact"
    assert not (d / "pending.json").exists() and updater.pending_notice()["failed"]["restored"] is False


def test_reconcile_half_done_update_is_restored(fake_install):
    app_dir, got = fake_install
    updater.launch(got["path"])
    d = updater.state_dir()
    (app_dir / "Handy2.exe").write_bytes(b"half written")            # the installer got half-way
    _age(d, updater.STALE_AFTER + 60)
    assert updater.reconcile() == {"state": "restoring", "dry_run": True}


def test_reconcile_finished_update_is_reported(fake_install):
    updater.launch(fake_install[1]["path"])
    d = updater.state_dir()
    j = json.loads((d / "pending.json").read_text("utf-8"))
    j["to_version"] = "2.0.0"                                          # this running version is the new one
    (d / "pending.json").write_text(json.dumps(j), "utf-8")
    (d / "done.flag").write_text("2.0.0")
    assert updater.reconcile()["state"] == "updated"
    assert updater.pending_notice()["updated"]["to"] == "2.0.0"
    updater.ack_notice()
    assert updater.pending_notice() == {"updated": None, "failed": None}
