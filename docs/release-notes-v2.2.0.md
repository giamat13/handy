# Handy 2 2.2.0

## New

- **Head gestures**: record your own head poses (a tilt, a turn, an open mouth, raised brows) the same way as hand gestures, and bind them to any action. They work whichever hand is set as the dominant one, and also while the head moves the cursor. Hand gestures and head gestures are separate: each has its own recording and list.
- **"My gestures" tab**: everything you recorded (hand and head) in one place. The first tab is now "Built-in gestures".
- **The video card shows hand and head apart**: one "recognised now" card for the hand, and one for the head, each with its action.
- **Start with the computer** (Settings): starts straight into the system tray without a window. The mouse control still starts off. A program started this way stays in the tray when you close its window.
- **Glow trail**: the trail after the controlling point is now a glow whose colour follows the speed, blue when slow through green and yellow to red when fast.
- **Click ripples**: a ring spreads from every click, in a colour per kind (left, right, middle, double).
- **3D head axes** above the nose with yaw / pitch / roll, and a **pinch gauge** between thumb and index finger with a tick where a pinch starts to count. All three can be turned off in the settings.
- **Diagnostics tab**: a live confidence bar for every gesture (so you can see which two gestures get confused, and how close an unrecognised pose is), and the real rate or duration of each stage from camera to cursor, with a note on what is slowing things down (for example a camera that only delivers 15 frames a second).

## Notes

- The head-gesture thresholds were tuned on synthetic faces. If a head gesture fires by mistake or is not recognised, record it again and hold the pose steadier; report it if it keeps happening.
