"""שמות בעברית למחוות ולפעולות, וברירות המחדל של המיפוי."""

GESTURES = {
    "pinch": "צביטה",
    "ok": "אוקיי",
    "victory": "ניצחון (V)",
    "hang_loose": "היי (Hang Loose)",
    "thumbs_up": "לייק",
    "thumbs_down": "דיסלייק",
    "fist": "אגרוף",
    "open": "כף פתוחה",
    "point": "הצבעה",
    "three": "שלוש אצבעות",
    "rock": "רוק",
}

# פעולות ישנות שהפכו ללחיצה רגילה: לחיצה שמחזיקים (המחווה) היא לחיצה ארוכה, אז אין להן יותר פעולה נפרדת
LEGACY_ACTIONS = {"drag": "left_click", "hold_right": "right_click", "hold_middle": "middle_click"}

# "peace" ו-"victory" הם אותה תנוחה (V). המזהה הישן נשאר רק כדי להעביר הגדרות שמורות מגרסה 2.0
LEGACY_GESTURES = {"peace": "victory"}

ACTIONS = {
    "none": "ללא",
    "left_click": "קליק שמאלי",
    "right_click": "קליק ימני",
    "double_click": "קליק כפול",
    "middle_click": "קליק אמצעי",
    "scroll_up": "גלילה למעלה",
    "scroll_down": "גלילה למטה",
    "toggle_control": "הפעלה / כיבוי של השליטה בעכבר",
    "hotkey": "קיצור מקשים…",
    "script": "הרצת תוכנה / סקריפט…",
}

# פעולות שהערך שלהן הוא מילון ({"type": "hotkey", "keys": "ctrl+c"}), לא מחרוזת פשוטה
PARAM_ACTIONS = ("hotkey", "script")

# הגלילה עברה מאגודל למעלה/למטה (שמשמש עכשיו להפעלה וכיבוי) לשתי תנוחות מכוונות שלא קורות בטעות
DEFAULT_BINDINGS = {
    "pinch": "none",
    "ok": "double_click",
    "victory": "left_click",
    "hang_loose": "right_click",
    "thumbs_up": "none",
    "thumbs_down": "none",
    "fist": "none",
    "open": "none",
    "point": "none",
    "three": "scroll_up",
    "rock": "scroll_down",
}


def binding_kind(binding):
    """סוג הפעולה של קשירה: מחרוזת פשוטה, או השדה type של מילון."""
    if isinstance(binding, dict):
        return binding.get("type", "none")
    return binding if isinstance(binding, str) else "none"


def binding_text(binding):
    """טקסט קצר להצגה בתפריט המיפוי."""
    kind = binding_kind(binding)
    if kind == "hotkey":
        return f"קיצור: {binding.get('keys', '')}"
    if kind == "script":
        return f"הרצה: {binding.get('path', '')}"
    return ACTIONS.get(kind, ACTIONS["none"])
