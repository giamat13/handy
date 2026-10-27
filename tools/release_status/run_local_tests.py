"""Runs the local tests one after the other and writes their progress to local-tests.json, which tools/release_status/status_page.py
shows live: what is running, how many checks of it passed so far, its last lines, what passed, how long is left. How long each test
took last time is kept in local-tests-history.json and is the estimate for the next run. Nothing here touches a real library: the
tests use throw-away profiles and fake cameras.

    python tools/release_status/run_local_tests.py                     the usual set (the same files as the Windows job in tests.yml)
    python tools/release_status/run_local_tests.py test_signs test_gaze   only these
    python tools/release_status/run_local_tests.py test_signs             one test: written to local-single.json, shown in its own card
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PROGRESS = HERE / "local-tests.json"
HISTORY = HERE / "local-tests-history.json"
# the project's local tests: the files of tests/ that the Windows job in .github/workflows/tests.yml runs.
# test_overlay.py is left out on purpose: it imports modules that do not exist in this layout (the same as in tests.yml).
DEFAULT = ["test_signs", "test_release", "test_updater", "test_mouse_clicks", "test_settings", "test_commands", "test_custom_gestures",
           "test_head_gestures", "test_head_motion", "test_body_gestures", "test_eye_gestures", "test_face_expressions", "test_hand_motion",
           "test_gaze", "test_diagnostics", "test_view_aids", "test_tray", "test_webui", "test_tuning", "test_mp_path", "test_tracker"]
GUESS = 45          # seconds, for a test that has never run
TAIL = 5            # lines of the running test that the page shows
WRITE_EVERY = 0.4   # seconds between writes of the progress file while a test runs


def load(p, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def notify_failure(name, detail):
    """A message box on the user's screen the moment a test fails (the run goes on; the box is its own process, so it stays up)."""
    if sys.platform != "win32" or not os.environ.get("RELEASE_TEST_POPUP"):   # no box by default: the failure shows on the dashboard; set RELEASE_TEST_POPUP=1 to get it back
        return
    code = "import ctypes,sys; ctypes.windll.user32.MessageBoxW(0, sys.argv[1], 'a test failed', 0x10 | 0x40000)"   # error icon, topmost
    try:
        subprocess.Popen([sys.executable, "-c", code, f"Test failed: {name}\n\n{detail[:500]}"], creationflags=0x00000008 | 0x00000200, close_fds=True)
    except OSError:
        pass


def command(name):
    # one test file of tests/ through pytest, verbose: every test prints its own PASSED / FAILED line for the live counter
    return [sys.executable, "-m", "pytest", "-v", str(ROOT / "tests" / f"{name}.py")]


def summarize(text):
    """('12/12' | '30 passed' | ..., failed count) from what a test printed."""
    fails = len(re.findall(r"^FAIL", text, re.M))
    m = re.findall(r"(\d+)/(\d+) passed", text)
    if m:
        a, b = m[-1]
        return f"{a}/{b}", fails
    m = re.findall(r"(\d+) passed", text)              # pytest's last line: "12 passed in 3.10s" (or "3 failed, 9 passed")
    if m:
        return f"{m[-1]} passed" + (f", {fails} failed" if fails else ""), fails
    ok = len(re.findall(r"^PASS", text, re.M))
    if ok or fails:
        return f"{ok} passed" + (f", {fails} failed" if fails else ""), fails
    if "OK:" in text:
        return "ok", fails
    return "", fails


SAVE_LOCK = threading.Lock()


def save(state):
    with SAVE_LOCK:
        tmp = PROGRESS.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), "utf-8")
        for _ in range(5):
            try:
                os.replace(tmp, PROGRESS)
                return
            except PermissionError:               # the page is reading it this very moment
                time.sleep(0.1)


