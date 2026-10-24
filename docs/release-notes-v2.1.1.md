# Handy 2 2.1.1

## Fixes and changes

- **Winks and blinks are removed**: the detection never worked reliably enough, so the wink gestures, the head-gestures tab and the eye meters are gone. Hand signs are unchanged. A mapping saved for a wink is dropped when the settings load. (Moving the cursor with the head is still there.)
- **Long press**: the separate long-press / drag actions are gone. A click now simply stays pressed for as long as you keep making the gesture: a short gesture is a click, a held gesture is a long press or a drag. Key combinations work the same way: the keys stay pressed while the gesture lasts and are released when it ends. A mapping saved with "drag" or a long-press action becomes the plain click automatically. Double click is still instant.
