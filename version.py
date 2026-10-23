"""The app version: the single source of truth.

build.bat and the release workflow read it (installer /DMyAppVersion, the tag, the file names). Bump it before every release.

Numbering "2.X.Y": the first number is always 2 (this is Handy 2). X is a feature: a release with a new feature raises X and
resets Y ("2.1.0"). Y is a fix: a release with only fixes raises Y ("2.1.1"). Several small features released together count as
one feature (three additions in one release make "2.1.0", not "2.3.0"). ALWAYS write all three parts.
Pre-releases add "-beta.N" ("2.1.0-beta.1"); the release workflow names them, and a pre-release build knows its N from
_prerelease.py (written by tools/write_prerelease.py into a PRE build only, never committed).
"""
__version__ = "2.0.1"
REPO = "giamat13/handy"
try:
    from _prerelease import PRE
except ImportError:
    PRE = 0  # 0 = a regular build (and every build from source)
# "2.1.0" for a regular build, "2.1.0-beta.2" for PRE 2 of 2.1.0. __version__ itself stays plain (file names and tags use it).
FULL_VERSION = f"{__version__}-beta.{PRE}" if PRE else __version__
