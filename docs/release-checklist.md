# How to release a version

Version scheme: **2.X.Y** — X is a feature, Y is a fix. A release with a new feature raises X and resets Y (`2.1.0`); a release with only fixes raises Y (`2.1.1`). Several small features released together count as one feature. Always write all three parts.

## Steps

1. Pick the number and set `__version__` in `version.py`.
2. Write `docs/release-notes-vX.Y.Z.md` (it becomes the body of the GitHub release; without it GitHub generates notes).
3. Run the tests: `python -m pytest tests`.
4. Run the app (F5) and check the camera, mesh, mouse control and a click gesture by hand.
5. Commit and push to `main`.
6. Release, either way:
   - **Tag:** `git tag vX.Y.Z && git push origin vX.Y.Z` (the tag must equal `version.py`).
   - **By hand:** Actions → *release* → *Run workflow* on `main` (the tag is created for you). Tick *prerelease* for a test build: its tag is `vX.Y.Z-beta.N`.
7. The workflow runs the tests, builds every target and publishes them. Open the run summary: the *publish* job lists each target as `built` or `MISSING`. The Windows files (`Handy2Setup.exe`, `Handy2-X.Y.Z-portable.zip`) are required; the NSIS installer, the macOS `.zip`, the Linux `.tar.gz` and the three Nuitka builds are best effort and are attached only if they were built.

## Build locally

`build.bat` (needs `pip install -r requirements-dev.txt`; Inno Setup 6 is optional and only needed for the installer).

Other targets (each on its own system):

- NSIS: `makensis /DVERSION=X.Y.Z installer.nsi` after `build.bat` has made `dist\Handy2`.
- macOS: `python tools/make_icon.py && pyinstaller Handy2.spec && python tools/make_platform_archive.py macos`
- Linux: `pyinstaller Handy2.spec && python tools/make_platform_archive.py linux`
- Nuitka: `pip install nuitka ordered-set zstandard && python tools/build_nuitka.py && python tools/make_platform_archive.py nuitka`

The single-file EXE `Handy2-X.Y.Z-onefile.exe` is attached by the separate `release-onefile` workflow once the release run succeeds (or run it by hand with the tag, if it did not start).

The in-app updater downloads only `Handy2Setup*.exe`, so the other file names must never start with `Handy2Setup` (a test checks this).

## Not done yet

- The macOS, Linux, Nuitka and NSIS builds were written without being run on those systems. Look at the first real run on GitHub and fix what it reports; the macOS app and the Linux build also need a manual check of the camera, the mouse and the key actions.
- macOS: no signing or notarization, so the first start needs right click → Open.
- Code signing: the EXE and installer are unsigned, so Windows SmartScreen / Smart App Control may warn or block them.
- The automatic update has only been tested against a mock GitHub. Before relying on it, test it once for real: install one release, publish the next, and watch the update window, the download, the silent install (`/SILENT /update=1`) and the restart.
- An unsigned installer may be blocked by Windows; the update window then sends the user to the release page.

## How the automatic update works

The app checks the latest GitHub release at start-up and once a day (`updater.py`, `update_ui.py`). It downloads only `Handy2Setup.exe` from this repository's release URLs, verifies size and SHA-256 (GitHub adds the digest to every asset), saves a rollback copy of the program folder, runs the installer silently and restarts. If the update is interrupted, the next start (or a RunOnce script at the next sign-in) puts the saved folder back. The portable build and a source checkout open the release page instead. Pre-releases (`-beta.N`) are offered only in tester mode.
