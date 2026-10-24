"""MediaPipe בחוט נפרד. מפרסם זוג (פריים, נקודות) מסונכרן, כך שהרשת תמיד צמודה ליד."""
import threading
from collections import namedtuple

import cv2
import mediapipe as mp
import numpy as np

from custom_gestures import CustomMatcher, pick_sign
from signs import Stabilizer, WinkDetector, assign_slots, classify_hand

SLOT_LABELS = ("Left", "Right")  # signs[0] = יד שמאל, signs[1] = יד ימין (כפי שהיא נראית למשתמש: הווידאו הפוך כמו מראה)

# slots: משבצת (0/1) לכל יד ברשימת hands. point: הנקודה השולטת בקואורדינטות הפריים, או None
TrackOutput = namedtuple("TrackOutput", "id frame hands face signs wink slots point")


class Tracker:
    def __init__(self, camera, controller=None, store=None):
        self.camera = camera
        self.controller = controller
        self.store = store  # מחוות מותאמות (CustomGestureStore) או None
        self.matchers = [CustomMatcher(store), CustomMatcher(store)] if store is not None else None
        self.recorder = None  # Recorder פעיל בזמן הקלטת מחווה: אז לא מפעילים פעולות
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
            hands, labels = [], []
            if self.track_hands:
                res = self.hands.process(rgb)
                if res.multi_hand_landmarks:
                    handed = res.multi_handedness or []
                    for i, lm in enumerate(res.multi_hand_landmarks):
                        hands.append(np.array([(p.x, p.y) for p in lm.landmark], np.float32))
                        labels.append(handed[i].classification[0].label if i < len(handed) else "Right")
            slots = assign_slots(labels)
            hands = [h for h, s in zip(hands, slots) if s is not None]
            slots = [s for s in slots if s is not None]
            face = None
            if self.track_face:
                res = self.face.process(rgb)
                if res.multi_face_landmarks:
                    face = np.array(
                        [(p.x, p.y) for p in res.multi_face_landmarks[0].landmark], np.float32
                    )
            fh, fw = frame.shape[:2]
            by_slot = dict(zip(slots, hands))
            signs = []
            for slot, stab in enumerate(self.sign_stabs):
                pts = by_slot.get(slot)
                builtin = stab.update(classify_hand(pts) if pts is not None else None)
                # מחווה מותאמת גוברת על מובנית דומה: כשזוהתה, וגם כשהיד כבר בתנוחה שלה (הסימן המובנה מושתק בזמן ההמתנה ליציבות)
                if self.matchers:
                    custom = self.matchers[slot].update(pts, SLOT_LABELS[slot])
                    builtin = pick_sign(custom, self.matchers[slot].claims, builtin)
                signs.append(builtin)
            wink = self.winker.update(face, fw, fh)
            rec = self.recorder
            if rec is not None:
                # בהקלטה לוקחים את היד השולטת (ימין, אם אין הגבלה); אף פעולה לא מופעלת עד שההקלטה נגמרת
                allowed = self.controller.allowed_slots() if self.controller is not None else (0, 1)
                slot = next((s for s in (1, 0) if s in allowed and s in by_slot), None)
                rec.add(by_slot[slot] if slot is not None else None, SLOT_LABELS[slot] if slot is not None else None)
                signs, wink = [None, None], None
            if self.controller is not None:
                self.controller.update(hands, face, signs, wink, slots)
            point = self.controller.point if self.controller is not None else None
            now = time.perf_counter()
            self.fps = 0.9 * self.fps + 0.1 / max(now - t_prev, 1e-6)
            t_prev = now
            with self._lock:
                self._out_id += 1
                self._out = TrackOutput(self._out_id, frame, hands, face, signs, wink, slots, point)

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
