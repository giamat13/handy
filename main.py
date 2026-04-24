"""
Handy - Hand Detection & Gesture Tracking
==========================================
דרישות: pip install opencv-python mediapipe numpy pyautogui
הפעלה: python main.py
"""

import subprocess, sys

def install_deps():
    pkgs = ["opencv-python", "mediapipe", "numpy", "pyautogui"]
    for pkg in pkgs:9
install_deps()

# הסתר חלון CMD על Windows (רלוונטי כשרצים כ-.py, לא כ-EXE עם --noconsole)
import sys as _sys, os as _os
if _sys.platform == "win32":
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

import cv2
import numpy as np
import time
import threading
import math
from collections import deque  
import mediapipe as mp
import tkinter as tk
import pyautogui
import queue

pyautogui.FAILSAFE = False
pyautogui.PAUSE    = 0
SCREEN_W, SCREEN_H = pyautogui.size()
ui_queue = queue.Queue()

# ── מצב טעינה ─────────────────────────────────────────────────────
USE_NEW_API   = False
detector      = None
hands_old     = None
mp_hands      = None
mp_draw       = None
model_ready   = False   # True כשהמודל מוכן
model_error   = None    # שגיאה אם נכשל
camera_ready  = False   # True כשהמצלמה נפתחה

# ── debug / hot-reload ──────────────────────────────────────────────
DEBUG_MODE   = False   # מופעל מהגדרות
FAST_RELOAD  = False   # מוגדר ל-True כשמופעל עם --fast-reload

