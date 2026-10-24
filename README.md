# Handy 2

Control your PC with a webcam (Windows, macOS, Linux). Hand or head tracking moves the mouse, and a wink or a hand sign triggers clicks, scrolling, dragging, key combinations or any program you choose.

The main window shows the live camera with the MediaPipe hand mesh and face landmarks drawn on top. A status line under the video shows what is detected right now (for example "wink left" or "thumbs up").

## Features

- Live video with hand mesh (21 points) and face landmarks, switchable in settings
- Mouse control by hand (palm center) or head (nose tip), with smoothing and sensitivity
- **Dominant hand**: right, left or both control the mouse; the active hand is marked on the video
- Wink detection (left / right; a normal blink is ignored)
- Hand signs: pinch, OK, victory (V), hang loose, thumbs up / down, fist, open palm, point, three fingers, rock
- **Custom gestures**: record your own static hand poses, name them, rename, re-record or delete them
- Every gesture can be mapped to an action: left / right / middle / double click, drag, scroll up / down, turn the control on / off, **press a key combination** (`Ctrl+C`, `Alt+Tab`, `Win+D`) or **run a program or script** with arguments
- Optional **trail** after the controlling point and **cursor coordinates** on the video
- Mouse control is off by default (and always off when the program starts)

### Default mapping

| Gesture | Action |
| --- | --- |
| Wink left / right | Left / right click |
| OK | Double click |
| Victory (V) | Left click |
| Hang loose | Right click |
| Thumbs up | Turn the mouse control on / off (same as F8) |
| Three fingers / rock | Scroll up / down |

**Why scrolling moved:** thumbs up used to scroll, but it is the natural pose for the on / off switch, and one pose cannot do both. Scrolling went to two deliberate poses that are not easy to make by accident (three fingers, rock). Settings saved by 2.0.x that were never customised are moved automatically; a customised mapping is left alone. Everything is changeable in Settings.

"Peace" and "Victory" are the same V sign. It is named Victory now, and a mapping saved for Peace is carried over.

### Custom gestures

Open **מחוות** (next to Settings), type a name and press **הקלט**. Hold the pose still in front of the camera until the bar is full (about a second). The gestures are saved in `custom_gestures.json` next to `settings.json`, and then appear in the mapping list in Settings like the built-in ones.

- Only static poses (no movement). The hand rests in the pose for a moment before it is recognised, and moving between poses triggers nothing.
- A recording is refused if the pose is already a built-in sign, or too close to another custom gesture of yours; pick a clearly different pose.
- A gesture recorded with one hand is recognised on the other hand too.
- No action fires while you record.

### Keys and programs

In Settings choose **קיצור מקשים…** or **הרצת תוכנה / סקריפט…** for a gesture and fill in the value.

- Keys: modifiers `Ctrl`, `Alt`, `Shift`, `Win` (Command on macOS, Super on Linux) plus exactly one key, for example `Ctrl+Shift+T`, `Alt+Tab`, `F5`.
- Programs: a full path and optional arguments. The program is started directly, **never through a shell**, so characters such as `&` or `|` in the arguments are plain text. Paths are checked when you save and again before running. For `.bat` / `.cmd` files, shell characters in the arguments are refused. Two runs of the same kind are at least a second apart.

## Requirements

- Windows 10 / 11, macOS or Linux (X11)
- Python 3.12
- A webcam

System notes:

- **macOS**: allow the camera, and give the app *Accessibility* and *Input Monitoring* permission (System Settings → Privacy & Security) so it can move the mouse, press keys and see F8 / F9. The app in the zip is not signed: open it with right click → Open the first time.
- **Linux**: needs an X11 session (Wayland blocks synthetic mouse and key events). F8 / F9 and the key actions work through X11; install `python3-tk` when running from source.
- The automatic update works only on the installed Windows version. Elsewhere the update window opens the release page.

