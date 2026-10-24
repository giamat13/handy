# Handy 2 2.1.3

## Fixes and changes

- **Drawing works**: in Paint and other drawing programs, a stroke made by moving your hand was drawn as straight lines between a few points. The cursor now moves with real mouse input and in many small steps (about 125 a second) instead of jumping once per camera frame, so curves and circles follow your hand.
- **Trail and cursor coordinates are on by default** (they can still be turned off in the settings).
- **The thumbs-up gesture does nothing by default** (it used to turn the control on and off; F8 still does). A mapping you chose yourself is kept.
