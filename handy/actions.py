"""
Action execution: keyboard hotkeys and script / application launching.

Binding format (stored in state.GESTURE_BINDINGS):
    {
        "gesture_name": {
            "type":  "none" | "hotkey" | "script",
            "value": ""     | "ctrl+c" | "/path/to/script.py"
        }
    }

The execute_action() function is designed to be called once per detected
gesture from the camera thread.  A per-gesture cooldown prevents the same
action from firing on every frame.
"""

import subprocess
import threading
import time
from typing import Optional

import handy.state as state


# ── Cooldown ───────────────────────────────────────────────────────────────

TRIGGER_COOLDOWN: float = 1.5    # seconds between repeated triggers of the same gesture

_last_trigger: dict[str, float] = {}
_lock = threading.Lock()


def _can_trigger(name: str) -> bool:
    now = time.time()
    with _lock:
        last = _last_trigger.get(name, 0.0)
        if now - last < TRIGGER_COOLDOWN:
            return False
        _last_trigger[name] = now
    return True


def reset_cooldown(name: str) -> None:
    """Manually reset the cooldown for a gesture (e.g. when its binding changes)."""
    with _lock:
        _last_trigger.pop(name, None)


# ── Public API ─────────────────────────────────────────────────────────────

def execute_action(gesture_name: str) -> None:
    """
    Fire the action bound to *gesture_name* if the cooldown allows.
    Safe to call from any thread.
    """
    binding: Optional[dict] = state.GESTURE_BINDINGS.get(gesture_name)
    if not binding:
        return
    action_type = binding.get("type", "none")
    if action_type == "none":
        return
    if not _can_trigger(gesture_name):
        return

    value = binding.get("value", "").strip()
    if not value:
        return

    if action_type == "hotkey":
        threading.Thread(target=_fire_hotkey, args=(value,), daemon=True).start()
    elif action_type == "script":
        threading.Thread(target=_run_script, args=(value,), daemon=True).start()


# ── Execution helpers ──────────────────────────────────────────────────────

def _fire_hotkey(combo: str) -> None:
    """Press-and-release a key combination such as 'ctrl+c'."""
    try:
        import keyboard          # already in requirements.txt
        keyboard.press_and_release(combo)
        print(f"[ACTION] hotkey fired: {combo}")
    except Exception as exc:
        print(f"[ACTION] hotkey error ({combo}): {exc}")


def _run_script(path: str) -> None:
    """Launch a script or executable in a new process."""
    try:
        subprocess.Popen(path, shell=True)
        print(f"[ACTION] script launched: {path}")
    except Exception as exc:
        print(f"[ACTION] script error ({path}): {exc}")


# ── Validation helpers (used by the UI) ───────────────────────────────────

def validate_hotkey(combo: str) -> tuple[bool, str]:
    """
    Try to validate a hotkey string without actually pressing it.
    Returns (ok, error_message).
    """
    if not combo.strip():
        return False, "Empty shortcut"
    try:
        import keyboard
        parsed = keyboard.parse_hotkey(combo.strip())
        if not parsed:
            return False, "Could not parse shortcut"
        return True, ""
    except Exception as exc:
        return False, str(exc)


def validate_script(path: str) -> tuple[bool, str]:
    """Check whether a script path looks runnable."""
    import os
    p = path.strip()
    if not p:
        return False, "Empty path"
    # Allow shell commands (no path check) and file paths
    if os.path.sep in p or p.startswith("./"):
        if not os.path.exists(p):
            return False, f"File not found: {p}"
    return True, ""
