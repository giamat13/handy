import json
import os
import shutil
import sys
from pathlib import Path

from actions import DEFAULT_BINDINGS, LEGACY_ACTIONS, LEGACY_GESTURES

APP_DIR = "Handy"          # תיקיית ההגדרות של הגרסה המותקנת
LEGACY_APP_DIR = "Handy2"  # השם ב-2.0.x: ההגדרות עוברות משם פעם אחת
MIGRATED_MARKER = ".migrated-from-handy2"
SETTINGS_VERSION = 2


def _is_frozen():
    return getattr(sys, "frozen", False)


def _exe_dir():
    return Path(sys.executable).resolve().parent


def is_portable(exe_dir=None):
    return (Path(exe_dir) if exe_dir else _exe_dir()) .joinpath("portable.txt").exists()


def data_dir(frozen=None, platform=None, env=None, home=None, exe_dir=None):
    """From source: next to the code. Installed (PyInstaller / Nuitka): the per-user data folder, because the install folder is
    replaced on every update: %APPDATA%\\Handy (Windows), ~/Library/Application Support/Handy (macOS), ~/.config/handy (Linux).
    Portable (a portable.txt beside the EXE): the "data" folder beside it. The arguments exist for the tests."""
    frozen = _is_frozen() if frozen is None else frozen
    if not frozen:
        return Path(__file__).resolve().parent
    platform = platform or sys.platform
    env = os.environ if env is None else env
    home = Path(home) if home else Path.home()
    exe_dir = Path(exe_dir) if exe_dir else _exe_dir()
    if (exe_dir / "portable.txt").exists():
        return exe_dir / "data"
    if platform == "win32":
        return Path(env.get("APPDATA", str(exe_dir))) / APP_DIR
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR
    return Path(env.get("XDG_CONFIG_HOME") or home / ".config") / APP_DIR.lower()


def legacy_dir(frozen=None, platform=None, env=None, exe_dir=None):
    """The 2.0.x settings folder (%APPDATA%\\Handy2), or None where there never was one (source run, portable, other systems)."""
    frozen = _is_frozen() if frozen is None else frozen
    platform = platform or sys.platform
    env = os.environ if env is None else env
    if not frozen or platform != "win32" or (Path(exe_dir) if exe_dir else _exe_dir()).joinpath("portable.txt").exists():
        return None
    appdata = env.get("APPDATA")
    return Path(appdata) / LEGACY_APP_DIR if appdata else None


def migrate_legacy(new_dir, old_dir):
    """Moves the files of the old settings folder into the new one, once. A file is deleted from the old folder only after the
    copy was read back and is identical; a file the new folder already has is never overwritten. Returns the moved names."""
    new_dir, old_dir = Path(new_dir), Path(old_dir) if old_dir else None
    if old_dir is None or not old_dir.is_dir() or (new_dir / MIGRATED_MARKER).exists():
        return []
    try:
        if old_dir.resolve() == new_dir.resolve():
            return []
    except OSError:
        return []
    moved, failed = [], False
    try:
        new_dir.mkdir(parents=True, exist_ok=True)
        for src in sorted(old_dir.iterdir()):
            if not src.is_file():
                continue
            dst = new_dir / src.name
            if dst.exists():
                continue
            try:
                shutil.copy2(src, dst)
                if dst.read_bytes() != src.read_bytes():
                    dst.unlink()
                    failed = True
                    continue
                src.unlink()
                moved.append(src.name)
            except OSError:
                failed = True
        if not failed:
            (new_dir / MIGRATED_MARKER).write_text("settings moved here from the Handy2 folder\n", encoding="utf-8")
            try:
                old_dir.rmdir()  # only if it is empty now
            except OSError:
                pass
    except OSError:
        pass
    return moved


DIR = data_dir()
PATH = DIR / "settings.json"
CUSTOM_PATH = DIR / "custom_gestures.json"  # the recorded gestures, beside settings.json

DEFAULTS = {
    "settings_version": SETTINGS_VERSION,
    "show_hand_mesh": True,
    "show_face_mesh": True,
    "show_trail": True,        # שובל אחרי הנקודה השולטת
    "show_coords": True,       # קואורדינטות הסמן על הווידאו
    "show_head_axes": True,    # צירי הראש התלת-ממדיים מעל האף, עם הזוויות
    "show_pinch_gauge": True,  # מד המרחק בין האגודל לאצבע
    "show_ripples": True,      # גל שמתרחב בנקודת כל קליק
    "control_enabled": False,  # העכבר לא זז עד שהמשתמש מדליק (או F8)
    "control_source": "hand",  # "hand", "head" או "eyes"
    "gaze_model": None,        # הכיול של המבט (gaze.GazeMap.to_dict), או None עד שמכוילים
    "control_hand": "both",    # "right", "left" או "both": איזו יד שולטת
    "run_in_background": False,  # סגירת החלון משאירה את התוכנה רצה ברקע (מגש המערכת) עם השליטה בעכבר
    "auto_update_check": True,
    "beta_channel": False,     # מצב בודק: מציעים גם גרסאות בטא
    "update_skipped": "",
    "sensitivity": 1.0,
    "smoothing": 0.5,
    "bindings": DEFAULT_BINDINGS,
}

_migrated = False


def _upgrade(saved):
    """Brings settings saved by an older version up to date. Edits `saved` (the raw file content) in place."""
    bindings = saved.get("bindings")
    if not isinstance(bindings, dict):
        saved.pop("bindings", None)
        return
    for old, new in LEGACY_GESTURES.items():  # "peace" became "victory"
        if old in bindings:
            value = bindings.pop(old)
            if value != "none":
                bindings.setdefault(new, value)
    for g in [g for g in bindings if g.startswith("wink_")]:  # קריצות הוסרו מהתוכנה
        bindings.pop(g)
    for g, v in list(bindings.items()):  # גרירה / לחיצה ארוכה נפרדות פסו: לחיצה רגילה שמחזיקים היא לחיצה ארוכה
        if isinstance(v, str) and v in LEGACY_ACTIONS:
            bindings[g] = LEGACY_ACTIONS[v]
        elif isinstance(v, dict) and "hold" in v:
            v.pop("hold")
    if saved.get("settings_version", 1) < 2:
        # 2.0.x scrolled with thumbs up / down. If the user never changed that, move to the new defaults: thumbs up does nothing
        # the control, the scrolling goes to three fingers / rock. A customised mapping is left alone.
        if bindings.get("thumbs_up") == "scroll_up" and bindings.get("thumbs_down") == "scroll_down":
            bindings["thumbs_up"], bindings["thumbs_down"] = "none", "none"
            if bindings.get("three", "none") == "none":
                bindings["three"] = "scroll_up"
            if bindings.get("rock", "none") == "none":
                bindings["rock"] = "scroll_down"
    saved["settings_version"] = SETTINGS_VERSION


def load():
    global _migrated
    if not _migrated:
        _migrated = True
        migrate_legacy(DIR, legacy_dir())
    data = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    try:
        saved = json.loads(PATH.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            raise ValueError("settings.json is not an object")
        _upgrade(saved)
        saved_bindings = saved.pop("bindings", {})
        data.update(saved)
        data["bindings"].update(saved_bindings)
    except (OSError, ValueError):
        pass
    data["control_enabled"] = False  # גם אם F8 או מחווה הדליקו אותה לפני שההגדרות נשמרו: העכבר לא זז עד שמדליקים במכוון
    if data["control_hand"] not in ("right", "left", "both"):
        data["control_hand"] = "both"
    return data


def save(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
