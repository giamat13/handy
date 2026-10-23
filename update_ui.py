"""The update screens: checking in the background, the "new version" window with its download progress, and the notices after a restart."""
import queue
import threading
import tkinter.messagebox as mb
import webbrowser

import customtkinter as ctk

import settings
import updater
from version import FULL_VERSION


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, master, manager, info):
        super().__init__(master)
        self.manager, self.info = manager, info
        self.title("עדכון זמין")
        self.geometry("460x420")
        self.transient(master)
        self.q = queue.Queue()
        pre = " (גרסת בטא)" if info["prerelease"] else ""
        ctk.CTkLabel(self, text=f"גרסה חדשה זמינה: {info['latest']}{pre}", font=ctk.CTkFont(size=16, weight="bold")).pack(
            padx=16, pady=(16, 0), anchor="w")
        ctk.CTkLabel(self, text=f"הגרסה שלך: {FULL_VERSION}").pack(padx=16, anchor="w")
        box = ctk.CTkTextbox(self, height=190)
        box.pack(fill="both", expand=True, padx=16, pady=10)
        box.insert("1.0", info["notes"] or "אין הערות לגרסה זו.")
        box.configure(state="disabled")
        self.msg = ctk.CTkLabel(self, text="", wraplength=420, justify="left")
        self.msg.pack(padx=16, anchor="w")
        self.bar = ctk.CTkProgressBar(self)
        self.bar.set(0)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=12)
        self.go = ctk.CTkButton(row, text="עדכן עכשיו", command=self.start)
        self.go.pack(side="right")
        self.skip = ctk.CTkButton(row, text="דלג על גרסה זו", fg_color="gray30", command=self.skip_version)
        self.skip.pack(side="right", padx=8)
        self.later = ctk.CTkButton(row, text="אחר כך", fg_color="gray30", command=self.destroy)
        self.later.pack(side="right")

    def skip_version(self):
        self.manager.cfg["update_skipped"] = self.info["latest"]
        settings.save(self.manager.cfg)
        self.destroy()

    def open_page(self, text=None):
        if text:
            self.msg.configure(text=text)
        webbrowser.open(self.info["page"])

    def start(self):
        if not updater.can_install(self.info):
            return self.open_page("אי אפשר לאמת את המתקין אוטומטית. מורידים אותו מעמוד השחרור.")
        self.go.configure(state="disabled"); self.skip.configure(state="disabled"); self.later.configure(state="disabled")
        self.bar.pack(fill="x", padx=16)
        self.msg.configure(text="מוריד עדכון…")
        threading.Thread(target=self._work, daemon=True).start()
        self.after(100, self._poll)

    def _work(self):
        try:
            got = updater.download(self.info, lambda done, total: self.q.put(("p", done, total)))
            self.q.put(("d", got))
        except Exception as e:
            self.q.put(("e", str(e)))

    def _poll(self):
        try:
            while True:
                kind, *rest = self.q.get_nowait()
                if kind == "p":
                    done, total = rest
                    if total:
                        self.bar.set(done / total)
                elif kind == "e":
                    self.msg.configure(text=rest[0])
                    self.later.configure(state="normal")
                    return
                else:
                    return self._install(rest[0])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _install(self, got):
        self.msg.configure(text="מתקין… האפליקציה תיסגר ותיפתח מחדש.")
        try:
            res = updater.launch(got["path"])
        except updater.BlockedError:
            self.later.configure(state="normal")
            return self.open_page("Windows חסם את המתקין (הוא לא חתום). מורידים אותו מעמוד השחרור.")
        except updater.UpdateError as e:
            self.msg.configure(text=str(e)); self.later.configure(state="normal")
            return
        if res["mode"] == "page":      # מקור או גרסה ניידת: אין איפה להתקין במקום
            self.later.configure(state="normal")
            return self.open_page("בגרסה ניידת או מקוד מקור מורידים את הגרסה החדשה מעמוד השחרור.")
        self.manager.app.close()


class UpdateManager:
    def __init__(self, app, cfg):
        self.app, self.cfg = app, cfg
        self.q = queue.Queue()
        self.dialog = None

    def startup(self) -> bool:
        """Settles an update started earlier and tells the user how it went. False when the app is about to be restored and must end."""
        state = updater.reconcile()["state"]
        if state == "restoring":
            return False
        notice = updater.pending_notice()
        if notice["updated"]:
            mb.showinfo("Handy 2", f"Handy 2 עודכן לגרסה {notice['updated'].get('to')}.")
        if notice["failed"]:
            mb.showwarning("Handy 2", "העדכון האחרון לא הסתיים." + (" הגרסה הקודמת שוחזרה." if notice["failed"].get("restored") else ""))
        updater.ack_notice()
        if self.cfg.get("auto_update_check", True):
            self.app.after(4000, self.auto_check)
        return True

    def auto_check(self):
        if self.cfg.get("auto_update_check", True):
            self.check(manual=False)
        self.app.after(updater.CHECK_EVERY * 1000, self.auto_check)

    def check(self, manual=True):
        threading.Thread(target=lambda: self.q.put((manual, updater.check(self.cfg))), daemon=True).start()
        self.app.after(200, self._poll)

    def _poll(self):
        try:
            manual, info = self.q.get_nowait()
        except queue.Empty:
            return self.app.after(200, self._poll)
        if info["error"]:
            if manual:
                mb.showwarning("עדכונים", f"הבדיקה נכשלה: {info['error']}")
        elif not info["available"]:
            if manual:
                mb.showinfo("עדכונים", f"הגרסה שלך ({FULL_VERSION}) עדכנית.")
        elif manual or not info["skipped"]:
            if self.dialog is None or not self.dialog.winfo_exists():
                self.dialog = UpdateDialog(self.app, self, info)
