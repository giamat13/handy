"""Persist user settings, custom gestures, and gesture bindings to JSON.

Portable EXE  → settings.json next to the EXE
Installed EXE → %APPDATA%\\Handy\\settings.json
Dev (script)  → settings.json next to main.py

Custom gesture templates are stored in a sibling file: gestures.json
"""

import json
import os
import sys
from pathlib import Path

import handy.state as state

# ── Setting keys (scalar values in state) ─────────────────────────────────
_SETTING_KEYS = [
    "SMOOTH", "SPEED", "DYNAMIC_SPEED", "SPEED_CURVE", "CAM_MARGIN",
    "DEADZONE", "MOUSE_ENABLED", "CONTROL_HAND", "CLICK_COOLDOWN",
    "SHOW_TRAIL", "SHOW_COORDS", "SHOW_LANDMARKS",
]


def _base_dir() -> Path:
    if state.IS_INSTALLED:
        base = Path(os.environ.get("APPDATA", Path.home())) / "Handy"
    elif getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parents[1]
    base.mkdir(parents=True, exist_ok=True)
    return base


def _settings_path() -> Path:
    return _base_dir() / "settings.json"


def _gestures_path() -> Path:
    return _base_dir() / "gestures.json"


# ── Load ───────────────────────────────────────────────────────────────────

def load() -> None:
    """Load settings, custom gesture templates, and gesture bindings."""
    _load_settings()
    _load_gestures()


def _load_settings() -> None:
    path = _settings_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in _SETTING_KEYS:
            if key in data:
                setattr(state, key, data[key])
        # Gesture bindings live inside settings.json for convenience
        if "GESTURE_BINDINGS" in data:
            state.GESTURE_BINDINGS = data["GESTURE_BINDINGS"]
        print(f"[SETTINGS] loaded from {path}")
    except Exception as exc:
        print(f"[SETTINGS] load failed: {exc}")


def _load_gestures() -> None:
    """Load custom gesture templates from gestures.json."""
    from handy.custom_gestures import GestureTemplate
    path = _gestures_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        state.CUSTOM_GESTURE_TEMPLATES = [
            GestureTemplate.from_dict(d) for d in data.get("templates", [])
        ]
        print(f"[GESTURES] loaded {len(state.CUSTOM_GESTURE_TEMPLATES)} template(s) from {path}")
    except Exception as exc:
        print(f"[GESTURES] load failed: {exc}")


# ── Save ───────────────────────────────────────────────────────────────────

def save() -> None:
    """Save settings, gesture bindings, and custom gesture templates."""
    _save_settings()
    _save_gestures()


def _save_settings() -> None:
    path = _settings_path()
    try:
        data = {key: getattr(state, key) for key in _SETTING_KEYS}
        data["GESTURE_BINDINGS"] = state.GESTURE_BINDINGS
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[SETTINGS] saved to {path}")
    except Exception as exc:
        print(f"[SETTINGS] save failed: {exc}")


def _save_gestures() -> None:
    path = _gestures_path()
    try:
        data = {"templates": [t.to_dict() for t in state.CUSTOM_GESTURE_TEMPLATES]}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[GESTURES] saved {len(state.CUSTOM_GESTURE_TEMPLATES)} template(s) to {path}")
    except Exception as exc:
        print(f"[GESTURES] save failed: {exc}")
