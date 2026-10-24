"""תצוגות עזר על הווידאו: שובל אחרי הנקודה השולטת, וקואורדינטות הסמן."""
from collections import deque


class Trail:
    """נקודות אחרונות (בקואורדינטות מנורמלות של הפריים) שדוהות עם הזמן. הלוגיקה בלי ציור, כדי שאפשר לבדוק אותה."""

    def __init__(self, max_age=0.6, max_points=48):
        self.max_age = max_age
        self._pts = deque(maxlen=max_points)

    def push(self, point, now):
        """point: (x, y) או None. בלי נקודה לא מוסיפים כלום והשובל פשוט דוהה."""
        if point is not None:
            self._pts.append((float(point[0]), float(point[1]), now))

    def clear(self):
        self._pts.clear()

    def points(self, now):
        """[(x, y, חיוניות 0..1)] מהישנה לחדשה, בלי נקודות שפג תוקפן."""
        while self._pts and now - self._pts[0][2] > self.max_age:
            self._pts.popleft()
        return [(x, y, 1.0 - (now - t) / self.max_age) for x, y, t in self._pts]


def draw_trail(img, points, color=(60, 220, 255)):
    """מצייר את השובל: קטעים שמתעבים וצבעם מתחזק לכיוון הנקודה הנוכחית."""
    import cv2

    h, w = img.shape[:2]
    scale = max(w / 640.0, 0.5)
    for (x0, y0, _a0), (x1, y1, a1) in zip(points, points[1:]):
        col = tuple(int(c * (0.35 + 0.65 * a1)) for c in color)
        cv2.line(img, (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h)), col,
                 max(1, round((1 + 4 * a1) * scale)), cv2.LINE_AA)


def format_coords(pos):
    """"X: 1234  Y: 567", או None אם אין מיקום."""
    if pos is None:
        return None
    return f"X: {int(pos[0])}  Y: {int(pos[1])}"


def draw_coords(img, text):
    """כתובת בפינה השמאלית התחתונה (ASCII בלבד, כי cv2 לא מצייר עברית), עם צל לקריאות על כל רקע."""
    import cv2

    if not text:
        return
    h, w = img.shape[:2]
    scale = max(w / 1000.0, 0.5)
    org = (int(10 * scale), h - int(12 * scale))
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.9 * scale, (0, 0, 0), max(3, round(4 * scale)), cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.9 * scale, (255, 255, 255), max(1, round(2 * scale)), cv2.LINE_AA)
