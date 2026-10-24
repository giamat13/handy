"""קריאת מצלמה בחוט נפרד: תמיד שומרים רק את הפריים האחרון, כדי שלא תצטבר השהיה."""
import sys
import threading
import time

import cv2

from perf import RateMeter


class Camera:
    def __init__(self, index=0, width=640, height=480):
        # DirectShow רק ב-Windows; ב-macOS וב-Linux המנוע שנבחר אוטומטית (AVFoundation / V4L2)
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(index)
        if sys.platform == "win32":
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if sys.platform == "win32":
            # חשיפה אוטומטית מורידה את המצלמה ל-12 FPS בתאורה חלשה; חשיפה ידנית נותנת ~28
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
            self.cap.set(cv2.CAP_PROP_EXPOSURE, -5)
        self.opened = self.cap.isOpened()
        self.rate = RateMeter()   # כמה פריימים המצלמה באמת מספקת בשנייה (שונה ממה שהתוכנה מציירת)
        self.stamp = None         # מתי הגיע הפריים האחרון (perf_counter), למדידת ההשהיה עד הסמן
        self._frame = None
        self._id = 0
        self._cond = threading.Condition()
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            frame = cv2.flip(frame, 1)  # מראה, כדי שהתנועה תרגיש טבעית
            self.rate.tick()
            with self._cond:
                self._frame = frame
                self.stamp = time.perf_counter()
                self._id += 1
                self._cond.notify_all()

    def read(self, last_id, timeout=0.2):
        """מחכה לפריים חדש (שונה מ-last_id). מחזיר (id, frame) או (last_id, None)."""
        with self._cond:
            if self._id == last_id:
                self._cond.wait(timeout)
            if self._id == last_id:
                return last_id, None
            return self._id, self._frame

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        self.cap.release()
