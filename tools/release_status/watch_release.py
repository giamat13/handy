"""Watches the release workflow run every 30 seconds: prints the jobs when they change, exits 1 at the first failed job (with the job id,
for the log), exits 0 when the run succeeded.

    python tools/release_status/watch_release.py owner/repo [release.yml]

The token comes from git's credential store and is never printed.
"""
import json
import subprocess
import sys
import time
import urllib.request

REPO = sys.argv[1]
WORKFLOW = sys.argv[2] if len(sys.argv) > 2 else "release.yml"


def token():
    r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True)
    return next((l[9:] for l in r.stdout.splitlines() if l.startswith("password=")), "")


TOKEN = token()


def api(path):
    req = urllib.request.Request("https://api.github.com/repos/" + REPO + path, headers={
        "Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json", "User-Agent": "gh-release-watch"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main():
    last = None
    while True:
        run = api(f"/actions/workflows/{WORKFLOW}/runs?per_page=1")["workflow_runs"][0]
        jobs = api(f"/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
        line = " | ".join(f"{j['name']}: {j['conclusion'] or j['status']}" for j in jobs)
        if line != last:
            print(f"run {run['id']} {run['status']}: {line}", flush=True)
            last = line
        bad = [j for j in jobs if j["conclusion"] == "failure"]
        if bad:
            print(f"FAILED job {bad[0]['id']} ({bad[0]['name']}) in run {run['id']}", flush=True)
            sys.exit(1)
        if run["status"] == "completed":
            ok = run["conclusion"] == "success"
            print("RELEASE " + ("SUCCEEDED" if ok else "ended: " + str(run["conclusion"])), flush=True)
            sys.exit(0 if ok else 1)
        time.sleep(30)


if __name__ == "__main__":
    main()
