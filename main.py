"""
זיהוי ידיים והזזתם - Hand Detection & Gesture Tracking
========================================================
דרישות: pip install opencv-python mediapipe numpy
הפעלה: python main.py
"""

import cv2
import numpy as np
import time
import threading
import math
from collections import deque
import mediapipe as mp
import tkinter as tk
import pyautogui

pyautogui.FAILSAFE = False
pyautogui.PAUSE    = 0
SCREEN_W, SCREEN_H = pyautogui.size()

# ── מצב טעינה ─────────────────────────────────────────────────────
USE_NEW_API   = False
detector      = None
hands_old     = None
mp_hands      = None
mp_draw       = None
model_ready   = False   # True כשהמודל מוכן
model_error   = None    # שגיאה אם נכשל

# ── קבועים ─────────────────────────────────────────────────────────
FINGER_TIPS  = [4, 8, 12, 16, 20]
MAX_TRAIL    = 40
COLOR_RIGHT  = (0, 200, 255)
COLOR_LEFT   = (255, 100, 0)
COLOR_TRAIL  = (0, 255, 150)
COLOR_TEXT   = (255, 255, 255)

trails     = {}
fps_buffer = deque(maxlen=30)
prev_time  = time.time()
smooth_x   = None
smooth_y   = None

# ── הגדרות (ניתן לשנות דרך חלון ההגדרות) ──────────────────────────
SMOOTH          = 7      # 0=עצלן 100=מהיר (100 = 0.07 הישן)
DEADZONE        = 8      # פיקסלים - מתחת לזה לא זז
MOUSE_ENABLED   = True   # האם לשלוט בעכבר
CONTROL_HAND    = "Right" # איזו יד שולטת - Right/Left/Both
CLICK_COOLDOWN  = 0.6    # שניות בין קליקים
SHOW_TRAIL      = True   # הצג שובל
SHOW_COORDS     = True   # הצג קואורדינטות

HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),
    (9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),
    (0,17)
]

# ── חלון טעינה ────────────────────────────────────────────────────
def show_loading_window():
    root = tk.Tk()
    root.title("Hand Tracker")
    root.configure(bg="#0a0a0a")
    root.resizable(False, False)
    w, h = 400, 260
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
    root.overrideredirect(True)

    canvas = tk.Canvas(root, width=w, height=h, bg="#0a0a0a", highlightthickness=0)
    canvas.pack()

    # מסגרת
    canvas.create_rectangle(2, 2, w-2, h-2, outline="#00ff96", width=1)

    # כותרת
    canvas.create_text(w//2, 55, text="HAND TRACKER",
                       font=("Consolas", 22, "bold"), fill="#00ff96")
    canvas.create_text(w//2, 85, text="Initializing model...",
                       font=("Consolas", 10), fill="#888888")

    # ספינר
    cx, cy, r = w//2, 155, 35
    arcs = []
    for i in range(12):
        angle = i * 30
        arc = canvas.create_arc(cx-r, cy-r, cx+r, cy+r,
                                start=angle, extent=20,
                                outline="#00ff96", width=3, style="arc")
        arcs.append(arc)

    # טקסט נקודות
    dots_id = canvas.create_text(w//2, 210, text="Loading",
                                 font=("Consolas", 11), fill="#cccccc")

    angle_offset = [0]
    dot_count    = [0]
    dot_timer    = [time.time()]

    def animate():
        if model_ready or model_error:
            root.destroy()
            return
        # סובב ספינר
        angle_offset[0] = (angle_offset[0] + 5) % 360
        for i, arc in enumerate(arcs):
            start = (i * 30 + angle_offset[0]) % 360
            brightness = int(80 + 175 * (i / 12))
            color = f"#{0:02x}{brightness:02x}{brightness//2:02x}"
            canvas.itemconfig(arc, start=start, outline=color)
        # עדכן נקודות
        if time.time() - dot_timer[0] > 0.5:
            dot_count[0] = (dot_count[0] + 1) % 4
            canvas.itemconfig(dots_id, text="Loading" + "." * dot_count[0])
            dot_timer[0] = time.time()
        root.after(40, animate)

    animate()
    root.mainloop()