def run_one(t, state, env):
    """Run one test, streaming its output: the page sees the checks pile up while it runs."""
    t["state"], t["began"], t["live"] = "run", time.time(), {"pass": 0, "fail": 0, "last": []}
    save(state)
    p = subprocess.Popen(command(t["name"]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         env=env, cwd=str(ROOT), bufsize=1)
    lines, last_write = [], 0.0
    for line in p.stdout:
        line = line.rstrip("\n")
        lines.append(line)
        live = t["live"]
        if line.startswith("PASS") or " PASSED" in line:
            live["pass"] += 1
        elif line.startswith("FAIL") or " FAILED" in line:
            live["fail"] += 1
        if line.strip():
            live["last"] = (live["last"] + [line[:150]])[-TAIL:]
        if time.time() - last_write > WRITE_EVERY:
            save(state)
            last_write = time.time()
    p.wait()
    return p.returncode, "\n".join(lines)


def wait_ports_free(ports, seconds=20):
    """A test ends right after telling its server to stop; the server may still hold the port for a moment. The next test on the same port
    would then talk to the old server (a different profile: an empty catalog) -- so wait until nothing answers there any more."""
    import socket
    end = time.time() + seconds
    for port in ports:
        while time.time() < end:
            with socket.socket() as sk:
                sk.settimeout(0.3)
                if sk.connect_ex(("127.0.0.1", int(port))) != 0:
                    break
            time.sleep(0.3)


def ports_of(name):
    """The fixed ports a test's file uses (its server, its fake services). Two tests that share one must not run together."""
    f = ROOT / "tests" / f"{name}.py"
    try:
        return set(re.findall(r"\b(8[0-9]{3})\b", f.read_text("utf-8")))
    except OSError:
        return set()


def main():
    args = sys.argv[1:]
    workers = 4                                  # at most 4 tests at a time: each one loads numpy and OpenCV; --serial runs one at a time
    if "--serial" in args:
        args.remove("--serial")
        workers = 1
    if "--parallel" in args:
        i = args.index("--parallel")
        workers = max(1, int(args[i + 1]))
        del args[i:i + 2]
    names = args or DEFAULT
    if args and len(names) == 1:                 # one test on its own: its own file, so a run of the whole set that is going on is not overwritten; the page shows it in its own card
        global PROGRESS
        PROGRESS = HERE / "local-single.json"
    hist = load(HISTORY, {})
    state = {"started": time.time(), "finished": None,
             "tests": [{"name": n, "state": "todo", "seconds": None, "estimate": hist.get(n, GUESS), "summary": ""} for n in names]}
    state["workers"] = workers
    save(state)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    lock, busy, pending = threading.Lock(), set(), sorted(state["tests"], key=lambda t: -t["estimate"])      # the longest first: they finish together
    ports = {t["name"]: ports_of(t["name"]) for t in pending}

    def take():
        """The next test whose ports nobody is using right now (None: nothing is free yet; False: nothing is left)."""
        with lock:
            if not pending:
                return False
            for t in pending:
                if not (ports[t["name"]] & busy):
                    pending.remove(t)
                    busy.update(ports[t["name"]])
                    return t
            return None

    def worker():
        while True:
            t = take()
            if t is False:
                return
            if t is None:
                time.sleep(0.3)
                continue
            try:
                code, out = run_one(t, state, env)
                t["seconds"] = round(time.time() - t["began"], 1)
                t["summary"], fails = summarize(out)
                t["state"] = "done" if code == 0 and not fails else "fail"
                t.pop("live", None)
                if t["state"] == "fail":
                    t["detail"] = "\n".join(l for l in out.splitlines() if l.startswith("FAIL") or "Error" in l)[-600:]
                    notify_failure(t["name"], t["detail"])
                else:
                    with lock:
                        hist[t["name"]] = t["seconds"]
                with lock:
                    HISTORY.write_text(json.dumps(hist, ensure_ascii=False), "utf-8")
                save(state)
            finally:
                wait_ports_free(ports[t["name"]])
                with lock:
                    busy.difference_update(ports[t["name"]])

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    state["finished"] = time.time()
    save(state)
    bad = [t["name"] for t in state["tests"] if t["state"] == "fail"]
    print("FAILED: " + ", ".join(bad) if bad else "all passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
