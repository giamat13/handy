# Handy 2 2.5.0

## New

- **Body gestures**: jump, crouch, lean left, lean right, and both arms up. Each one can be bound to any action, the same way as the hand and head gestures. All of them start unbound.
- **Whole-body skeleton on the video**: the body is drawn with its bones and points, and a part that is only partly in the frame is still drawn. Where the face mesh is drawn, the nose of the body skeleton is hidden. Where a hand is drawn, the body's hand bones are hidden, so the hand is not drawn twice. A "show body" setting turns the skeleton off.
- **Diagnostics**: a confidence bar for each body gesture, and the time the body detection takes in the performance rows.

## Notes

- The body-gesture thresholds are estimates that have not been tuned on a camera yet. If a gesture fires by mistake or does not fire, look at its bar in the Diagnostics tab and report it.
- Body gestures need the shoulders in the camera frame. Arms up also needs both wrists.
- A lean that is held for more than 8 seconds ends, and the new position becomes the level.
