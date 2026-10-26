"""קשירת מחווה לקיצור מקשים או לתוכנה/סקריפט. הכול עובר ולידציה לפני שמירה ושוב לפני הרצה, ושום דבר לא רץ דרך shell:
תוכנה נפתחת כרשימת ארגומנטים (argv), וקיצור מקשים מורכב רק ממקשים מתוך רשימה סגורה."""
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_HOTKEY_LEN = 40
MAX_PATH_LEN = 520
MAX_ARGS_LEN = 1000
MAX_ARGS = 32

_MODIFIERS = {
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "option": "alt",
    "shift": "shift",
    "win": "cmd", "windows": "cmd", "cmd": "cmd", "command": "cmd", "super": "cmd", "meta": "cmd",
}
_MOD_ORDER = ("ctrl", "alt", "shift", "cmd")
_KEY_ALIASES = {"return": "enter", "escape": "esc", "del": "delete", "ins": "insert", "pgup": "pageup", "pgdn": "pagedown",
                "pagedn": "pagedown", "plus": "+", "spacebar": "space"}
_NAMED_KEYS = {"tab", "enter", "esc", "space", "backspace", "delete", "insert", "home", "end", "pageup", "pagedown",
               "up", "down", "left", "right", "capslock", "printscreen", "volume_up", "volume_down", "volume_mute",
               "play_pause", "next_track", "prev_track"}
_FKEY = re.compile(r"^f([1-9]|1[0-9]|2[0-4])$")


