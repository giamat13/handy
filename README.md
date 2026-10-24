# Handy 2

Control your PC with a webcam (Windows, macOS, Linux). Hand or head tracking moves the mouse, and a hand sign triggers clicks, scrolling, dragging, key combinations or any program you choose.

The main window shows the live camera with the MediaPipe hand mesh and face landmarks drawn on top. A status line under the video shows what is detected right now (for example "thumbs up").

## Features

- Live video with hand mesh (21 points) and face landmarks, switchable in settings
- Mouse control by hand (palm center) or head (nose tip), with smoothing and sensitivity
- **Dominant hand**: right, left or both control the mouse; the active hand is marked on the video
- Hand signs: pinch, OK, victory (V), hang loose, thumbs up / down, fist, open palm, point, three fingers, rock
- **Custom gestures**: record your own static poses of the **hand or the head** (tilt, turn, open mouth, raised brows). Hand gestures and head gestures live in separate tabs. Name them, rename, re-record, train more or delete them
- Every gesture can be mapped to an action: left / right / middle / double click, scroll up / down, turn the control on / off, **press a key combination** (`Ctrl+C`, `Alt+Tab`, `Win+D`) or **run a program or script** with arguments
- A click (or a key combination) stays pressed for as long as you keep making the gesture: a short gesture is a click, a held gesture is a long press or a drag. There is no separate long-press action
- **Run in the background**: closing the window can leave the program running (system tray) with the mouse control
- The interface is a web page (`web/`), see below
- Optional **glow trail** after the controlling point (blue when slow, through green and yellow to red when fast) and **cursor coordinates** on the video
- **Click ripples**: a ring spreads from the point of every click, in a colour per kind (left, right, middle, double)
- **3D head axes** above the nose (X red, Y green, Z blue) with yaw / pitch / roll in degrees, and a **pinch gauge** between thumb and index finger with a tick where a pinch starts to count
- **Diagnostics** tab: a live confidence bar for every gesture (built-in, custom hand and custom head) and the real rate or duration of each stage, from camera to cursor
- **Start with the computer** (Settings): starts straight into the system tray without opening the window
- Mouse control is off by default (and always off when the program starts)

### Default mapping

| Gesture | Action |
| --- | --- |
| OK | Double click |
| Victory (V) | Left click |
| Hang loose | Right click |
| Thumbs up | Turn the mouse control on / off (same as F8) |
| Three fingers / rock | Scroll up / down |

**Why scrolling moved:** thumbs up used to scroll, but it is the natural pose for the on / off switch, and one pose cannot do both. Scrolling went to two deliberate poses that are not easy to make by accident (three fingers, rock). Settings saved by 2.0.x that were never customised are moved automatically; a customised mapping is left alone. Everything is changeable in Settings.

"Peace" and "Victory" are the same V sign. It is named Victory now, and a mapping saved for Peace is carried over.

### Custom gestures

Hand gestures and head gestures are two separate things, each with its own tab, recording card, list and mapping: **מחוות יד** (built-in signs plus your own hand poses) and **מחוות ראש** (only your own head poses; there are no built-in head signs). Open the tab of the kind you want, type a name and press **הקלט**. Hold the pose still in front of the camera until the bar is full (about a second). The gestures are saved in `custom_gestures.json` next to `settings.json`. They never block or replace each other: a head gesture and a hand gesture can be active together, each with its own action.

- Only static poses (no movement). The hand or head rests in the pose for a moment before it is recognised, and moving between poses triggers nothing.
- A hand recording is refused if the pose is already a built-in sign, or too close to another custom hand gesture of yours; pick a clearly different pose. Head gestures are compared only with other head gestures.
- A gesture recorded with one hand is recognised on the other hand too.
- A head gesture is the pose of the face points (tilt, turn, nod angle, mouth, brows), independent of where the head is and how far it is. It works whichever hand is set as the dominant one, and also while the head moves the cursor.
- No action fires while you record.

### Keys and programs