## Install and run

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt     (macOS / Linux: .venv/bin/pip)
.venv\Scripts\python run.py
```

MediaPipe is pinned to 0.10.21 because later releases removed the `mp.solutions` API this project uses.

## Hotkeys

| Key | Action |
| --- | --- |
| F8 | Toggle mouse control |
| F9 | Set the current head position as the screen center |

## Settings

Settings are saved to `settings.json`, and custom gestures to `custom_gestures.json`, in the same folder:

| Run as | Folder |
| --- | --- |
| From source | next to the code (not tracked by git) |
| Installed, Windows | `%APPDATA%\Handy` |
| Installed, macOS | `~/Library/Application Support/Handy` |
| Installed, Linux | `~/.config/handy` |
| Portable (a `portable.txt` next to the program) | the `data` folder next to the program |

Version 2.0.x kept them in `%APPDATA%\Handy2`. The first start of the new version moves those files to `%APPDATA%\Handy` once (it never overwrites a file that is already there, and deletes an old file only after the copy is verified).

## Project layout

| File | Purpose |
| --- | --- |
| `run.py` | Entry point |
| `app.py` | Main window, settings window, custom gestures window |
| `camera.py` | Threaded camera capture, always the latest frame |
| `tracker.py` | MediaPipe hands and face, publishes frame and landmarks together |
| `signs.py` | Hand sign classifier and wink detector |
| `custom_gestures.py` | Recording, storing and recognising custom gestures |
| `mouse_control.py` | Cursor movement, clicks, scrolling, dominant hand, key and program actions |
| `commands.py` | Validation and running of key combinations and programs (no shell) |
| `view_aids.py` | The trail and the coordinates drawn on the video |
| `overlay.py` | Drawing the mesh over the video |
| `actions.py` | Gesture and action names, default mapping |
| `settings.py` | Load and save settings, data folders, the move from `Handy2` |
| `tests/` | Tests with synthetic landmarks and fake devices (no camera) |

## Tests

```
.venv\Scripts\pip install pytest
.venv\Scripts\python -m pytest tests
```

`tests/test_overlay.py` belongs to another layout (it imports `core.tracker` and `ui.overlay`) and is not part of this project's test run.

## Releases and builds

Versions are `2.X.Y`: X is a feature, Y is a fix. The version lives in `version.py`. To release, follow [docs/release-checklist.md](docs/release-checklist.md): push a tag `vX.Y.Z` (or run the *release* workflow by hand) and GitHub Actions builds every target and publishes them.

| Target | File | Built with |
| --- | --- | --- |
| Windows installer (used by the automatic update) | `Handy2Setup.exe` | PyInstaller + Inno Setup |
| Windows portable | `Handy2-X.Y.Z-portable.zip` | PyInstaller |
| Windows installer, alternative | `Handy2-NSIS-Setup-X.Y.Z.exe` | PyInstaller + NSIS (`installer.nsi`) |
| macOS | `Handy2-X.Y.Z-macos.zip` (the `.app`) | PyInstaller |
| Linux | `Handy2-X.Y.Z-linux-x64.tar.gz` | PyInstaller |
| Nuitka | `Handy2-X.Y.Z-<windows\|macos\|linux>-nuitka.(zip\|tar.gz)` | Nuitka (`tools/build_nuitka.py`) |

The Windows build and the tests decide whether a release is published; the other targets are built on the same run, reported in the run summary, and attached when they succeed.

## Roadmap

- [x] Live camera with hand and face mesh
- [x] Mouse control by hand or head
- [x] Click and scroll by wink or hand sign
- [x] Gesture-to-action mapping
- [x] Recording custom gestures
- [x] Key combinations and programs bound to gestures
- [x] Dominant hand
- [x] Installer and portable ZIP built by GitHub Actions (not yet tried on GitHub)
- [x] macOS, Linux, Nuitka and NSIS builds (workflows written, not yet run on GitHub)
- [ ] Code signing (and macOS notarization)
- [x] Automatic update from GitHub releases, with rollback (tested only against a mock server)

## Privacy

All processing happens locally. Camera frames are never saved or sent anywhere.

## License

[MIT](LICENSE)
