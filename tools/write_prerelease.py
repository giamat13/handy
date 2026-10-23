"""Release build step: for a PRE (pre-release) build, write _prerelease.py with its PRE number, so that the program knows it is
"PRE N" of its version and says so in its title. The file is not in the repository (.gitignore). For a regular build nothing is
written (and an old file is removed).

N = the highest existing tag v<version>-beta.* + 1 (the release job names the tag the same way, so the number inside the program
is the number in the release). Needs the `gh` command and GH_TOKEN, which the GitHub runners have.

    PRERELEASE=true GITHUB_REPOSITORY=giamat13/handy python tools/write_prerelease.py
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
out = ROOT / "_prerelease.py"
out.unlink(missing_ok=True)
if os.environ.get("PRERELEASE", "").lower() != "true":
    print("a regular build: no PRE number")
    sys.exit(0)
version = re.search(r'^__version__\s*=\s*"([^"]+)"', (ROOT / "version.py").read_text("utf-8"), re.M).group(1)
repo = os.environ["GITHUB_REPOSITORY"]
r = subprocess.run(["gh", "api", f"repos/{repo}/git/matching-refs/tags/v{version}-beta."], capture_output=True, text=True, check=True)
nums = [int(m.group(1)) for ref in json.loads(r.stdout) if (m := re.search(r"-beta\.(\d+)$", ref["ref"]))]
n = max(nums, default=0) + 1
out.write_text(f"PRE = {n}\n", "utf-8")
print(f"wrote _prerelease.py: PRE {n} of {version}")
