"""Main window: live camera preview with hand/face mesh, plus settings (customtkinter)."""
import tkinter as tk

import cv2
import customtkinter as ctk
from PIL import Image, ImageTk

import config
from core.actions import ACTION_LABELS
from core.engine import Engine
from ui.overlay import LandmarkSmoother, draw_overlay

PREVIEW_W, PREVIEW_H = 560, 420

BUILTIN_GESTURES = {
    "pinch": "Pinch (thumb + index)",
    "pinch_middle": "Pinch (thumb + middle)",
    "two_fingers": "Two fingers up",
    "fist": "Fist",
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Handy 2")
        self.geometry("1120x560")
        self.settings = config.load()
        self.engine = Engine(self.settings)
        self.smoother = LandmarkSmoother()
        self.preview_frames = 0
        self._last_seq = -1
        self._photo = None

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", padx=12, pady=12)
        self.preview = tk.Label(left, bg="black", bd=0, highlightthickness=0)
        self._photo = ImageTk.PhotoImage(Image.new("RGB", (PREVIEW_W, PREVIEW_H)))
        self.preview.configure(image=self._photo)
        self.preview.pack()
        self.status = ctk.CTkLabel(left, text="Starting camera...", font=ctk.CTkFont(size=15, weight="bold"))
        self.status.pack(pady=(10, 4))
        self.toggle_btn = ctk.CTkButton(left, text="Start control", command=self.toggle)
        self.toggle_btn.pack(pady=4)

        tabs = ctk.CTkTabview(self, width=460)
        tabs.pack(side="right", fill="both", expand=True, padx=(0, 12), pady=12)
        self._build_settings(tabs.add("Settings"))
        self.map_tab = tabs.add("Gestures")
        self._build_map()
        self._build_record(tabs.add("Record"))

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.engine.start()  # camera + tracking run from the start; mouse control is a separate switch
        self.after(8, self._update_preview)
        self.after(200, self.refresh)

    # --- live preview ----------------------------------------------------
    def _update_preview(self):
        latest = self.engine.latest
        if latest and latest[0] != self._last_seq:
            self._last_seq, frame, res = latest
            img = cv2.resize(frame, (PREVIEW_W, PREVIEW_H), interpolation=cv2.INTER_LINEAR)
            draw_overlay(img, res, self.settings["show_hand_mesh"], self.settings["show_face_mesh"], self.smoother)
            self._photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            self.preview.configure(image=self._photo)
            self.preview_frames += 1
        self.after(8, self._update_preview)

    # --- settings tab ----------------------------------------------------
    def _build_settings(self, tab):
        s = self.settings
        self._row(tab, "Control hand", ctk.CTkOptionMenu(
            tab, values=["Right", "Left"], command=lambda v: self.set("control_hand", v)), s["control_hand"])
        self._row(tab, "Move cursor with", ctk.CTkOptionMenu(
            tab, values=["Hand", "Head"], command=lambda v: self.set("move_source", v)), s["move_source"])
        self._row(tab, "Sensitivity", ctk.CTkSlider(
            tab, from_=0.5, to=4.0, command=lambda v: self.set("sensitivity", round(v, 2))), s["sensitivity"])
        self._row(tab, "Smoothing", ctk.CTkSlider(
            tab, from_=0.0, to=0.9, command=lambda v: self.set("smoothing", round(v, 2))), s["smoothing"])
        self._switches = {}
        for key, label in (("show_hand_mesh", "Show hand mesh"), ("show_face_mesh", "Show face mesh")):
            sw = ctk.CTkSwitch(tab, text=label, command=lambda k=key: self.set(k, bool(self._switches[k].get())))
            sw.select() if s[key] else sw.deselect()
            sw.pack(anchor="w", padx=14, pady=6)
            self._switches[key] = sw
        ctk.CTkLabel(tab, text=f"Emergency toggle: {s['kill_switch']}").pack(pady=10)

    def _row(self, parent, label, widget, value):
        row = ctk.CTkFrame(parent)
        row.pack(fill="x", pady=6, padx=6)
        ctk.CTkLabel(row, text=label, width=140, anchor="w").pack(side="left", padx=8)
        widget.pack(side="right", padx=8, fill="x", expand=isinstance(widget, ctk.CTkSlider))
        widget.set(value)

    def set(self, key, value):
        self.settings[key] = value
        self.engine.apply_settings()
        config.save(self.settings)

    # --- gesture mapping tab ---------------------------------------------
    def _build_map(self):
        for w in self.map_tab.winfo_children():
            w.destroy()
        labels = list(ACTION_LABELS.values())
        by_label = {v: k for k, v in ACTION_LABELS.items()}
        names = dict(BUILTIN_GESTURES)
        names.update({n: f"Custom: {n}" for n in self.settings["custom_gestures"]})
        for gid, title in names.items():
            row = ctk.CTkFrame(self.map_tab)
            row.pack(fill="x", pady=4, padx=6)
            ctk.CTkLabel(row, text=title, width=150, anchor="w").pack(side="left", padx=8)
            menu = ctk.CTkOptionMenu(row, values=labels, width=200, command=lambda v, g=gid: self._map(g, by_label[v]))
            menu.set(ACTION_LABELS.get(self.settings["gesture_map"].get(gid, "none"), "None"))
            menu.pack(side="right", padx=8)

    def _map(self, gesture, action):
        self.settings["gesture_map"][gesture] = action
        config.save(self.settings)

    # --- record tab ------------------------------------------------------
    def _build_record(self, tab):
        ctk.CTkLabel(tab, text="Name the gesture, press Record, then hold the pose\n"
                               "with your control hand in front of the camera.",
                     justify="left").pack(pady=8)
        self.name_entry = ctk.CTkEntry(tab, placeholder_text="Gesture name")
        self.name_entry.pack(pady=6)
        self.rec_btn = ctk.CTkButton(tab, text="Record", command=self.record)
        self.rec_btn.pack(pady=6)
        self.rec_bar = ctk.CTkProgressBar(tab)
        self.rec_bar.set(0)
        self.rec_bar.pack(pady=6, fill="x", padx=20)
        self.rec_msg = ctk.CTkLabel(tab, text="")
        self.rec_msg.pack()

    def record(self):
        name = self.name_entry.get().strip()
        if not name:
            self.rec_msg.configure(text="Enter a name first")
            return
        self.engine.start()  # no-op while the camera is already running
        self.engine.start_recording(name)
        self.rec_msg.configure(text="Recording... hold the pose")

    # --- runtime ---------------------------------------------------------
    def toggle(self):
        """Turn mouse/keyboard control on or off. The preview keeps running either way."""
        self.engine.start()  # retry the camera if it failed earlier
        self.engine.control = not self.engine.control
        self.engine.mouse.smoother.reset()
        self.toggle_btn.configure(text="Stop control" if self.engine.control else "Start control")

    def refresh(self):
        e = self.engine
        text = e.status + (f"  |  last gesture: {e.last_gesture}" if e.last_gesture else "")
        if e.running and e.frames_processed:
            text += f"  |  {e.process_ms:.0f} ms/frame"
        self.status.configure(text=text)
        if e.recorder:
            self.rec_bar.set(e.recorder.progress)
            if e.recorder.done:
                name = e.finish_recording()
                self.rec_bar.set(0)
                self.rec_msg.configure(text=f"Saved '{name}'. Map it in the Gestures tab.")
                config.save(self.settings)
                self._build_map()
        self.after(200, self.refresh)

    def on_close(self):
        self.engine.stop()
        config.save(self.settings)
        self.destroy()


def run():
    ctk.set_appearance_mode("system")
    App().mainloop()
