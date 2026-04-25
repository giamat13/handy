"""Cross-platform mouse control using pynput."""

import time

from pynput.mouse import Button as _MouseButton
from pynput.mouse import Controller as _MouseController

import handy.state as state

_mouse = _MouseController()
_is_pressed = False  # Track if mouse button is currently pressed


def init_screen_size() -> None:
    """Detect screen dimensions and store in state.SCREEN_W / state.SCREEN_H.

    Uses tkinter (already a dependency via customtkinter) so no extra package needed.
    Falls back to 1920×1080 if detection fails.
    """
    try:
        import tkinter as _tk
        _root = _tk.Tk()
        _root.withdraw()
        state.SCREEN_W = _root.winfo_screenwidth()
        state.SCREEN_H = _root.winfo_screenheight()
        _root.destroy()
    except Exception:
        state.SCREEN_W, state.SCREEN_H = 1920, 1080


def reset_anchor() -> None:
    """Reset delta tracking — call whenever hands leave the frame."""
    global _is_pressed
    state.prev_hand_x = None
    state.prev_hand_y = None
    state.smooth_dx = 0.0
    state.smooth_dy = 0.0
    # Release mouse button when hand leaves frame
    if _is_pressed:
        _mouse.release(_MouseButton.left)
        _is_pressed = False


def move_mouse(lm_list: list, gesture: str) -> None:
    global _is_pressed
    
    if not state.MOUSE_ENABLED:
        # Release button if mouse is disabled
        if _is_pressed:
            _mouse.release(_MouseButton.left)
            _is_pressed = False
        return

    tx, ty = lm_list[8][0], lm_list[8][1]

    if gesture == "Fist":
        state.prev_hand_x, state.prev_hand_y = tx, ty
        state.smooth_dx, state.smooth_dy = 0.0, 0.0
        # Release button when making a fist
        if _is_pressed:
            _mouse.release(_MouseButton.left)
            _is_pressed = False
        return

    if state.prev_hand_x is None:
        state.prev_hand_x, state.prev_hand_y = tx, ty
        cx, cy = _mouse.position
        state.smooth_x, state.smooth_y = float(cx), float(cy)
        state.smooth_dx, state.smooth_dy = 0.0, 0.0
        return

    dx_raw = (tx - state.prev_hand_x) * state.SCREEN_W
    dy_raw = (ty - state.prev_hand_y) * state.SCREEN_H

    # Guard against large jumps (hand reappeared after absence)
    if abs(dx_raw) > state.SCREEN_W * 0.15 or abs(dy_raw) > state.SCREEN_H * 0.15:
        state.prev_hand_x, state.prev_hand_y = tx, ty
        state.smooth_dx, state.smooth_dy = 0.0, 0.0
        return

    if state.DYNAMIC_SPEED:
        dist = (dx_raw**2 + dy_raw**2) ** 0.5
        if dist < state.DEADZONE:
            state.prev_hand_x, state.prev_hand_y = tx, ty
            return
        norm = dist / (state.SCREEN_W * 0.1)
        scale = min(norm ** state.SPEED_CURVE, 1.0) * state.SPEED * 0.8
        dx_raw *= scale
        dy_raw *= scale
    else:
        if (dx_raw**2 + dy_raw**2) ** 0.5 < state.DEADZONE:
            state.prev_hand_x, state.prev_hand_y = tx, ty
            return
        dx_raw *= state.SPEED * 0.5
        dy_raw *= state.SPEED * 0.5

    state.prev_hand_x, state.prev_hand_y = tx, ty

    # When drawing (4 Fingers), use much higher responsiveness for precise tracking
    # Otherwise use normal smoothing
    if gesture == "4 Fingers":
        # High responsiveness for drawing - capture every movement
        s = 0.85 + (state.SMOOTH / 100) * 0.15  # 85%-100% instant response
    else:
        # Normal smoothing for cursor movement
        s = 0.05 + (state.SMOOTH / 100) * 0.95
    
    state.smooth_dx = state.smooth_dx * (1 - s) + dx_raw * s
    state.smooth_dy = state.smooth_dy * (1 - s) + dy_raw * s
    state.smooth_x = max(0, min(state.SCREEN_W - 1, state.smooth_x + state.smooth_dx))
    state.smooth_y = max(0, min(state.SCREEN_H - 1, state.smooth_y + state.smooth_dy))

    _mouse.position = (int(state.smooth_x), int(state.smooth_y))

    # For "4 Fingers": repeatedly release and press for connected dots
    if gesture == "4 Fingers":
        if time.time() - state.last_click > 0.01:  # 10ms between dots
            if _is_pressed:
                # Release and immediately press again - creates a dot while maintaining connection
                _mouse.release(_MouseButton.left)
                _mouse.press(_MouseButton.left)
            else:
                # First time - just press
                _mouse.press(_MouseButton.left)
                _is_pressed = True
            state.last_click = time.time()
    else:
        # Release button for any other gesture
        if _is_pressed:
            _mouse.release(_MouseButton.left)
            _is_pressed = False