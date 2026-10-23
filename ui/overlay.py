"""Draws the hand skeleton and face landmarks over a preview frame."""
import cv2

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
]

# BGR colors
PALM_COLOR = (235, 235, 235)
FINGER_COLORS = {
    "thumb": (60, 150, 255),
    "index": (255, 190, 60),
    "middle": (120, 220, 120),
    "ring": (200, 120, 255),
    "pinky": (255, 120, 120),
}
FACE_COLOR = (210, 200, 90)
JOINT_RING = (255, 255, 255)

SHIFT = 4          # sub-pixel precision: coordinates are fixed-point with 4 fractional bits
ONE = 1 << SHIFT


def _finger(i):
    if i == 0:
        return "palm"
    return ("thumb", "index", "middle", "ring", "pinky")[(i - 1) // 4]


def _connection_color(a, b):
    fa, fb = _finger(a), _finger(b)
    return FINGER_COLORS[fa] if fa == fb and fa != "palm" else PALM_COLOR


def _pt(p, w, h):
    return int(p[0] * w * ONE), int(p[1] * h * ONE)


class LandmarkSmoother:
    """Light exponential smoothing for display only (the mouse uses its own filter).
    alpha is the weight of the new sample: higher = snappier, lower = smoother."""

    def __init__(self, alpha=0.55):
        self.alpha = alpha
        self._prev = {}

    def update(self, key, pts):
        prev = self._prev.get(key)
        if prev is None or len(prev) != len(pts):
            out = list(pts)
        else:
            a = self.alpha
            out = [(p[0] + a * (q[0] - p[0]), p[1] + a * (q[1] - p[1]), q[2]) for p, q in zip(prev, pts)]
        self._prev[key] = out
        return out

    def keep(self, keys):
        """Forget everything that was not seen this frame, so a returning hand does not glide in."""
        for k in list(self._prev):
            if k not in keys:
                del self._prev[k]


def draw_overlay(img, result, show_hand, show_face, smoother):
    """Draw on img (BGR, modified in place). Landmarks are normalized, so any image size works."""
    h, w = img.shape[:2]
    scale = max(w / 640.0, 0.5)
    seen = set()

    if show_face and result.face:
        seen.add("face")
        pts = smoother.update("face", result.face)
        r = int(max(0.9 * scale, 0.8) * ONE)
        for p in pts:
            cv2.circle(img, _pt(p, w, h), r, FACE_COLOR, -1, cv2.LINE_AA, SHIFT)

    if show_hand:
        for label, lm in result.hands.items():
            seen.add(label)
            pts = [_pt(p, w, h) for p in smoother.update(label, lm)]
            thick = max(2, round(3 * scale))
            for a, b in HAND_CONNECTIONS:
                cv2.line(img, pts[a], pts[b], _connection_color(a, b), thick, cv2.LINE_AA, SHIFT)
            for i, p in enumerate(pts):
                color = PALM_COLOR if i == 0 else FINGER_COLORS[_finger(i)]
                cv2.circle(img, p, int(5 * scale * ONE), JOINT_RING, -1, cv2.LINE_AA, SHIFT)
                cv2.circle(img, p, int(3.5 * scale * ONE), color, -1, cv2.LINE_AA, SHIFT)

    smoother.keep(seen)
