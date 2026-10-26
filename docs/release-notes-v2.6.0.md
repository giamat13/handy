# Handy 2 2.6.0

## New

- **Tuning for each gesture**: in the Diagnostics tab every gesture that can be tuned has a **Tune** button (the button is labelled כוונון) next to its bar. It opens two sliders:
  - **Sensitivity**: the threshold. Higher means the gesture is recognised with a smaller movement or pose; lower means it has to be more exact.
  - **Hold time**: how long the pose has to be held before the gesture counts. Higher means it has to be held longer.

  100% is the default, and the **Reset** button goes back to it. Each change is saved at once and applies from the next frame, without restarting.
- **Which gestures**: sensitivity and hold time for head tilt left / right, head forward / back, mouth open, smile, raised brows, body crouch, body lean left / right. Sensitivity only for nod, shake and body jump. Hold time only for wink left / right, long blink and arms up.
- **Not covered**: the built-in hand signs (pinch, OK, victory, and the rest), the hand motions (swipe, circle, wave) and your own custom gestures. Custom gestures keep the threshold that was learned when they were recorded.

## Notes

- Nothing changes until a slider is moved. The values are saved in `settings.json` under `tuning`, and a value outside the range (50% to 200%) is refused.
- The body-gesture thresholds of 2.5.0 can now be adjusted, so if a body gesture fires by mistake or does not fire, change its sensitivity or hold time in the Diagnostics tab and keep the values that work for you.
- Checked with automated tests on synthetic landmarks only, with no camera. Not checked in this release: how the sliders feel on a real camera, and the macOS and Linux builds (the CI runs their tests on each push).
