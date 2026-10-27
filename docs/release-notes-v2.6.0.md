# Handy 2 2.6.0

## New

- **Threshold line on the Diagnostics bars**: the bar of each head, face and body gesture that has a threshold has a line where the threshold is (the default is the middle). Drag the line to the right, toward the edge the bar fills from, to make the gesture easier to recognise; drag it left to make it harder. Past the left edge the bar stretches, so the line stays visible. The new value is saved at once and applies from the next frame. With the keyboard, focus the bar and use the left and right arrow keys (left makes it harder, right easier).
- **Reset**: a reset button appears next to a bar only when its line has been moved from the default, and puts the line back.
- **Which gestures have the line**: head tilt left / right, head forward / back, mouth open, smile, raised brows, body jump, body crouch, body lean left / right.

- **Installer options when Handy 2 is already installed**: `Handy2Setup.exe` asks whether to update, repair or uninstall. Repair installs all the program files again and keeps your settings. Uninstall runs the uninstaller. The in-app updater and silent installs skip the question and update as before.

## Fixed

- **Start failed with a user name that is not in English**: the program stopped at start with "The path does not exist" when the installation path had letters outside ASCII (for example a Hebrew user name), because MediaPipe cannot open its models from such a path. The models are now copied once to `C:\ProgramData\Handy2` (or `C:\Handy2`) and loaded from there.

## Notes

- The fix for the user name is tested with synthetic folders only. Not checked: starting the installed program on a Windows user with a non-ASCII user name (the CI user name is ASCII), which is to be checked by hand.
- The new installer page is not tested automatically: the CI only builds the installer. Not checked: running `Handy2Setup.exe` over an installed copy and choosing each option, to be checked by hand.
- Nothing changes until a line is moved. The value is saved in `settings.json` under `tuning`. The line can go from almost the right edge (sensitivity 25) to four times the bar's length (sensitivity 0.125); a value outside that range is refused.
- Not covered: the built-in hand signs (pinch, OK, victory, and the rest), the hand motions (swipe, circle, wave), nod / shake and your own custom gestures. Nod and shake count swings rather than a threshold, and the others have their own thresholds, so they have no line.
- Arms up, the wink gestures and the long blink have no threshold, so they have no line. Their hold time can be set in `settings.json` under `tuning`, but there is no control for it in the Diagnostics tab in this version.
- Checked with automated tests on synthetic landmarks only, with no camera. Not checked in this release: how the line feels to drag on a real camera, and the macOS and Linux builds (the CI runs their tests on each push).
