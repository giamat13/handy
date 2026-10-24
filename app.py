import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk

import actions
import commands
import settings
import view_aids
from actions import ACTIONS, GESTURES, PARAM_ACTIONS
from custom_gestures import CustomGestureStore, Recorder, validate_name
import overlay
from camera import Camera
from mouse_control import MouseController, SLOT_NAMES, screen_size
from tracker import Tracker
from update_ui import UpdateManager
from version import FULL_VERSION

ICON_PATH = Path(__file__).resolve().parent / "icon.png"
VIEW_W, VIEW_H = 800, 600
SOURCES = {"hand": "יד", "head": "ראש"}
HANDS = {"right": "ימין", "left": "שמאל", "both": "שתיהן"}
HAND_SLOT_TEXT = {0: "שמאל", 1: "ימין"}
RECORD_HINTS = {"waiting": "ממתין ליד מול המצלמה…", "moving": "החזק את היד במקום…", "recording": "מקליט…", "done": "ההקלטה הסתיימה"}


class BindingDialog(ctk.CTkToplevel):
    """הזנת קיצור מקשים או תוכנה/סקריפט לקשירה למחווה. הערך נבדק לפני ששומרים."""

    def __init__(self, master, kind, current, on_save, on_cancel):
        super().__init__(master)
        self.kind, self.on_save, self.on_cancel = kind, on_save, on_cancel
        self.title(ACTIONS[kind].rstrip("…"))
        self.geometry("460x" + ("190" if kind == "hotkey" else "300"))
        self.transient(master)
        self.after(150, self._grab)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        cur = current if isinstance(current, dict) else {}
        if kind == "hotkey":
            ctk.CTkLabel(self, text="קיצור מקשים (למשל Ctrl+C, Alt+Tab, Win+D, F5):").pack(anchor="w", padx=16, pady=(16, 4))
            self.keys = ctk.CTkEntry(self, width=420)
            self.keys.insert(0, cur.get("keys", ""))
            self.keys.pack(padx=16)
        else:
            ctk.CTkLabel(self, text="נתיב מלא לתוכנה או לסקריפט:").pack(anchor="w", padx=16, pady=(16, 4))
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=16)
            self.path = ctk.CTkEntry(row, width=330)
            self.path.insert(0, cur.get("path", ""))
            self.path.pack(side="left")
            ctk.CTkButton(row, text="עיון…", width=70, command=self._browse).pack(side="left", padx=(8, 0))
            ctk.CTkLabel(self, text="ארגומנטים (אופציונלי; מירכאות לרווחים):").pack(anchor="w", padx=16, pady=(12, 4))
            self.args = ctk.CTkEntry(self, width=420)
            self.args.insert(0, cur.get("args", ""))
            self.args.pack(padx=16)
            ctk.CTkLabel(self, text="התוכנה נפתחת ישירות, בלי shell: תווים כמו & ו-| הם סתם טקסט.",
                         text_color="gray").pack(anchor="w", padx=16, pady=(8, 0))
        self.error = ctk.CTkLabel(self, text="", text_color="#ff6b6b", wraplength=420, justify="left")
        self.error.pack(anchor="w", padx=16, pady=6)
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=4)
        ctk.CTkButton(btns, text="שמור", width=100, command=self._ok).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="ביטול", width=100, fg_color="gray40", command=self._cancel).pack(side="left", padx=6)

    def _grab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _browse(self):
        path = filedialog.askopenfilename(parent=self)
        if path:
            self.path.delete(0, "end")
            self.path.insert(0, path)

    def _ok(self):
        try:
            if self.kind == "hotkey":
                tokens = commands.parse_hotkey(self.keys.get())
                value = {"type": "hotkey", "keys": commands.hotkey_text(tokens)}
            else:
                value = {"type": "script", **commands.parse_script(self.path.get(), self.args.get())}
        except ValueError as e:
            self.error.configure(text=str(e))
            return
        self.destroy()
        self.on_save(value)

    def _cancel(self):
        self.destroy()
        self.on_cancel()


