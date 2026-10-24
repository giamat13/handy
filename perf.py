"""מדידת קצב ומשך של שלבי העבודה (מצלמה, מעקב, ציור), בשביל לשונית האבחון."""
import threading
import time
from collections import deque


class RateMeter:
    """כמה פעמים בשנייה קורה משהו, ממדידה אמיתית של חלון הזמן האחרון (לא הערכה). כשהאירועים נפסקים הקצב יורד ל-0."""

    def __init__(self, window=1.5, clock=time.perf_counter):
        self.window = window
        self._clock = clock
        self._ticks = deque()
        self._lock = threading.Lock()

    def tick(self):
        now = self._clock()
        with self._lock:
            self._ticks.append(now)
            self._trim(now)

    def _trim(self, now):
        while self._ticks and now - self._ticks[0] > self.window:
            self._ticks.popleft()

    @property
    def rate(self):
        with self._lock:
            self._trim(self._clock())
            if len(self._ticks) < 2:
                return 0.0
            span = self._ticks[-1] - self._ticks[0]
            return (len(self._ticks) - 1) / span if span > 0 else 0.0


class TimeMeter:
    """משך ממוצע (אלפיות שנייה) של שלב, בממוצע נע. שימוש: `with meter:` סביב השלב, או meter.add(שניות)."""

    def __init__(self, smoothing=0.1, clock=time.perf_counter):
        self.ms = 0.0
        self._a = smoothing
        self._clock = clock
        self._start = 0.0

    def add(self, seconds):
        v = max(seconds, 0.0) * 1000.0
        self.ms = v if self.ms == 0.0 else self.ms + self._a * (v - self.ms)

    def __enter__(self):
        self._start = self._clock()
        return self

    def __exit__(self, *_):
        self.add(self._clock() - self._start)
