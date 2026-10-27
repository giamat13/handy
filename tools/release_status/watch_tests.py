"""Starts run_local_tests.py and watches it: at the FIRST failed test it kills the whole run (the test processes too), prints the failed
test with its last lines and exits with 1 (that exit code wakes Claude up). When everything passed it prints "FINISHED OK" and exits 0.

    python tools/release_status/watch_tests.py            the usual set
    python tools/release_status/watch_tests.py test_pool  only these names (or --parallel N / --serial)

Run it in the background. It deletes a stale local-tests.json first (a killed run leaves one behind with every test marked failed).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROGRESS = HERE / "local-single.json" if len([a for a in sys.argv[1:] if not a.startswith("--")]) == 1 else HERE / "local-tests.json"


def kill_tree(p):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        p.kill()


def main():
    PROGRESS.unlink(missing_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.Popen([sys.executable, str(HERE / "run_local_tests.py"), *sys.argv[1:]], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while True:
        time.sleep(3)
        try:
            state = json.loads(PROGRESS.read_text("utf-8"))
        except (OSError, ValueError):
            state = None
        if state:
            bad = [t for t in state["tests"] if t["state"] == "fail"]
            if bad:
                kill_tree(p)
                for t in bad:
                    print("FAILED:", t["name"], t.get("summary", ""))
                    print(t.get("detail", ""))
                sys.exit(1)
            if state.get("finished") and p.poll() is not None:
                print("FINISHED OK")
                sys.exit(0)
        if p.poll() is not None and not (state and state.get("finished")):
            print("the run ended without a result; exit code", p.returncode)
            sys.exit(1)


if __name__ == "__main__":
    main()
