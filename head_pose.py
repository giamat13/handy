"""כיוון הראש מנקודות הפנים: שלושה צירים (ימינה, למטה, קדימה) וזוויות yaw / pitch / roll.

MediaPipe נותן x ו-y מנורמלים בנפרד לרוחב ולגובה, ו-z בקנה מידה של x. לכן לפני כל חישוב גיאומטרי ממירים לפיקסלים (scaled)."""
import math
from collections import namedtuple

import numpy as np

# הנקודות שמגדירות תנוחת ראש (אף, עיניים, גבות, פה ומתאר הפנים). מעט נקודות יציבות מקטינות רעש לעומת כל 468
HEAD_POINTS = (1, 6, 168, 98, 327,
               33, 133, 362, 263, 159, 386, 145, 374,
               70, 105, 107, 300, 334, 336,
               61, 291, 13, 14, 0, 17,
               10, 152, 234, 454, 172, 397, 127, 356)
EYE_CORNERS = (33, 133, 362, 263)
_NOSE, _LEFT_CHEEK, _RIGHT_CHEEK, _FOREHEAD, _CHIN = 1, 234, 454, 10, 152

# axes: שלוש שורות (ימינה, למטה, קדימה אל המצלמה), בקואורדינטות פיקסלים. nose: קצה האף מנורמל. size: אורך ציר לציור, בפיקסלים של הפריים.
# frame: (רוחב, גובה). הזוויות במעלות, כפי שרואים על המסך (הווידאו הפוך כמו מראה): yaw חיובי = פונה ימינה, pitch חיובי = למעלה,
# roll חיובי = ההטיה לכיוון הכתף הימנית.
HeadPose = namedtuple("HeadPose", "axes yaw pitch roll nose size frame")


def scaled(face3d, w, h):
    """נקודות הפנים (468,3) מנורמלות -> פיקסלים של הפריים (z בקנה מידה של x)."""
    return np.asarray(face3d, np.float32) * np.array([w, h, w], np.float32)


def estimate(face3d, w, h):
    """HeadPose מנקודות הפנים, או None אם הן מנוונות."""
    p = scaled(face3d, w, h)
    across = p[_RIGHT_CHEEK] - p[_LEFT_CHEEK]
    width = float(np.linalg.norm(across))
    if width < 1e-3:
        return None
    x = across / width
    down = p[_CHIN] - p[_FOREHEAD]
    down = down - x * float(np.dot(down, x))      # אנך לציר הרוחב
    n = float(np.linalg.norm(down))
    if n < 1e-3:
        return None
    y = down / n
    forward = -np.cross(x, y)                      # z קטן = קרוב למצלמה, לכן "קדימה" הוא כלפי z שלילי
    yaw = math.degrees(math.atan2(forward[0], -forward[2]))
    pitch = math.degrees(math.atan2(-forward[1], math.hypot(forward[0], forward[2])))
    roll = math.degrees(math.atan2(x[1], x[0]))
    axes = np.stack([x, y, forward]).astype(np.float32)
    return HeadPose(axes, yaw, pitch, roll, np.asarray(face3d[_NOSE][:2], np.float32), 0.8 * width, (w, h))
