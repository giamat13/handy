"""כוונון מחוות: רגישות (הסף) וזמן החזקה, לכל מחווה לחוד, לפי מה שנשמר בהגדרות (cfg["tuning"]).

בברירת מחדל שני הערכים הם 1, והמחוות עובדות בדיוק כמו קודם. רגישות 2 = הסף חצי מהרגיל (מזהה בקלות יותר), רגישות 0.5 = הסף כפול.
זמן החזקה מוכפל: 2 = צריך להחזיק פי שניים. הערכים נקראים בכל פריים, לכן שינוי בלשונית האבחון נכנס מיד בלי הפעלה מחדש."""
import math

SENS_MIN, SENS_MAX = 0.5, 2.0
HOLD_MIN, HOLD_MAX = 0.5, 2.0
LIMITS = {"sens": (SENS_MIN, SENS_MAX), "hold": (HOLD_MIN, HOLD_MAX)}
# שם וטקסט עזר לכל ערך. הדף מקבל אותם מהשרת, כמו שמות הפעולות
LABELS = {
    "sens": ("רגישות", "גבוה = מזהה בקלות יותר. נמוך = צריך תנועה או תנוחה מדויקת יותר"),
    "hold": ("זמן החזקה", "גבוה = צריך להחזיק יותר זמן עד שהמחווה מזוהה"),
}

# לכל מחווה מכווננת: אילו ערכים חלים עליה. sens = הסף (או גודל התנועה), hold = זמן ההחזקה.
# מחוות יד (סימנים סטטיים, תנועות יד) ומחוות מותאמות לא מופיעות כאן: לכל אחת יש סף משלה שנלמד מההקלטה.
TUNABLE = {
    "nod": ("sens",),
    "shake": ("sens",),
    "tilt_left": ("sens", "hold"),
    "tilt_right": ("sens", "hold"),
    "lean_forward": ("sens", "hold"),
    "lean_back": ("sens", "hold"),
    "eye_wink_left": ("hold",),
    "eye_wink_right": ("hold",),
    "eye_blink_long": ("hold",),
    "face_mouth_open": ("sens", "hold"),
    "face_smile": ("sens", "hold"),
    "face_brows_up": ("sens", "hold"),
    "body_jump": ("sens",),
    "body_crouch": ("sens", "hold"),
    "body_lean_left": ("sens", "hold"),
    "body_lean_right": ("sens", "hold"),
    "body_arms_up": ("hold",),
}


def clean_value(key, value):
    """ערך כוונון שהגיע מהממשק: מספר סופי בטווח של הערך, אחרת ValueError."""
    lo, hi = LIMITS[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError("ערך מחוץ לטווח")
    return float(value)


class Tuning:
    """הכוונון הנוכחי. cfg הוא אותו מילון הגדרות שהתוכנה שומרת, כך ששינוי נכנס לכל הגלאים מיד."""

    def __init__(self, cfg=None):
        self._cfg = cfg if cfg is not None else {}

    def value(self, gid, key):
        """הערך שנשמר למחווה (sens או hold), מתוקן לטווח. 1 אם לא נשמר דבר תקין."""
        table = self._cfg.get("tuning")
        entry = table.get(gid) if isinstance(table, dict) else None
        raw = entry.get(key) if isinstance(entry, dict) else None
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            return 1.0
        lo, hi = LIMITS[key]
        return min(max(float(raw), lo), hi)

    def threshold(self, gid, base):
        """סף של מחווה: הבסיס חלקי הרגישות. למחווה בלי רגישות מחזיר את הבסיס כמו שהוא."""
        if "sens" not in TUNABLE.get(gid, ()):
            return base
        return base / self.value(gid, "sens")

    def hold_time(self, gid, base):
        """זמן החזקה של מחווה, בשניות: הבסיס כפול הכוונון. למחווה בלי זמן החזקה מחזיר את הבסיס."""
        if "hold" not in TUNABLE.get(gid, ()):
            return base
        return base * self.value(gid, "hold")