def _do_hot_reload():
    """
    Hot reload שמשמר את המודל בRAM:
    - Mac/Linux: os.fork() — הבן יורש את כל הזיכרון כולל המודל,
      קורא את הקוד החדש ומריץ אותו. האב מת.
    - Windows: fallback — subprocess חדש טוען מהדיסק (מהיר, ללא הורדה).
    """
    import sys, os

    print("[HOT-RELOAD] reloading...")

    if sys.platform != "win32":
        # ── fork: הבן יורש RAM + מודל ──────────────────────────────
        pid = os.fork()
        if pid == 0:
            # אנחנו הבן — שמור מצב המודל לפני שה-exec יאפס גלובלים
            _saved_detector    = detector
            _saved_hands_old   = hands_old
            _saved_mp_hands    = mp_hands
            _saved_mp_draw     = mp_draw
            _saved_use_new_api = USE_NEW_API
            _saved_model_ready = model_ready
            _saved_model_error = model_error

            try:
                with open(os.path.abspath(__file__), "r", encoding="utf-8") as f:
                    src = f.read()
                # דלג על guard ועל install (כבר מותקן)
                src = src.replace('if __name__ == "__main__":', 'if False:')
                src = src.replace('install_deps()', '')
                g = sys.modules["__main__"].__dict__
                exec(compile(src, __file__, "exec"), g)

                # שחזר מצב המודל אחרי ה-exec
                g["detector"]      = _saved_detector
                g["hands_old"]     = _saved_hands_old
                g["mp_hands"]      = _saved_mp_hands
                g["mp_draw"]       = _saved_mp_draw
                g["USE_NEW_API"]   = _saved_use_new_api
                g["model_ready"]   = _saved_model_ready
                g["model_error"]   = _saved_model_error
                g["_FORKED_RELOAD"] = True
                g["DEBUG_MODE"]    = True

                # הפעל מחדש
                g["main"]()
            except Exception as e:
                print(f"[HOT-RELOAD] child error: {e}")
            finally:
                os._exit(0)
        else:
            # אנחנו האב — מת
            import time
            time.sleep(0.2)
            os._exit(0)
    else:
        # ── Windows fallback: subprocess ────────────────────────────
        import subprocess, time
        script = os.path.abspath(__file__)
        subprocess.Popen(
            [sys.executable, script, "--fast-reload"],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        time.sleep(0.3)
        os._exit(0)

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
smooth_x    = None
smooth_y    = None
prev_hand_x = None
prev_hand_y = None
smooth_dx   = 0.0
smooth_dy   = 0.0

# ── הגדרות (ניתן לשנות דרך חלון ההגדרות) ──────────────────────────
SMOOTH          = 7      # 0=עצלן 100=מהיר (100 = 0.07 הישן)
SPEED           = 5      # מכפיל מהירות עכבר
DYNAMIC_SPEED   = True   # מהירות דינמית: איטי=מאוד איטי, מהיר=רגיל
SPEED_CURVE     = 2.0    # חזקה: 1=לינארי, 2=ריבועי, 3=קובי
CAM_MARGIN      = 0.15   # חתך משולי המצלמה למיפוי מלא למסך
DEADZONE        = 8      # פיקסלים - מתחת לזה לא זז
MOUSE_ENABLED   = False  # האם לשלוט בעכבר
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

# ── סטטוס טעינה ────────────────────────────────────────────────────
loading_status = "Starting..."

def set_status(msg):
    global loading_status
    loading_status = msg
    print(msg)

# ── חלון טעינה ────────────────────────────────────────────────────
def show_loading_window(root, check_queue):
    root.title("Handy - Loading")
    root.configure(bg="#0a0a0a")
    root.resizable(False, False)
    w, h = 420, 280
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
    root.overrideredirect(True)

    canvas = tk.Canvas(root, width=w, height=h, bg="#0a0a0a", highlightthickness=0)
    canvas.pack()

    canvas.create_rectangle(2, 2, w-2, h-2, outline="#00ff96", width=1)
    canvas.create_text(w//2, 50, text="HANDY",
                       font=("Consolas", 22, "bold"), fill="#00ff96")

    # ספינר
    cx, cy, r = w//2, 145, 35
    arcs = []
    for i in range(12):
        arc = canvas.create_arc(cx-r, cy-r, cx+r, cy+r,
                                start=i*30, extent=20,
                                outline="#00ff96", width=3, style="arc")
        arcs.append(arc)

    status_id = canvas.create_text(w//2, 205, text="Starting...",
                                   font=("Consolas", 10), fill="#00ff96")
    dots_id   = canvas.create_text(w//2, 235, text="",
                                   font=("Consolas", 9), fill="#555555")

    angle_offset = [0]
    dot_count    = [0]
    dot_timer    = [time.time()]

    def animate():
        if (model_ready or model_error) and camera_ready:
            root.overrideredirect(False)
            root.withdraw()
            return
        angle_offset[0] = (angle_offset[0] + 6) % 360
        for i, arc in enumerate(arcs):
            start = (i * 30 + angle_offset[0]) % 360
            brightness = int(60 + 195 * (i / 12))
            canvas.itemconfig(arc, start=start, outline=f"#00{brightness:02x}{brightness//2:02x}")
        canvas.itemconfig(status_id, text=loading_status)
        if time.time() - dot_timer[0] > 0.5:
            dot_count[0] = (dot_count[0] + 1) % 4
            canvas.itemconfig(dots_id, text="● " * dot_count[0])
            dot_timer[0] = time.time()
        root.after(40, animate)

    animate()

# ── טעינת מודל ב-background ────────────────────────────────────────
def load_model():
    global detector, hands_old, mp_hands, mp_draw, USE_NEW_API, model_ready, model_error
    try:
        set_status("Importing mediapipe..." if not FAST_RELOAD else "Fast reload — loading model...")
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python.vision import HandLandmarkerOptions, HandLandmarker
        import urllib.request, os

        # שמירה תמיד ליד קובץ הסקריפט, לא תלוי ב-cwd
        MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
        if not os.path.exists(MODEL_PATH):
            if FAST_RELOAD:
                set_status("ERROR: model file missing, run normally first")
                model_error = "hand_landmarker.task not found"
                return
            set_status("Downloading hand model (~9MB)...")
            urllib.request.urlretrieve(
                "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                "hand_landmarker/float16/1/hand_landmarker.task",
                MODEL_PATH
            )
        set_status("Loading hand model..." if not FAST_RELOAD else "Building model from cache...")
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
        set_status("Model ready (new API)")

    except Exception as new_api_err:
        print(f"[new API failed: {new_api_err}]")
        try:
            set_status("Trying legacy mediapipe API...")
            import mediapipe as _mp
            # תמיכה בגרסאות ישנות וחדשות כאחד
            if hasattr(_mp, 'solutions'):
                mp_hands = _mp.solutions.hands
                mp_draw  = _mp.solutions.drawing_utils
            else:
                # גרסאות חדשות — ייבוא ישיר
                from mediapipe.python.solutions import hands as _hands_mod
                from mediapipe.python.solutions import drawing_utils as _draw_mod
                mp_hands = _hands_mod
                mp_draw  = _draw_mod
            hands_old = mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.6
            )
            set_status("Model ready (legacy API)")
        except Exception as e:
            model_error = str(e)
            set_status(f"ERROR: {e}")
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
    hint = "ESC=quit  S=screenshot  G=settings" + ("  R=reload" if DEBUG_MODE else "")
    cv2.putText(frame, f"HANDY  |  {hint}",
                (12,32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_TEXT, 1, cv2.LINE_AA)
    cv2.putText(frame, f"FPS: {fps:.0f}", (w-120,32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_TRAIL, 2, cv2.LINE_AA)
    cv2.putText(frame, f"Hands: {hand_count}", (w-240,32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, COLOR_RIGHT, 2, cv2.LINE_AA)
    mouse_status = f"Mouse: {'ON' if MOUSE_ENABLED else 'OFF'}  Hand: {CONTROL_HAND}"
    cv2.putText(frame, mouse_status, (12, h-12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TRAIL if MOUSE_ENABLED else (100,100,100), 1, cv2.LINE_AA)
    if DEBUG_MODE:
        cv2.putText(frame, "DEBUG", (w-68, h-12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 80, 255), 2, cv2.LINE_AA)

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
    global settings_open
    if settings_open:
        return
    settings_open = True
    ui_queue.put("open_settings")

def _show_settings_window(root):
    global SMOOTH, SPEED, DEADZONE, MOUSE_ENABLED, CONTROL_HAND, CLICK_COOLDOWN, SHOW_TRAIL, SHOW_COORDS, DYNAMIC_SPEED, SPEED_CURVE, settings_open, DEBUG_MODE
    win = tk.Toplevel(root)
    win.title("Handy - Settings")
    win.configure(bg="#0f0f0f")
    win.resizable(False, True)
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win_h = min(600, sh - 80)
    w = 460
    win.geometry(f"{w}x{win_h}+{(sw-w)//2}+{(sh-win_h)//2}")
    win.minsize(w, 300)

    BG, FG, ACC, DIM = "#0f0f0f", "#eeeeee", "#00ff96", "#555555"

    # ── גלילה ──────────────────────────────────────────────────────
    outer = tk.Frame(win, bg=BG)
    outer.pack(fill="both", expand=True)

    canvas_scroll = tk.Canvas(outer, bg=BG, highlightthickness=0)
    scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas_scroll.yview)
    canvas_scroll.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas_scroll.pack(side="left", fill="both", expand=True)

    inner = tk.Frame(canvas_scroll, bg=BG)
    inner_win = canvas_scroll.create_window((0, 0), window=inner, anchor="nw")

    def _on_resize(e):
        canvas_scroll.itemconfig(inner_win, width=e.width)
    canvas_scroll.bind("<Configure>", _on_resize)

    def _on_frame_configure(e):
        canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
    inner.bind("<Configure>", _on_frame_configure)

    def _on_mousewheel(e):
        canvas_scroll.yview_scroll(int(-1 * (e.delta / 120)), "units")
    win.bind("<MouseWheel>", _on_mousewheel)
    win.bind("<Button-4>", lambda e: canvas_scroll.yview_scroll(-1, "units"))
    win.bind("<Button-5>", lambda e: canvas_scroll.yview_scroll(1, "units"))

    tk.Label(inner, text="HANDY  SETTINGS", bg=BG, fg=ACC,
             font=("Consolas", 14, "bold")).pack(pady=(18,12))

    frame = tk.Frame(inner, bg=BG)
    frame.pack(fill="x", padx=30)

    def row(label, widget_fn, row_i):
        tk.Label(frame, text=label, bg=BG, fg=FG, font=("Consolas", 10),
                 anchor="w", width=22).grid(row=row_i, column=0, pady=4, sticky="w")
        ww = widget_fn(frame)
        ww.grid(row=row_i, column=1, pady=4, sticky="ew")
        return ww

    slider_style     = dict(bg=BG, fg=FG, troughcolor="#333", activebackground=ACC,
                            highlightthickness=0, length=180, orient="horizontal")
    slider_style_dim = dict(bg=BG, fg=DIM, troughcolor="#222", activebackground=DIM,
                            highlightthickness=0, length=180, orient="horizontal", state="disabled")

    # תצוגה
    trail_var  = tk.BooleanVar(value=SHOW_TRAIL)
    coords_var = tk.BooleanVar(value=SHOW_COORDS)
    row("Show trail",       lambda f: tk.Checkbutton(f, variable=trail_var,  bg=BG, fg=FG, selectcolor="#333", activebackground=BG, font=("Consolas",10)), 0)
    row("Show coordinates", lambda f: tk.Checkbutton(f, variable=coords_var, bg=BG, fg=FG, selectcolor="#333", activebackground=BG, font=("Consolas",10)), 1)

    # קו מפריד
    tk.Frame(frame, bg="#333", height=1).grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)

    # כותרת קטגוריית עכבר
    mouse_var = tk.BooleanVar(value=MOUSE_ENABLED)
    mouse_lbl = tk.Label(frame, text="▼  Mouse Control", bg=BG, fg=ACC, font=("Consolas", 10, "bold"), anchor="w")
    mouse_lbl.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4,2))
    tk.Checkbutton(frame, text="Enable", variable=mouse_var, bg=BG, fg=FG,
                   selectcolor="#333", activebackground=BG, font=("Consolas",10)).grid(row=4, column=1, sticky="w")
    tk.Label(frame, text="Enable mouse", bg=BG, fg=FG, font=("Consolas",10), anchor="w", width=22).grid(row=4, column=0, sticky="w")

    smooth_var   = tk.IntVar(value=SMOOTH)
    speed_var    = tk.IntVar(value=SPEED)
    dead_var     = tk.IntVar(value=DEADZONE)
    cooldown_var = tk.DoubleVar(value=CLICK_COOLDOWN)
    hand_var     = tk.StringVar(value=CONTROL_HAND)
    dyn_var      = tk.BooleanVar(value=DYNAMIC_SPEED)
    curve_var    = tk.DoubleVar(value=SPEED_CURVE)

    s_smooth   = row("Smoothing (1-100)", lambda f: tk.Scale(f, from_=1, to=100, variable=smooth_var,   **slider_style), 5)
    s_speed    = row("Speed (1-10)",      lambda f: tk.Scale(f, from_=1, to=10,  variable=speed_var,    **slider_style), 6)
    row("Dynamic speed",    lambda f: tk.Checkbutton(f, variable=dyn_var, bg=BG, fg=FG, selectcolor="#333", activebackground=BG, font=("Consolas",10)), 7)
    s_curve    = row("Speed curve (1-4)", lambda f: tk.Scale(f, from_=1.0, to=4.0, resolution=0.1, variable=curve_var, **slider_style), 8)
    s_dead     = row("Deadzone (px)",     lambda f: tk.Scale(f, from_=0, to=40,  variable=dead_var,     **slider_style), 9)
    s_cooldown = row("Click cooldown (s)",lambda f: tk.Scale(f, from_=0.1, to=2.0, resolution=0.1, variable=cooldown_var, **slider_style), 10)

    tk.Label(frame, text="Control hand", bg=BG, fg=FG, font=("Consolas",10), anchor="w", width=22).grid(row=11, column=0, pady=4, sticky="w")
    hf = tk.Frame(frame, bg=BG)
    hf.grid(row=11, column=1, sticky="w")
    radio_btns = []
    for val in ("Right", "Left", "Both"):
        rb = tk.Radiobutton(hf, text=val, variable=hand_var, value=val, bg=BG, fg=FG,
                            selectcolor="#333", activebackground=BG, font=("Consolas",10))
        rb.pack(side="left")
        radio_btns.append(rb)

    mouse_widgets = [s_smooth, s_speed, s_dead, s_cooldown, s_curve] + radio_btns

    def update_mouse_widgets(*_):
        enabled = mouse_var.get()
        for ww in mouse_widgets:
            ww.config(state="normal" if enabled else "disabled")

    mouse_var.trace_add("write", update_mouse_widgets)
    update_mouse_widgets()

    # ── Debug Mode ─────────────────────────────────────────────────
    tk.Frame(frame, bg="#333", height=1).grid(row=12, column=0, columnspan=2, sticky="ew", pady=8)
    debug_lbl = tk.Label(frame, text="▼  Developer", bg=BG, fg=ACC, font=("Consolas", 10, "bold"), anchor="w")
    debug_lbl.grid(row=13, column=0, columnspan=2, sticky="w", pady=(2,4))

    debug_var = tk.BooleanVar(value=DEBUG_MODE)
    debug_frame = tk.Frame(frame, bg=BG)
    debug_frame.grid(row=14, column=0, columnspan=2, sticky="w")
    tk.Checkbutton(debug_frame, text="Debug Mode  (R = hot reload — reloads code, keeps model)",
                   variable=debug_var, bg=BG, fg=FG,
                   selectcolor="#333", activebackground=BG,
                   font=("Consolas", 9), wraplength=340, justify="left").pack(anchor="w")

    def apply():
        global SMOOTH, SPEED, DEADZONE, MOUSE_ENABLED, CONTROL_HAND, CLICK_COOLDOWN, SHOW_TRAIL, SHOW_COORDS, settings_open, DEBUG_MODE
        SMOOTH, SPEED, DEADZONE = int(smooth_var.get()), speed_var.get(), dead_var.get()
        CLICK_COOLDOWN, MOUSE_ENABLED = cooldown_var.get(), mouse_var.get()
        SHOW_TRAIL, SHOW_COORDS, CONTROL_HAND = trail_var.get(), coords_var.get(), hand_var.get()
        DYNAMIC_SPEED, SPEED_CURVE = dyn_var.get(), curve_var.get()
        DEBUG_MODE = debug_var.get()
        settings_open = False
        win.destroy()

    def on_close():
        global settings_open
        settings_open = False
        win.destroy()

    tk.Button(inner, text="Apply", command=apply, bg=ACC, fg="#000",
              font=("Consolas", 11, "bold"), relief="flat", padx=20, pady=6).pack(pady=16)
    win.protocol("WM_DELETE_WINDOW", on_close)