# ── טעינת מודל ב-background ────────────────────────────────────────
def load_model():
    global detector, hands_old, mp_hands, mp_draw, USE_NEW_API, model_ready, model_error
    try:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python.vision import HandLandmarkerOptions, HandLandmarker
        import urllib.request, os

        MODEL_PATH = "hand_landmarker.task"
        if not os.path.exists(MODEL_PATH):
            print("Downloading hand model (~9MB)...")
            urllib.request.urlretrieve(
                "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                "hand_landmarker/float16/1/hand_landmarker.task",
                MODEL_PATH
            )
            print("Model downloaded!")

        base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
        options = HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.7,
            min_tracking_confidence=0.6
        )
        detector    = HandLandmarker.create_from_options(options)
        USE_NEW_API = True
        print("Using NEW mediapipe API (0.10+)")

    except Exception:
        try:
            mp_hands  = mp.solutions.hands
            mp_draw   = mp.solutions.drawing_utils
            hands_old = mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.6
            )
            print("Using OLD mediapipe API (0.9.x)")
        except Exception as e:
            model_error = str(e)
            print(f"ERROR loading mediapipe: {e}")
            return

    model_ready = True

# ── ג'סטות ─────────────────────────────────────────────────────────
def fingers_up(lm_list, handedness):
    up = []
    # אגודל
    tip_x  = lm_list[4][0]
    base_x = lm_list[3][0]
    dx = lm_list[4][0] - lm_list[0][0]
    dy = lm_list[4][1] - lm_list[0][1]
    thumb_dist = (dx**2 + dy**2) ** 0.5
    thumb_dir  = tip_x < base_x if handedness == "Right" else tip_x > base_x
    up.append(thumb_dir and thumb_dist > 0.1)
    for tip_id in FINGER_TIPS[1:]:
        up.append(lm_list[tip_id][1] < lm_list[tip_id - 2][1])
    return up

def is_fist(lm_list):
    """אגרוף אמיתי: כל קצות האצבעות קרובים לבסיס כף היד"""
    wrist = np.array(lm_list[0][:2])
    mid_base = np.array(lm_list[9][:2])  # בסיס אצבע אמצעית
    hand_size = np.linalg.norm(mid_base - wrist)
    for tip_id in FINGER_TIPS[1:]:  # אצבעות בלי אגודל
        tip  = np.array(lm_list[tip_id][:2])
        dist = np.linalg.norm(tip - wrist) / (hand_size + 1e-6)
        if dist > 0.85:  # אצבע פתוחה
            return False
    return True

def classify_gesture(up, lm_list):
    if is_fist(lm_list):                      return "Fist"
    count = sum(up)
    if count == 5:                            return "Open Hand"
    if up[1] and not any(up[2:]):             return "One Finger"
    if up[1] and up[2] and not any(up[3:]):   return "Victory"
    if up[0] and up[4] and not any(up[1:4]): return "Hang Loose"
    if up[0] and not any(up[1:]):             return "Thumbs Up"
    return f"{count} Fingers"

# ── ציור ───────────────────────────────────────────────────────────
def draw_skeleton(frame, lm_list, color, h, w):
    pts = [(int(lm[0]*w), int(lm[1]*h)) for lm in lm_list]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (200,200,200), 1, cv2.LINE_AA)
    for pt in pts:
        cv2.circle(frame, pt, 5, color, -1, cv2.LINE_AA)
        cv2.circle(frame, pt, 6, (255,255,255), 1, cv2.LINE_AA)

def draw_trail(frame, trail):
    pts = list(trail)
    for i in range(1, len(pts)):
        alpha = i / len(pts)
        color = tuple(int(c * alpha) for c in COLOR_TRAIL)
        cv2.line(frame, pts[i-1], pts[i], color, max(1, int(alpha*5)), cv2.LINE_AA)

