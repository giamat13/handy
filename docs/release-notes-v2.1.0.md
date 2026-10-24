# Handy 2 2.1.0

## New

- **Custom gestures**: record your own static hand poses (window "מחוות", or the button in Settings). Give the pose a name and hold it in front of the camera; it is saved in `custom_gestures.json` next to `settings.json`. You can rename, re-record and delete gestures. A custom gesture appears in the status line and in the gesture-to-action mapping like a built-in one. A pose that is already a built-in sign, or too close to another custom gesture, is refused; a gesture is recognised only after the hand rests in the pose for a moment, so moving between poses triggers nothing.
- **Keys and programs**: every gesture (built-in or custom) can press a key combination (`Ctrl+C`, `Alt+Tab`, `Win+D`, ...) or start a program or script with arguments. Nothing runs through a shell, the key names come from a fixed list, and the values are checked when you save them and again before they run.
- **Dominant hand**: choose which hand controls the mouse: right, left or both (default: both, as before). The active hand is marked with a green ring on the video and in the status line.
- **Hang Loose** (right click) and **Victory** (left click) signs.
- **Trail** after the controlling point, and **cursor coordinates** on the video. Both are switches in Settings, off by default.
- **Windows, macOS and Linux**: the code now runs on all three (data folders, mouse, key presses, hotkeys F8 / F9). See the README for the system-specific notes.
- **More downloads**: Windows installer (Inno Setup, used by the automatic update), portable ZIP, an NSIS installer, a macOS app (`.zip`), a Linux archive (`.tar.gz`) and Nuitka builds for all three systems.

- **New interface, written in HTML**: the window is now a web page (`web/index.html`, `style.css`, `app.js`) shown by the program in an app window of Edge / Chrome (no address bar), instead of a Python window. The layout is the same: live video with the hand mesh on one side; on the other side tabs for **hand gestures**, **head gestures** (winks), **settings** and **updates**. The page is served only to this PC (`127.0.0.1`, with a random key), and the program's own icon is the window's icon in the taskbar.
- **Run in the background**: a switch in Settings. When it is on, closing the window leaves the program running (camera, tracking and mouse control) with an icon in the system tray; from there you open the window again, switch the control on / off, or quit. Starting the program a second time just opens the window of the one that is already running.
- **Long press**: a gesture can hold the left / right / middle mouse button, or a key combination, pressed for as long as you keep making the gesture, and lets go when you stop. The held buttons and keys are always released when the gesture ends, when the control is switched off, and when the program closes.
- **Custom gestures take priority**: a pose that looks like a built-in sign is now allowed. While your pose is held, the built-in sign is not triggered. **Train more** adds samples to an existing gesture (another angle, another distance) so it is recognised more reliably.
- **Winks are recognised on more faces**: the detector learns how wide each of your eyes is normally open (small eyes, glasses and an angled camera used to make it miss).

## Changes you may notice

- **Thumbs up now turns the mouse control on and off** (same as F8). The scrolling that used thumbs up / down moved to **three fingers = scroll up** and **rock = scroll down**, because a gesture that switches the control and a gesture that scrolls cannot share a pose. If you never changed the mapping, the move is automatic; if you did, your mapping is left as it was. Everything can still be changed in Settings.
- **"Peace" and "Victory" are the same sign (V)**; it is now called Victory, and a mapping you saved for Peace is kept. Default: left click.
- **Settings folder**: an installed app now keeps its settings in `%APPDATA%\Handy` (before: `%APPDATA%\Handy2`). The first start moves the old files over and does not overwrite anything that already exists in the new folder. The portable build is unchanged (`data` folder next to the program).
- The mouse control is always off when the program starts, even if it was on when you closed it.
- The program needs Microsoft Edge or Google Chrome for its window (Edge is part of Windows 10 / 11). Without them it opens the page in your default browser.
