"""Gesture recognition — pure functions, no side effects.

classify_gesture()         — original built-in classifier (unchanged)
classify_with_custom()     — checks custom templates first, then falls back
"""

import numpy as np

from .config import FINGER_TIPS


def fingers_up(lm_list: list, handedness: str) -> list[bool]:
    """Return a 5-element list: [thumb, index, middle, ring, pinky] are up."""
    up = []
    tip_x = lm_list[4][0]
    base_x = lm_list[3][0]
    dx = lm_list[4][0] - lm_list[0][0]
    dy = lm_list[4][1] - lm_list[0][1]
    thumb_dist = (dx**2 + dy**2) ** 0.5
    thumb_dir = tip_x < base_x if handedness == "Right" else tip_x > base_x
    up.append(thumb_dir and thumb_dist > 0.1)
    for tip_id in FINGER_TIPS[1:]:
        up.append(lm_list[tip_id][1] < lm_list[tip_id - 2][1])
    return up


def is_fist(lm_list: list) -> bool:
    """True when all non-thumb fingertips are close to the wrist."""
    wrist = np.array(lm_list[0][:2])
    mid_base = np.array(lm_list[9][:2])
    hand_size = np.linalg.norm(mid_base - wrist)
    for tip_id in FINGER_TIPS[1:]:
        tip = np.array(lm_list[tip_id][:2])
        dist = np.linalg.norm(tip - wrist) / (hand_size + 1e-6)
        if dist > 0.85:
            return False
    return True


def classify_gesture(up: list[bool], lm_list: list) -> str:
    """Original built-in gesture classifier. Returns a gesture name string."""
    if is_fist(lm_list):
        return "Fist"
    count = sum(up)
    if count == 5:
        return "Open Hand"
    if up[1] and not any(up[2:]):
        return "One Finger"
    if up[1] and up[2] and not any(up[3:]):
        return "Victory"
    if up[0] and up[4] and not any(up[1:4]):
        return "Hang Loose"
    if up[0] and not any(up[1:]):
        return "Thumbs Up"
    return f"{count} Fingers"


def classify_with_custom(up: list[bool], lm_list: list, custom_templates: list) -> str:
    """
    Full gesture classifier: custom templates take priority over built-in.

    1. Run custom gesture matching against trained templates.
    2. If a custom gesture matches (above confidence threshold), return it.
    3. Otherwise fall back to the original built-in classifier.

    Parameters
    ----------
    up              : output of fingers_up()
    lm_list         : raw landmark list from MediaPipe
    custom_templates: list[GestureTemplate] from state.CUSTOM_GESTURE_TEMPLATES
    """
    if custom_templates:
        from .custom_gestures import match_custom_gesture
        custom_hit = match_custom_gesture(lm_list, custom_templates)
        if custom_hit:
            return custom_hit

    return classify_gesture(up, lm_list)
