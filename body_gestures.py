"""מחוות גוף: קפיצה, התכופפות, רכינה ימינה ושמאלה, ושתי ידיים למעלה. מתוך נקודות הגוף העליון (body_pose.py).

קפיצה היא אירוע, כמו הנהון: הכתפיים עולות מהר מעל הרגיל וחוזרות אליו מהר. עלייה שנשארת למעלה (קימה, ישיבה ישרה) היא לא קפיצה.
שאר המחוות הן תנוחות שמחזיקים (כמו הטיית ראש): מזוהות אחרי שהגוף נשאר בתנוחה כמה רגעים. הרגיל נלמד לאט מהגוף עצמו, כך שישיבה
אחרת או כתפיים לא סימטריות לא נחשבות. כל המדידות ביחס לרוחב הכתפיים, לכן המרחק מהמצלמה לא משנה."""
import math

JUMP, CROUCH = "body_jump", "body_crouch"
LEAN_LEFT, LEAN_RIGHT = "body_lean_left", "body_lean_right"
ARMS_UP = "body_arms_up"

JUMP_START = 0.05    # רוחב כתפיים: עלייה מעל הרגיל שמתחילה את הספירה (רעש מעקב קטן מזה)
JUMP_ENTER = 0.25    # כמה הכתפיים צריכות לעלות, מהר, כדי שזו תיחשב קפיצה בדרך
JUMP_WINDOW = 0.6    # שניות: העלייה חייבת להגיע ל-JUMP_ENTER תוך זה מההתחלה. עלייה איטית (קימה מכיסא) לא נחשבת
JUMP_LAND = 1.0      # שניות: אחרי השיא הכתפיים חייבות לחזור לרגיל תוך זה, אחרת זו הרמה ולא קפיצה
JUMP_SHOW = 0.5      # שניות שהקפיצה מוצגת אחרי שזוהתה
CROUCH_ENTER = 0.20  # כמה הכתפיים צריכות לרדת כדי שתתחיל התכופפות (גם ישיבה שקועה בכיסא)
CROUCH_EXIT = 0.12   # ההתכופפות נגמרת רק כשהירידה חוזרת מתחת לזה (היסטרזיס, כמו ב-head_motion.py)
CROUCH_HOLD = 0.5    # שניות שצריך להחזיק את ההתכופפות לפני שהיא נחשבת
LEAN_ENTER = 7.0     # מעלות מעל הרגיל: הטיית הכתפיים שמתחילה רכינה. לראש הסף הוא 20, כי הראש מטה הרבה יותר מהגוף
LEAN_EXIT = 4.0      # הרכינה נגמרת רק כשההטיה יורדת מתחת לזה
LEAN_HOLD = 0.4      # שניות שצריך להחזיק את הרכינה
ARMS_HOLD = 0.5      # שניות שצריך להחזיק את שתי הידיים מעל האף
BODY_TAU = 6.0       # שניות: קצב ההסתגלות של הרגיל (גובה הכתפיים והטיתן), כמו LEAN_TAU בראש


class _Hold:
    """תנוחה שמחזיקים: מזוהה כשהערך עובר enter ונשאר שם hold שניות, ונגמר כשהוא יורד מתחת ל-exit."""

    def __init__(self, name, enter, exit_, hold):
        self.name, self.enter, self.exit, self.hold = name, enter, exit_, hold
        self.on = False
        self.score = 0.0      # 0.5 = הערך הדרוש, 1 = גם הוחזק מספיק זמן (לתצוגת האבחון)
        self._since = None    # מתי הערך עבר את הסף

    def update(self, value, now):
        """value באותה יחידה כמו enter. מחזיר את שם המחווה כל עוד היא פעילה, אחרת None."""
        if value >= (self.exit if self.on else self.enter):
            if self._since is None:
                self._since = now
            held = now - self._since
            self.score = 0.5 + 0.5 * min(held / self.hold, 1.0)
            self.on = self.on or held >= self.hold
        else:
            self._since, self.on = None, False
            self.score = 0.5 * max(value, 0.0) / self.enter
        return self.name if self.on else None


def _arms_up(pose):
    """שתי הידיים נראות, ושתיהן מעל האף (y קטן יותר = גבוה יותר)."""
    left, right = pose.wrists
    return pose.nose is not None and left is not None and right is not None and left[1] < pose.nose[1] and right[1] < pose.nose[1]


