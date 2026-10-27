"""Start the release dashboard from a clean page: puts the current log, tasks and test results away (tools/release_status/archive/)
and clears them. The page does this by itself when a release is out and new work begins; this is the same thing by hand.

    python tools/release_status/reset.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_page  # noqa: E402

status_page.reset("v" + status_page.version())
print("the dashboard was reset (the old log, tasks and test results are in tools/release_status/archive/)")
