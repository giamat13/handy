"""Settings window (CustomTkinter).

Sliders display a live value label so the user always knows the current number.
"""

import tkinter as tk

import customtkinter as ctk

import handy.state as state
from handy.settings_io import save as save_settings

_BG = "#0f0f0f"
_ACC = "#00ff96"
_FG = "#eeeeee"
_DIM = "#555555"


def show_settings_window(root: ctk.CTk) -> None:
    """Open the settings window if one is not already open."""
    if state.settings_open:
        print("[SETTINGS] open request ignored (already open)")
        return
    state.settings_open = True
    print("[SETTINGS] opening settings window")
    try:
        _build(root)
    except Exception as exc:
        state.settings_open = False
        print(f"[SETTINGS] failed to open: {exc}")
        raise


def _build(root: ctk.CTk) -> None:
    win = ctk.CTkToplevel(root)
    win.title("Handy - Settings")
    win.resizable(False, True)
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win_h = min(620, sh - 80)
    win_w = 500
    win.geometry(f"{win_w}x{win_h}+{(sw - win_w) // 2}+{(sh - win_h) // 2}")
    win.configure(fg_color=_BG)
    win.lift()
    win.focus_force()

    # ── Scrollable content ─────────────────────────────────────────
    scroll = ctk.CTkScrollableFrame(win, fg_color=_BG)
    scroll.pack(fill="both", expand=True)

    ctk.CTkLabel(
        scroll, text="HANDY  SETTINGS",
        font=ctk.CTkFont("Consolas", 14, "bold"),
        text_color=_ACC,
    ).pack(pady=(18, 12))

    grid = ctk.CTkFrame(scroll, fg_color=_BG)
    grid.pack(fill="x", padx=30)
    grid.columnconfigure(1, weight=1)
    grid.columnconfigure(2, minsize=44)

    # ── Widget factory helpers ─────────────────────────────────────
    _row = [0]

    def next_row() -> int:
        r = _row[0]
        _row[0] += 1
        return r

    def sep():
        r = next_row()
        ctk.CTkFrame(grid, fg_color="#333333", height=1).grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=8,
        )

    def section(text: str):
        r = next_row()
        ctk.CTkLabel(
            grid, text=text,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color=_ACC, anchor="w",
        ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(4, 2))

    def add_slider(label: str, var, from_: float, to: float,
                   steps: int = 100, fmt: str = "{:.0f}") -> ctk.CTkSlider:
        r = next_row()
        ctk.CTkLabel(
            grid, text=label,
            font=ctk.CTkFont("Consolas", 10),
            text_color=_FG, anchor="w",
        ).grid(row=r, column=0, pady=4, sticky="w")

        val_lbl = ctk.CTkLabel(
            grid, text=fmt.format(var.get()),
            font=ctk.CTkFont("Consolas", 10),
            text_color=_ACC, width=40, anchor="e",
        )
        val_lbl.grid(row=r, column=2, pady=4, sticky="e")

        def on_change(v):
            var.set(v)
            val_lbl.configure(text=fmt.format(v))

        s = ctk.CTkSlider(
            grid, from_=from_, to=to, number_of_steps=steps,
            variable=var, command=on_change,
            button_color=_ACC, button_hover_color="#00cc77",
            progress_color=_ACC,
        )
        s.grid(row=r, column=1, pady=4, sticky="ew", padx=(8, 4))
        return s

    def add_check(label: str, var: tk.BooleanVar) -> ctk.CTkCheckBox:
        r = next_row()
        cb = ctk.CTkCheckBox(
            grid, text=label, variable=var,
            font=ctk.CTkFont("Consolas", 10),
            text_color=_FG,
            checkmark_color="#000000",
            fg_color=_ACC, hover_color="#00cc77",
            border_color=_ACC,
        )
        cb.grid(row=r, column=0, columnspan=3, pady=4, sticky="w")
        return cb

    # ── Variables ──────────────────────────────────────────────────
    landmarks_var = tk.BooleanVar(value=state.SHOW_LANDMARKS)
    trail_var    = tk.BooleanVar(value=state.SHOW_TRAIL)
    coords_var   = tk.BooleanVar(value=state.SHOW_COORDS)
    mouse_var    = tk.BooleanVar(value=state.MOUSE_ENABLED)
    smooth_var   = tk.DoubleVar(value=state.SMOOTH)
    speed_var    = tk.DoubleVar(value=state.SPEED)
    dead_var     = tk.DoubleVar(value=state.DEADZONE)
    cooldown_var = tk.DoubleVar(value=state.CLICK_COOLDOWN)
    hand_var     = tk.StringVar(value=state.CONTROL_HAND)
    dyn_var      = tk.BooleanVar(value=state.DYNAMIC_SPEED)
    curve_var    = tk.DoubleVar(value=state.SPEED_CURVE)
    debug_var    = tk.BooleanVar(value=state.DEBUG_MODE)

    # ── Display ────────────────────────────────────────────────────
    section("▼  Display")
    add_check("Show landmarks", landmarks_var)
    add_check("Show trail", trail_var)
    add_check("Show coordinates", coords_var)

    sep()

    # ── Mouse control ──────────────────────────────────────────────
    section("▼  Mouse Control")
    mouse_cb = add_check("Enable mouse", mouse_var)

    s_smooth   = add_slider("Smoothing (1–100)", smooth_var, 1, 100, 99)
    s_speed    = add_slider("Speed (1–10)",      speed_var,  1, 10,  9)
    dyn_cb     = add_check("Dynamic speed", dyn_var)
    s_curve    = add_slider("Speed curve (1–4)", curve_var,  1.0, 4.0, 30, "{:.1f}")
    s_dead     = add_slider("Deadzone (px)",     dead_var,   0,  40,  40)
    s_cooldown = add_slider("Click cooldown (s)", cooldown_var, 0.1, 2.0, 19, "{:.1f}")

    # Control hand radio buttons
    r = next_row()
    ctk.CTkLabel(
        grid, text="Control hand",
        font=ctk.CTkFont("Consolas", 10),
        text_color=_FG, anchor="w",
    ).grid(row=r, column=0, pady=4, sticky="w")
    radio_frame = ctk.CTkFrame(grid, fg_color=_BG)
    radio_frame.grid(row=r, column=1, columnspan=2, sticky="w")
    radio_btns = []
    for val in ("Right", "Left", "Both"):
        rb = ctk.CTkRadioButton(
            radio_frame, text=val, variable=hand_var, value=val,
            font=ctk.CTkFont("Consolas", 10),
            text_color=_FG,
            fg_color=_ACC, hover_color="#00cc77",
            border_color=_ACC,
        )
        rb.pack(side="left", padx=6)
        radio_btns.append(rb)

    mouse_dependents = [s_smooth, s_speed, dyn_cb, s_curve, s_dead, s_cooldown] + radio_btns

    def update_mouse_state(*_):
        new_state = "normal" if mouse_var.get() else "disabled"
        for w in mouse_dependents:
            w.configure(state=new_state)

    mouse_var.trace_add("write", update_mouse_state)
    update_mouse_state()

    sep()

    # ── Developer ──────────────────────────────────────────────────
    section("▼  Developer")
    add_check("Debug mode  (R = hot reload)", debug_var)

    # ── Apply ──────────────────────────────────────────────────────
    def apply():
        state.SMOOTH         = int(smooth_var.get())
        state.SPEED          = int(speed_var.get())
        state.DEADZONE       = int(dead_var.get())
        state.CLICK_COOLDOWN = round(cooldown_var.get(), 1)
        state.MOUSE_ENABLED  = mouse_var.get()
        state.SHOW_LANDMARKS  = landmarks_var.get()
        state.SHOW_TRAIL     = trail_var.get()
        state.SHOW_COORDS    = coords_var.get()
        state.CONTROL_HAND   = hand_var.get()
        state.DYNAMIC_SPEED  = dyn_var.get()
        state.SPEED_CURVE    = round(curve_var.get(), 1)
        state.DEBUG_MODE     = debug_var.get()
        state.settings_open  = False
        save_settings()
        print("[SETTINGS] apply")
        win.destroy()

    def on_close():
        state.settings_open = False
        print("[SETTINGS] closed")
        win.destroy()

    bottom_row = ctk.CTkFrame(scroll, fg_color=_BG)
    bottom_row.pack(pady=16)

    ctk.CTkButton(
        bottom_row, text="Apply", command=apply,
        fg_color=_ACC, text_color="#000000",
        font=ctk.CTkFont("Consolas", 11, "bold"),
        hover_color="#00cc77",
        corner_radius=6,
        width=120,
    ).pack(side="left", padx=(0, 10))

    def open_trainer():
        win.destroy()
        state.settings_open = False
        if not state.gesture_trainer_open:
            state.ui_queue.put("open_gesture_trainer")

    ctk.CTkButton(
        bottom_row,
        text="Gesture Trainer →",
        command=open_trainer,
        fg_color="#1e1e1e",
        hover_color="#1e3a2f",
        text_color=_ACC,
        font=ctk.CTkFont("Consolas", 11, "bold"),
        border_width=1,
        border_color=_ACC,
        corner_radius=6,
        width=160,
    ).pack(side="left")

    win.protocol("WM_DELETE_WINDOW", on_close)
