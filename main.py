"""
Handy - Hand Detection & Gesture Tracking
==========================================
Requirements: pip install -r requirements.txt
Run:          python main.py
"""

import sys
import threading
import queue

import customtkinter as ctk

import handy.state as state
from handy.camera import run_camera
from handy.model import load_model
from handy.mouse import init_screen_size
from handy.settings_io import load as load_settings
from handy.ui.loading import show_loading_window
from handy.ui.settings import show_settings_window
from handy.ui.gesture_trainer import show_gesture_trainer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


def _check_queue(root: ctk.CTk) -> None:
    try:
        while True:
            msg = state.ui_queue.get_nowait()
            print(f"[UI] queue message: {msg}")
            if msg == "open_settings":
                show_settings_window(root)
            elif msg == "open_gesture_trainer":
                show_gesture_trainer(root)
    except queue.Empty:
        pass
    except Exception as exc:
        print(f"[UI] queue handler error: {exc}")
    root.after(100, lambda: _check_queue(root))


def main() -> None:
    state.FAST_RELOAD = "--fast-reload" in sys.argv

    if state.FAST_RELOAD:
        state.DEBUG_MODE = True

    load_settings()

    init_screen_size()

    threading.Thread(target=load_model, daemon=True).start()
    threading.Thread(target=run_camera, daemon=True).start()

    root = ctk.CTk()
    root.after(100, lambda: _check_queue(root))
    show_loading_window(root)
    root.mainloop()


if __name__ == "__main__":
    main()
