"""נקודות הגוף העליון מ-MediaPipe Pose: אמצע הכתפיים, הרוחב שלהן, הטיית הכתפיים, האף והידיים (body_gestures.py).

MediaPipe נותן x ו-y מנורמלים, לכן מכפילים ברוחב ובגובה הפריים לפני כל חישוב, כמו ב-head_pose.py."""
import math
from collections import namedtuple

import numpy as np

# אינדקסים של MediaPipe Pose. 11 = כתף שמאל של האדם, 12 = כתף ימין (כמו 454 ו-234 בפנים, אותו סימן לרוחב)
NOSE, _L_SHOULDER, _R_SHOULDER, _L_WRIST, _R_WRIST = 0, 11, 12, 15, 16
MIN_VISIBLE = 0.5    # נקודה עם ביטחון נמוך מזה (מחוץ לפריים או מוסתרת) לא נכנסת לחישוב
HAND_POINTS = ((15, 17, 19, 21), (16, 18, 20, 22))   # שורש וכל האצבעות של כף היד השמאלית והימנית של האדם (MediaPipe Pose)

# center: אמצע הכתפיים (פיקסלים). width: המרחק בין הכתפיים (פיקסלים), הסולם לכל המדידות. roll: הזווית של הקו בין הכתפיים, במעלות,
# באותו סימן כמו roll של הראש: חיובי = הטיה לכיוון הכתף הימנית. nose: (x, y) של האף בפיקסלים, או None. wrists: (שמאל, ימין), כל אחד (x, y) או None.
BodyPose = namedtuple("BodyPose", "center width roll nose wrists")


def estimate(points, w, h):
    """points: (33, 3) = (x, y, ביטחון) מנורמלים, כמו שמחזיר MediaPipe Pose. BodyPose, או None אם הכתפיים לא נראות."""
    p = np.asarray(points, np.float32) * np.array([w, h, 1.0], np.float32)
    ls, rs = p[_L_SHOULDER], p[_R_SHOULDER]
    if min(ls[2], rs[2]) < MIN_VISIBLE:
        return None
    across = ls[:2] - rs[:2]
    width = float(np.linalg.norm(across))
    if width < 1e-3:
        return None
    roll = math.degrees(math.atan2(across[1], across[0]))
    center = (ls[:2] + rs[:2]) / 2
    nose = p[NOSE, :2] if p[NOSE, 2] >= MIN_VISIBLE else None
    wrists = tuple(p[i, :2] if p[i, 2] >= MIN_VISIBLE else None for i in (_L_WRIST, _R_WRIST))
    return BodyPose(center, width, roll, nose, wrists)