def move_mouse(lm_list, gesture):
    global smooth_x, smooth_y, last_click, prev_hand_x, prev_hand_y, smooth_dx, smooth_dy
    if not MOUSE_ENABLED:
        return
    tx, ty = lm_list[8][0], lm_list[8][1]
    if gesture == "Fist":
        # כשאגרוף - עצור ואפס delta כדי שלא יצטבר
        prev_hand_x, prev_hand_y = tx, ty
        smooth_dx, smooth_dy = 0.0, 0.0
        return
    if prev_hand_x is None:
        # יד הופיעה לראשונה - עגן למיקום נוכחי של העכבר ואפס delta
        prev_hand_x, prev_hand_y = tx, ty
        cx, cy = pyautogui.position()
        smooth_x, smooth_y = float(cx), float(cy)
        smooth_dx, smooth_dy = 0.0, 0.0
        return
    dx_raw = (tx - prev_hand_x) * SCREEN_W
    dy_raw = (ty - prev_hand_y) * SCREEN_H
    # מגן מפני קפיצות גדולות (יד נעלמה וחזרה) - אפס delta במקום לצבור
    if abs(dx_raw) > SCREEN_W * 0.15 or abs(dy_raw) > SCREEN_H * 0.15:
        prev_hand_x, prev_hand_y = tx, ty
        smooth_dx, smooth_dy = 0.0, 0.0
        return
    if DYNAMIC_SPEED:
        dist = (dx_raw**2 + dy_raw**2) ** 0.5
        if dist < DEADZONE:
            prev_hand_x, prev_hand_y = tx, ty
            return
        norm = dist / (SCREEN_W * 0.1)
        scale = min((norm ** SPEED_CURVE), 1.0) * SPEED * 0.8
        dx_raw *= scale
        dy_raw *= scale
    else:
        if (dx_raw**2 + dy_raw**2) ** 0.5 < DEADZONE:
            prev_hand_x, prev_hand_y = tx, ty
            return
        dx_raw *= SPEED * 0.5
        dy_raw *= SPEED * 0.5
    prev_hand_x, prev_hand_y = tx, ty
    # SMOOTH=0 → עצלן (s=0.05), SMOOTH=100 → מיידי (s=1.0)
    s = 0.05 + (SMOOTH / 100) * 0.95
    smooth_dx = smooth_dx * (1 - s) + dx_raw * s
    smooth_dy = smooth_dy * (1 - s) + dy_raw * s
    smooth_x = max(0, min(SCREEN_W - 1, smooth_x + smooth_dx))
    smooth_y = max(0, min(SCREEN_H - 1, smooth_y + smooth_dy))
    pyautogui.moveTo(int(smooth_x), int(smooth_y))
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
def _reset_mouse_anchor():
    """כשאין ידיים - אפס את נקודת העיגון כדי שבחזרה לא יהיה drift"""
    global prev_hand_x, prev_hand_y, smooth_dx, smooth_dy
    prev_hand_x = None
    prev_hand_y = None
    smooth_dx   = 0.0
    smooth_dy   = 0.0

