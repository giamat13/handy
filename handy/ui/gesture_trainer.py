"""
Gesture Trainer window (CustomTkinter).

Layout
------
┌─────────────────────────────────────────────────────────┐
│  ●  GESTURE TRAINER                                     │
├─────────────────────────┬───────────────────────────────┤
│  Gesture List           │  Edit Panel                   │
│  ─────────────────────  │  ─────────────────────────    │
│  ▼ Custom Gestures      │  Name  [__________________]   │
│    ► My Wave            │                               │
│    ► Peace Sign         │  Samples  ████████░░  20/30   │
│  [+ Add New]            │  [● Record]  [✕ Clear]        │
│                         │  Status: Trained ✓            │
│  ▼ Built-in Gestures    │  ─────────────────────────    │
│    ► Fist               │  Action                       │
│    ► Open Hand          │  ◉ None                       │
│    ► One Finger         │  ○ Hotkey   [ctrl+shift+h]    │
│    ...                  │  ○ Script   [Browse…]         │
│                         │  ─────────────────────────    │
│                         │  [  Save  ]  [ Delete ]       │
└─────────────────────────┴───────────────────────────────┘
"""

from __future__ import annotations

import threading
import tkinter as tk
import tkinter.filedialog as fd
from typing import Optional

import customtkinter as ctk

import handy.state as state
from handy.actions import execute_action, reset_cooldown, validate_hotkey, validate_script
from handy.custom_gestures import BUILTIN_ENTRIES, RECORD_SAMPLES, GestureTemplate
from handy.settings_io import save as save_settings

# ── Palette (matches settings window) ─────────────────────────────────────
_BG  = "#0f0f0f"
_ACC = "#00ff96"
_FG  = "#eeeeee"
_DIM = "#555555"
_ERR = "#ff5555"
_YEL = "#ffdd55"

# ── Recording state machine ────────────────────────────────────────────────
_IDLE      = "idle"
_RECORDING = "recording"
_DONE      = "done"


def show_gesture_trainer(root: ctk.CTk) -> None:
    """Open the gesture trainer window; only one instance at a time."""
    if state.gesture_trainer_open:
        print("[TRAINER] open request ignored (already open)")
        return
    state.gesture_trainer_open = True
    print("[TRAINER] opening gesture trainer window")
    try:
        _GestureTrainer(root)
    except Exception as exc:
        state.gesture_trainer_open = False
        print(f"[TRAINER] failed to open: {exc}")
        raise


# ── Main window class ──────────────────────────────────────────────────────