class BodyGestures:
    """מחוות הגוף של הפריים. update מחזיר tuple של המחוות הפעילות עכשיו (אפשר כמה יחד), או None."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._base_y = self._base_roll = self._last = None   # הרגיל: גובה אמצע הכתפיים והטיתן
        self._rise_since = None     # מתי הכתפיים התחילו לעלות מהרגיל
        self._peak = None           # מתי עברו את JUMP_ENTER מהר מספיק: עכשיו מחכים לראות שהן חוזרות לרגיל
        self._spent = False         # העלייה הנוכחית לא תיספר כקפיצה (איטית, או שנשארה למעלה). מתעלמים ממנה עד שהכתפיים יורדות
        self._jump_until = 0.0      # עד מתי מציגים את הקפיצה
        self._crouch = _Hold(CROUCH, CROUCH_ENTER, CROUCH_EXIT, CROUCH_HOLD)
        self._right = _Hold(LEAN_RIGHT, LEAN_ENTER, LEAN_EXIT, LEAN_HOLD)
        self._left = _Hold(LEAN_LEFT, LEAN_ENTER, LEAN_EXIT, LEAN_HOLD)
        self._arms = _Hold(ARMS_UP, 1.0, 1.0, ARMS_HOLD)
        self.scores = {JUMP: 0.0, CROUCH: 0.0, LEAN_LEFT: 0.0, LEAN_RIGHT: 0.0, ARMS_UP: 0.0}

    def update(self, pose, now):
        """פריים אחד. pose = BodyPose או None."""
        if pose is None:
            self.reset()
            return None
        if self._base_y is None:
            self._base_y, self._base_roll, self._last = float(pose.center[1]), pose.roll, now
        rise = (self._base_y - pose.center[1]) / pose.width   # מעלה = חיובי, ביחידות של רוחב הכתפיים
        tilt = pose.roll - self._base_roll
        jump = self._jump(rise, now)
        crouch = self._crouch.update(-rise, now)
        right = self._right.update(tilt, now)
        left = self._left.update(-tilt, now)
        arms = self._arms.update(1.0 if _arms_up(pose) else 0.0, now)
        # הרגיל לא זז בזמן עלייה שנבדקת או תנוחה, אחרת ההסתגלות הייתה מבטלת את המחווה. עלייה שכבר נפסלה לא מקפיאה את הרגיל
        judging = self._rise_since is not None and not self._spent
        if not judging and not (self._crouch.on or self._left.on or self._right.on):
            alpha = 1.0 - math.exp(-(now - self._last) / BODY_TAU)
            self._base_y += alpha * (pose.center[1] - self._base_y)
            self._base_roll += alpha * (pose.roll - self._base_roll)
        self._last = now
        self.scores = {
            JUMP: 1.0 if jump else 0.5 * min(max(rise, 0.0) / JUMP_ENTER, 1.0),
            CROUCH: self._crouch.score, LEAN_LEFT: self._left.score, LEAN_RIGHT: self._right.score, ARMS_UP: self._arms.score,
        }
        active = tuple(g for g in (jump, crouch, left, right, arms) if g)
        return active or None

    def _jump(self, rise, now):
        """קפיצה: הכתפיים עולות מהר מעל הרגיל, ואז חוזרות אליו תוך JUMP_LAND שניות. נספרת פעם אחת, ומוצגת JUMP_SHOW שניות."""
        if rise < JUMP_START:
            if self._peak is not None and now - self._peak <= JUMP_LAND:
                self._jump_until = now + JUMP_SHOW   # חזרו לרגיל בזמן: קפיצה
            self._rise_since = self._peak = None
            self._spent = False
        else:
            if self._rise_since is None:
                self._rise_since = now
            if not self._spent:
                if self._peak is None and now - self._rise_since > JUMP_WINDOW:
                    self._spent = True                     # עלייה איטית, לא קפיצה
                elif self._peak is None and rise >= JUMP_ENTER:
                    self._peak = now                       # מהר מספיק: מחכים לראות אם הן חוזרות
                elif self._peak is not None and now - self._peak > JUMP_LAND:
                    self._peak, self._spent = None, True   # נשארו למעלה: הרמה, לא קפיצה
        return JUMP if now < self._jump_until else None
