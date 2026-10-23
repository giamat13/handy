import time, cv2
from camera import Camera
import mediapipe as mp
c = Camera().start()
last=0; n=0; t0=time.time()
while time.time()-t0<3:
    last,f=c.read(last)
    if f is not None: n+=1
print("camera-only fps", n/3)
hands = mp.solutions.hands.Hands(max_num_hands=2, model_complexity=0)
face = mp.solutions.face_mesh.FaceMesh(max_num_faces=1)
th=tf=0; k=0
t0=time.time()
while time.time()-t0<4:
    last,f=c.read(last)
    if f is None: continue
    rgb=cv2.cvtColor(f,cv2.COLOR_BGR2RGB)
    a=time.perf_counter(); hands.process(rgb); b=time.perf_counter(); face.process(rgb); d=time.perf_counter()
    th+=b-a; tf+=d-b; k+=1
print(f"hands {th/k*1000:.1f}ms face {tf/k*1000:.1f}ms frames {k}")
c.stop()
