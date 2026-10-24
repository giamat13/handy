# Handy 2 2.3.0

## New

- **Built-in head gestures**, no recording needed, in the "Built-in gestures" tab, each bound to any action (all start as "none"):
  - **Nod (yes)** and **shake (no)**: three quick alternating swings of the head.
  - **Head tilt** to the left or right shoulder: stays active while the head is tilted, so it suits continuous scrolling or a key combination such as Alt+Left / Alt+Right.
  - **Head forward / back**: leaning towards the camera or away from it, read from the size of the face against your usual. Suits zoom (Ctrl+plus / Ctrl+minus).
  - **Wink** with the left or right eye, and a **long blink**: they stay active while the eye is shut, so they work as a click or a drag. A normal blink is ignored.
  - **Open mouth**, **smile** and **raised brows**: measured against your own usual, and they can be active together.
- **Built-in hand motions** (an open hand): swipe in four directions, a circle clockwise or counter-clockwise, and waving. They are measured in palm widths, so the distance from the camera does not matter, and they work only for the dominant hand set in the settings.
- The diagnostics tab shows a confidence bar for each of the new gestures.

## Notes

- All the new thresholds were tuned on synthetic faces and hands and then adjusted by hand on a real camera. If a gesture fires by mistake or is missed, report which one and how: the diagnostics tab shows how close it was.
- Face detection now uses the refined landmarks (more accurate around the eyes and the mouth); it costs a little time per frame, which the diagnostics tab shows.
- Winks and swipes also work while the hand or head moves the cursor, so the cursor can move a little during them.