def parse_hotkey(text):
    """"Ctrl+Shift+T" -> ("ctrl", "shift", "t"). Exactly one non-modifier key, at most 4 modifiers, only known key names.
    Raises ValueError (with a message for the user) for anything else."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("הזן קיצור מקשים, למשל Ctrl+C")
    if len(text) > MAX_HOTKEY_LEN:
        raise ValueError("הקיצור ארוך מדי")
    mods, main = [], None
    for raw in text.split("+"):
        tok = raw.strip().lower()
        if not tok:
            raise ValueError("קיצור לא תקין: חסר מקש ליד ה-+")
        tok = _KEY_ALIASES.get(tok, tok)
        if tok in _MODIFIERS:
            m = _MODIFIERS[tok]
            if m in mods:
                raise ValueError(f"המקש {raw.strip()} מופיע פעמיים")
            mods.append(m)
        elif tok in _NAMED_KEYS or _FKEY.match(tok) or (len(tok) == 1 and tok.isprintable() and not tok.isspace()):
            if main is not None:
                raise ValueError("אפשר רק מקש אחד חוץ ממקשי העזר (Ctrl, Alt, Shift, Win)")
            main = tok
        else:
            raise ValueError(f"מקש לא מוכר: {raw.strip()}")
    if main is None:
        raise ValueError("חסר מקש ראשי (למשל C, Tab או F5)")
    return tuple(sorted(mods, key=_MOD_ORDER.index)) + (main,)


def hotkey_text(tokens):
    return "+".join(t.capitalize() if len(t) > 1 else t.upper() for t in tokens)


# שם כל מקש ב-pynput (Key.<שם>). לא כל מקש קיים בכל מערכת (ב-macOS אין Key.insert, למשל), לכן מחפשים רק את המקש שנבחר
_KEY_NAMES = {"tab": "tab", "enter": "enter", "esc": "esc", "space": "space", "backspace": "backspace",
              "delete": "delete", "insert": "insert", "home": "home", "end": "end", "pageup": "page_up",
              "pagedown": "page_down", "up": "up", "down": "down", "left": "left", "right": "right",
              "capslock": "caps_lock", "printscreen": "print_screen", "volume_up": "media_volume_up",
              "volume_down": "media_volume_down", "volume_mute": "media_volume_mute",
              "play_pause": "media_play_pause", "next_track": "media_next", "prev_track": "media_previous"}


def _pynput_key(token):
    from pynput.keyboard import Key

    if token in _MODIFIERS.values():
        return {"ctrl": Key.ctrl, "alt": Key.alt, "shift": Key.shift, "cmd": Key.cmd}[token]
    name = token if _FKEY.match(token) else _KEY_NAMES.get(token)  # f1..f24 כבר עברו ולידציה
    if name is None:
        return token  # תו בודד נשלח כמו שהוא
    key = getattr(Key, name, None)
    if key is None:
        raise ValueError(f"המקש {token} לא זמין במערכת הזו")
    return key


def press_hotkey(keyboard, tokens):
    """לוחץ את מקשי העזר, מקיש את המקש הראשי ומשחרר הכול (גם אם משהו נכשל באמצע). keyboard: pynput Controller או דומה."""
    keys = [_pynput_key(t) for t in tokens]
    held = []
    try:
        for k in keys[:-1]:
            keyboard.press(k)
            held.append(k)
        keyboard.press(keys[-1])
        keyboard.release(keys[-1])
    finally:
        for k in reversed(held):
            keyboard.release(k)


def hold_hotkey(keyboard, tokens):
    """לחיצה ארוכה: לוחץ את כל המקשים ומשאיר אותם לחוצים. מחזיר את רשימת המקשים שנלחצו, לשחרור ב-release_keys.
    אם משהו נכשל באמצע, מה שכבר נלחץ משתחרר, כדי שמקש לא יישאר תקוע."""
    pressed = []
    try:
        for t in tokens:
            k = _pynput_key(t)
            keyboard.press(k)
            pressed.append(k)
    except Exception:
        release_keys(keyboard, pressed)
        raise
    return pressed


def release_keys(keyboard, pressed):
    """משחרר מקשים שנלחצו ב-hold_hotkey, בסדר הפוך. שחרור שנכשל לא עוצר את שחרור השאר."""
    for k in reversed(pressed):
        try:
            keyboard.release(k)
        except Exception:
            pass


# --- תוכנה / סקריפט ---------------------------------------------------------

_ARG = re.compile(r'"([^"]*)"|(\S+)')
_BATCH_UNSAFE = set('&|<>^%!()"\'`')  # cmd.exe מפרש אותם גם בלי shell, לכן אסורים בארגומנטים של .bat / .cmd


def split_args(text):
    """מפצל שורת ארגומנטים: רווחים מפרידים, ומירכאות כפולות שומרות על רווחים בתוך ארגומנט. בלי escape ובלי הרחבות."""
    text = (text or "").strip()
    if text.count('"') % 2:
        raise ValueError("מירכאות לא סגורות בארגומנטים")
    args = [m.group(1) if m.group(1) is not None else m.group(2) for m in _ARG.finditer(text)]
    if len(args) > MAX_ARGS:
        raise ValueError("יותר מדי ארגומנטים")
    return args


def _is_app_bundle(p):
    return sys.platform == "darwin" and p.suffix.lower() == ".app" and p.is_dir()


def parse_script(path, args=""):
    """בודק נתיב וארגומנטים. מחזיר {"path", "args"} מנוקה, או זורק ValueError. הנתיב חייב להיות מוחלט וקיים."""
    path = (path or "").strip()
    if len(path) >= 2 and path[0] == path[-1] == '"':
        path = path[1:-1].strip()
    args = (args or "").strip()
    if not path:
        raise ValueError("בחר קובץ להרצה")
    if len(path) > MAX_PATH_LEN or len(args) > MAX_ARGS_LEN:
        raise ValueError("הנתיב או הארגומנטים ארוכים מדי")
    if any(ord(c) < 32 for c in path + args):
        raise ValueError("תווים לא חוקיים")
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError("יש להזין נתיב מלא")
    if not (p.is_file() or _is_app_bundle(p)):
        raise ValueError("הקובץ לא נמצא")
    if os.name != "nt" and not _is_app_bundle(p) and p.suffix.lower() != ".ps1" and not os.access(p, os.X_OK):
        raise ValueError("הקובץ אינו ניתן להרצה (chmod +x)")
    parsed = split_args(args)
    if p.suffix.lower() in (".bat", ".cmd") and any(_BATCH_UNSAFE & set(a) for a in parsed):
        raise ValueError("בארגומנטים של קובץ .bat / .cmd אסור להשתמש בתווים & | < > ^ % ! ( ) ' `")
    return {"path": str(p), "args": args}


def build_argv(script):
    """הופך קשירה מאומתת לרשימת argv. אף פעם לא מחרוזת לפקודה."""
    p = Path(script["path"])
    args = split_args(script.get("args", ""))
    if _is_app_bundle(p):
        return ["open", "-a", str(p), "--args", *args]
    if p.suffix.lower() == ".ps1":
        return ["powershell" if os.name == "nt" else "pwsh", "-NoProfile", "-File", str(p), *args]
    return [str(p), *args]


def run_script(script, popen=subprocess.Popen):
    """מריץ ברקע בלי לחכות ובלי shell. מאמת מחדש (הקובץ יכול להימחק מאז ההגדרה). popen מוזרק בבדיקות."""
    checked = parse_script(script.get("path", ""), script.get("args", ""))
    argv = build_argv(checked)
    kwargs = dict(shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  cwd=str(Path(checked["path"]).parent), close_fds=True)
    if os.name != "nt":
        kwargs["start_new_session"] = True
    return popen(argv, **kwargs)
