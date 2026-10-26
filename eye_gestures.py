"""קריצה ומצמוץ ארוך מתוך פתיחות העיניים (EAR: גובה העין חלקי רוחבה, מנקודות העפעפיים).

פתיחות העין שונה מאדם לאדם, ולכן משווים כל עין ל"פתוחה הרגילה" שלה (ממוצע שמסתגל לאט), ולא לערך קבוע.
קריצה מזוהה לפי ההפרש בין שתי העיניים ולא לפי סף מוחלט: כשעין אחת נסגרת, העין השנייה בדרך כלל מצטמצמת קצת גם היא (השרירים
והמעקב), ולכן דורשים שעין אחת תהיה סגורה בבירור וגם סגורה הרבה יותר מהשנייה.
המחוות נשארות מזוהות כל עוד העין סגורה, ולכן אפשר לקשור אליהן לחיצה ארוכה או גרירה, לא רק קליק.
"שמאל" ו"ימין" הם כפי שרואים על המסך (הווידאו הפוך כמו מראה), כמו בשאר מחוות הראש."""
import math

import numpy as np

from tuning import Tuning

WINK_LEFT, WINK_RIGHT, BLINK_LONG = "eye_wink_left", "eye_wink_right", "eye_blink_long"

# לכל עין: (פינה פנימית, פינה חיצונית) ושלושה זוגות (עפעף עליון, עפעף תחתון). קבוצת 33 היא העין שמשמאל במסך
_LEFT_EYE = ((33, 133), ((160, 144), (159, 145), (158, 153)))
_RIGHT_EYE = ((362, 263), ((385, 380), (386, 374), (387, 373)))

WINK_RATIO = 0.7     # עין שפתיחותה מתחת ל-70% מהרגילה היא מועמדת לקריצה (וחוזרת להיות פתוחה רק מעל WINK_EXIT)
WINK_EXIT = 0.8
WINK_GAP = 0.2       # והיא חייבת להיות סגורה יותר מהעין השנייה בלפחות כל כך (מהפתיחות הרגילה); נשארת קריצה עד שההפרש יורד מתחת ל-WINK_GAP_EXIT
WINK_GAP_EXIT = 0.1
BOTH_CLOSED = 0.6    # שתי העיניים מתחת לזה, וקרובות זו לזו (פחות מ-WINK_GAP), = שתיהן סגורות
WINK_MIN = 0.2       # שניות: מצמוץ רגיל נגמר לפני כן
BLINK_LONG_MIN = 0.5  # שניות: שתי העיניים סגורות ברצף. מצמוץ טבעי הוא כ-0.1 עד 0.4
LOOK_DOWN = -20.0    # מעלות: כשמסתכלים למטה העפעפיים יורדים משתי העיניים, ולכן לא מזהים
TURNED = 35.0        # מעלות: כשהראש מופנה מאוד נקודות עין אחת פחות מדויקות
RISE_TAU = 0.5       # שניות: הפתיחות הרגילה עולה מהר כשהעין נפתחת יותר
SETTLE_TAU = 5.0     # ויורדת לאט, כדי שכמעט־עצימת עיניים ממושכת לא תהפוך ל"רגילה"


def openness(face_px):
    """(שמאל, ימין) פתיחות העיניים, או None אם העין מנוונת. face_px = נקודות הפנים בפיקסלים (head_pose.scaled)."""
    out = []
    for (a, b), pairs in (_LEFT_EYE, _RIGHT_EYE):
        width = float(np.linalg.norm(face_px[a][:2] - face_px[b][:2]))
        if width < 1e-3:
            return None
        heights = [float(np.linalg.norm(face_px[u][:2] - face_px[d][:2])) for u, d in pairs]
        out.append(sum(heights) / len(heights) / width)
    return out[0], out[1]


class EyeGestures:
    def __init__(self, tuning=None):
        self.tuning = tuning if tuning is not None else Tuning()
        self.reset()

    def reset(self):
        self._base = [None, None]
        self._wink = [False, False]      # העין מוכרת כקרויצה (עם היסטרזיס)
        self._since = [None, None]       # מאיזה רגע העין מועמדת לקריצה
        self._both = False
        self._both_since = None
        self._tainted = False            # בזמן הסגירה הנוכחית שתי העיניים היו סגורות יחד: זה מצמוץ ולא קריצה
        self._last = None
        self.ratios = (1.0, 1.0)         # פתיחות כל עין מול הרגילה שלה (לכוונון)
        self.scores = {WINK_LEFT: 0.0, WINK_RIGHT: 0.0, BLINK_LONG: 0.0}

    def update(self, face_px, pose, now):
        """פריים אחד. מחזיר WINK_LEFT / WINK_RIGHT / BLINK_LONG כל עוד העין (או שתיהן) סגורה, אחרת None."""
        eyes = openness(face_px) if face_px is not None else None
        if eyes is None or pose is None or pose.pitch < LOOK_DOWN or abs(pose.yaw) > TURNED:
            self.reset()
            return None
        dt = 0.0 if self._last is None else max(now - self._last, 0.0)
        self._last = now
        r = []
        for i, ear in enumerate(eyes):
            base = self._base[i] if self._base[i] is not None else ear
            ratio = ear / base
            if ear > base or ratio > WINK_EXIT:   # עין סגורה או מצומצמת לא מלמדת מה "פתוח"
                base += (ear - base) * (1.0 - math.exp(-dt / (RISE_TAU if ear > base else SETTLE_TAU)))
            self._base[i] = base
            r.append(ear / base)
        self.ratios = (r[0], r[1])

        # שתי העיניים סגורות: שתיהן נמוכות וקרובות זו לזו
        both = max(r) < (WINK_EXIT if self._both else BOTH_CLOSED) and abs(r[0] - r[1]) < WINK_GAP
        self.scores = {WINK_LEFT: 0.0, WINK_RIGHT: 0.0, BLINK_LONG: 0.0}
        if both:
            if not self._both:
                self._both_since = now
            self._both = self._tainted = True
            self._wink, self._since = [False, False], [None, None]
            held = now - self._both_since
            hold = self.tuning.hold_time(BLINK_LONG, BLINK_LONG_MIN)
            self.scores[BLINK_LONG] = 0.5 + 0.5 * min(held / hold, 1.0)
            return BLINK_LONG if held >= hold else None
        self._both, self._both_since = False, None
        if min(r) > WINK_EXIT:
            self._tainted = False

        found = None
        for i, name in ((0, WINK_LEFT), (1, WINK_RIGHT)):
            gap = r[1 - i] - r[i]
            on = self._wink[i]
            cand = r[i] < (WINK_EXIT if on else WINK_RATIO) and gap >= (WINK_GAP_EXIT if on else WINK_GAP)
            if cand and not self._tainted:
                if self._since[i] is None:
                    self._since[i] = now
                held = now - self._since[i]
                wink_min = self.tuning.hold_time(name, WINK_MIN)
                self.scores[name] = 0.5 + 0.5 * min(held / wink_min, 1.0)
                self._wink[i] = held >= wink_min
                if self._wink[i]:
                    found = found or name
            else:
                self._since[i] = None
                self._wink[i] = False
                # התקדמות הסגירה עד שנעשית מועמדת (0 עד 0.5), כדי לראות באבחון שהעין מגיעה לסף
                self.scores[name] = 0.5 * min(max(gap / WINK_GAP, 0.0), 1.0) * min(max((1.0 - r[i]) / (1.0 - WINK_RATIO), 0.0), 1.0)
        return found