class _GestureTrainer:
    """
    Self-contained gesture trainer window.
    Writes directly to state.CUSTOM_GESTURE_TEMPLATES and state.GESTURE_BINDINGS.
    """

    def __init__(self, root: ctk.CTk) -> None:
        self._root = root
        self._rec_state = _IDLE
        self._sel_name: Optional[str] = None   # currently selected gesture name
        self._sel_is_builtin = False

        # ── Build window ───────────────────────────────────────────────────
        self._win = ctk.CTkToplevel(root)
        self._win.title("Handy – Gesture Trainer")
        self._win.resizable(True, True)
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        ww, wh = 820, 560
        self._win.geometry(f"{ww}x{wh}+{(sw-ww)//2}+{(sh-wh)//2}")
        self._win.configure(fg_color=_BG)
        self._win.lift()
        self._win.focus_force()
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_list()
        self._poll_recording()   # start recording-status polling loop

    # ── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        win = self._win

        # Title bar
        title_frame = ctk.CTkFrame(win, fg_color="#1a1a1a", corner_radius=0)
        title_frame.pack(fill="x")
        ctk.CTkLabel(
            title_frame,
            text="●  GESTURE TRAINER",
            font=ctk.CTkFont("Consolas", 14, "bold"),
            text_color=_ACC,
        ).pack(side="left", padx=18, pady=10)

        # Main body: two columns
        body = ctk.CTkFrame(win, fg_color=_BG)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, minsize=220)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self._build_list_panel(body)
        self._build_edit_panel(body)

    def _build_list_panel(self, parent) -> None:
        """Left panel: gesture list."""
        frame = ctk.CTkFrame(parent, fg_color="#161616", corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew")

        scroll = ctk.CTkScrollableFrame(frame, fg_color="#161616")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self._list_scroll = scroll

        # "Add new" button at the bottom
        add_btn = ctk.CTkButton(
            frame,
            text="+ Add Custom Gesture",
            command=self._add_new,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            text_color=_ACC,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            border_width=1,
            border_color=_ACC,
            corner_radius=4,
            height=32,
        )
        add_btn.pack(fill="x", padx=8, pady=6)

    def _build_edit_panel(self, parent) -> None:
        """Right panel: edit area."""
        frame = ctk.CTkFrame(parent, fg_color=_BG)
        frame.grid(row=0, column=1, sticky="nsew", padx=(1, 0))

        scroll = ctk.CTkScrollableFrame(frame, fg_color=_BG)
        scroll.pack(fill="both", expand=True, padx=16, pady=12)
        self._edit_scroll = scroll
        self._edit_widgets: list = []   # kept for enable/disable

        # ── Name ──────────────────────────────────────────────────────────
        self._section("Gesture Name")
        self._name_var = tk.StringVar()
        self._name_entry = ctk.CTkEntry(
            scroll,
            textvariable=self._name_var,
            placeholder_text="e.g.  My Wave",
            font=ctk.CTkFont("Consolas", 11),
            fg_color="#1a1a1a",
            text_color=_FG,
            border_color=_DIM,
        )
        self._name_entry.pack(fill="x", pady=(2, 10))

        self._sep()

        # ── Recording ─────────────────────────────────────────────────────
        self._section("Training Samples")
        self._sample_label = ctk.CTkLabel(
            scroll,
            text="0 / 30 samples",
            font=ctk.CTkFont("Consolas", 10),
            text_color=_DIM,
            anchor="w",
        )
        self._sample_label.pack(fill="x")

        self._progress = ctk.CTkProgressBar(
            scroll, progress_color=_ACC, fg_color="#333",
        )
        self._progress.set(0)
        self._progress.pack(fill="x", pady=4)

        btn_row = ctk.CTkFrame(scroll, fg_color=_BG)
        btn_row.pack(fill="x", pady=(2, 4))
        self._rec_btn = ctk.CTkButton(
            btn_row,
            text="● Record",
            command=self._toggle_record,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            text_color=_YEL,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            border_width=1,
            border_color=_YEL,
            corner_radius=4,
            width=120,
        )
        self._rec_btn.pack(side="left", padx=(0, 8))

        self._clear_btn = ctk.CTkButton(
            btn_row,
            text="✕ Clear",
            command=self._clear_samples,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            text_color=_ERR,
            font=ctk.CTkFont("Consolas", 10),
            border_width=1,
            border_color=_ERR,
            corner_radius=4,
            width=80,
        )
        self._clear_btn.pack(side="left")

        self._status_label = ctk.CTkLabel(
            scroll,
            text="Select or create a gesture to begin",
            font=ctk.CTkFont("Consolas", 10),
            text_color=_DIM,
            anchor="w",
        )
        self._status_label.pack(fill="x", pady=(2, 10))

        self._sep()

        # ── Action binding ────────────────────────────────────────────────
        self._section("Action on Gesture Detected")

        self._action_var = tk.StringVar(value="none")
        for val, label in [("none", "None"), ("hotkey", "Hotkey"), ("script", "Script")]:
            rb = ctk.CTkRadioButton(
                scroll,
                text=label,
                variable=self._action_var,
                value=val,
                command=self._on_action_type_change,
                font=ctk.CTkFont("Consolas", 10),
                text_color=_FG,
                fg_color=_ACC,
                hover_color="#00cc77",
                border_color=_ACC,
            )
            rb.pack(anchor="w", pady=2)

        self._action_value_var = tk.StringVar()
        self._action_row = ctk.CTkFrame(scroll, fg_color=_BG)
        self._action_row.pack(fill="x", pady=(4, 0))

        self._action_entry = ctk.CTkEntry(
            self._action_row,
            textvariable=self._action_value_var,
            placeholder_text='e.g.  ctrl+shift+h',
            font=ctk.CTkFont("Consolas", 10),
            fg_color="#1a1a1a",
            text_color=_FG,
            border_color=_DIM,
        )
        self._action_entry.pack(side="left", fill="x", expand=True)

        self._browse_btn = ctk.CTkButton(
            self._action_row,
            text="Browse…",
            command=self._browse_script,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            text_color=_FG,
            font=ctk.CTkFont("Consolas", 10),
            width=80,
            corner_radius=4,
        )
        # browse btn is hidden by default; shown when type == "script"
        self._browse_btn.pack(side="left", padx=(6, 0))
        self._browse_btn.pack_forget()

        self._action_hint = ctk.CTkLabel(
            scroll,
            text="",
            font=ctk.CTkFont("Consolas", 9),
            text_color=_DIM,
            anchor="w",
        )
        self._action_hint.pack(fill="x", pady=(2, 10))

        self._sep()

        # ── Save / Delete ─────────────────────────────────────────────────
        btn_row2 = ctk.CTkFrame(scroll, fg_color=_BG)
        btn_row2.pack(fill="x", pady=(4, 0))

        self._save_btn = ctk.CTkButton(
            btn_row2,
            text="Save",
            command=self._save,
            fg_color=_ACC,
            hover_color="#00cc77",
            text_color="#000",
            font=ctk.CTkFont("Consolas", 11, "bold"),
            corner_radius=6,
            width=110,
        )
        self._save_btn.pack(side="left", padx=(0, 10))

        self._del_btn = ctk.CTkButton(
            btn_row2,
            text="Delete Gesture",
            command=self._delete,
            fg_color="#1e1e1e",
            hover_color="#330000",
            text_color=_ERR,
            font=ctk.CTkFont("Consolas", 10),
            border_width=1,
            border_color=_ERR,
            corner_radius=6,
            width=110,
        )
        self._del_btn.pack(side="left")

        self._set_edit_active(False)

    # ── List panel helpers ─────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        """Rebuild the left-panel list from state."""
        for w in self._list_scroll.winfo_children():
            w.destroy()

        self._section_header("▼ Custom Gestures", self._list_scroll)
        custom = state.CUSTOM_GESTURE_TEMPLATES
        if custom:
            for tmpl in custom:
                self._list_row(tmpl.name, is_builtin=False)
        else:
            ctk.CTkLabel(
                self._list_scroll,
                text="  (none yet)",
                font=ctk.CTkFont("Consolas", 9),
                text_color=_DIM,
                anchor="w",
            ).pack(fill="x", padx=8)

        self._section_header("▼ Built-in Gestures", self._list_scroll)
        for name in BUILTIN_ENTRIES:
            self._list_row(name, is_builtin=True)

    def _section_header(self, text: str, parent) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color=_ACC,
            anchor="w",
        ).pack(fill="x", padx=8, pady=(10, 2))

    def _list_row(self, name: str, is_builtin: bool) -> None:
        binding = state.GESTURE_BINDINGS.get(name, {})
        btype = binding.get("type", "none")
        bval  = binding.get("value", "")
        tag = ""
        if btype == "hotkey":
            tag = f"  ⌨ {bval}"
        elif btype == "script":
            tag = f"  ▶ {bval[-25:]}" if len(bval) > 25 else f"  ▶ {bval}"

        is_sel = (name == self._sel_name)
        bg = "#1e3a2f" if is_sel else "#1a1a1a"

        row = ctk.CTkFrame(self._list_scroll, fg_color=bg, corner_radius=4)
        row.pack(fill="x", padx=6, pady=2)

        ctk.CTkLabel(
            row,
            text=f"  {'⚙' if is_builtin else '●'} {name}{tag}",
            font=ctk.CTkFont("Consolas", 10),
            text_color=_ACC if is_sel else _FG,
            anchor="w",
        ).pack(side="left", padx=4, pady=5)

        row.bind("<Button-1>", lambda _e, n=name, b=is_builtin: self._select(n, b))
        for child in row.winfo_children():
            child.bind("<Button-1>", lambda _e, n=name, b=is_builtin: self._select(n, b))

    # ── Selection & population ────────────────────────────────────────────

    def _select(self, name: str, is_builtin: bool) -> None:
        """Load a gesture into the edit panel."""
        if self._rec_state == _RECORDING:
            self._stop_record()

        self._sel_name = name
        self._sel_is_builtin = is_builtin
        self._refresh_list()
        self._set_edit_active(True)

        self._name_var.set(name)
        self._name_entry.configure(state="disabled" if is_builtin else "normal")

        # Samples
        if is_builtin:
            tmpl = None
        else:
            tmpl = self._find_template(name)

        self._update_sample_display(tmpl)

        # Recording controls: only for custom gestures
        rec_state = "normal" if not is_builtin else "disabled"
        self._rec_btn.configure(state=rec_state)
        self._clear_btn.configure(state=rec_state)

        # Action
        binding = state.GESTURE_BINDINGS.get(name, {"type": "none", "value": ""})
        self._action_var.set(binding.get("type", "none"))
        self._action_value_var.set(binding.get("value", ""))
        self._on_action_type_change()

        # Delete only for custom
        self._del_btn.configure(state="normal" if not is_builtin else "disabled")

    def _add_new(self) -> None:
        """Create a blank custom gesture and select it for editing."""
        if self._rec_state == _RECORDING:
            self._stop_record()

        name = f"Gesture {len(state.CUSTOM_GESTURE_TEMPLATES) + 1}"
        tmpl = GestureTemplate(name=name)
        state.CUSTOM_GESTURE_TEMPLATES.append(tmpl)
        self._refresh_list()
        self._select(name, is_builtin=False)

    def _find_template(self, name: str) -> Optional[GestureTemplate]:
        for t in state.CUSTOM_GESTURE_TEMPLATES:
            if t.name == name:
                return t
        return None

    # ── Recording ─────────────────────────────────────────────────────────

    def _toggle_record(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        else:
            self._start_record()

    def _start_record(self) -> None:
        if self._sel_name is None or self._sel_is_builtin:
            return
        tmpl = self._find_template(self._sel_name)
        if tmpl is None:
            return
        tmpl.clear_samples()
        state.recording_samples = []
        state.recording_gesture = True
        self._rec_state = _RECORDING
        self._rec_btn.configure(
            text="■ Stop",
            text_color=_ERR,
            border_color=_ERR,
        )
        self._status_label.configure(
            text="🔴 Hold your gesture steady...",
            text_color=_YEL,
        )

    def _stop_record(self) -> None:
        state.recording_gesture = False
        self._rec_state = _DONE
        self._rec_btn.configure(
            text="● Record",
            text_color=_YEL,
            border_color=_YEL,
        )
        # Flush samples from state into the template
        if self._sel_name:
            tmpl = self._find_template(self._sel_name)
            if tmpl is not None and state.recording_samples:
                tmpl.samples = list(state.recording_samples)
                state.recording_samples = []
                self._update_sample_display(tmpl)

    def _clear_samples(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        if self._sel_name:
            tmpl = self._find_template(self._sel_name)
            if tmpl:
                tmpl.clear_samples()
                state.recording_samples = []
                self._update_sample_display(tmpl)

    def _update_sample_display(self, tmpl: Optional[GestureTemplate]) -> None:
        if tmpl is None:
            count, total = 0, RECORD_SAMPLES
            trained = False
        else:
            count = min(tmpl.sample_count(), RECORD_SAMPLES)
            total = RECORD_SAMPLES
            trained = tmpl.is_trained()

        ratio = count / total if total else 0
        self._progress.set(ratio)
        self._sample_label.configure(text=f"{count} / {total} samples")

        if trained:
            self._status_label.configure(text="✓ Trained", text_color=_ACC)
        elif count > 0:
            self._status_label.configure(
                text=f"Need {total - count} more samples",
                text_color=_YEL,
            )
        else:
            self._status_label.configure(
                text="No samples — click Record",
                text_color=_DIM,
            )

    # ── Recording poll (runs on UI thread via after()) ─────────────────────

    def _poll_recording(self) -> None:
        """Check recording progress and update UI; reschedule itself."""
        try:
            if self._rec_state == _RECORDING and self._sel_name:
                tmpl = self._find_template(self._sel_name)
                n = len(state.recording_samples)
                # Sync samples to template for live display
                if tmpl is not None:
                    tmpl.samples = list(state.recording_samples[:n])
                    self._update_sample_display(tmpl)

                if n >= RECORD_SAMPLES:
                    self._stop_record()
        except Exception:
            pass

        if self._win.winfo_exists():
            self._win.after(100, self._poll_recording)

    # ── Action type UI ─────────────────────────────────────────────────────

    def _on_action_type_change(self) -> None:
        atype = self._action_var.get()
        if atype == "none":
            self._action_entry.pack_forget()
            self._browse_btn.pack_forget()
            self._action_hint.configure(text="No action will be triggered.")
        elif atype == "hotkey":
            self._action_entry.configure(placeholder_text="e.g.  ctrl+shift+h")
            self._action_entry.pack(side="left", fill="x", expand=True)
            self._browse_btn.pack_forget()
            self._action_hint.configure(
                text="Key names: ctrl, shift, alt, win, a–z, f1–f12, space, …"
            )
        elif atype == "script":
            self._action_entry.configure(placeholder_text="Path or shell command")
            self._action_entry.pack(side="left", fill="x", expand=True)
            self._browse_btn.pack(side="left", padx=(6, 0))
            self._action_hint.configure(text="Any executable, .py, .bat, .sh, …")

    def _browse_script(self) -> None:
        path = fd.askopenfilename(
            parent=self._win,
            title="Select Script or Executable",
            filetypes=[
                ("All files", "*.*"),
                ("Python", "*.py"),
                ("Batch", "*.bat *.cmd"),
                ("Shell", "*.sh"),
                ("Executable", "*.exe"),
            ],
        )
        if path:
            self._action_value_var.set(path)

    # ── Save / Delete ─────────────────────────────────────────────────────

    def _save(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()

        name = self._name_var.get().strip()
        if not name:
            self._status_label.configure(text="⚠ Name cannot be empty", text_color=_ERR)
            return

        # Rename support for custom gestures
        if not self._sel_is_builtin and self._sel_name and name != self._sel_name:
            tmpl = self._find_template(self._sel_name)
            if tmpl:
                # Move binding to new name
                if self._sel_name in state.GESTURE_BINDINGS:
                    state.GESTURE_BINDINGS[name] = state.GESTURE_BINDINGS.pop(self._sel_name)
                tmpl.name = name
                reset_cooldown(name)
            self._sel_name = name

        # Save action binding
        atype = self._action_var.get()
        aval  = self._action_value_var.get().strip()

        if atype == "hotkey" and aval:
            ok, err = validate_hotkey(aval)
            if not ok:
                self._action_hint.configure(text=f"⚠ {err}", text_color=_ERR)
                return
        elif atype == "script" and aval:
            ok, err = validate_script(aval)
            if not ok:
                self._action_hint.configure(text=f"⚠ {err}", text_color=_ERR)
                return

        state.GESTURE_BINDINGS[name] = {"type": atype, "value": aval}
        reset_cooldown(name)

        save_settings()
        self._status_label.configure(text="✓ Saved", text_color=_ACC)
        self._refresh_list()
        print(f"[TRAINER] saved gesture '{name}', action={atype}:{aval}")

    def _delete(self) -> None:
        if self._sel_is_builtin or self._sel_name is None:
            return
        if self._rec_state == _RECORDING:
            self._stop_record()

        # Remove template
        state.CUSTOM_GESTURE_TEMPLATES = [
            t for t in state.CUSTOM_GESTURE_TEMPLATES if t.name != self._sel_name
        ]
        # Remove binding
        state.GESTURE_BINDINGS.pop(self._sel_name, None)

        self._sel_name = None
        self._set_edit_active(False)
        save_settings()
        self._refresh_list()
        self._status_label.configure(text="Deleted", text_color=_DIM)
        print(f"[TRAINER] deleted gesture '{self._sel_name}'")

    # ── Utility ───────────────────────────────────────────────────────────

    def _section(self, text: str) -> None:
        ctk.CTkLabel(
            self._edit_scroll,
            text=text,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color=_ACC,
            anchor="w",
        ).pack(fill="x", pady=(6, 2))

    def _sep(self) -> None:
        ctk.CTkFrame(
            self._edit_scroll, fg_color="#2a2a2a", height=1
        ).pack(fill="x", pady=8)

    def _set_edit_active(self, active: bool) -> None:
        state_ = "normal" if active else "disabled"
        for w in [self._name_entry, self._rec_btn, self._clear_btn,
                  self._action_entry, self._save_btn, self._del_btn]:
            try:
                w.configure(state=state_)
            except Exception:
                pass

    def _on_close(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        state.gesture_trainer_open = False
        print("[TRAINER] closed")
        self._win.destroy()
