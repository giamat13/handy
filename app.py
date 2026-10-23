import tkinter as tk
from pathlib import Path

import customtkinter as ctk
import cv2
import keyboard
from PIL import Image, ImageTk

import settings
from actions import ACTIONS, GESTURES
import overlay
from camera import Camera
from mouse_control import MouseController
from tracker import Tracker

ICON_PATH = Path(__file__).resolve().parent / "icon.png"
VIEW_W, VIEW_H = 800, 600
SOURCES = {"hand": "יד", "head": "ראש"}


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, cfg):
        super().__init__(master)
        self.title("הגדרות")
        self.geometry("380x640")
        self.cfg = cfg
        self.transient(master)
        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        for key, text in (
            ("show_hand_mesh", "הצג רשת יד"),
            ("show_face_mesh", "הצג נקודות פנים"),
        ):
            var = ctk.BooleanVar(value=cfg[key])
            ctk.CTkSwitch(
                body, text=text, variable=var,
                command=lambda k=key, v=var: self._set(k, v.get()),
            ).pack(anchor="w", padx=12, pady=(10, 0))

        self._label(body, "שליטה בעכבר באמצעות")
        names = list(SOURCES.values())
        ctk.CTkSegmentedButton(
            body, values=names, command=lambda n: self._set("control_source", self._key(SOURCES, n))
        ).pack(anchor="w", padx=12)
        body.winfo_children()[-1].set(SOURCES[cfg["control_source"]])

        self._slider(body, "רגישות", "sensitivity", 0.4, 3.0)
        self._slider(body, "החלקה", "smoothing", 0.0, 1.0)

        self._label(body, "מיפוי מחוות לפעולות")
        for g, gname in GESTURES.items():
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(row, text=gname, width=110, anchor="w").pack(side="left")
            menu = ctk.CTkOptionMenu(
                row, values=list(ACTIONS.values()), width=170,
                command=lambda n, g=g: self._bind(g, n),
            )
            menu.set(ACTIONS[cfg["bindings"].get(g, "none")])
            menu.pack(side="right")

    @staticmethod
    def _key(table, name):
        return next(k for k, v in table.items() if v == name)

    @staticmethod
    def _label(parent, text):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=12, pady=(16, 4)
        )

    def _slider(self, parent, text, key, lo, hi):
        self._label(parent, text)
        s = ctk.CTkSlider(parent, from_=lo, to=hi, command=lambda v: self._set(key, float(v)))
        s.set(self.cfg[key])
        s.pack(fill="x", padx=12)

    def _set(self, key, value):
        self.cfg[key] = value
        settings.save(self.cfg)

    def _bind(self, gesture, action_name):
        self.cfg["bindings"][gesture] = self._key(ACTIONS, action_name)
        settings.save(self.cfg)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Handy 2")
        self.geometry(f"{VIEW_W}x{VIEW_H + 44 + 40}")
        self.resizable(False, False)
        self.cfg = settings.load()
        self.after(250, self._set_icon)  # customtkinter דורס אייקון שמוגדר מוקדם יותר

        top = ctk.CTkFrame(self, height=44, corner_radius=0)
        top.pack(fill="x")
        ctk.CTkButton(top, text="הגדרות", width=90, command=self.open_settings).pack(
            side="right", padx=8, pady=6
        )
        self.control_var = ctk.BooleanVar(value=self.cfg["control_enabled"])
        ctk.CTkSwitch(
            top, text="שליטה בעכבר (F8)", variable=self.control_var, command=self.on_control_switch
        ).pack(side="right", padx=8)
        self.status = ctk.CTkLabel(top, text="")
        self.status.pack(side="left", padx=12)

        self.view = tk.Label(self, bd=0, bg="black")
        self.view.pack()
        self.photo = ImageTk.PhotoImage(Image.new("RGB", (VIEW_W, VIEW_H)))
        self.view.configure(image=self.photo)

        # שורת זיהוי מתחת לווידאו: מה המערכת מזהה כרגע
        self.detect = ctk.CTkLabel(
            self, text="—", height=40, font=ctk.CTkFont(size=20, weight="bold")
        )
        self.detect.pack(fill="x")

        self.camera = Camera().start()
        if not self.camera.opened:
            self.status.configure(text="לא נמצאה מצלמה")
        self.mouse = MouseController(self.cfg)
        self.tracker = Tracker(self.camera, self.mouse).start()

        try:
            keyboard.add_hotkey("f8", self.toggle_control)
            keyboard.add_hotkey("f9", self.mouse.recenter_head)
        except Exception:
            pass  # בלי קיצורי מקלדת עדיין אפשר להשתמש בכפתור

        self.last_id = 0
        self.last_text = None
        self.settings_win = None
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(5, self.tick)

    def _set_icon(self):
        try:
            self._icon = ImageTk.PhotoImage(Image.open(ICON_PATH))
            self.iconphoto(True, self._icon)
        except OSError:
            pass

    def on_control_switch(self):
        self.cfg["control_enabled"] = self.control_var.get()
        settings.save(self.cfg)

    def toggle_control(self):
        self.cfg["control_enabled"] = not self.cfg["control_enabled"]

    def open_settings(self):
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.focus()
            return
        self.settings_win = SettingsWindow(self, self.cfg)

    @staticmethod
    def _detect_text(signs, wink):
        names = [GESTURES[s] for s in signs if s in GESTURES]
        if wink:
            names.insert(0, GESTURES[wink])
        return " + ".join(names) if names else "—"

    def tick(self):
        if self.control_var.get() != self.cfg["control_enabled"]:
            self.control_var.set(self.cfg["control_enabled"])  # שינוי מ-F8
        out = self.tracker.latest(self.last_id)
        if out is not None:
            self.last_id, frame, hands, face, signs, wink = out
            # מגדילים קודם ומציירים אחרי, כדי שהקווים יהיו חדים וחלקים
            img = cv2.resize(frame, (VIEW_W, VIEW_H), interpolation=cv2.INTER_LINEAR)
            if self.cfg["show_face_mesh"] and face is not None:
                overlay.draw_face(img, face)
            if self.cfg["show_hand_mesh"]:
                for h in hands:
                    overlay.draw_hand(img, h)
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            self.photo.paste(Image.fromarray(rgb))
            self.status.configure(text=f"{self.tracker.fps:.0f} FPS")
            text = self._detect_text(signs, wink)
            if text != self.last_text:
                self.last_text = text
                self.detect.configure(text=text)
        self.after(4, self.tick)

    def close(self):
        self.mouse.release()
        self.tracker.stop()
        self.camera.stop()
        self.destroy()
