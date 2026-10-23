# Handy 2

Control your Windows PC with a webcam. Hand or head tracking moves the mouse, and a wink or a hand sign triggers clicks, scrolling and dragging.

The main window shows the live camera with the MediaPipe hand mesh and face landmarks drawn on top. A status line under the video shows what is detected right now (for example "wink left" or "thumbs up").

## Features

- Live video with hand mesh (21 points) and face landmarks, switchable in settings
- Mouse control by hand (palm center) or head (nose tip), with smoothing and sensitivity
- Wink detection (left / right; a normal blink is ignored)
- Hand signs: pinch, OK, peace, thumbs up / down, fist, open palm, point, three fingers, rock
- Every gesture can be mapped to an action: left / right / middle / double click, drag, scroll up / down
- Mouse control is off by default

## Requirements

- Windows 10 / 11
- Python 3.12
- A webcam

## Install and run

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run.py
```

MediaPipe is pinned to 0.10.21 because later releases removed the `mp.solutions` API this project uses.

## Hotkeys

| Key | Action |
| --- | --- |
| F8 | Toggle mouse control |
| F9 | Set the current head position as the screen center |

## Settings

Settings are saved to `settings.json` next to the code (not tracked by git). Gesture-to-action mapping, source (hand / head), sensitivity and smoothing are all in the settings window.

## Project layout

| File | Purpose |
| --- | --- |
| `run.py` | Entry point |
| `app.py` | Main window and settings window |
| `camera.py` | Threaded camera capture, always the latest frame |
| `tracker.py` | MediaPipe hands and face, publishes frame and landmarks together |
| `signs.py` | Hand sign classifier and wink detector |
| `mouse_control.py` | Cursor movement, clicks, scrolling |
| `overlay.py` | Drawing the mesh over the video |
| `actions.py` | Gesture and action names, default mapping |
| `settings.py` | Load and save settings |
| `tests/` | Tests for sign and wink detection (synthetic landmarks, no camera) |

## Tests

```
.venv\Scripts\pip install pytest
.venv\Scripts\python -m pytest tests
```

## Releases

Versions are `2.X.Y`: X is a feature, Y is a fix. The version lives in `version.py`. To release, follow [docs/release-checklist.md](docs/release-checklist.md): push a tag `vX.Y.Z` (or run the *release* workflow by hand) and GitHub Actions builds `Handy2Setup.exe` and a portable ZIP and publishes them.

## Roadmap

- [x] Live camera with hand and face mesh
- [x] Mouse control by hand or head
- [x] Click and scroll by wink or hand sign
- [x] Gesture-to-action mapping
- [ ] Recording custom gestures
- [x] Installer and portable ZIP built by GitHub Actions (not yet tried on GitHub)
- [ ] Code signing
- [x] Automatic update from GitHub releases, with rollback (tested only against a mock server)

## Privacy

All processing happens locally. Camera frames are never saved or sent anywhere.

## License

[MIT](LICENSE)
