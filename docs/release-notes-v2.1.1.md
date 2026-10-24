# Handy 2 2.1.1

## Fixes and changes

- **Winks**: a real wink almost always narrows the other eye a little, and the detector wanted it to stay wide open, so winks were missed. It now needs one eye clearly closed (under 70% of its normal opening) and the other clearly more open than it (and not under 60%). A blink, with both eyes shutting, is still not a wink. The **Head gestures** tab shows how open each eye is, live, with the closing line, so you can see what the detector sees.
- **Long press**: the separate long-press / drag actions are gone. A click now simply stays pressed for as long as you keep making the gesture: a short gesture is a click, a held gesture is a long press or a drag. Key combinations work the same way: the keys stay pressed while the gesture lasts and are released when it ends. A mapping saved with "drag" or a long-press action becomes the plain click automatically. Double click is still instant.