def process_frame(frame, h, w):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)    

    if USE_NEW_API:
        mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp = int(time.time() * 1000)
        result    = detector.detect_for_video(mp_image, timestamp)
        if not result.hand_landmarks:
            trails.clear()
            _reset_mouse_anchor()
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
            _reset_mouse_anchor()
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
_FORKED_RELOAD = False  # מוגדר True אחרי fork

def main():
    global prev_time, camera_ready, DEBUG_MODE

    forked = globals().get("_FORKED_RELOAD", False)

    if forked:
        # המודל כבר בRAM — רק מאתחל מצב camera ו-ui
        camera_ready = False
        print("[HOT-RELOAD] model preserved in RAM, restarting camera+ui...")
    else:
        threading.Thread(target=load_model, daemon=True).start()

    threading.Thread(target=run_camera, daemon=True).start()

    root = tk.Tk()

    # אם זה fast-reload — הפעל debug mode אוטומטית
    if FAST_RELOAD or forked:
        DEBUG_MODE = True

    def check_queue():
        try:
            while True:
                msg = ui_queue.get_nowait()
                if msg == "open_settings":
                    _show_settings_window(root)
        except queue.Empty:
            pass
        root.after(100, check_queue)

    root.after(100, check_queue)
    show_loading_window(root, check_queue)
    root.mainloop()

