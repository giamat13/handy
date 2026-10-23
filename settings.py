import json
from pathlib import Path

from actions import DEFAULT_BINDINGS

PATH = Path(__file__).resolve().parent / "settings.json"

DEFAULTS = {
    "show_hand_mesh": True,
    "show_face_mesh": True,
    "control_enabled": False,  # העכבר לא זז עד שהמשתמש מדליק (או F8)
    "control_source": "hand",  # "hand" או "head"
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
    PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
