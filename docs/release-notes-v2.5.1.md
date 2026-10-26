# Handy 2 2.5.1

## Fixed

- **Keyboard shortcuts on macOS**: a shortcut with a key other than a single letter (Tab, Enter, F5, the arrow keys, and so on) did not work on macOS, and a shortcut with Insert could not run there at all. Now only the keys of the shortcut itself have to exist on the system. A key that macOS does not have is skipped, and the log says so.
- **The single-folder build (Nuitka)** for Windows, macOS and Linux failed with a conflict in the pywebview plugin. It builds again.

## Notes

- The macOS and Linux tests are part of every release now, so a version is published only when they pass.
- If a shortcut still does nothing on a Mac, report it with the shortcut you used.
