# Handy 2 2.6.0

## New

- **Threshold line on the Diagnostics bars**: the bar of each head, face and body gesture that has a threshold has a line where the threshold is (the default is the middle). Drag the line to the right, toward the edge the bar fills from, to make the gesture easier to recognise; drag it left to make it harder. Past the left edge the bar stretches, so the line stays visible. The new value is saved at once and applies from the next frame. With the keyboard, focus the bar and use the left and right arrow keys (left makes it harder, right easier).
- **Reset**: a reset button appears next to a bar only when its line has been moved from the default, and puts the line back.
- **Which gestures have the line**: head tilt left / right, head forward / back, mouth open, smile, raised brows, body jump, body crouch, body lean left / right.

## Notes

- Nothing changes until a line is moved. The value is saved in `settings.json` under `tuning`. The line can go from almost the right edge (sensitivity 25) to four times the bar's length (sensitivity 0.125); a value outside that range is refused.
- Not covered: the built-in hand signs (pinch, OK, victory, and the rest), the hand motions (swipe, circle, wave), nod / shake and your own custom gestures. Nod and shake count swings rather than a threshold, and the others have their own thresholds, so they have no line.
- Arms up, the wink gestures and the long blink have no threshold, so they have no line. Their hold time can be set in `settings.json` under `tuning`, but there is no control for it in the Diagnostics tab in this version.
- Checked with automated tests on synthetic landmarks only, with no camera. Not checked in this release: how the line feels to drag on a real camera, and the macOS and Linux builds (the CI runs their tests on each push).
