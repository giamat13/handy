# Handy - Hand Detection & Gesture Tracking

Real-time hand tracking and gesture recognition using your webcam. Control your mouse with hand gestures via MediaPipe and OpenCV.

## Features

- Real-time hand landmark detection (up to 2 hands)
- Gesture recognition: Fist, Open Hand, Victory, Thumbs Up, Hang Loose, and more
- Mouse control via index finger position
- Visual trail effect
- Settings window for customization
- Auto-installs dependencies on first run

## Requirements

- Python 3.8+
- Webcam

## Installation

```bash
pip install opencv-python mediapipe numpy pyautogui
```

Or just run the script — it will install missing packages automatically.

## Usage

```bash
python main.py
```

On first run, the model file `hand_landmarker.task` (~9MB) will be downloaded automatically.

## Gestures

| Gesture | Description |
|---|---|
| ☝️ One Finger | Move mouse cursor |
| ✌️ Victory | Left click |
| 👊 Fist | Stop mouse control |
| 👍 Thumbs Up | Toggle mouse control |
| 🤙 Hang Loose | Right click |
| 🖐️ Open Hand | No action |

## Configuration

Adjustable settings (via settings window or directly in `main.py`):

| Setting | Default | Description |
|---|---|---|
| `SMOOTH` | 7 | Cursor smoothing (0=slow, 100=fast) |
| `SPEED` | 5 | Mouse speed multiplier |
| `CAM_MARGIN` | 0.15 | Camera edge margin for full-screen mapping |
| `DEADZONE` | 8 | Minimum pixel movement threshold |
| `CONTROL_HAND` | Right | Which hand controls the mouse (Right/Left/Both) |
| `CLICK_COOLDOWN` | 0.6s | Minimum time between clicks |

## Notes

- Tries the new MediaPipe Tasks API first, falls back to legacy API automatically
- Set `pyautogui.FAILSAFE = True` if you want to re-enable the failsafe corner
