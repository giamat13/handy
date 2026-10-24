"""מצייר את הווידאו החי (רשת יד, פנים, שובל, קואורדינטות) ומקודד ל-JPEG בשביל הממשק. מצייר רק כשיש מי שצופה."""
import threading
import time

import cv2

import overlay
import view_aids
from actions import GESTURES

VIEW_W, VIEW_H = 800, 600
WATCH_TIMEOUT = 3.0  # בלי בקשת וידאו כל כך הרבה זמן = אף אחד לא צופה, ואז לא מציירים ולא מקודדים


def detect_text(signs, names):
    """מה מזוהה עכשיו, לשורת הסטטוס: קריצה, ואחריה מחוות היד (מובנות ומותאמות)."""
    found = [names[s] for s in signs if s in names]
    return " + ".join(found) if found else "—"


class Renderer:
    def __init__(self, tracker, mouse, cfg, names):
        """names: פונקציה שמחזירה {מזהה מחווה: שם} (כולל מותאמות), כי הרשימה משתנה בזמן ריצה."""
        self.tracker, self.mouse, self.cfg, self.names = tracker, mouse, cfg, names
        self.trail = view_aids.Trail()
        self.detect = "—"
        self.fps = 0.0
        self._cond = threading.Condition()
        self._jpeg = None
        self._seq = 0
        self._want_until = 0.0
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def want(self):
        """מישהו צופה בווידאו."""
        self._want_until = time.monotonic() + WATCH_TIMEOUT

    def wait_frame(self, last_seq, timeout=1.0):
        """מחכה לפריים חדש. מחזיר (seq, jpeg), או (last_seq, None) אם לא הגיע."""
        with self._cond:
            if self._seq == last_seq:
                self._cond.wait(timeout)
            if self._seq == last_seq:
                return last_seq, None
            return self._seq, self._jpeg

    def draw(self, out):
        """הפריים הרגיל של המעקב -> תמונה מצוירת (BGR)."""
        cfg = self.cfg
        # מגדילים קודם ומציירים אחרי, כדי שהקווים יהיו חדים וחלקים
        img = cv2.resize(out.frame, (VIEW_W, VIEW_H), interpolation=cv2.INTER_LINEAR)
        if cfg["show_face_mesh"] and out.face is not None:
            overlay.draw_face(img, out.face)
        if cfg["show_hand_mesh"]:
            active = self.mouse.active_slot if cfg["control_source"] == "hand" else None
            for h, slot in zip(out.hands, out.slots):
                overlay.draw_hand(img, h, active=slot == active)
        now = time.perf_counter()
        if cfg["show_trail"]:
            self.trail.push(out.point, now)
            view_aids.draw_trail(img, self.trail.points(now))
        else:
            self.trail.clear()
        if cfg["show_coords"]:
            view_aids.draw_coords(img, view_aids.format_coords(self.mouse.cursor_position()))
        return img

    def _loop(self):
        last = 0
        while self._running:
            out = self.tracker.latest(last)
            if out is None:
                time.sleep(0.004)
                continue
            last = out.id
            self.detect = detect_text(out.signs, self.names())
            self.fps = self.tracker.fps
            if time.monotonic() > self._want_until:
                continue
            ok, buf = cv2.imencode(".jpg", self.draw(out), [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                with self._cond:
                    self._jpeg = buf.tobytes()
                    self._seq += 1
                    self._cond.notify_all()
