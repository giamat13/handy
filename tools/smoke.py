import time
from camera import Camera
from tracker import Tracker
c = Camera().start()
print("camera opened:", c.opened)
t = Tracker(c).start()
last = 0; n = 0; hands = 0; faces = 0; t0 = time.time()
while time.time() - t0 < 6:
    o = t.latest(last)
    if o:
        last = o[0]; n += 1; hands += len(o[2]); faces += o[3] is not None
    time.sleep(0.002)
print(f"frames={n} fps={n/6:.1f} hands_seen={hands} face_frames={faces} shape={o[1].shape if o else None}")
t.stop(); c.stop()
