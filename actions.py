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

# מחוות ראש מובנות: תנועה ולא תנוחה (head_motion.py), ולכן אי אפשר להקליט אותן
HEAD_GESTURES = {
    "nod": "הנהון (כן)",
    "shake": "ניעור ראש (לא)",
    "tilt_left": "הטיית ראש שמאלה",
    "tilt_right": "הטיית ראש ימינה",
    "lean_forward": "ראש קדימה (התקרבות)",
    "lean_back": "ראש אחורה (התרחקות)",
    "eye_wink_left": "קריצה בעין שמאל",
    "eye_wink_right": "קריצה בעין ימין",
    "eye_blink_long": "מצמוץ ארוך",
    "face_mouth_open": "פה פתוח",
    "face_smile": "חיוך",
    "face_brows_up": "גבות מורמות",
}

# תנועות יד מובנות (hand_motion.py): החלקה, עיגול ונפנוף של כף יד פתוחה. אירועים, ולכן אי אפשר להקליט אותן
HAND_MOTIONS = {
    "swipe_left": "החלקת יד שמאלה",
    "swipe_right": "החלקת יד ימינה",
    "swipe_up": "החלקת יד למעלה",
    "swipe_down": "החלקת יד למטה",
    "circle_cw": "עיגול עם כיוון השעון",
    "circle_ccw": "עיגול נגד כיוון השעון",
    "wave": "נפנוף",
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
    "nod": "none",
    "shake": "none",
    "tilt_left": "none",
    "tilt_right": "none",
    "lean_forward": "none",
    "lean_back": "none",
    "eye_wink_left": "none",
    "eye_wink_right": "none",
    "eye_blink_long": "none",
    "face_mouth_open": "none",
    "face_smile": "none",
    "face_brows_up": "none",
    "swipe_left": "none",
    "swipe_right": "none",
    "swipe_up": "none",
    "swipe_down": "none",
    "circle_cw": "none",
    "circle_ccw": "none",
    "wave": "none",
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
