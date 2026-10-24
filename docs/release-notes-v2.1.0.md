# Handy 2 2.1.0

## New

- **Custom gestures**: record your own static hand poses (window "מחוות", or the button in Settings). Give the pose a name and hold it in front of the camera; it is saved in `custom_gestures.json` next to `settings.json`. You can rename, re-record and delete gestures. A custom gesture appears in the status line and in the gesture-to-action mapping like a built-in one. A pose that is already a built-in sign, or too close to another custom gesture, is refused; a gesture is recognised only after the hand rests in the pose for a moment, so moving between poses triggers nothing.
- **Keys and programs**: every gesture (built-in or custom) can press a key combination (`Ctrl+C`, `Alt+Tab`, `Win+D`, ...) or start a program or script with arguments. Nothing runs through a shell, the key names come from a fixed list, and the values are checked when you save them and again before they run.
- **Dominant hand**: choose which hand controls the mouse: right, left or both (default: both, as before). The active hand is marked with a green ring on the video and in the status line.
- **Hang Loose** (right click) and **Victory** (left click) signs.
- **Trail** after the controlling point, and **cursor coordinates** on the video. Both are switches in Settings, off by default.
- **Windows, macOS and Linux**: the code now runs on all three (data folders, mouse, key presses, hotkeys F8 / F9). See the README for the system-specific notes.
- **More downloads**: Windows installer (Inno Setup, used by the automatic update), portable ZIP, an NSIS installer, a macOS app (`.zip`), a Linux archive (`.tar.gz`) and Nuitka builds for all three systems.

## Changes you may notice

- **Thumbs up now turns the mouse control on and off** (same as F8). The scrolling that used thumbs up / down moved to **three fingers = scroll up** and **rock = scroll down**, because a gesture that switches the control and a gesture that scrolls cannot share a pose. If you never changed the mapping, the move is automatic; if you did, your mapping is left as it was. Everything can still be changed in Settings.
- **"Peace" and "Victory" are the same sign (V)**; it is now called Victory, and a mapping you saved for Peace is kept. Default: left click.
- **Settings folder**: an installed app now keeps its settings in `%APPDATA%\Handy` (before: `%APPDATA%\Handy2`). The first start moves the old files over and does not overwrite anything that already exists in the new folder. The portable build is unchanged (`data` folder next to the program).
- The mouse control is always off when the program starts, even if it was on when you closed it.