class CustomGesturesWindow(ctk.CTkToplevel):
    """רשימת המחוות המותאמות: הקלטה, שינוי שם, הקלטה מחדש ומחיקה."""

    def __init__(self, master):
        super().__init__(master)
        self.app = master
        self.title("מחוות מותאמות")
        self.geometry("460x560")
        self.transient(master)
        self.rec = None
        self.protocol("WM_DELETE_WINDOW", self._close)

        ctk.CTkLabel(self, text="תן שם, לחץ על הקלט והחזק את התנוחה מול המצלמה (ללא תנועה).\n"
                                "אחרי ההקלטה אפשר לקשור את המחווה לפעולה בחלון ההגדרות.",
                     justify="left").pack(anchor="w", padx=12, pady=(12, 6))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12)
        self.name = ctk.CTkEntry(row, placeholder_text="שם המחווה", width=240)
        self.name.pack(side="left")
        self.rec_btn = ctk.CTkButton(row, text="הקלט", width=90, command=self._record_new)
        self.rec_btn.pack(side="left", padx=8)
        self.cancel_btn = ctk.CTkButton(row, text="בטל", width=70, fg_color="gray40", command=self._cancel)
        self.bar = ctk.CTkProgressBar(self)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=12, pady=(10, 2))
        self.msg = ctk.CTkLabel(self, text="", wraplength=420, justify="left")
        self.msg.pack(anchor="w", padx=12)
        self.list = ctk.CTkScrollableFrame(self, label_text="המחוות שלי")
        self.list.pack(fill="both", expand=True, padx=12, pady=10)
        self._render()

    # --- הרשימה ---
    def _render(self):
        for w in self.list.winfo_children():
            w.destroy()
        names = self.app.store.names()
        if not names:
            ctk.CTkLabel(self.list, text="עדיין אין מחוות מותאמות").pack(pady=10)
        for gid, name in names.items():
            r = ctk.CTkFrame(self.list, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkLabel(r, text=name, anchor="w", width=130).pack(side="left")
            ctk.CTkButton(r, text="מחק", width=52, fg_color="#a33", command=lambda g=gid: self._delete(g)).pack(side="right", padx=2)
            ctk.CTkButton(r, text="הקלט מחדש", width=84, command=lambda g=gid: self._start(g, names[g])).pack(side="right", padx=2)
            ctk.CTkButton(r, text="שם", width=44, command=lambda g=gid: self._rename(g)).pack(side="right", padx=2)

    def _changed(self):
        self._render()
        self.app.on_custom_changed()

    def _rename(self, gid):
        new = ctk.CTkInputDialog(text="שם חדש:", title="שינוי שם").get_input()
        if new is None:
            return
        try:
            self.app.store.rename(gid, new)
        except ValueError as e:
            self.msg.configure(text=str(e))
            return
        self.msg.configure(text="השם שונה")
        self._changed()

    def _delete(self, gid):
        self.app.store.delete(gid)
        self.app.cfg["bindings"].pop(gid, None)
        settings.save(self.app.cfg)
        self.msg.configure(text="המחווה נמחקה")
        self._changed()

    # --- הקלטה ---
    def _record_new(self):
        try:
            name = validate_name(self.name.get())
            if name.casefold() in {n.casefold() for n in self.app.store.names().values()}:
                raise ValueError("כבר יש מחווה בשם הזה")
        except ValueError as e:
            self.msg.configure(text=str(e))
            return
        self._start(None, name)

    def _start(self, gid, name):
        if self.rec is not None:
            return
        if not self.app.camera.opened:
            self.msg.configure(text="לא נמצאה מצלמה")
            return
        self.rec = Recorder(name, gid)
        self.app.tracker.recorder = self.rec  # בזמן ההקלטה אף פעולה לא מופעלת
        self.rec_btn.configure(state="disabled")
        self.cancel_btn.pack(side="left")
        self._poll()

    def _poll(self):
        rec = self.rec
        if rec is None:
            return
        self.bar.set(rec.progress)
        if not rec.done:
            self.msg.configure(text=RECORD_HINTS.get(rec.hint, ""))
            self.after(100, self._poll)
            return
        self._end_recording()
        try:
            if rec.gesture_id:
                self.app.store.rerecord(rec.gesture_id, rec)
            else:
                self.app.store.add(rec.name, rec)
            self.msg.configure(text=f"'{rec.name}' נשמרה. אפשר לקשור אותה לפעולה בהגדרות.")
            self.name.delete(0, "end")
        except ValueError as e:
            self.msg.configure(text=str(e))
        self._changed()

    def _end_recording(self):
        self.app.tracker.recorder = None
        self.rec = None
        self.rec_btn.configure(state="normal")
        self.cancel_btn.pack_forget()
        self.bar.set(0)

    def _cancel(self):
        self._end_recording()
        self.msg.configure(text="ההקלטה בוטלה")

    def _close(self):
        self._end_recording()
        self.destroy()


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, cfg):
        super().__init__(master)
        self.title("הגדרות")
        self.geometry("420x720")
        self.cfg = cfg
        self.app = master
        self.transient(master)
        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        for key, text in (
            ("show_hand_mesh", "הצג רשת יד"),
            ("show_face_mesh", "הצג נקודות פנים"),
            ("show_trail", "הצג שובל אחרי הנקודה השולטת"),
            ("show_coords", "הצג קואורדינטות של הסמן"),
        ):
            var = ctk.BooleanVar(value=cfg[key])
            ctk.CTkSwitch(
                body, text=text, variable=var,
                command=lambda k=key, v=var: self._set(k, v.get()),
            ).pack(anchor="w", padx=12, pady=(10, 0))

        for key, text in (
            ("auto_update_check", "בדוק עדכונים אוטומטית"),
            ("beta_channel", "הצע גם גרסאות בטא"),
        ):
            var = ctk.BooleanVar(value=cfg[key])
            ctk.CTkSwitch(
                body, text=text, variable=var,
                command=lambda k=key, v=var: self._set(k, v.get()),
            ).pack(anchor="w", padx=12, pady=(10, 0))
        ctk.CTkButton(
            body, text=f"בדוק עדכונים עכשיו (גרסה {FULL_VERSION})", command=lambda: master.updates.check(manual=True)
        ).pack(anchor="w", padx=12, pady=(10, 0))

        self._label(body, "שליטה בעכבר באמצעות")
        seg = ctk.CTkSegmentedButton(
            body, values=list(SOURCES.values()), command=lambda n: self._set("control_source", self._key(SOURCES, n))
        )
        seg.pack(anchor="w", padx=12)
        seg.set(SOURCES[cfg["control_source"]])

        self._label(body, "איזו יד שולטת")
        seg = ctk.CTkSegmentedButton(
            body, values=list(HANDS.values()), command=lambda n: self._set("control_hand", self._key(HANDS, n))
        )
        seg.pack(anchor="w", padx=12)
        seg.set(HANDS[cfg["control_hand"]])

        self._slider(body, "רגישות", "sensitivity", 0.4, 3.0)
        self._slider(body, "החלקה", "smoothing", 0.0, 1.0)

        self._label(body, "מחוות מותאמות")
        ctk.CTkButton(body, text="ניהול והקלטה של מחוות…", command=master.open_custom).pack(anchor="w", padx=12)

        self._label(body, "מיפוי מחוות לפעולות")
        self.map_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.map_frame.pack(fill="x")
        self.rebuild_mapping()

    def rebuild_mapping(self):
        """בונה מחדש את שורות המיפוי: המובנות והמותאמות (נקרא גם כשמחווה מותאמת נוספה, נמחקה או שונה שמה)."""
        for w in self.map_frame.winfo_children():
            w.destroy()
        for g, gname in self.app.gesture_names().items():
            row = ctk.CTkFrame(self.map_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(row, text=gname, width=110, anchor="w").pack(side="left")
            menu = ctk.CTkOptionMenu(row, values=list(ACTIONS.values()), width=190)
            menu.configure(command=lambda n, g=g, m=menu: self._choose_action(g, n, m))
            menu.set(actions.binding_text(self.cfg["bindings"].get(g, "none")))
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

    def _choose_action(self, gesture, action_name, menu):  # לא _bind: זה שם של שיטה פנימית של tkinter
        kind = self._key(ACTIONS, action_name)
        if kind in PARAM_ACTIONS:
            current = self.cfg["bindings"].get(gesture)
            BindingDialog(
                self, kind, current if actions.binding_kind(current) == kind else None,
                on_save=lambda value: self._save_binding(gesture, value, menu),
                on_cancel=lambda: menu.set(actions.binding_text(self.cfg["bindings"].get(gesture, "none"))),
            )
        else:
            self._save_binding(gesture, kind, menu)

    def _save_binding(self, gesture, value, menu):
        self.cfg["bindings"][gesture] = value
        settings.save(self.cfg)
        menu.set(actions.binding_text(value))


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(f"Handy 2 {FULL_VERSION}")
        self.geometry(f"{VIEW_W}x{VIEW_H + 44 + 40}")
        self.resizable(False, False)
        self.cfg = settings.load()
        self.store = CustomGestureStore(settings.CUSTOM_PATH)
        self.after(250, self._set_icon)  # customtkinter דורס אייקון שמוגדר מוקדם יותר
        self.updates = UpdateManager(self, self.cfg)
        if not self.updates.startup():  # עדכון שנקטע: סקריפט השחזור מחזיר את הגרסה הקודמת ומפעיל מחדש
            self.withdraw()
            return

        top = ctk.CTkFrame(self, height=44, corner_radius=0)
        top.pack(fill="x")
        ctk.CTkButton(top, text="הגדרות", width=90, command=self.open_settings).pack(
            side="right", padx=8, pady=6
        )
        ctk.CTkButton(top, text="מחוות", width=80, command=self.open_custom).pack(side="right", padx=0, pady=6)
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
        self.mouse = MouseController(self.cfg, screen=screen_size(self))
        self.tracker = Tracker(self.camera, self.mouse, self.store).start()
        self.trail = view_aids.Trail()

        self._hotkeys = None
        self._register_hotkeys()

        self.last_id = 0
        self.last_text = None
        self.settings_win = None
        self.custom_win = None
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(5, self.tick)

    def _register_hotkeys(self):
        """F8 מחליף מצב שליטה, F9 מרכז את הראש. ב-Windows דרך ספריית keyboard, בשאר המערכות דרך pynput."""
        try:
            if sys.platform == "win32":
                import keyboard

                keyboard.add_hotkey("f8", self.toggle_control)
                keyboard.add_hotkey("f9", self.mouse.recenter_head)
            else:
                from pynput.keyboard import GlobalHotKeys

                self._hotkeys = GlobalHotKeys({"<f8>": self.toggle_control, "<f9>": self.mouse.recenter_head})
                self._hotkeys.start()
        except Exception:
            pass  # בלי קיצורי מקלדת עדיין אפשר להשתמש בכפתור (ב-Linux/macOS נדרשת הרשאה)

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

    def gesture_names(self):
        """כל המחוות שאפשר למפות: המובנות, ואחריהן המותאמות (לפי המזהה שלהן)."""
        return {**GESTURES, **self.store.names()}

    def open_settings(self):
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.focus()
            return
        self.settings_win = SettingsWindow(self, self.cfg)

    def open_custom(self):
        if self.custom_win is not None and self.custom_win.winfo_exists():
            self.custom_win.focus()
            return
        self.custom_win = CustomGesturesWindow(self)

    def on_custom_changed(self):
        self.last_text = None
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.rebuild_mapping()

    def _detect_text(self, signs, wink):
        table = self.gesture_names()
        names = [table[s] for s in signs if s in table]
        if wink:
            names.insert(0, GESTURES[wink])
        return " + ".join(names) if names else "—"

    def _status_text(self):
        text = f"{self.tracker.fps:.0f} FPS"
        if self.cfg["control_source"] == "hand":
            text += f"  |  יד שולטת: {HANDS[self.cfg['control_hand']]}"
            slot = self.mouse.active_slot
            if slot is not None and self.cfg["control_hand"] == "both":
                text += f" ({HAND_SLOT_TEXT[slot]} פעילה)"
        return text

    def tick(self):
        if self.control_var.get() != self.cfg["control_enabled"]:
            self.control_var.set(self.cfg["control_enabled"])  # שינוי מ-F8 או ממחוות
        out = self.tracker.latest(self.last_id)
        if out is not None:
            self.last_id = out.id
            # מגדילים קודם ומציירים אחרי, כדי שהקווים יהיו חדים וחלקים
            img = cv2.resize(out.frame, (VIEW_W, VIEW_H), interpolation=cv2.INTER_LINEAR)
            if self.cfg["show_face_mesh"] and out.face is not None:
                overlay.draw_face(img, out.face)
            if self.cfg["show_hand_mesh"]:
                active = self.mouse.active_slot
                for h, slot in zip(out.hands, out.slots):
                    overlay.draw_hand(img, h, active=slot == active and self.cfg["control_source"] == "hand")
            now = time.perf_counter()
            if self.cfg["show_trail"]:
                self.trail.push(out.point, now)
                view_aids.draw_trail(img, self.trail.points(now))
            else:
                self.trail.clear()
            if self.cfg["show_coords"]:
                view_aids.draw_coords(img, view_aids.format_coords(self.mouse.cursor_position()))
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            self.photo.paste(Image.fromarray(rgb))
            self.status.configure(text=self._status_text())
            text = self._detect_text(out.signs, out.wink)
            if text != self.last_text:
                self.last_text = text
                self.detect.configure(text=text)
        self.after(4, self.tick)

    def close(self):
        if self._hotkeys is not None:
            self._hotkeys.stop()
        self.mouse.release()
        self.tracker.stop()
        self.camera.stop()
        self.destroy()
