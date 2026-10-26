"""Where the settings live (per platform, installed / portable), the one-time move from %APPDATA%\\Handy2, and upgrading
settings saved by 2.0.x. Everything happens in temp folders: no camera, no real %APPDATA%."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import settings  # noqa: E402
from actions import BODY_GESTURES, DEFAULT_BINDINGS, GESTURES, HAND_MOTIONS, HEAD_GESTURES  # noqa: E402


def test_installed_windows_uses_appdata_handy(tmp_path):
    exe = tmp_path / "app"
    exe.mkdir()
    d = settings.data_dir(frozen=True, platform="win32", env={"APPDATA": str(tmp_path / "Roaming")}, exe_dir=exe)
    assert d == tmp_path / "Roaming" / "Handy"          # not Handy2


def test_portable_mode_still_uses_the_data_folder_beside_the_exe(tmp_path):
    (tmp_path / "portable.txt").write_text("x")
    d = settings.data_dir(frozen=True, platform="win32", env={"APPDATA": str(tmp_path / "Roaming")}, exe_dir=tmp_path)
    assert d == tmp_path / "data"
    assert settings.legacy_dir(frozen=True, platform="win32", env={"APPDATA": "C:/x"}, exe_dir=tmp_path) is None


def test_other_platforms(tmp_path):
    exe = tmp_path / "app"
    exe.mkdir()
    mac = settings.data_dir(frozen=True, platform="darwin", env={}, home=tmp_path, exe_dir=exe)
    assert mac == tmp_path / "Library" / "Application Support" / "Handy"
    lin = settings.data_dir(frozen=True, platform="linux", env={}, home=tmp_path, exe_dir=exe)
    assert lin == tmp_path / ".config" / "handy"
    xdg = settings.data_dir(frozen=True, platform="linux", env={"XDG_CONFIG_HOME": str(tmp_path / "xdg")}, home=tmp_path, exe_dir=exe)
    assert xdg == tmp_path / "xdg" / "handy"


def test_source_run_keeps_the_code_folder():
    assert settings.data_dir(frozen=False) == ROOT


def test_legacy_dir_only_exists_for_an_installed_windows_app(tmp_path):
    env = {"APPDATA": str(tmp_path)}
    assert settings.legacy_dir(frozen=True, platform="win32", env=env, exe_dir=tmp_path / "e") == tmp_path / "Handy2"
    assert settings.legacy_dir(frozen=False, platform="win32", env=env) is None
    assert settings.legacy_dir(frozen=True, platform="linux", env=env, exe_dir=tmp_path) is None


def test_migration_moves_everything_once(tmp_path):
    old, new = tmp_path / "Handy2", tmp_path / "Handy"
    old.mkdir()
    (old / "settings.json").write_text('{"sensitivity": 2.0}', "utf-8")
    (old / "custom_gestures.json").write_text("{}", "utf-8")
    assert sorted(settings.migrate_legacy(new, old)) == ["custom_gestures.json", "settings.json"]
    assert json.loads((new / "settings.json").read_text("utf-8")) == {"sensitivity": 2.0}
    assert not old.exists()                                    # emptied, so removed
    (tmp_path / "Handy2").mkdir()                              # a second run does nothing, even if the folder is back
    (tmp_path / "Handy2" / "settings.json").write_text("new", "utf-8")
    assert settings.migrate_legacy(new, old) == []
    assert json.loads((new / "settings.json").read_text("utf-8")) == {"sensitivity": 2.0}


def test_migration_never_overwrites_and_never_loses_data(tmp_path):
    old, new = tmp_path / "Handy2", tmp_path / "Handy"
    old.mkdir(), new.mkdir()
    (old / "settings.json").write_text("old", "utf-8")
    (new / "settings.json").write_text("new", "utf-8")
    assert settings.migrate_legacy(new, old) == []
    assert (new / "settings.json").read_text("utf-8") == "new"
    assert (old / "settings.json").read_text("utf-8") == "old"   # stays where it was


def test_migration_without_an_old_folder_is_a_noop(tmp_path):
    assert settings.migrate_legacy(tmp_path / "Handy", tmp_path / "Handy2") == []
    assert settings.migrate_legacy(tmp_path / "Handy", None) == []


def _load_from(monkeypatch, tmp_path, content):
    p = tmp_path / "settings.json"
    if content is not None:
        p.write_text(json.dumps(content), "utf-8")
    monkeypatch.setattr(settings, "PATH", p)
    monkeypatch.setattr(settings, "_migrated", True)
    return settings.load()


def test_defaults_are_safe(monkeypatch, tmp_path):
    cfg = _load_from(monkeypatch, tmp_path, None)
    assert cfg["control_enabled"] is False and cfg["control_hand"] == "both"
    assert cfg["show_trail"] is True and cfg["show_coords"] is True
    assert cfg["bindings"]["hang_loose"] == "right_click" and cfg["bindings"]["victory"] == "left_click"
    assert cfg["bindings"]["thumbs_up"] == "none"
    assert set(DEFAULT_BINDINGS) == set(GESTURES) | set(HEAD_GESTURES) | set(HAND_MOTIONS) | set(BODY_GESTURES)          # every gesture has a default
    assert cfg["bindings"]["body_jump"] == "none" and cfg["bindings"]["body_arms_up"] == "none"
    assert cfg["bindings"]["nod"] == "none" and cfg["bindings"]["shake"] == "none"


def test_a_bad_control_hand_falls_back_to_both(monkeypatch, tmp_path):
    assert _load_from(monkeypatch, tmp_path, {"control_hand": "nose"})["control_hand"] == "both"


def test_settings_from_2_0_are_upgraded(monkeypatch, tmp_path):
    old = {"sensitivity": 1.7, "bindings": {**{k: v for k, v in DEFAULT_BINDINGS.items() if k != "victory"},
                                            "thumbs_up": "scroll_up", "thumbs_down": "scroll_down",
                                            "three": "none", "rock": "none", "peace": "middle_click"}}
    cfg = _load_from(monkeypatch, tmp_path, old)
    b = cfg["bindings"]
    assert cfg["sensitivity"] == 1.7
    assert b["victory"] == "middle_click" and "peace" not in b         # the user's choice for the V sign is kept
    assert b["thumbs_up"] == "none" and b["thumbs_down"] == "none"
    assert b["three"] == "scroll_up" and b["rock"] == "scroll_down"    # scrolling did not disappear


def test_a_customised_scroll_mapping_is_left_alone(monkeypatch, tmp_path):
    old = {"bindings": {"thumbs_up": "scroll_up", "thumbs_down": "left_click"}}
    b = _load_from(monkeypatch, tmp_path, old)["bindings"]
    assert b["thumbs_up"] == "scroll_up" and b["thumbs_down"] == "left_click"


def test_an_upgraded_file_is_not_upgraded_again(monkeypatch, tmp_path):
    cfg = _load_from(monkeypatch, tmp_path, {"settings_version": 2, "bindings": {"thumbs_up": "scroll_up", "thumbs_down": "scroll_down"}})
    assert cfg["bindings"]["thumbs_up"] == "scroll_up"


def test_old_drag_and_long_press_settings_become_plain_clicks(monkeypatch, tmp_path):
    old = {"settings_version": 2, "bindings": {"fist": "drag", "open": "hold_right", "point": "hold_middle", "pinch": "left_click",
                                              "ok": {"type": "hotkey", "keys": "Ctrl+C", "hold": True}}}
    b = _load_from(monkeypatch, tmp_path, old)["bindings"]
    assert (b["fist"], b["open"], b["point"], b["pinch"]) == ("left_click", "right_click", "middle_click", "left_click")
    assert b["ok"] == {"type": "hotkey", "keys": "Ctrl+C"}


def test_hotkey_bindings_survive_a_save_and_load(monkeypatch, tmp_path):
    cfg = _load_from(monkeypatch, tmp_path, None)
    cfg["bindings"]["fist"] = {"type": "hotkey", "keys": "ctrl+c"}
    settings.save(cfg)
    assert settings.load()["bindings"]["fist"] == {"type": "hotkey", "keys": "ctrl+c"}
