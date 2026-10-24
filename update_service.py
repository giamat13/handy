"""העדכון האוטומטי בלי חלונות: בדיקה ברקע, הורדה והתקנה. הממשק (HTML) רק מציג את snapshot() ושולח פעולות.
הלוגיקה עצמה (הורדה, אימות, שחזור) נמצאת ב-updater.py."""
import threading
import time

import updater

FIRST_CHECK_AFTER = 4.0  # שניות מההפעלה עד הבדיקה האוטומטית הראשונה


class UpdateService:
    """status: idle / checking / available / uptodate / error / downloading / installing / page / blocked."""

    def __init__(self, cfg, save, quit_cb, updater_mod=updater, clock=time.monotonic):
        self.cfg, self.save, self.quit_cb, self.u, self.clock = cfg, save, quit_cb, updater_mod, clock
        self.status = "idle"
        self.info = None
        self.manual = False
        self.progress = 0.0
        self.message = ""
        self.notice = None  # הודעה אחרי הפעלה מחדש: עודכן / העדכון נכשל
        self._next_auto = clock() + FIRST_CHECK_AFTER
        self._lock = threading.Lock()

    def startup(self):
        """מסיים עדכון שנקטע ומכין הודעה למשתמש. False = האפליקציה עומדת להיות משוחזרת ויש לסיים אותה."""
        if self.u.reconcile()["state"] == "restoring":
            return False
        n = self.u.pending_notice()
        if n["updated"]:
            self.notice = {"kind": "updated", "text": f"Handy 2 עודכן לגרסה {n['updated'].get('to')}."}
        elif n["failed"]:
            self.notice = {"kind": "failed", "text": "העדכון האחרון לא הסתיים." + (" הגרסה הקודמת שוחזרה." if n["failed"].get("restored") else "")}
        self.u.ack_notice()
        return True

    def ack(self):
        self.notice = None
        if self.status in ("uptodate", "error", "page", "blocked"):
            self.status = "idle"

    def tick(self):
        """נקרא מהלולאה הראשית: בדיקה אוטומטית ראשונה אחרי הפעלה, ואחריה כל CHECK_EVERY שניות."""
        if self.clock() >= self._next_auto:
            self._next_auto = self.clock() + self.u.CHECK_EVERY
            if self.cfg.get("auto_update_check", True) and self.status in ("idle", "uptodate", "error"):
                self.check(manual=False)

    def check(self, manual=True):
        with self._lock:
            if self.status in ("checking", "downloading", "installing"):
                return
            self.status, self.manual, self.message = "checking", manual, ""
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        info = self.u.check(self.cfg)
        with self._lock:
            if info["error"]:
                self.status, self.message = ("error", info["error"]) if self.manual else ("idle", "")
            elif not info["available"]:
                self.status = "uptodate" if self.manual else "idle"
            elif self.manual or not info["skipped"]:
                self.status, self.info = "available", info
            else:
                self.status = "idle"

    def skip(self):
        if self.info:
            self.cfg["update_skipped"] = self.info["latest"]
            self.save(self.cfg)
        self.status = "idle"

    def dismiss(self):
        """"אחר כך": סוגרים את ההצעה בלי לדלג על הגרסה."""
        if self.status in ("available", "page", "blocked", "error"):
            self.status = "idle"

    def install(self):
        with self._lock:
            if self.status != "available" or not self.info:
                return
            if not self.u.can_install(self.info):
                self.status, self.message = "page", "אי אפשר לאמת את המתקין אוטומטית. מורידים אותו מעמוד השחרור."
                return
            self.status, self.progress, self.message = "downloading", 0.0, "מוריד עדכון…"
        threading.Thread(target=self._install, daemon=True).start()

    def _on_progress(self, done, total):
        if total:
            self.progress = done / total

    def _install(self):
        try:
            got = self.u.download(self.info, self._on_progress)
            self.status, self.message = "installing", "מתקין… האפליקציה תיסגר ותיפתח מחדש."
            res = self.u.launch(got["path"])
        except self.u.BlockedError:
            self.status, self.message = "blocked", "Windows חסם את המתקין (הוא לא חתום). מורידים אותו מעמוד השחרור."
            return
        except Exception as e:
            self.status, self.message = "error", str(e)
            return
        if res["mode"] == "page":  # מקור, גרסה ניידת, macOS או Linux: אין מתקין להריץ
            self.status, self.message = "page", "בגרסה ניידת, מקוד מקור או ב-macOS / Linux מורידים את הגרסה החדשה מעמוד השחרור."
            return
        self.quit_cb()

    def snapshot(self):
        info = self.info
        return {
            "status": self.status, "progress": round(self.progress, 3), "message": self.message, "notice": self.notice,
            "info": None if not info else {"latest": info["latest"], "prerelease": info["prerelease"], "notes": info["notes"] or "",
                                           "page": info["page"]},
        }
