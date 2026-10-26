"""MediaPipe בחוט נפרד. מפרסם זוג (פריים, נקודות) מסונכרן, כך שהרשת תמיד צמודה ליד."""
import threading
import time
from collections import namedtuple

import cv2
import mediapipe as mp
import numpy as np

import body_pose
import gaze
import head_pose
from body_gestures import BodyGestures
from eye_gestures import EyeGestures
from face_expressions import ExpressionGestures
from hand_motion import HandMotions
from custom_gestures import KIND_HEAD, CustomMatcher, pick_sign
from head_motion import HeadLean, HeadMotion, HeadTilt
from perf import RateMeter, TimeMeter
from signs import Stabilizer, assign_slots, classify_hand, sign_scores
from tuning import Tuning

SLOT_LABELS = ("Left", "Right")  # signs[0] = יד שמאל, signs[1] = יד ימין (כפי שהיא נראית למשתמש: הווידאו הפוך כמו מראה)
# signs[2] = מחווה מותאמת של הראש, signs[3] = הנהון / ניעור, signs[4] = הטיית ראש, signs[5] = ראש קדימה / אחורה, signs[6] = קריצה / מצמוץ, signs[7] = פה / חיוך / גבות (tuple, כי כמה יכולות להיות פעילות יחד) (mouse_control.HEAD_SLOTS)
# signs[8] = תנועות יד, signs[9] = מחוות גוף (tuple, כמו signs[7]) (mouse_control.BODY_SLOTS)

# slots: משבצת (0/1) לכל יד ברשימת hands. point: הנקודה השולטת בקואורדינטות הפריים, או None.
# pose: HeadPose (head_pose.py) או None. conf: {מזהה מחווה: ביטחון 0..1} ליד המשמשת למיקוד ולראש (לתצוגת האבחון)
# body: נקודות הגוף (33, 3) = (x, y, ביטחון) מנורמלות, כמו MediaPipe Pose, או None (לשלד הגוף על הווידאו; עצמות יד מוסתרות כשיש יד מצוירת)
# near: ידיים (21, 2) שנמצאו סביב שורשי כפות הגוף ולא מזוהות על ידי מעקב היד, לציור בלבד
TrackOutput = namedtuple("TrackOutput", "id frame hands face signs slots point pose conf body near")


FACE_WINDOW = 0.25   # חיפוש פנים סביב האף: חצי רוחב החלון, כחלק מהצלע הארוכה של הפריים (ראה Tracker._face_near)
HAND_WINDOW = 0.15   # חיפוש יד סביב שורש כף היד של הגוף: אותו סולם כמו FACE_WINDOW
HAND_COVER = 0.1     # יד שמעקב היד מצא שורשה קרוב לשורש של הגוף (בחלק מהצלע הארוכה) נחשבת לאותה יד: עצמות הגוף מוסתרות
HAND_SEARCH_EVERY = 0.5   # שניות בין שני חיפושי יד לאותו צד, כי חיפוש בכל פריים עולה הרבה במעבד
HAND_HOLD = 1.0      # שניות שיד שנמצאה נשארת מוצגת בלי חיפוש חדש