def run_camera():
    global prev_time, camera_ready, settings_open
    set_status("Opening camera...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        set_status("ERROR: Camera not found")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    set_status("Camera ready")
    camera_ready = True

    screenshot_cnt = 0
    dots           = 0
    dot_timer      = time.time()

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

        cv2.imshow("Handy", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        elif cv2.getWindowProperty("Handy", cv2.WND_PROP_VISIBLE) < 1:
            break
        elif key in (ord('g'), ord('G')):
            if not settings_open:
                settings_open = True
                ui_queue.put("open_settings")
        elif key in (ord('r'), ord('R')):
            if DEBUG_MODE:
                _do_hot_reload()
        elif key in (ord('s'), ord('S')):
            fname = f"screenshot_{screenshot_cnt:03d}.png"
            cv2.imwrite(fname, frame)
            print(f"Saved: {fname}")
            screenshot_cnt += 1

    cap.release()
    cv2.destroyAllWindows()
    import os
    os.kill(os.getpid(), 9)

if __name__ == "__main__":
    import sys as _sys
    FAST_RELOAD = "--fast-reload" in _sys.argv

    if "--build" in _sys.argv:
        # בנה את עצמך עם --noconsole
        import subprocess, os, shutil
        script = os.path.abspath(__file__)
        src_dir = os.path.dirname(script)
        pyinstaller = shutil.which("pyinstaller")
        cmd = [pyinstaller or (_sys.executable + " -m PyInstaller")]
        if not pyinstaller:
            cmd = [_sys.executable, "-m", "PyInstaller"]
        cmd += ["--onefile", "--noconsole", "--clean", "--name", "Handy", script]
        print("[BUILD] Running:", " ".join(cmd))
        subprocess.run(cmd, cwd=src_dir)
        # העבר את ה-EXE מ-dist לתיקייה הראשית
        dist_exe = os.path.join(src_dir, "dist", "Handy.exe")
        final_exe = os.path.join(src_dir, "Handy.exe")
        if os.path.exists(dist_exe):
            if os.path.exists(final_exe):
                os.remove(final_exe)
            shutil.move(dist_exe, final_exe)
            print(f"[BUILD] Done: {final_exe}")
        # נקה
        for d in ["build", "dist"]:
            shutil.rmtree(os.path.join(src_dir, d), ignore_errors=True)
        spec = os.path.join(src_dir, "Handy.spec")
        if os.path.exists(spec):
            os.remove(spec)
    else:
        main()