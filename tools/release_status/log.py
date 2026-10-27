"""Adds one line to the live log that the release dashboard (status_page.py) shows: what is being done right now.

    python tools/release_status/log.py "running the smart UI test again"
"""
import json
import sys
import time
from pathlib import Path

FILE = Path(__file__).resolve().parent / "activity.json"
KEEP = 40


def main():
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        return
    try:
        items = json.loads(FILE.read_text("utf-8"))
    except (OSError, ValueError):
        items = []
    items.append({"at": time.time(), "text": text[:200]})
    FILE.write_text(json.dumps(items[-KEEP:], ensure_ascii=False), "utf-8")


if __name__ == "__main__":
    main()