class Tracker:
    def __init__(self, camera, controller=None, store=None, tuning=None):
        self.camera = camera
        self.controller = controller
        self.store = store  # מחוות מותאמות (CustomGestureStore) או None
        self.tuning = tuning if tuning is not None else Tuning()   # כוונון הרגישות וזמני ההחזקה של המחוות (tuning.py)
        self.matchers = [CustomMatcher(store), CustomMatcher(store)] if store is not None else None
        self.head_matcher = CustomMatcher(store, KIND_HEAD) if store is not None else None
        self.head_motion = HeadMotion(self.tuning)   # הנהון / ניעור ראש מתוך תנועת הזוויות
        self.head_tilt = HeadTilt(self.tuning)       # הטיית ראש לכתף מתוך זווית ה-roll
        self.head_lean = HeadLean(self.tuning)       # ראש קדימה / אחורה מתוך גודל הפנים
        self.eyes = EyeGestures(self.tuning)         # קריצה ומצמוץ ארוך מתוך פתיחות העיניים
        self.hand_motion = HandMotions()  # החלקה, עיגול ונפנוף של יד פתוחה
        self.expressions = ExpressionGestures(self.tuning)   # פה פתוח, חיוך וגבות מורמות
        self.body = BodyGestures(self.tuning)        # קפיצה, התכופפות, רכינה ושתי ידיים למעלה מתוך הגוף העליון
        self.gaze_calib = gaze.GazeCalibration()  # כיול המבט: אוסף דגימות כשהממשק מציג נקודה (gaze.py)
        self.recorder = None  # Recorder פעיל בזמן הקלטת מחווה: אז לא מפעילים פעולות
        self.sign_stabs = [Stabilizer(3), Stabilizer(3)]
        self.hands = mp.solutions.hands.Hands(
            max_num_hands=2,
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )
        self.face = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,   # מדויק יותר סביב העיניים והפה (העפעפיים לקריצה), במחיר מעט זמן עיבוד: ראה "אבחון"
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=0,
            smooth_landmarks=True,
            min_detection_confidence=0.3,   # נמוך מהידיים והפנים: גם חלק מגוף (למשל רק הכתפיים והזרועות) צריך להיספר
            min_tracking_confidence=0.3,
        )
        self.face_near = mp.solutions.face_mesh.FaceMesh(   # פנים בחלון קטן סביב האף, כש-FaceMesh של כל הפריים לא מצא פנים
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        )
        self.hand_near = mp.solutions.hands.Hands(   # יד סביב שורש כף היד של הגוף, כש-Hands של כל הפריים לא מצא אותה
            static_image_mode=True,
            max_num_hands=1,
            min_detection_confidence=0.5,
        )
        self._hand_checked = [-1e9, -1e9]   # מתי חיפשנו יד לכל צד (שמאל, ימין) לאחרונה
        self._hand_found = {}                # צד -> (מתי נמצאה, נקודות היד)
        self.track_hands = True
        self.track_face = True
        self.track_body = True
        self._lock = threading.Lock()
        self._out = None  # (id, frame, hands, face)
        self._out_id = 0
        self._running = False
        self._thread = None
        self.fps = 0.0
        # מדידות לשונית האבחון: קצב אמיתי של הלולאה, ומשך כל שלב באלפיות שנייה
        self.rate = RateMeter()
        self.hands_ms, self.face_ms, self.body_ms, self.logic_ms, self.latency_ms = TimeMeter(), TimeMeter(), TimeMeter(), TimeMeter(), TimeMeter()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _focus_slot(self, by_slot):
        """איזו יד מציגים בתצוגת הביטחון: היד ששולטת עכשיו, ואחרת הימנית ואז השמאלית (מבין המותרות)."""
        allowed = self.controller.allowed_slots() if self.controller is not None else (0, 1)
        prev = getattr(self.controller, "active_slot_prev", None)
        return next((s for s in (prev, 1, 0) if s in by_slot and s in allowed), None)

    def _loop(self):
        last = 0
        t_prev = time.perf_counter()
        while self._running:
            last, frame = self.camera.read(last)
            if frame is None:
                continue
            stamp = getattr(self.camera, "stamp", None)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            hands, labels = [], []
            if self.track_hands:
                with self.hands_ms:
                    res = self.hands.process(rgb)
                if res.multi_hand_landmarks:
                    handed = res.multi_handedness or []
                    for i, lm in enumerate(res.multi_hand_landmarks):
                        hands.append(np.array([(p.x, p.y) for p in lm.landmark], np.float32))
                        labels.append(handed[i].classification[0].label if i < len(handed) else "Right")
            slots = assign_slots(labels)
            hands = [h for h, s in zip(hands, slots) if s is not None]
            slots = [s for s in slots if s is not None]
            face = face3d = None
            if self.track_face:
                with self.face_ms:
                    res = self.face.process(rgb)
                if res.multi_face_landmarks:
                    face3d = np.array([(p.x, p.y, p.z) for p in res.multi_face_landmarks[0].landmark], np.float32)
                    face = face3d[:, :2].copy()
            body3d = None
            if self.track_body:
                with self.body_ms:
                    res = self.pose.process(rgb)
                if res.pose_landmarks:
                    body3d = np.array([(p.x, p.y, p.visibility) for p in res.pose_landmarks.landmark], np.float32)
            if face3d is None and self.track_face and body3d is not None and body3d[body_pose.NOSE, 2] >= body_pose.MIN_VISIBLE:
                face3d = self._face_near(rgb, body3d[body_pose.NOSE])   # Pose מצא את האף, אבל FaceMesh של כל הפריים לא: מחפשים פנים סביבו
                if face3d is not None:
                    face = face3d[:, :2].copy()
            body_shown, near = (None, []) if body3d is None else self._body_hands(rgb, body3d, hands, time.perf_counter())
            fh, fw = frame.shape[:2]
            t_logic = time.perf_counter()
            pose = head_pose.estimate(face3d, fw, fh) if face3d is not None else None
            body = body_pose.estimate(body3d, fw, fh) if body3d is not None else None
            face_px = head_pose.scaled(face3d, fw, fh) if face3d is not None else None
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
            signs.append(self.head_matcher.update(face_px, None) if self.head_matcher is not None else None)
            signs.append(self.head_motion.update(pose, time.perf_counter()))
            signs.append(self.head_tilt.update(pose, time.perf_counter()))
            signs.append(self.head_lean.update(pose, time.perf_counter()))
            signs.append(self.eyes.update(face_px, pose, time.perf_counter()))
            signs.append(self.expressions.update(face_px, pose, time.perf_counter()))
            allowed = self.controller.allowed_slots() if self.controller is not None else (0, 1)
            signs.append(self.hand_motion.update(by_slot, allowed, (fw, fh), time.perf_counter()))
            signs.append(self.body.update(body, time.perf_counter()))
            conf = {**self.hand_motion.scores, **self.head_motion.scores, **self.head_tilt.scores, **self.head_lean.scores, **self.eyes.scores,
                    **self.expressions.scores, **self.body.scores}
            focus = self._focus_slot(by_slot)
            if focus is not None:
                conf.update(sign_scores(by_slot[focus]))
                if self.matchers:
                    conf.update(self.matchers[focus].scores)
            if self.head_matcher is not None:
                conf.update(self.head_matcher.scores)
            rec = self.recorder
            if rec is not None:
                if getattr(rec, "kind", "hand") == KIND_HEAD:
                    rec.add(face_px, None)
                else:
                    # בהקלטה לוקחים את היד השולטת (ימין, אם אין הגבלה); אף פעולה לא מופעלת עד שההקלטה נגמרת
                    allowed = self.controller.allowed_slots() if self.controller is not None else (0, 1)
                    slot = next((s for s in (1, 0) if s in allowed and s in by_slot), None)
                    rec.add(by_slot[slot] if slot is not None else None, SLOT_LABELS[slot] if slot is not None else None)
                signs = [None] * 10
                self.hand_motion.reset()
                self.expressions.reset()
                self.body.reset()
                self.head_motion.reset()
                self.head_tilt.reset()
                self.head_lean.reset()
                self.eyes.reset()
            gaze_feat = gaze.features(face_px, pose)   # None כשהעיניים סגורות או אין פנים
            self.gaze_calib.add(gaze_feat, time.perf_counter())
            if self.controller is not None:
                self.controller.update(hands, face, signs, slots, gaze_feat)
            point = self.controller.point if self.controller is not None else None
            now = time.perf_counter()
            self.logic_ms.add(now - t_logic)
            if stamp is not None:
                self.latency_ms.add(now - stamp)
            self.rate.tick()
            self.fps = 0.9 * self.fps + 0.1 / max(now - t_prev, 1e-6)
            t_prev = now
            with self._lock:
                self._out_id += 1
                self._out = TrackOutput(self._out_id, frame, hands, face, signs, slots, point, pose, conf, body_shown, near)

    def _body_hands(self, rgb, body3d, hands, now):
        """עצמות היד של הגוף: מוסתרות במקום שיש יד מצוירת (של מעקב היד או שנמצאה סביב השורש). בלי יד כזו מחפשים אחת סביב השורש.
        מחזיר (נקודות הגוף להצגה, ידיים שנמצאו סביב השורשים). רק לתצוגה: מעקב היד והמחוות לא משתנים."""
        h, w = rgb.shape[:2]
        cover = HAND_COVER * max(w, h)
        shown, near = body3d.copy(), []
        for side, idx in enumerate(body_pose.HAND_POINTS):
            wrist = body3d[idx[0]]
            if wrist[2] < body_pose.MIN_VISIBLE:
                continue
            tracked = any(np.hypot(*((hand[0] - wrist[:2]) * (w, h))) < cover for hand in hands)
            if not tracked and now - self._hand_checked[side] >= HAND_SEARCH_EVERY:
                self._hand_checked[side] = now
                pts = self._hand_near(rgb, wrist)
                if pts is not None:
                    self._hand_found[side] = (now, pts)
            found = self._hand_found.get(side)
            fresh = found is not None and now - found[0] < HAND_HOLD
            if tracked or fresh:
                shown[list(idx), 2] = 0.0   # יש כבר יד מצוירת כאן, אז לא מציירים גם את העצמות של הגוף
            if fresh and not tracked:
                near.append(found[1])
        return shown, near

    def _hand_near(self, rgb, wrist):
        """יד בחלון קטן סביב שורש כף היד של הגוף. מחזיר את נקודות היד (21, 2) מנורמלות לכל הפריים, או None."""
        h, w = rgb.shape[:2]
        half = HAND_WINDOW * max(w, h)
        x0, x1 = int(max(wrist[0] * w - half, 0)), int(min(wrist[0] * w + half, w))
        y0, y1 = int(max(wrist[1] * h - half, 0)), int(min(wrist[1] * h + half, h))
        crop = np.ascontiguousarray(rgb[y0:y1, x0:x1])
        if crop.size == 0:
            return None
        res = self.hand_near.process(crop)
        if not res.multi_hand_landmarks:
            return None
        cw, ch = x1 - x0, y1 - y0
        return np.array([((x0 + p.x * cw) / w, (y0 + p.y * ch) / h) for p in res.multi_hand_landmarks[0].landmark], np.float32)

    def _face_near(self, rgb, nose):
        """פנים בחלון קטן סביב האף. מחזיר את נקודות הפנים (468, 3) מנורמלות לכל הפריים, כמו face3d, או None אם לא נמצאו."""
        h, w = rgb.shape[:2]
        half = FACE_WINDOW * max(w, h)
        x0, x1 = int(max(nose[0] * w - half, 0)), int(min(nose[0] * w + half, w))
        y0, y1 = int(max(nose[1] * h - half, 0)), int(min(nose[1] * h + half, h))
        crop = np.ascontiguousarray(rgb[y0:y1, x0:x1])
        if crop.size == 0:
            return None
        res = self.face_near.process(crop)
        if not res.multi_face_landmarks:
            return None
        cw, ch = x1 - x0, y1 - y0
        pts = np.array([(p.x, p.y, p.z) for p in res.multi_face_landmarks[0].landmark], np.float32)
        pts[:, 0] = (x0 + pts[:, 0] * cw) / w
        pts[:, 1] = (y0 + pts[:, 1] * ch) / h
        pts[:, 2] *= cw / w   # z בקנה מידה של רוחב החלון, ולכן מחושב מחדש לקנה מידה של כל הפריים
        return pts

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
        self.pose.close()
        self.face_near.close()
        self.hand_near.close()