In Settings choose **קיצור מקשים…** or **הרצת תוכנה / סקריפט…** for a gesture and fill in the value.

- Keys stay pressed while the gesture lasts and are released when it ends. Modifiers `Ctrl`, `Alt`, `Shift`, `Win` (Command on macOS, Super on Linux) plus exactly one key, for example `Ctrl+Shift+T`, `Alt+Tab`, `F5`.
- Programs: a full path and optional arguments. The program is started directly, **never through a shell**, so characters such as `&` or `|` in the arguments are plain text. Paths are checked when you save and again before running. For `.bat` / `.cmd` files, shell characters in the arguments are refused. Two runs of the same kind are at least a second apart.

## The interface

The window is a web page written in HTML, CSS and JavaScript (`web/index.html`, `web/style.css`, `web/app.js`). The program serves it to this PC only (`127.0.0.1`, a random port and a random key in the address) together with the live video and a small API, and shows it in its own native window (no address bar, no browser profile, using the WebView2 runtime that comes with Windows 10 / 11). If that is not available it opens your default browser. The program's icon is the page's icon, so it is also the icon of the taskbar button.

To work on the design, open `web/index.html` straight from the folder (for example with Live Server): without the program behind it the page shows sample data.

Closing the window ends the program, unless **Run in the background** is on (Settings): then it keeps running with an icon in the system tray (open the window, switch the control, quit). Starting the program again while it runs just opens its window. On macOS there is no tray icon: the window is only minimized.

## Requirements

- Windows 10 / 11, macOS or Linux (X11)
- Python 3.12
- A webcam
- The Microsoft Edge WebView2 runtime (part of Windows 10 / 11)

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
| `app.py` | The program: starts the camera, tracking, server, tray and the app window |
| `webui.py` | The local server and the API behind the page, with its security checks |
| `web/` | The interface: `index.html`, `style.css`, `app.js`, icons |
| `render.py` | Draws the live video (mesh, trail, coordinates) and encodes it for the page |
| `window.py` | Shows the page in a native pywebview window (a child process) |
| `tray.py` | The system tray icon (run in the background) |
| `update_service.py` | Automatic update (check, download, install) without windows |
| `camera.py` | Threaded camera capture, always the latest frame |
| `tracker.py` | MediaPipe hands and face, publishes frame and landmarks together |
| `signs.py` | Hand sign classifier |
| `custom_gestures.py` | Recording, storing and recognising custom gestures |
| `mouse_control.py` | Cursor movement, clicks, scrolling, dominant hand, key and program actions |
| `commands.py` | Validation and running of key combinations and programs (no shell) |
| `view_aids.py` | The glow trail, click ripples, head axes, pinch gauge and the coordinates drawn on the video |
| `head_pose.py` | Head direction (3 axes, yaw / pitch / roll) and the face points that define a head pose |
| `perf.py` | Real rate and duration meters for the diagnostics tab |
| `autostart.py` | Start with the computer (Windows Run key, macOS LaunchAgent, Linux autostart file) |
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
| Windows single file | `Handy2-X.Y.Z-onefile.exe` (one EXE, nothing to unzip; slower first start) | PyInstaller, `Handy2-onefile.spec`; attached by the `release-onefile` workflow right after the release |
| Windows installer, alternative | `Handy2-NSIS-Setup-X.Y.Z.exe` | PyInstaller + NSIS (`installer.nsi`) |
| macOS | `Handy2-X.Y.Z-macos.zip` (the `.app`) | PyInstaller |
| Linux | `Handy2-X.Y.Z-linux-x64.tar.gz` | PyInstaller |
| Nuitka | `Handy2-X.Y.Z-<windows\|macos\|linux>-nuitka.(zip\|tar.gz)` | Nuitka (`tools/build_nuitka.py`) |

The Windows build and the tests decide whether a release is published; the other targets are built on the same run, reported in the run summary, and attached when they succeed.

## Roadmap

- [x] Live camera with hand and face mesh
- [x] Mouse control by hand or head
- [x] Click and scroll by hand sign
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
