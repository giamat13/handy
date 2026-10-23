import cv2, time
def run(name, setup):
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    setup(cap)
    n=0; t0=time.time()
    while time.time()-t0<3:
        ok,_=cap.read(); n+=ok
    print(name, round(n/3,1), "fps", int(cap.get(3)), "x", int(cap.get(4)))
    cap.release()
def mjpg(c):
    c.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")); c.set(3,640); c.set(4,480); c.set(5,30)
def raw(c):
    c.set(3,640); c.set(4,480); c.set(5,30)
def mjpg_exp(c):
    mjpg(c); c.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25); c.set(cv2.CAP_PROP_EXPOSURE, -5)
def mjpg_exp2(c):
    mjpg(c); c.set(cv2.CAP_PROP_EXPOSURE, -6)
for n,f in (("mjpg",mjpg),("raw",raw),("mjpg+manual exp -5",mjpg_exp),("mjpg+exp -6",mjpg_exp2)): run(n,f)
