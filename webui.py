"""הממשק כ-HTML: שרת מקומי שמגיש את תיקיית web/, את הווידאו החי (MJPEG) ו-API קטן להגדרות, למחוות ולעדכונים.

אבטחה: השרת מאזין על 127.0.0.1 בלבד, כל בקשת API וידאו דורשת טוקן אקראי (שנמצא רק בכתובת שנפתחת בחלון), הכותרת Host
חייבת להיות הכתובת המקומית (נגד DNS rebinding), ו-POST עם Origin זר נדחה. כל ערך שנשלח מהדף עובר ולידציה מחדש כאן."""
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import actions
import autostart
import commands
from custom_gestures import KIND_HAND, KIND_HEAD, KINDS, Recorder, validate_name
from version import FULL_VERSION

WEB_DIR = Path(__file__).resolve().parent / "web"
MAX_BODY = 64 * 1024
UI_GONE_AFTER = 120.0   # שניות בלי שום פנייה מהדף (דפדפן שקרס). סגירה רגילה מדווחת מיד דרך /api/bye
BYE_GRACE = 3.0         # אחרי bye מחכים רגע: רענון של הדף שולח bye ומיד אחריו פנייה חדשה

BOOL_KEYS = ("show_hand_mesh", "show_face_mesh", "show_trail", "show_coords", "show_head_axes", "show_pinch_gauge", "show_ripples",
             "run_in_background", "auto_update_check", "beta_channel")
CHOICES = {"control_source": ("hand", "head", "eyes", "pupils"), "control_hand": ("right", "left", "both")}
RANGES = {"sensitivity": (0.4, 3.0), "smoothing": (0.0, 1.0)}
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _bool(v):
    if not isinstance(v, bool):
        raise ApiError("ערך לא תקין")
    return v


