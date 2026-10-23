import json
import os
import sys
from pathlib import Path

from actions import DEFAULT_BINDINGS

def _data_dir():
    """From source: next to the code. Installed (PyInstaller): %APPDATA%\\Handy2, because the install folder is replaced on
    every update. Portable (a portable.txt beside the EXE): the "data" folder beside it."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "portable.txt").exists():
            return exe_dir / "data"
        return Path(os.environ.get("APPDATA", str(exe_dir))) / "Handy2"
    return Path(__file__).resolve().parent


PATH = _data_dir() / "settings.json"

DEFAULTS = {
    "show_hand_mesh": True,
    "show_face_mesh": True,
    "control_enabled": False,  # העכבר לא זז עד שהמשתמש מדליק (או F8)
    "control_source": "hand",  # "hand" או "head"
    "auto_update_check": True,
    "beta_channel": False,     # מצב בודק: מציעים גם גרסאות בטא
    "update_skipped": "",
    "sensitivity": 1.0,
    "smoothing": 0.5,
    "bindings": DEFAULT_BINDINGS,
}


def load():
    data = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    try:
        saved = json.loads(PATH.read_text(encoding="utf-8"))
        saved_bindings = saved.pop("bindings", {})
        data.update(saved)
        data["bindings"].update(saved_bindings)
    except (OSError, ValueError):
        pass
    return data


def save(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
