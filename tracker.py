"""MediaPipe בחוט נפרד. מפרסם זוג (פריים, נקודות) מסונכרן, כך שהרשת תמיד צמודה ליד."""
import threading

import cv2
import mediapipe as mp
import numpy as np

from signs import Stabilizer, WinkDetector, classify_hand


class Tracker:
    def __init__(self, camera, controller=None):
        self.camera = camera
        self.controller = controller
        self.sign_stabs = [Stabilizer(3), Stabilizer(3)]
        self.winker = WinkDetector()
        self.hands = mp.solutions.hands.Hands(
            max_num_hands=2,
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )
        self.face = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.track_hands = True
        self.track_face = True
        self._lock = threading.Lock()
        self._out = None  # (id, frame, hands, face)
        self._out_id = 0
        self._running = False
        self._thread = None
        self.fps = 0.0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        import time
        last = 0
        t_prev = time.perf_counter()
        while self._running:
            last, frame = self.camera.read(last)
            if frame is None:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            hands = []
            if self.track_hands:
                res = self.hands.process(rgb)
                if res.multi_hand_landmarks:
                    for lm in res.multi_hand_landmarks:
                        hands.append(np.array([(p.x, p.y) for p in lm.landmark], np.float32))
            face = None
            if self.track_face:
                res = self.face.process(rgb)
                if res.multi_face_landmarks:
                    face = np.array(
                        [(p.x, p.y) for p in res.multi_face_landmarks[0].landmark], np.float32
                    )
            fh, fw = frame.shape[:2]
            signs = []
            for i, stab in enumerate(self.sign_stabs):
                raw = classify_hand(hands[i]) if i < len(hands) else None
                signs.append(stab.update(raw))
            wink = self.winker.update(face, fw, fh)
            if self.controller is not None:
                self.controller.update(hands, face, signs, wink)
            now = time.perf_counter()
            self.fps = 0.9 * self.fps + 0.1 / max(now - t_prev, 1e-6)
            t_prev = now
            with self._lock:
                self._out_id += 1
                self._out = (self._out_id, frame, hands, face, signs, wink)

    def latest(self, last_id):
        with self._lock:
            if self._out is None or self._out[0] == last_id:
                return None
            return self._out

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        self.hands.close()
        self.face.close()