class Backend:
    """כל מה שהממשק צריך מהתוכנה. בלי HTTP, כדי שאפשר לבדוק בלי שרת ובלי מצלמה."""

    def __init__(self, cfg, store, tracker, mouse, renderer, updates, save, quit_cb, pick_file=None, clock=time.monotonic):
        self.cfg, self.store, self.tracker, self.mouse, self.renderer = cfg, store, tracker, mouse, renderer
        self.updates, self.save, self.quit_cb, self._pick, self.clock = updates, save, quit_cb, pick_file, clock
        self.config_version = 1   # עולה בכל שינוי הגדרות / מחוות, והדף טוען מחדש כשהוא משתנה
        self.rec = None
        self.rec_result = None    # {"ok": bool, "text": str, "kind": hand / head} אחרי ההקלטה האחרונה
        self.ui_open = False
        self._last_ui = None
        self._bye_at = None

    # --- חיבור הדף ---
    def touch(self):
        self._last_ui = self.clock()
        self._bye_at = None
        self.ui_open = True

    def bye(self):
        self._bye_at = self.clock() + BYE_GRACE

    def ui_gone(self):
        """True כשהדף נסגר (דיווח bye שלא בא אחריו חיבור חדש, או שתיקה ארוכה). לא True לפני שהדף התחבר אי פעם."""
        if not self.ui_open:
            return False
        now = self.clock()
        if self._bye_at is not None and now >= self._bye_at:
            self.ui_open = False
            return True
        if self._last_ui is not None and now - self._last_ui > UI_GONE_AFTER:
            self.ui_open = False
            return True
        return False

    def tick(self):
        """מהלולאה הראשית: משלים הקלטה שהסתיימה גם כשאין דף פתוח, ושומר כיול מבט שהסתיים."""
        rec = self.rec
        if rec is not None and rec.done:
            self._finish_recording(rec)
        calib = self._gaze_calib()
        models = calib.take_result() if calib is not None else None
        if models is not None:
            self.mouse.gaze_maps.update(models)
            self.cfg["gaze_models"] = {name: m.to_dict() for name, m in models.items()}
            self.save(self.cfg)
            self._changed()

    # --- קריאה ---
    def names(self):
        return {**actions.GESTURES, **actions.HAND_MOTIONS, **actions.HEAD_GESTURES, **self.store.names()}

    def _row(self, gid, name, kind=KIND_HAND):
        b = self.cfg["bindings"].get(gid, "none")
        return {"id": gid, "name": name, "kind": kind, "binding": b, "text": actions.binding_text(b)}

    def _autostart(self):
        try:
            return autostart.is_enabled()
        except OSError:
            return False

    def config(self):
        c = self.cfg
        kinds = self.store.kinds()
        return {
            "version": self.config_version,
            "app_version": FULL_VERSION,
            "settings": {**{k: c[k] for k in (*BOOL_KEYS, *CHOICES, *RANGES)}, "autostart": self._autostart()},
            "control_enabled": c["control_enabled"],
            "groups": {
                "hand": [self._row(g, n) for g, n in actions.GESTURES.items()],
                "motion": [self._row(g, n) for g, n in actions.HAND_MOTIONS.items()],
                "head": [self._row(g, n, KIND_HEAD) for g, n in actions.HEAD_GESTURES.items()],
                "custom": [self._row(g, n, kinds.get(g, KIND_HAND)) for g, n in self.store.names().items()],
            },
            "actions": [{"id": k, "label": v, "param": k in actions.PARAM_ACTIONS} for k, v in actions.ACTIONS.items()],
            "limits": {k: list(v) for k, v in RANGES.items()},
        }

    def perf(self):
        """קצב ומשך של כל שלב בדרך מהפריים לסמן (לשונית האבחון). None = השלב לא נמדד כאן. ms = אלפיות שנייה, fps = פעמים בשנייה."""
        t, r, m = self.tracker, self.renderer, self.mouse

        def val(obj, attr, field):
            meter = getattr(obj, attr, None)
            v = getattr(meter, field, None)
            return None if v is None else round(v, 1)

        return {
            "camera_fps": val(getattr(t, "camera", None), "rate", "rate"),
            "tracker_fps": val(t, "rate", "rate"),
            "hands_ms": val(t, "hands_ms", "ms"),
            "face_ms": val(t, "face_ms", "ms"),
            "logic_ms": val(t, "logic_ms", "ms"),
            "latency_ms": val(t, "latency_ms", "ms"),
            "draw_fps": val(r, "draw_rate", "rate"),
            "draw_ms": val(r, "draw_ms", "ms"),
            "encode_ms": val(r, "encode_ms", "ms"),
            "cursor_hz": val(m, "glide_rate", "rate"),
        }

    def state(self):
        self.touch()
        self.tick()
        rec = self.rec
        slot = self.mouse.active_slot
        return {
            "config_version": self.config_version,
            "fps": round(self.tracker.fps, 1),
            "detect": self.renderer.detect,
            "detect_hand": getattr(self.renderer, "detect_hand", self.renderer.detect),
            "detect_head": getattr(self.renderer, "detect_head", "—"),
            "conf": {g: round(float(v), 2) for g, v in getattr(self.renderer, "conf", {}).items()},
            "perf": self.perf(),
            "enabled": self.cfg["control_enabled"],
            "camera": bool(getattr(self.tracker.camera, "opened", True)),
            "active_hand": {0: "left", 1: "right"}.get(slot),
            "recording": None if rec is None else {"name": rec.name, "mode": rec.mode, "kind": rec.kind, "progress": round(rec.progress, 3),
                                                   "hint": rec.hint},
            "rec_result": self.rec_result,
            "gaze": self._gaze_state(),
            "update": self.updates.snapshot(),
        }

    def _gaze_calib(self):
        return getattr(self.tracker, "gaze_calib", None)   # בלי מעקב מבט (בבדיקות) אין כיול

    def _gaze_state(self):
        calib = self._gaze_calib()
        snap = calib.snapshot() if calib is not None else {"active": False, "status": "idle"}
        return {"calibrated": self.cfg.get("gaze_models") is not None, "calib": snap}

    def gaze(self, body):
        """כיול המבט: התחלה או ביטול. הנקודות מוצגות בדף, והשמירה נעשית ב-tick."""
        calib = self._gaze_calib()
        if calib is None:
            raise ApiError("אין מעקב מבט")
        action = body.get("action")
        if action == "start":
            calib.start()
        elif action == "cancel":
            calib.cancel()
        else:
            raise ApiError("פעולה לא מוכרת")
        return {"ok": True}

    # --- כתיבה ---
    def _changed(self):
        self.config_version += 1

    def set_value(self, body):
        key, value = body.get("key"), body.get("value")
        if key == "autostart":   # נשמר במערכת (לא ב-settings.json): ראה autostart.py
            try:
                autostart.set_enabled(_bool(value))
            except OSError as e:
                raise ApiError(f"לא הצלחתי לעדכן את ההפעלה עם המחשב: {e}")
            self._changed()
            return {"ok": True}
        if key in BOOL_KEYS:
            self.cfg[key] = _bool(value)
        elif key in CHOICES:
            if value not in CHOICES[key]:
                raise ApiError("ערך לא תקין")
            self.cfg[key] = value
        elif key in RANGES:
            lo, hi = RANGES[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= float(value) <= hi:
                raise ApiError("ערך מחוץ לטווח")
            self.cfg[key] = float(value)
        else:
            raise ApiError("הגדרה לא מוכרת")
        self.save(self.cfg)
        self._changed()
        return {"ok": True}

    def set_control(self, body):
        enabled = _bool(body.get("enabled"))
        self.cfg["control_enabled"] = enabled
        if not enabled:
            self.mouse.release()
        self._changed()
        return {"ok": True}

    def set_binding(self, body):
        gid, action = body.get("gesture"), body.get("action")
        if gid not in self.names():
            raise ApiError("מחווה לא מוכרת")
        if action not in actions.ACTIONS:
            raise ApiError("פעולה לא מוכרת")
        try:
            if action == "hotkey":
                value = {"type": "hotkey", "keys": commands.hotkey_text(commands.parse_hotkey(body.get("keys")))}
            elif action == "script":
                value = {"type": "script", **commands.parse_script(body.get("path"), body.get("args"))}
            else:
                value = action
        except ValueError as e:
            raise ApiError(str(e))
        self.cfg["bindings"][gid] = value
        self.save(self.cfg)
        self._changed()
        return {"binding": value, "text": actions.binding_text(value)}

    def pick_file(self, _body):
        if self._pick is None:
            raise ApiError("בחירת קובץ לא זמינה כאן")
        return {"path": self._pick() or ""}

    # --- מחוות מותאמות ---
    def custom(self, body):
        op = body.get("op")
        gid = body.get("id")
        if op == "record":
            return self._start_recording(body.get("name"), gid, body.get("mode", "new"), body.get("kind"))
        if op == "cancel":
            kind = self.rec.kind if self.rec is not None else None
            self._end_recording()
            self.rec_result = {"ok": True, "text": "ההקלטה בוטלה", "kind": kind}
            return {"ok": True}
        if op in ("rename", "delete") and gid not in self.store.names():
            raise ApiError("מחווה לא מוכרת")
        try:
            if op == "rename":
                self.store.rename(gid, body.get("name"))
            elif op == "delete":
                self.store.delete(gid)
                self.cfg["bindings"].pop(gid, None)
                self.save(self.cfg)
            else:
                raise ApiError("פעולה לא מוכרת")
        except ValueError as e:
            raise ApiError(str(e))
        self._changed()
        return {"ok": True}

    def _start_recording(self, name, gid, mode, kind=None):
        """kind (hand / head) חובה למחווה חדשה: בכל יצירה בוחרים מי מבצע אותה. בהקלטה מחדש ובאימון הסוג נשאר כמו של המחווה."""
        if self.rec is not None:
            raise ApiError("כבר מקליטים")
        if mode not in ("new", "replace", "train"):
            raise ApiError("מצב הקלטה לא מוכר")
        if not getattr(self.tracker.camera, "opened", True):
            raise ApiError("לא נמצאה מצלמה")
        try:
            if mode == "new":
                if kind not in KINDS:
                    raise ValueError("בחר מי מבצע את המחווה: יד או ראש")
                name = validate_name(name)
                if name.casefold() in {n.casefold() for n in self.store.names().values()}:
                    raise ValueError("כבר יש מחווה בשם הזה")
            else:
                if gid not in self.store.names():
                    raise ValueError("מחווה לא מוכרת")
                name = self.store.names()[gid]
                kind = self.store.kinds()[gid]
        except ValueError as e:
            raise ApiError(str(e))
        self.rec = Recorder(name, gid if mode != "new" else None, kind)
        self.rec.mode = mode
        self.rec_result = None
        self.tracker.recorder = self.rec  # בזמן ההקלטה אף פעולה לא מופעלת
        return {"ok": True}

    def _end_recording(self):
        self.tracker.recorder = None
        self.rec = None

    def _finish_recording(self, rec):
        self._end_recording()
        try:
            if rec.mode == "train":
                text = f"נוספו דגימות ל-'{rec.name}' (סה״כ {self.store.train(rec.gesture_id, rec)}). המחווה תזהה אותה טוב יותר."
            elif rec.mode == "replace":
                self.store.rerecord(rec.gesture_id, rec)
                text = f"'{rec.name}' הוקלטה מחדש."
            else:
                self.store.add(rec.name, rec)
                text = f"'{rec.name}' נשמרה. אפשר לקשור אותה לפעולה ברשימה למטה."
            overlap = rec.builtin_overlap()
            if overlap:  # מותר, והמותאמת גוברת: אומרים את זה במפורש
                text += f" התנוחה דומה למחווה המובנית '{actions.GESTURES.get(overlap, overlap)}': המחווה שלך מקבלת עדיפות והמובנית לא תופעל בתנוחה הזו."
            self.rec_result = {"ok": True, "text": text, "kind": rec.kind}
        except (ValueError, KeyError) as e:
            self.rec_result = {"ok": False, "text": str(e), "kind": rec.kind}
        self._changed()

    # --- עדכונים ויציאה ---
    def update(self, body):
        op = body.get("op")
        ops = {"check": lambda: self.updates.check(manual=True), "install": self.updates.install, "skip": self.updates.skip,
               "dismiss": self.updates.dismiss, "ack": self.updates.ack}
        if op not in ops:
            raise ApiError("פעולה לא מוכרת")
        ops[op]()
        return {"ok": True}

    def quit(self, _body=None):
        threading.Thread(target=self.quit_cb, daemon=True).start()
        return {"ok": True}


class Handler(BaseHTTPRequestHandler):
    server_version = "Handy"
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    # --- בדיקות אבטחה ---
    @property
    def be(self):
        return self.server.backend

    def _host_ok(self):
        return self.headers.get("Host", "") in (f"127.0.0.1:{self.server.port}", f"localhost:{self.server.port}")

    def _token_ok(self, query):
        sent = self.headers.get("X-Handy-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(sent.encode(), self.server.token.encode())

    def _reply(self, status, body=b"", ctype="application/json", extra=()):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._reply(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _guard(self, query, need_token=True):
        if not self._host_ok():
            self._json(403, {"error": "host"})
            return False
        if need_token and not self._token_ok(query):
            self._json(401, {"error": "token"})
            return False
        return True

    # --- GET ---
    def do_GET(self):
        url = urlparse(self.path)
        query, path = parse_qs(url.query), url.path
        if path == "/":
            return self._index(query)
        if path.startswith("/api/") or path == "/video":
            if not self._guard(query):
                return
            if path == "/video":
                return self._video()
            routes = {"/api/state": self.be.state, "/api/config": self.be.config, "/api/ping": lambda: {"ok": True, "app": "handy"}}
            if path not in routes:
                return self._json(404, {"error": "not found"})
            return self._json(200, routes[path]())
        self._static(path)

    def _index(self, query):
        if not self._guard(query, need_token=False):
            return
        if not self._token_ok(query):  # הכתובת בלי טוקן לא מקבלת את הדף (שמכיל את הטוקן)
            return self._json(401, {"error": "token"})
        html = (WEB_DIR / "index.html").read_text("utf-8").replace("__TOKEN__", self.server.token)
        self._reply(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _static(self, path):
        if not self._host_ok():
            return self._json(403, {"error": "host"})
        target = (WEB_DIR / path.lstrip("/")).resolve()
        if WEB_DIR.resolve() not in target.parents or not target.is_file() or target.suffix not in CONTENT_TYPES or target.name == "index.html":
            return self._json(404, {"error": "not found"})
        self._reply(200, target.read_bytes(), CONTENT_TYPES[target.suffix])

    def _video(self):
        boundary = "frame"
        self.send_response(200)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={boundary}")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        seq, r = 0, self.be.renderer
        try:
            while not self.server.stopping:
                r.want()
                seq, jpeg = r.wait_frame(seq, 1.0)
                if jpeg is None:
                    continue
                self.wfile.write(f"--{boundary}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode() + jpeg + b"\r\n")
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        self.close_connection = True

    # --- POST ---
    def do_POST(self):
        url = urlparse(self.path)
        if not self._guard(parse_qs(url.query)):
            return
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{self.server.port}", f"http://localhost:{self.server.port}"):
            return self._json(403, {"error": "origin"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if not 0 <= n <= MAX_BODY:
            return self._json(413, {"error": "body"})
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self._json(400, {"error": "json"})
        be = self.be
        routes = {"/api/set": be.set_value, "/api/control": be.set_control, "/api/binding": be.set_binding,
                  "/api/custom": be.custom, "/api/update": be.update, "/api/pick-file": be.pick_file, "/api/quit": be.quit,
                  "/api/gaze": be.gaze,
                  "/api/bye": lambda b: (be.bye(), {"ok": True})[1]}
        handler = routes.get(url.path)
        if handler is None:
            return self._json(404, {"error": "not found"})
        try:
            self._json(200, handler(body))
        except ApiError as e:
            self._json(e.status, {"error": str(e)})


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, backend, port=0):
        super().__init__(("127.0.0.1", port), Handler)
        self.backend = backend
        self.port = self.server_address[1]
        self.token = secrets.token_urlsafe(24)
        self.stopping = False
        self._thread = None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def start(self):
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self.stopping = True
        self.shutdown()
        self.server_close()