def draw_info_box(frame, label, wx, wy, color):
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    bx = max(0, wx - tw // 2)
    by = max(60, wy - 40)
    cv2.rectangle(frame, (bx-6, by-th-8), (bx+tw+6, by+4), (0,0,0), -1)
    cv2.putText(frame, label, (bx, by),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

def draw_ui(frame, fps, hand_count):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0,0), (w,50), (10,10,10), -1)
    cv2.putText(frame, "HAND TRACKER  |  ESC = quit  |  S = screenshot  |  G = settings",
                (12,32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_TEXT, 1, cv2.LINE_AA)
    cv2.putText(frame, f"FPS: {fps:.0f}", (w-120,32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_TRAIL, 2, cv2.LINE_AA)
    cv2.putText(frame, f"Hands: {hand_count}", (w-240,32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_RIGHT, 2, cv2.LINE_AA)
    mouse_status = f"Mouse: {'ON' if MOUSE_ENABLED else 'OFF'}  Hand: {CONTROL_HAND}"
    cv2.putText(frame, mouse_status, (12, h-12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TRAIL if MOUSE_ENABLED else (100,100,100), 1, cv2.LINE_AA)

def draw_loading(frame, dots):
    """מסך המתנה בזמן טעינת המודל"""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0,0), (w,h), (10,10,10), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    # כותרת
    title = "Hand Tracker"
    (tw,_),_ = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 1.4, 3)
    cv2.putText(frame, title, ((w-tw)//2, h//2 - 80),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, COLOR_TRAIL, 3, cv2.LINE_AA)

    # ספינר מסתובב
    cx, cy = w//2, h//2
    radius = 30
    num_segments = 12
    for i in range(num_segments):
        angle = (i / num_segments) * 2 * np.pi - (dots * 0.4)
        brightness = int(255 * (i / num_segments))
        color = (0, brightness, brightness // 2)
        x1 = int(cx + (radius - 8) * np.cos(angle))
        y1 = int(cy + (radius - 8) * np.sin(angle))
        x2 = int(cx + radius * np.cos(angle))
        y2 = int(cy + radius * np.sin(angle))
        cv2.line(frame, (x1,y1), (x2,y2), color, 3, cv2.LINE_AA)

    # טקסט טעינה
    text = "Loading model" + "." * (dots % 4)
    (lw,_),_ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
    cv2.putText(frame, text, ((w-lw)//2, h//2 + 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220,220,220), 2, cv2.LINE_AA)

    # פס התקדמות
    bar_w, bar_h = 300, 8
    bx = (w - bar_w) // 2
    by = h//2 + 90
    cv2.rectangle(frame, (bx, by), (bx+bar_w, by+bar_h), (50,50,50), -1)
    fill = int(bar_w * ((dots % 20) / 20))
    cv2.rectangle(frame, (bx, by), (bx+fill, by+bar_h), COLOR_TRAIL, -1)

last_click = 0
settings_open = False

def open_settings():
    global SMOOTH, DEADZONE, MOUSE_ENABLED, CONTROL_HAND, CLICK_COOLDOWN, SHOW_TRAIL, SHOW_COORDS, settings_open
    if settings_open:
        return
    settings_open = True

    root = tk.Tk()
    root.title("Settings")
    root.configure(bg="#0f0f0f")
    root.resizable(False, False)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = 420, 480
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    BG, FG, ACC, ENTRY_BG = "#0f0f0f", "#eeeeee", "#00ff96", "#1e1e1e"

    tk.Label(root, text="HAND TRACKER  SETTINGS", bg=BG, fg=ACC,
             font=("Consolas", 14, "bold")).pack(pady=(18,12))

    frame = tk.Frame(root, bg=BG)
    frame.pack(fill="x", padx=30)

    def row(label, widget_fn, row_i):
        tk.Label(frame, text=label, bg=BG, fg=FG, font=("Consolas", 10),
                 anchor="w", width=22).grid(row=row_i, column=0, pady=6, sticky="w")
        w = widget_fn(frame)
        w.grid(row=row_i, column=1, pady=6, sticky="ew")
        return w

    slider_style = dict(bg=BG, fg=FG, troughcolor="#333", activebackground=ACC,
                        highlightthickness=0, length=180, orient="horizontal")

    # Smooth
    smooth_var = tk.IntVar(value=SMOOTH)
    row("Smoothing (0-100)", lambda f: tk.Scale(f, from_=1, to=100,
        variable=smooth_var, **slider_style), 0)

    # Deadzone
    dead_var = tk.IntVar(value=DEADZONE)
    row("Deadzone (px)", lambda f: tk.Scale(f, from_=0, to=40,
        variable=dead_var, **slider_style), 1)

    # Click cooldown
    cooldown_var = tk.DoubleVar(value=CLICK_COOLDOWN)
    row("Click cooldown (s)", lambda f: tk.Scale(f, from_=0.1, to=2.0,
        resolution=0.1, variable=cooldown_var, **slider_style), 2)

    # Mouse enabled
    mouse_var = tk.BooleanVar(value=MOUSE_ENABLED)
    row("Mouse control", lambda f: tk.Checkbutton(f, variable=mouse_var,
        bg=BG, fg=FG, selectcolor="#333", activebackground=BG,
        font=("Consolas", 10)), 3)

    # Show trail
    trail_var = tk.BooleanVar(value=SHOW_TRAIL)
    row("Show trail", lambda f: tk.Checkbutton(f, variable=trail_var,
        bg=BG, fg=FG, selectcolor="#333", activebackground=BG,
        font=("Consolas", 10)), 4)

    # Show coords
    coords_var = tk.BooleanVar(value=SHOW_COORDS)
    row("Show coordinates", lambda f: tk.Checkbutton(f, variable=coords_var,
        bg=BG, fg=FG, selectcolor="#333", activebackground=BG,
        font=("Consolas", 10)), 5)

    # Control hand
    hand_var = tk.StringVar(value=CONTROL_HAND)
    tk.Label(frame, text="Control hand", bg=BG, fg=FG, font=("Consolas", 10),
             anchor="w", width=22).grid(row=6, column=0, pady=6, sticky="w")
    hf = tk.Frame(frame, bg=BG)
    hf.grid(row=6, column=1, sticky="w")
    for val in ("Right", "Left", "Both"):
        tk.Radiobutton(hf, text=val, variable=hand_var, value=val,
                       bg=BG, fg=FG, selectcolor="#333", activebackground=BG,
                       font=("Consolas", 10)).pack(side="left")

    def apply():
        global SMOOTH, DEADZONE, MOUSE_ENABLED, CONTROL_HAND, CLICK_COOLDOWN, SHOW_TRAIL, SHOW_COORDS, settings_open
        SMOOTH         = int(smooth_var.get())
        DEADZONE       = dead_var.get()
        CLICK_COOLDOWN = cooldown_var.get()
        MOUSE_ENABLED  = mouse_var.get()
        SHOW_TRAIL     = trail_var.get()
        SHOW_COORDS    = coords_var.get()
        CONTROL_HAND   = hand_var.get()
        settings_open  = False
        root.destroy()

    def on_close():
        global settings_open
        settings_open = False
        root.destroy()

    tk.Button(root, text="Apply", command=apply, bg=ACC, fg="#000",
              font=("Consolas", 11, "bold"), relief="flat",
              padx=20, pady=6).pack(pady=20)
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

def move_mouse(lm_list, gesture):
    global smooth_x, smooth_y, last_click
    if not MOUSE_ENABLED or gesture == "Fist":
        return
    tx, ty = lm_list[8][0], lm_list[8][1]
    mx, my = int(tx * SCREEN_W), int(ty * SCREEN_H)
    if smooth_x is None:
        smooth_x, smooth_y = mx, my
    s = SMOOTH / 100
    prev_x, prev_y = smooth_x, smooth_y
    smooth_x = max(0, min(SCREEN_W - 1, int(smooth_x + s * (mx - smooth_x))))
    smooth_y = max(0, min(SCREEN_H - 1, int(smooth_y + s * (my - smooth_y))))
    if abs(smooth_x - prev_x) > DEADZONE or abs(smooth_y - prev_y) > DEADZONE:
        pyautogui.moveTo(smooth_x, smooth_y)
    if gesture == "4 Fingers" and time.time() - last_click > CLICK_COOLDOWN:
        pyautogui.click()
        last_click = time.time()
    if gesture == "4 Fingers" and time.time() - last_click > CLICK_COOLDOWN:
        pyautogui.click()
        last_click = time.time()

def draw_hand(frame, idx, lm_list, label, h, w, use_mp_draw=False, hand_lm_raw=None):
    color = COLOR_RIGHT if label == "Right" else COLOR_LEFT

    if use_mp_draw and hand_lm_raw is not None:
        mp_draw.draw_landmarks(
            frame, hand_lm_raw, mp_hands.HAND_CONNECTIONS,
            mp_draw.DrawingSpec(color=color, thickness=2, circle_radius=4),
            mp_draw.DrawingSpec(color=(200,200,200), thickness=1)
        )
    else:
        draw_skeleton(frame, lm_list, color, h, w)

    tx = int(lm_list[8][0] * w)
    ty = int(lm_list[8][1] * h)

    up      = fingers_up(lm_list, label)
    gesture = classify_gesture(up, lm_list)

    controls = (CONTROL_HAND == "Both") or \
               (CONTROL_HAND == "Right" and label == "Right") or \
               (CONTROL_HAND == "Left"  and label == "Left")
    if idx == 0 and controls:
        move_mouse(lm_list, gesture)

    if idx not in trails:
        trails[idx] = deque(maxlen=MAX_TRAIL)
    if trails[idx]:
        last_x, last_y = trails[idx][-1]
        dist = ((tx - last_x)**2 + (ty - last_y)**2) ** 0.5
        if dist > 80:
            trails[idx].clear()
    trails[idx].append((tx, ty))
    if SHOW_TRAIL:
        draw_trail(frame, trails[idx])

    wx = int(lm_list[0][0] * w)
    wy = int(lm_list[0][1] * h)
    draw_info_box(frame, f"{label}  {gesture}", wx, wy, color)
    if SHOW_COORDS:
        cv2.putText(frame, f"({tx},{ty})", (tx+10, ty-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200,255,200), 1, cv2.LINE_AA)

# ── עיבוד פריים ────────────────────────────────────────────────────
def process_frame(frame, h, w):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    if USE_NEW_API:
        mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp = int(time.time() * 1000)
        result    = detector.detect_for_video(mp_image, timestamp)
        if not result.hand_landmarks:
            trails.clear()
            return 0
        for idx, (hand_lms, hand_info) in enumerate(
                zip(result.hand_landmarks, result.handedness)):
            raw_label = hand_info[0].category_name
            label     = "Left" if raw_label == "Right" else "Right"
            lm_list   = [(lm.x, lm.y, lm.z) for lm in hand_lms]
            draw_hand(frame, idx, lm_list, label, h, w)
        return len(result.hand_landmarks)

    else:
        results = hands_old.process(rgb)
        if not results.multi_hand_landmarks:
            trails.clear()
            return 0
        for idx, (hand_lm, hand_info) in enumerate(
                zip(results.multi_hand_landmarks, results.multi_handedness)):
            raw_label = hand_info.classification[0].label
            label     = "Left" if raw_label == "Right" else "Right"
            lm_list   = [(lm.x, lm.y, lm.z) for lm in hand_lm.landmark]
            draw_hand(frame, idx, lm_list, label, h, w,
                      use_mp_draw=True, hand_lm_raw=hand_lm)
        return len(results.multi_hand_landmarks)

# ── לולאה ראשית ─────────────────────────────────────────────────────
def main():
    global prev_time

    # הפעל טעינת מודל ב-background
    t = threading.Thread(target=load_model, daemon=True)
    t.start()

    threading.Thread(target=show_loading_window, daemon=True).start()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Camera not found.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    screenshot_cnt = 0
    dots           = 0
    dot_timer      = time.time()
    print("Window open - model loading in background...")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w  = frame.shape[:2]

        now       = time.time()
        fps_val   = 1.0 / max(now - prev_time, 1e-6)
        fps_buffer.append(fps_val)
        fps_avg   = sum(fps_buffer) / len(fps_buffer)
        prev_time = now

        if not model_ready:
            # עדיין טוען - הצג מסך המתנה
            if now - dot_timer > 0.05:
                dots += 1
                dot_timer = now
            draw_loading(frame, dots)
            hand_count = 0
        else:
            if model_error:
                print(f"ERROR: {model_error}")
                break
            hand_count = process_frame(frame, h, w)
            draw_ui(frame, fps_avg, hand_count)

        cv2.imshow("Hand Tracker", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        elif key in (ord('g'), ord('G')):
            threading.Thread(target=open_settings, daemon=True).start()
        elif key in (ord('s'), ord('S')):
            fname = f"screenshot_{screenshot_cnt:03d}.png"
            cv2.imwrite(fname, frame)
            print(f"Saved: {fname}")
            screenshot_cnt += 1

    cap.release()
    cv2.destroyAllWindows()
    print("Done!")

if __name__ == "__main__":
    main()