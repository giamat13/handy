"""ציור רשת היד והפנים מעל הווידאו, עם קווים חלקים (LINE_AA)."""
import cv2
import mediapipe as mp
import numpy as np

# צבעים ב-BGR, צבע לכל אצבע
_FINGER_COLORS = {
    "thumb": (80, 80, 255),
    "index": (60, 200, 255),
    "middle": (90, 230, 120),
    "ring": (255, 190, 60),
    "pinky": (230, 90, 210),
    "palm": (235, 235, 235),
}

_FINGER_OF = {}
for _name, _ids in {
    "thumb": (1, 2, 3, 4),
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}.items():
    for _i in _ids:
        _FINGER_OF[_i] = _name

HAND_CONNECTIONS = sorted((a, b) for a, b in mp.solutions.hands.HAND_CONNECTIONS)
FACE_CONTOURS = sorted((a, b) for a, b in mp.solutions.face_mesh.FACEMESH_CONTOURS)


def _finger(a, b):
    return _FINGER_OF.get(max(a, b), "palm") if (a in _FINGER_OF or b in _FINGER_OF) else "palm"


def draw_hand(img, pts):
    h, w = img.shape[:2]
    p = (pts * (w, h)).astype(np.int32)
    t = max(2, round(w / 320))
    for a, b in HAND_CONNECTIONS:
        col = _FINGER_COLORS[_finger(a, b)]
        cv2.line(img, tuple(p[a]), tuple(p[b]), col, t, cv2.LINE_AA)
    for i, (x, y) in enumerate(p):
        col = _FINGER_COLORS[_FINGER_OF.get(i, "palm")]
        cv2.circle(img, (x, y), t + 2, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(img, (x, y), t + 1, col, -1, cv2.LINE_AA)


def draw_face(img, pts):
    h, w = img.shape[:2]
    p = (pts * (w, h)).astype(np.int32)
    col = (200, 220, 90)
    for a, b in FACE_CONTOURS:
        cv2.line(img, tuple(p[a]), tuple(p[b]), col, 1, cv2.LINE_AA)
    for x, y in p[::2]:
        cv2.circle(img, (x, y), 1, (255, 255, 255), -1, cv2.LINE_AA)
