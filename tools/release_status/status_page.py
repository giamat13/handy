"""A live dashboard about a release, in plain language: the local tests (from local-tests.json, written by run_local_tests.py), the commit and
push, and what GitHub is doing (the release workflow's jobs and steps), with a time estimate for each part and for the whole.

Open tools/release_status/status.html in a browser. It loads fresh data (status-data.js, written here every few seconds) without
reloading the page, its clocks tick every second, and it says so loudly when the data stops coming. Read-only: it never pushes,
releases or changes anything. The GitHub token (from git's credential store) stays in this process and is never written anywhere.

    python tools/release_status/status_page.py            keeps running; the page resets itself when a release is out and new work begins
    python tools/release_status/status_page.py --once     write the data once and stop
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PAGE = HERE / "status.html"
DATA = HERE / "status-data.js"
PROGRESS = HERE / "local-tests.json"
SINGLE = HERE / "local-single.json"      # one test run on its own (run_local_tests.py with a single name)
CYCLE = HERE / "cycle.json"          # {"closed": "v2.6.0"}: the last release whose page was put away
ARCHIVE = HERE / "archive"
ACTIVITY = HERE / "activity.json"   # the live log: [{"at": epoch, "text": "..."}], written by log.py
TODO = HERE / "todo.json"          # the coding tasks, written by whoever is writing the code: [{"text": "...", "state": "todo|run|done"}]
VERSION_FILE = "version.py"                          # the file that holds the version number (relative to the repository root)
VERSION_RE = r'__version__\s*=\s*"([^"]+)"'          # a regex whose group 1 is the version in that file
RELEASE_WORKFLOW = "release"                         # the `name:` of the release workflow in .github/workflows
DEFAULT_GH_SECONDS = 720
LOCAL_EVERY, GITHUB_EVERY = 3, 8          # seconds


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=str(ROOT))
    return r.stdout.strip()


def repo():
    """owner/name from the origin remote."""
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", git("remote", "get-url", "origin"))
    return m.group(1) if m else ""


REPO = repo()
BRANCH = (git("symbolic-ref", "--short", "refs/remotes/origin/HEAD").split("/", 1)[-1]) or "main"


def token():
    r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True)
    return next((l[9:] for l in r.stdout.splitlines() if l.startswith("password=")), "")


TOKEN = token()


def api(path):
    req = urllib.request.Request("https://api.github.com/repos/" + REPO + path, headers={
        "Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json", "User-Agent": "release-status"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def epoch(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def version():
    m = re.search(VERSION_RE, (ROOT / VERSION_FILE).read_text("utf-8"))
    return m.group(1) if m else "?"


# ---- plain-language names of what GitHub does (job names and step names come from .github/workflows)
# one entry per job of the workflows: "<job name as GitHub shows it>": ("short title", "one-line description")
JOBS = {
    "tests / test": ("בדיקות Windows", "מריץ את הבדיקות האוטומטיות על Windows"),
    "tests / test-other-platforms (ubuntu-latest)": ("בדיקות Linux", "אותן בדיקות על Linux"),
    "tests / test-other-platforms (macos-latest)": ("בדיקות macOS", "אותן בדיקות על macOS"),
    "build": ("בנייה ל-Windows", "בונה את מתקין Windows, ה-ZIP הנייד ומתקין NSIS"),
    "build-macos": ("בנייה ל-macOS", "אפליקציית macOS (לא חובה)"),
    "build-linux": ("בנייה ל-Linux", "קובץ Linux (לא חובה)"),
    "build-nuitka (windows-latest)": ("Nuitka ל-Windows", "גרסת Nuitka ל-Windows (לא חובה)"),
    "build-nuitka (ubuntu-latest)": ("Nuitka ל-Linux", "גרסת Nuitka ל-Linux (לא חובה)"),
    "publish": ("פרסום", "אוסף את כל הקבצים ומפרסם את השחרור - השלב האחרון"),
}
# (a part of a step name, plain text) for the steps worth explaining; other steps show their own name
STEPS = [
    ("Tag matches version.py", "בודק ש-version.py תואם לתג"),
    ("A PRE build knows", "כותב את מספר ה-PRE (בשחרור רגיל לא כותב כלום)"),
    ("Build the portable ZIP", "בונה את ה-ZIP הנייד"),
    ("Build the installer", "בונה את מתקין Inno Setup"),
    ("Build the NSIS installer", "בונה את מתקין NSIS (לא חובה)"),
    ("Keep the release files", "אוסף את קבצי השחרור"),
    ("upload-artifact", "מעלה את הקבצים שנבנו"),
    ("download-artifact", "לוקח את הקבצים שנבנו"),
    ("Report every target", "רושם איזה קובץ נבנה ואיזה חסר"),
    ("Publish the release", "יוצר את השחרור ב-GitHub (כאן נוצר התג)"),
    ("PyInstaller", "אורז את התוכנה (PyInstaller)"),
    ("build_nuitka", "בונה את גרסת Nuitka"),
    ("make_platform_archive", "אורז את הקבצים לארכיון"),
    ("python -m pytest", "מריץ את הבדיקות"),
    ("Run the tests", "מריץ את הבדיקות"),
    ("pip install", "מתקין את התוכנות הדרושות"),
]
PLUMBING = ("Set up job", "Complete job", "Post Run", "Run actions/checkout", "Run actions/setup-python")


def plain_step(name):
    for key, text in STEPS:
        if key in name:
            return text, ("" if name == text else name)
    return name, ""


def state_of(o):
    if o.get("status") != "completed":
        return "run" if o.get("status") == "in_progress" else "todo"
    return "done" if o.get("conclusion") in ("success", "neutral", "skipped") else "fail"


class Cache:
    prog = None            # the last good content of the local tests' progress file
    gh_at = 0.0
    gh = {}
    hist = {}              # the jobs (with their steps) of the last successful release run: how long each part usually takes


def dur(o):
    return (epoch(o["completed_at"]) - epoch(o["started_at"])) if o and o.get("started_at") and o.get("completed_at") else None


def github(remote):
    """Runs, jobs and releases, at most every GITHUB_EVERY seconds."""
    if time.time() - Cache.gh_at < GITHUB_EVERY and Cache.gh.get("remote") == remote:
        return Cache.gh
    out = {"remote": remote, "error": "", "runs": [], "rels": [], "jobs": [], "cur": None}
    try:
        out["runs"] = api("/actions/runs?per_page=15")["workflow_runs"]
        out["rels"] = api("/releases?per_page=4")
        ok_runs = [r for r in out["runs"] if r["name"] == RELEASE_WORKFLOW and r["status"] == "completed" and r["conclusion"] == "success"]
        if ok_runs and Cache.hist.get("run") != ok_runs[0]["id"]:
            try:
                Cache.hist = {"run": ok_runs[0]["id"], "jobs": {j["name"]: j for j in api(f"/actions/runs/{ok_runs[0]['id']}/jobs?per_page=50")["jobs"]}}
            except Exception:
                pass
        rel_runs = [r for r in out["runs"] if r["name"] == RELEASE_WORKFLOW]
        out["cur"] = next((r for r in rel_runs if r["head_sha"] == remote), None) if remote else None
        if out["cur"]:
            out["jobs"] = api(f"/actions/runs/{out['cur']['id']}/jobs?per_page=50")["jobs"]
    except Exception as e:
        out["error"] = f"GitHub לא ענה ({e}). מנסה שוב."
        out["runs"] = Cache.gh.get("runs", []) if Cache.gh else []
    Cache.gh, Cache.gh_at = out, time.time()
    return out


def collect():
    now = time.time()
    target = "v" + version()
    # ---- local tests
    try:
        prog = json.loads(PROGRESS.read_text("utf-8"))
        Cache.prog = prog
    except (OSError, ValueError):
        prog = Cache.prog if PROGRESS.exists() else None          # the file was being replaced at that moment (Windows): keep the last good state, do not blink the tests away
        if prog is None:
            Cache.prog = None
    local, local_left, local_state, local_now = [], 0.0, "todo", ""
    if prog:
        lefts, running = [], []
        for i, t in enumerate(prog["tests"]):
            left = 0.0
            if t["state"] == "run":
                left = max(0.0, t["estimate"] - (now - t["began"]))
                running.append(t["name"])
            elif t["state"] == "todo":
                left = t["estimate"]
            if left:
                lefts.append(left)
            local.append({"name": t["name"], "state": t["state"], "summary": t.get("summary", ""), "seconds": t.get("seconds"),
                          "estimate": t["estimate"], "began": t.get("began"), "detail": t.get("detail", ""), "live": t.get("live")})
        # tests run several at a time: what is left is the longest one, or all of it divided among the workers, whichever is more
        workers = max(1, int(prog.get("workers") or 1))
        local_left = max(max(lefts), sum(lefts) / workers) if lefts else 0.0
        if running:
            done_n = sum(1 for t in prog["tests"] if t["state"] == "done")
            local_now = f"{done_n} מתוך {len(prog['tests'])} הסתיימו · רצות עכשיו: " + ", ".join(running[:4]) + (f" (+{len(running) - 4})" if len(running) > 4 else "")
        sts = [t["state"] for t in prog["tests"]]
        local_state = "fail" if "fail" in sts else ("done" if all(s == "done" for s in sts) else "run")

    # ---- one test on its own: shown while it runs, and for ten minutes after it ended
    single = None
    try:
        sp = json.loads(SINGLE.read_text("utf-8"))
        st = sp["tests"][0]
        if st["state"] in ("run", "todo") or now - (sp.get("finished") or sp.get("started") or 0) < 600:
            single = {"name": st["name"], "state": st["state"], "summary": st.get("summary", ""), "seconds": st.get("seconds"), "estimate": st["estimate"],
                      "began": st.get("began"), "detail": st.get("detail", ""), "live": st.get("live")}
    except (OSError, ValueError, KeyError, IndexError):
        pass

    # ---- git
    dirty = len([l for l in git("status", "--porcelain").splitlines() if l.strip()])
    head = git("rev-parse", "HEAD")
    remote = git("ls-remote", "origin", f"refs/heads/{BRANCH}").split("\t")[0] if time.time() - Cache.gh_at >= GITHUB_EVERY else Cache.gh.get("remote", "")
    # this version is on GitHub when the remote is the commit that is checked out AND that commit holds this version's number: the run of the last
    # release (an older version) is not this work's run, and edits made while this version is building (a fix for the next one) change nothing here
    remote_ver = re.search(VERSION_RE, git("show", f"{remote}:{VERSION_FILE}")) if (remote and remote == head) else None
    pushed = bool(remote) and remote == head and bool(remote_ver) and ("v" + remote_ver.group(1)) == target

    # ---- GitHub
    gh = github(remote if pushed else "")
    cur, rels = gh["cur"], gh["rels"]
    rel_runs = [r for r in gh["runs"] if r["name"] == RELEASE_WORKFLOW]
    prev = [r for r in rel_runs if r["status"] == "completed" and r["conclusion"] == "success"][:3]
    typical = sum(epoch(r["updated_at"]) - epoch(r["created_at"]) for r in prev) / len(prev) if prev else DEFAULT_GH_SECONDS
    published = any(r["tag_name"] == target and not r["draft"] for r in rels)
    # a release that is out and a page that is done: when new work begins (files changed) or after a quarter of an hour, start clean
    try:
        closed = json.loads(CYCLE.read_text("utf-8")).get("closed")
    except (OSError, ValueError):
        closed = None
    pub_at = next((epoch(r["published_at"]) for r in rels if r["tag_name"] == target and not r["draft"]), None)
    if published and target != closed and (dirty > 0 or (pub_at and now - pub_at > 900)):
        reset(target)
        closed = target
    next_mode = target == closed                         # this version is already out and its page was put away: this is the page of the next one
    if next_mode:
        published = False
    gh_state = "done" if published else (state_of(cur) if cur else "todo")
    cur_began = epoch(cur["created_at"]) if cur else None
    if published or gh_state == "fail":
        gh_left = 0.0
    elif cur:
        gh_left = max(0.0, typical - (now - cur_began))
    else:
        gh_left = typical

    jobs, hero_run = [], ""
    for j in gh["jobs"]:
        plain, desc = JOBS.get(j["name"], (j["name"], ""))
        steps = []
        hj = Cache.hist.get("jobs", {}).get(j["name"])
        hs = {x["name"]: x for x in (hj or {}).get("steps", [])}
        for s in j.get("steps", []):
            text, small = plain_step(s["name"])
            st = state_of(s)
            est, sbegan = dur(hs.get(s["name"])), epoch(s.get("started_at"))
            steps.append({"text": text, "small": small, "state": st, "plumbing": s["name"].startswith(PLUMBING), "est": est,
                          "took": dur(s) if st in ("done", "fail") else None, "end": (sbegan + est) if st == "run" and sbegan and est else None})
        done_n = sum(1 for s in steps if s["state"] == "done")
        running = next((s for s in steps if s["state"] == "run" and not s["plumbing"]), None) or next((s for s in steps if s["state"] == "run"), None)
        if running and not hero_run and not running["plumbing"]:
            hero_run = f"{plain}: {running['text']}"
        jest, jbegan = dur(hj), epoch(j.get("started_at"))
        jobs.append({"name": plain, "desc": desc, "state": state_of(j), "done": done_n, "total": len(steps), "began": jbegan,
                     "est": jest, "took": dur(j) if state_of(j) in ("done", "fail") else None, "end": (jbegan + jest) if state_of(j) == "run" and jbegan and jest else None,
                     "now": running["text"] if running else "", "failed": next((x["text"] for x in steps if x["state"] == "fail"), "")})

    stale = False
    if prog and prog.get("finished"):
        changed = [ln[3:].strip().strip('"') for ln in git("status", "--porcelain").splitlines() if len(ln) > 3]
        newest = 0.0
        for rel in changed:
            try:
                newest = max(newest, (ROOT / rel).stat().st_mtime)
            except OSError:
                pass
        stale = (not pushed) and newest > prog["finished"] + 1       # once this version is on GitHub, edits for the next one do not make its tests old
    local_eff = "todo" if (stale and local_state == "done") else local_state
    if jobs and local_eff == "fail":          # the release is already building on GitHub, which runs the same tests and publishes nothing if they fail: the old local failure is not a failure of this release
        local_eff = "done"
    stages = [
        {"name": "בדיקה מקומית שהכול עובד", "plain": "מריצים את הבדיקות המקומיות כדי לוודא שכלום לא נשבר.", "state": local_eff,
         "note": local_now or ("רץ לפני השינויים האחרונים - להריץ שוב" if (stale and local_state == "done") else "")},
        {"name": "שמירת השינויים (commit)", "plain": "שומרים את העבודה בהיסטוריית הפרויקט (commit).", "state": "done" if (dirty == 0 or pushed) else "todo",
         "note": "" if (dirty == 0 or pushed) else f"{dirty} קבצים עוד לא נשמרו"},
        {"name": "העלאה ל-GitHub (push)", "plain": "שולחים את הקוד ל-GitHub, כדי שאפשר יהיה לבנות ממנו שחרור (push).", "state": "done" if pushed else "todo", "note": ""},
        {"name": "הפעלת תהליך השחרור", "plain": "מפעילים את תהליך השחרור ב-GitHub. מכאן GitHub עובד לבד.", "state": "done" if cur else "todo", "note": ""},
        {"name": "בדיקות ובנייה ב-GitHub", "plain": "GitHub מריץ שוב את הבדיקות ובונה את כל קבצי השחרור.",
         "state": gh_state if (cur or published) else "todo", "note": hero_run},
        {"name": f"גרסה {target} פורסמה", "plain": "היא מופיעה בדף השחרורים.", "state": "done" if published else ("fail" if gh_state == "fail" else "todo"), "note": ""},
    ]
    if local_state == "run":
        stages[0]["end"] = now + local_left
    elif local_state == "todo" and local_left:
        stages[0]["est"] = local_left
    if gh_state == "run":
        stages[4]["end"] = now + gh_left
    elif gh_state == "todo":
        stages[4]["est"] = typical
    try:
        todo = [{"text": str(x.get("text", ""))[:160], "state": x.get("state") if x.get("state") in ("todo", "run", "done") else "todo"}
                for x in json.loads(TODO.read_text("utf-8")) if x.get("text")]
    except (OSError, ValueError, AttributeError):
        todo = []
    todo_done = sum(1 for x in todo if x["state"] == "done")
    todo_open = bool(todo) and todo_done < len(todo)
    try:
        activity = [{"at": float(x["at"]), "text": str(x["text"])[:200]} for x in json.loads(ACTIVITY.read_text("utf-8"))][-12:][::-1]
    except (OSError, ValueError, KeyError, TypeError):
        activity = []
    n_done = sum(1 for s in stages if s["state"] == "done")
    local_total = sum(t["estimate"] for t in local)
    local_frac = 1.0 if local_eff == "done" else (max(0.0, 1 - local_left / local_total) if local_total else 0.0)
    got = tot = 0.0
    for j in jobs:
        e = j["est"] or 0.0
        tot += e
        got += e if j["state"] == "done" else (min(now - j["began"], e) if j["state"] == "run" and j["began"] else 0.0)
    gh_frac = 1.0 if (published or gh_state == "done") else (got / tot if tot else (sum(1 for j in jobs if j["state"] == "done") / len(jobs) if jobs else 0.0))
    pct = 100 if published else min(99.99, 100 * (0.25 * local_frac + 0.03 * (stages[1]["state"] == "done") + 0.03 * (stages[2]["state"] == "done")
                                                  + 0.04 * (stages[3]["state"] == "done") + 0.65 * gh_frac))
    local_need = local_total if (stale and local_state == "done") else local_left      # old results: all of them have to run again
    left = (local_need if local_eff != "done" else 0.0) + gh_left
    failing = [s["name"] for s in stages if s["state"] == "fail"]
    bad_jobs = [j for j in jobs if j["state"] == "fail"]          # one failed job on GitHub already means this release will not go out: the timer stops at once
    if bad_jobs and not published and not failing:
        failing = ["GitHub"]
    # the last release is out, the page was put away and nothing is being worked on (no tests running, no release run, the task card is empty or done):
    # there is no release on its way, so no countdown (the stale local tests and the new commit would otherwise make it promise a release in ~7 minutes)
    idle = next_mode and local_state != "run" and not cur and not todo_open and not failing
    # still being written: the task card has open tasks and neither the tests nor a release have started -- no countdown (it used to promise "7 minutes" all day)
    dev = not idle and not published and not failing and local_state != "run" and not cur and todo_open
    if dev:
        hero = "עדיין בפיתוח - אין הערכת זמן עד שהבדיקות או השחרור מתחילים"
        sub = next((x["text"] for x in todo if x["state"] == "run"), "")
    elif idle:
        hero, sub = f"אין שחרור בתהליך - הגרסה האחרונה ({target}) כבר פורסמה", "כשמתחילה עבודה חדשה הדף מתחיל לספור שוב."
    elif published:
        hero, sub = f"גרסה {target} פורסמה! ✓", "היא נמצאת בדף השחרורים."
    elif failing:
        bad = [t["name"] for t in local if t["state"] == "fail"]
        hero = ("בדיקה מקומית נכשלה: " + ", ".join(bad)) if bad else (("נכשל ב-GitHub: " + ", ".join(str(j.get("name", "")) for j in bad_jobs[:3])) if bad_jobs else "משהו נכשל")
        sub = activity[0]["text"] if activity else "הפריט האדום למטה מראה איפה."
    elif local_state == "run":
        hero, sub = "עכשיו: בודקים מקומית שהכול עובד", local_now
    elif local_eff == "todo" and stale:
        hero, sub = "צריך להריץ שוב את הבדיקות המקומיות", "הקוד השתנה אחרי ההרצה האחרונה שלהן."
    elif not pushed:
        hero, sub = "עכשיו: מעלים את השינויים ל-GitHub", "אחר כך GitHub יתחיל לבנות."
    elif not cur:
        hero, sub = "השחרור עוד לא התחיל", "הטיימר יתחיל ברגע שהשחרור יופעל ב-GitHub."
    else:
        hero, sub = "עכשיו: GitHub בונה את השחרור", hero_run

    running_eta = not (idle or dev or published or failing or (pushed and not cur and local_state != "run"))
    pct_rate = max(0.0, (99.5 - pct) / max(left, 5.0)) if running_eta else 0.0      # percent per second: it reaches ~99.5% when the release is expected to end
    return {
        "pct_rate": pct_rate, "at": now, "target": target, "next": next_mode, "hero": hero, "sub": sub, "published": published, "failed": bool(failing),
        "waiting": bool(dev or (not idle and not published and not failing and pushed and not cur and local_state != "run")), "idle": idle, "dev": dev,
        "todo": todo, "activity": activity,
        "eta_end": None if (idle or dev or published or failing or (pushed and not cur and local_state != "run")) else now + left, "local_left": local_left, "gh_left": gh_left, "typical": typical,
        "percent": pct, "stages": stages, "local": local, "single": single, "local_stale": stale, "jobs": jobs, "gh_began": cur_began,
        "error": gh["error"], "recent": [r["tag_name"] for r in rels[:3]],
    }


TEMPLATE = r"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>לוח השחרור</title><style>
:root{--bg:#eef1f5;--card:#fff;--tx:#18202a;--mut:#5f6b79;--ok:#1a7f37;--run:#0b6bdb;--bad:#cf222e;--warn:#9a6700;--todo:#8d98a5;--ln:#dde2e8;--sh:0 1px 2px rgba(20,30,50,.06),0 4px 14px rgba(20,30,50,.05)}
@media (prefers-color-scheme:dark){:root{--bg:#0e1217;--card:#171d25;--tx:#e8edf2;--mut:#98a4b1;--ok:#3fb950;--run:#58a6ff;--bad:#f85149;--warn:#d29922;--todo:#66727f;--ln:#27303a;--sh:0 1px 2px rgba(0,0,0,.4)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif}
main{max-width:1180px;margin:0 auto;padding:16px 16px 48px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.ttl{font-size:24px;font-weight:800;letter-spacing:-.3px}.mut{color:var(--mut);font-size:13px}
.live{display:flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--ln);border-radius:99px;padding:5px 13px;font-size:13px;color:var(--mut);box-shadow:var(--sh)}
.dot{width:10px;height:10px;border-radius:50%;background:var(--ok);animation:pulse 1.2s infinite}
.live.stale .dot{background:var(--warn);animation:none}.live.dead .dot{background:var(--bad);animation:none}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(63,185,80,.6)}70%{box-shadow:0 0 0 9px rgba(63,185,80,0)}100%{box-shadow:0 0 0 0 rgba(63,185,80,0)}}
.warn{background:rgba(210,153,34,.14);border:1px solid var(--warn);border-radius:12px;padding:10px 14px;margin:8px 0}.warn.dead{background:rgba(248,81,73,.12);border-color:var(--bad)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:12px 0}
@media (max-width:900px){.kpis{grid-template-columns:repeat(2,1fr)}}@media (max-width:520px){.kpis{grid-template-columns:1fr}}
.tile{background:var(--card);border:1px solid var(--ln);border-radius:16px;padding:14px 16px;box-shadow:var(--sh);min-height:150px;position:relative;overflow:hidden}
.lbl{font-size:12px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px}
.ring-tile{display:grid;place-items:center}.ring{width:130px;height:130px}
.ring .bg{fill:none;stroke:var(--ln);stroke-width:11}.ring .fg{fill:none;stroke:var(--ok);stroke-width:11;stroke-linecap:round;stroke-dasharray:326.7;stroke-dashoffset:326.7}
.ready .ring .fg{transition:stroke-dashoffset .9s}
.ringtxt{position:absolute;inset:0;display:grid;place-content:center;text-align:center}.ringtxt b{font-size:30px;line-height:1}.ringtxt span{font-size:12px;color:var(--mut)}
.eta-tile .big{font-size:46px;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums;margin:4px 0}
.eta-tile.done .big{color:var(--ok)}.eta-tile.fail .big{color:var(--bad)}
.now-tile{border-inline-start:5px solid var(--run)}.now-tile.done{border-inline-start-color:var(--ok)}.now-tile.fail{border-inline-start-color:var(--bad)}
.nowtxt{font-size:19px;font-weight:700;line-height:1.35}
.counts .row{display:flex;justify-content:space-between;padding:5px 0;border-top:1px solid var(--ln)}.counts .row:first-of-type{border-top:0}.counts b{font-variant-numeric:tabular-nums}
.pipe{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 4px}
.stg{flex:1 1 150px;background:var(--card);border:1px solid var(--ln);border-radius:12px;padding:9px 12px;display:flex;gap:9px;align-items:flex-start;box-shadow:var(--sh);border-top:4px solid var(--todo)}
.stg .n{flex:none;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:13px;font-weight:800;color:#fff;background:var(--todo)}
.stg.done{border-top-color:var(--ok)}.stg.done .n{background:var(--ok)}.stg.run{border-top-color:var(--run)}.stg.run .n{background:var(--run);animation:blink 1.4s infinite}.stg.fail{border-top-color:var(--bad)}.stg.fail .n{background:var(--bad)}
@keyframes blink{50%{opacity:.5}}.stg .t{font-weight:700;font-size:14px;line-height:1.3}.stg.todo .t{color:var(--mut)}.stg .s{font-size:12px;color:var(--run)}
.todo-card{margin:10px 0 4px;background:var(--card);border:1px solid var(--ln);border-radius:14px;padding:12px 16px;box-shadow:var(--sh);border-inline-start:5px solid var(--run)}
.todo-card.done{border-inline-start-color:var(--ok)}.todo-card h3{margin:0 0 6px;font-size:15px;display:flex;justify-content:space-between;gap:10px}
.todo-card ul{list-style:none;margin:6px 0 0;padding:0}.todo-card li{display:flex;gap:9px;padding:3px 0;font-size:14px;align-items:baseline}
.todo-card li .ic{width:1.2em;text-align:center;font-weight:800;flex:none}.todo-card li.done .ic{color:var(--ok)}.todo-card li.done{color:var(--mut);text-decoration:line-through}
.todo-card li.run .ic{color:var(--run);animation:blink 1.4s infinite}.todo-card li.run{font-weight:700}.todo-card li.todo{color:var(--mut)}
.todo-card .bar{margin:4px 0 6px}
.log-card{margin:10px 0 4px;background:var(--card);border:1px solid var(--ln);border-radius:14px;padding:12px 16px;box-shadow:var(--sh);border-inline-start:5px solid var(--ok)}
.log-card.stale{border-inline-start-color:var(--warn)}
.log-card .now{font-size:17px;font-weight:700;line-height:1.35;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.log-card .ago{font-size:13px;font-weight:400;color:var(--mut);white-space:nowrap}
.log-card .stalemsg{color:var(--warn);font-size:13px;margin-top:3px}
.log-card ul{list-style:none;margin:8px 0 0;padding:6px 0 0;border-top:1px solid var(--ln)}
.log-card li{display:flex;gap:10px;font-size:13px;color:var(--mut);padding:1px 0}.log-card li .ago{margin-inline-start:auto}
.explain{font-size:14px;color:var(--mut);margin:4px 2px 0;min-height:21px}
h2{font-size:15px;margin:20px 2px 8px;color:var(--mut);text-transform:uppercase;letter-spacing:.4px;display:flex;align-items:center;gap:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}.grid.small{grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
.job{background:var(--card);border:1px solid var(--ln);border-radius:14px;padding:12px 14px;box-shadow:var(--sh);border-top:4px solid var(--todo)}
.job.done{border-top-color:var(--ok)}.job.run{border-top-color:var(--run)}.job.fail{border-top-color:var(--bad)}
.chip{display:inline-block;font-size:11px;border-radius:99px;padding:1px 9px;color:#fff;background:var(--todo);font-weight:700}.chip.done{background:var(--ok)}.chip.run{background:var(--run)}.chip.fail{background:var(--bad)}
.job .nm{font-weight:700;margin:5px 0 1px;line-height:1.3}.job .ds{font-size:12px;color:var(--mut);min-height:34px}
.job .cur{font-size:13px;color:var(--run);font-weight:600;min-height:20px}
.bar{height:8px;background:var(--ln);border-radius:5px;overflow:hidden;margin:7px 0 3px}.bar i{display:block;height:100%;background:var(--run);width:0}.ready .bar i{transition:width .7s}.job.done .bar i{background:var(--ok)}.job.fail .bar i{background:var(--bad)}
.job.run .bar i{background-image:linear-gradient(135deg,rgba(255,255,255,.28) 25%,transparent 25% 50%,rgba(255,255,255,.28) 50% 75%,transparent 75%);background-size:20px 20px;animation:mv 1s linear infinite}
@keyframes mv{to{background-position:20px 0}}
.job .meta{display:flex;justify-content:space-between;font-size:12px;color:var(--mut)}
small{color:var(--mut);font-weight:400}
.lt{background:var(--card);border:1px solid var(--ln);border-radius:12px;padding:9px 12px;box-shadow:var(--sh);border-inline-start:5px solid var(--todo)}
.lt.done{border-inline-start-color:var(--ok)}.lt.run{border-inline-start-color:var(--run);animation:blink 1.6s infinite}.lt.fail{border-inline-start-color:var(--bad)}
.lt pre.live{color:var(--mut);font-size:10.5px;line-height:1.35;margin:4px 0 0;max-height:none;white-space:pre-wrap;word-break:break-word}
.lt.run{grid-column:span 2}
.lt .nm{font-weight:700;font-size:13px;word-break:break-word}.lt .sm{font-size:12px;color:var(--mut)}.lt pre{white-space:pre-wrap;color:var(--bad);font-size:11px;margin:3px 0 0}
.empty{grid-column:1/-1;color:var(--mut);padding:10px 2px}
footer{margin-top:22px;color:var(--mut);font-size:13px;line-height:1.7}footer .err{color:var(--bad)}
/* everything on one screen */
main{padding:8px 12px 10px}.top{margin-bottom:4px}.ttl{font-size:19px}
.kpis{gap:8px;margin:6px 0}.tile{min-height:0;padding:8px 12px}
.ring{width:72px;height:72px}.ringtxt b{font-size:18px}.ringtxt span{font-size:10px}
.eta-tile .big{font-size:30px;margin:0}.nowtxt{font-size:15px}.lbl{margin-bottom:3px}
.counts .row{padding:2px 0;font-size:13px}
.pipe{margin:4px 0 0}.stg{padding:5px 9px;flex:1 1 130px}.stg .t{font-size:12.5px}.stg .n{width:20px;height:20px;font-size:11px}
.explain{display:none}
.duo{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:8px;margin:6px 0}
.log-card,.todo-card{margin:0;padding:8px 12px}.log-card .now{font-size:15px}.todo-card li,.log-card li{font-size:12.5px;padding:1px 0}
h2{font-size:12px;margin:8px 2px 3px}
.grid{grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}
.job{padding:7px 10px}.job .ds{display:none}.job .nm{margin:3px 0 0;font-size:13.5px}.job .cur{min-height:0;font-size:12px}.job .bar{margin:4px 0 2px}
.grid.small{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:5px}
.lt{padding:3px 8px;display:flex;gap:6px;align-items:baseline;flex-wrap:wrap}.lt .nm{font-size:12px}.lt .sm{font-size:11px}
.lt.run{grid-column:span 2}.lt pre.live{flex-basis:100%;max-height:3.9em;overflow:hidden}
.job pre.live{color:var(--mut);font-size:10.5px;line-height:1.35;margin:4px 0 0;max-height:2.8em;overflow:hidden;white-space:pre-wrap;word-break:break-word}
footer{margin-top:6px;font-size:11px;line-height:1.4}
.ringtxt b{font-size:15px;font-variant-numeric:tabular-nums}.ready .ring .fg{transition:stroke-dashoffset .3s linear}
/* wide screens: the whole width is used, three columns (numbers + steps | log + tasks | GitHub + local tests) */
@media (min-width:1100px){
main{max-width:none;width:100%;display:grid;gap:10px 16px;align-items:start;padding:10px 18px 12px;
  grid-template-columns:minmax(300px,.85fr) minmax(340px,1fr) minmax(380px,1.35fr);
  grid-template-areas:"top top top" "stale stale stale" "kpis duo gh" "pipe duo gh" "foot foot foot"}
.top{grid-area:top;margin:0}#stale{grid-area:stale}.kpis{grid-area:kpis;grid-template-columns:1fr 1fr;margin:0}
.pipe{grid-area:pipe;flex-direction:column;margin:0}.pipe .stg{flex:none}
.duo{grid-area:duo;grid-template-columns:1fr;margin:0;gap:10px}#ghcol{grid-area:gh;min-width:0}footer{grid-area:foot;margin:0}
.log-card .now{font-size:16px}.todo-card li,.log-card li{font-size:13.5px;padding:2px 0}
.tile{padding:12px 14px}.ring{width:84px;height:84px}.eta-tile .big{font-size:34px}.nowtxt{font-size:16px}
.stg{padding:8px 12px}.stg .t{font-size:13.5px}
h2{font-size:13px;margin:0 2px 6px}#ghcol .grid+#localsec h2,#localsec h2{margin-top:14px}
.job{padding:9px 12px}.job .nm{font-size:14px}.job .cur{font-size:12.5px}
}
</style></head><body><main>
<header class="top"><div><div class="ttl" id="title">שחרור</div><div class="mut">לוח חי לשחרור חדש</div></div>
<div class="live" id="live"><span class="dot"></span><span id="livetxt">טוען…</span></div></header>
<div id="stale"></div>
<section class="kpis">
 <div class="tile ring-tile"><svg viewBox="0 0 120 120" class="ring"><circle class="bg" cx="60" cy="60" r="52"/><circle class="fg" id="ringfg" cx="60" cy="60" r="52" transform="rotate(-90 60 60)"/></svg><div class="ringtxt"><b id="ringpct">0%</b><span>הושלם</span></div></div>
 <div class="tile eta-tile" id="etatile"><div class="lbl">עד שהשחרור יצא</div><div class="big" id="etabig">—</div><div class="mut" id="etasub"></div></div>
 <div class="tile now-tile" id="nowtile"><div class="lbl">קורה עכשיו</div><div class="nowtxt" id="hero"></div><div class="mut" id="sub"></div></div>
 <div class="tile counts"><div class="lbl">במספרים</div><div id="counts"></div></div>
</section>
<section class="pipe" id="pipe"></section>
<div class="explain" id="explain"></div>
<div class="duo"><section class="log-card" id="logcard" style="display:none"><div class="lbl">יומן חי - מה קורה עכשיו</div><div class="now"><span id="lognow"></span><span class="ago" id="logago"></span></div><div class="stalemsg" id="logstale"></div><ul id="loglist"></ul></section>
<section class="todo-card" id="todocard" style="display:none"><h3><span>משימות</span><span class="mut" id="todocount"></span></h3><div class="bar"><i id="todobar" style="width:0"></i></div><ul id="todolist"></ul></section></div>
<div id="ghcol"><h2>GitHub <span class="mut" style="text-transform:none;font-weight:400">- מה נבנה ונבדק עכשיו</span></h2>
<div class="grid" id="jobs"></div>
<div id="localsec" style="display:none"><h2>בדיקות מקומיות <span class="mut" style="text-transform:none;font-weight:400">- מה נבדק עכשיו</span> <span id="stale-local" class="mut" style="text-transform:none;color:var(--warn)"></span></h2><div class="grid" id="local"></div></div>
<div id="singlesec" style="display:none"><h2>בדיקה בודדת <span class="mut" style="text-transform:none;font-weight:400">- בדיקה אחת שרצה לבד</span></h2><div class="grid" id="single"></div></div>
<div class="mut" id="localok" style="display:none;margin:6px 2px"></div></div>
<footer id="foot"></footer>
</main><script src="status-data.js"></script><script>
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const IC = {done:'✓', run:'●', todo:'○', fail:'✕'}, CHIP = {done:'הושלם', run:'רץ', todo:'ממתין', fail:'נכשל'};
const mmss = s => { s = Math.max(0, Math.round(s)); return Math.floor(s/60) + ':' + String(s%60).padStart(2,'0'); };
const RING = 2 * Math.PI * 52;
let D = null;
// Only what really changed is touched: a part whose HTML is the same as last time is left alone, so nothing flickers, restarts an
// animation or loses the scroll position.
const setHtml = (el, html) => { if(el._h !== html){ el._h = html; el.innerHTML = html; } };
const setText = (el, t) => { if(el.textContent !== t) el.textContent = t; };
// the time of a card / step: how long it took, how much is left (ticking), or how long it usually takes
const timeOf = x => x.state === 'done' || x.state === 'fail' ? (x.took ? `<span>לקח ${mmss(x.took)}</span>` : '')
  : x.state === 'run' ? (x.end ? `<span data-end="${x.end}"></span>` : (x.began ? `<span data-began="${x.began}"></span>` : ''))
  : (x.est ? `<span>~${mmss(x.est)}</span>` : '');
function render(){
  if(!D) return;
  if(D.idle){ D.published = true; D.percent = 100; }       // nothing is being released: show it as finished, with no countdown
  const st = D.published ? 'done' : D.failed ? 'fail' : 'run';
  document.title = (D.published ? '✓ ' : D.failed ? '✕ ' : D.percent.toFixed(2) + '% · ') + D.target.replace('v','');
  setText($('title'), D.next ? 'השחרור הבא (הקודם, ' + D.target.replace('v','') + ', כבר יצא)' : 'שחרור ' + D.target.replace('v',''));
  $('ringfg').style.stroke = D.failed ? 'var(--bad)' : 'var(--ok)';
  $('nowtile').className = 'tile now-tile ' + (D.published ? 'done' : D.failed ? 'fail' : '');
  $('etatile').className = 'tile eta-tile ' + (D.published ? 'done' : D.failed ? 'fail' : '');
  setText($('hero'), D.hero); setText($('sub'), D.sub || '');
  const jd = D.jobs.filter(j => j.state === 'done').length, ld = D.local.filter(t => t.state === 'done').length, sd = D.stages.filter(s => s.state === 'done').length;
  const lg = D.activity || [];
  $('logcard').style.display = lg.length ? '' : 'none';
  if(lg.length){
    setText($('lognow'), lg[0].text);
    $('logago').dataset.at = lg[0].at;
    setHtml($('loglist'), lg.slice(1, 8).map(x => `<li><span>${esc(x.text)}</span><span class="ago" data-at="${x.at}"></span></li>`).join(''));
  }
  const td = D.todo || [], tdDone = td.filter(x => x.state === 'done').length;
  $('todocard').style.display = td.length ? '' : 'none';
  $('todocard').className = 'todo-card' + (td.length && tdDone === td.length ? ' done' : '');
  if(td.length){
    setText($('todocount'), tdDone + ' מתוך ' + td.length);
    $('todobar').style.width = Math.round(100 * tdDone / td.length) + '%';
    setHtml($('todolist'), (tdDone ? `<li class="done"><span class="ic">✓</span><span>${tdDone} משימות הושלמו</span></li>` : '')
      + td.filter(x => x.state !== 'done').map(x => `<li class="${x.state}"><span class="ic">${IC[x.state]}</span><span>${esc(x.text)}</span></li>`).join(''));
  }
  setText($('stale-local'), D.local_stale ? '- רץ לפני השינויים האחרונים, להריץ שוב' : '');
  setHtml($('counts'), `<div class="row"><span>שלבים</span><b>${sd}/${D.stages.length}</b></div><div class="row"><span>בדיקות מקומיות</span><b>${D.local.length ? ld + '/' + D.local.length : '—'}</b></div><div class="row"><span>עבודות GitHub</span><b>${D.jobs.length ? jd + '/' + D.jobs.length : '—'}</b></div><div class="row"><span>גרסה אחרונה שפורסמה</span><b dir="ltr">${esc((D.recent||[])[0] || '—')}</b></div>`);
  setHtml($('pipe'), D.stages.map((s,i) => `<div class="stg ${s.state}" title="${esc(s.plain)}"><div class="n">${s.state==='done'?'✓':s.state==='fail'?'✕':i+1}</div><div><div class="t">${esc(s.name)}</div>${s.note?`<div class="s">${esc(s.note)}</div>`:''}${s.end?`<div class="s" data-end="${s.end}"></div>`:s.est?`<div class="mut">בערך ${mmss(s.est)}</div>`:''}</div></div>`).join(''));
  const act = D.stages.find(s => s.state === 'run') || D.stages.find(s => s.state === 'fail') || D.stages.find(s => s.state === 'todo');
  setText($('explain'), act ? 'מה קורה בשלב הזה: ' + act.plain : '');
  const lt = D.local || [], ltBad = lt.some(t => t.state === 'fail'), ltRun = lt.some(t => t.state === 'run'), ltDone = lt.filter(t => t.state === 'done').length;
  const showLocal = lt.length && (ltRun || (ltBad && !(D.jobs || []).length));               // only while running, or failed and no release started yet (once GitHub is building, the old local failures are history)
  $('localsec').style.display = showLocal ? '' : 'none';
  $('localok').style.display = lt.length && !showLocal ? '' : 'none';
  setText($('localok'), lt.length && !showLocal ? (ltDone === lt.length ? `✓ כל ${lt.length} הבדיקות המקומיות עברו` : `בדיקות מקומיות: ${ltDone} מתוך ${lt.length} עברו`) + (D.local_stale ? ' - רץ לפני השינויים האחרונים, להריץ שוב' : '') : '');
  const sg = D.single;
  $('singlesec').style.display = sg ? '' : 'none';
  if(sg){
    const run = sg.state === 'run' || sg.state === 'todo', lv = sg.live || {pass:0, fail:0, last:[]};
    const cur = run ? `${lv.pass} בדיקות עברו${lv.fail ? ` · <b style="color:var(--bad)">${lv.fail} נכשלו</b>` : ''}` : sg.state === 'done' ? esc(sg.summary) + ' ✓' : 'נכשל' + (sg.summary ? ' · ' + esc(sg.summary) : '');
    const extra = run && lv.last.length ? `<pre class="live" dir="ltr">${esc(lv.last.slice(-3).join('\n'))}</pre>` : sg.state === 'fail' && sg.detail ? `<pre class="live" dir="ltr" style="color:var(--bad)">${esc(sg.detail)}</pre>` : '';
    setHtml($('single'), `<div class="job ${sg.state}"><span class="chip ${sg.state}">${CHIP[sg.state]}</span><div class="nm" dir="ltr" style="text-align:start">${esc(sg.name)}</div><div class="cur">${cur}</div>
      <div class="bar"><i ${sg.state === 'run' ? `data-pb="${sg.began}" data-pe="${sg.estimate}"` : ''} style="width:${sg.state === 'done' ? 100 : 0}%"></i></div><div class="meta"><span>${sg.state === 'run' ? 'רץ' : ''}</span>${sg.state === 'run' ? `<span data-end="${sg.began + sg.estimate}"></span>` : sg.seconds ? `<span>לקח ${Math.round(sg.seconds)} שניות</span>` : ''}</div>${extra}</div>`);
  }
  if(showLocal){
    setHtml($('local'), lt.map(t => {
      const run = t.state === 'run', lv = t.live || {pass:0, fail:0, last:[]};
      const pct = t.state === 'done' ? 100 : run ? 0 : 0;
      const cur = run ? `${lv.pass} בדיקות עברו${lv.fail ? ` · <b style="color:var(--bad)">${lv.fail} נכשלו</b>` : ''}` : t.state === 'done' ? esc(t.summary) + ' ✓' : t.state === 'fail' ? 'נכשל' : 'ממתין';
      const time = run ? `<span data-end="${t.began + t.estimate}"></span>` : t.state === 'done' && t.seconds ? `<span>לקח ${Math.round(t.seconds)} שניות</span>` : t.state === 'todo' ? `<span>~${Math.round(t.estimate)} שניות</span>` : '';
      const extra = run && lv.last.length ? `<pre class="live" dir="ltr">${esc(lv.last.slice(-2).join('\n'))}</pre>` : t.state === 'fail' && t.detail ? `<pre class="live" dir="ltr" style="color:var(--bad)">${esc(t.detail)}</pre>` : '';
      return `<div class="job ${t.state}"><span class="chip ${t.state}">${CHIP[t.state]}</span><div class="nm" dir="ltr" style="text-align:start">${esc(t.name)}</div><div class="cur">${cur}</div>
        <div class="bar"><i ${run ? `data-pb="${t.began}" data-pe="${t.estimate}"` : ''} style="width:${pct}%"></i></div><div class="meta"><span>${run ? 'רץ' : ''}</span>${time}</div>${extra}</div>`; }).join(''));
  }
  const box = $('jobs');
  if(!D.jobs.length){ setHtml(box, '<div class="empty">עוד לא התחיל. אחרי ההעלאה וההפעלה של השחרור יופיעו כאן עבודות GitHub: בדיקות, בנייה ופרסום.</div>'); }
  else {
    if(box._h !== 'jobs'){ box.innerHTML = ''; box._h = 'jobs'; }
    D.jobs.forEach((j, i) => {
      let el = box.children[i];
      if(!el){ el = document.createElement('div'); box.appendChild(el); }
      const cls = 'job ' + j.state; if(el.className !== cls) el.className = cls;
      const pct = j.total ? Math.round(100 * j.done / j.total) : 0;
      setHtml(el, `<div><span class="chip ${j.state}">${CHIP[j.state]}</span><div class="nm">${esc(j.name)}</div><div class="ds">${esc(j.desc)}</div>
        <div class="cur">${j.state==='run' && j.now ? 'עכשיו: ' + esc(j.now) : j.state==='done' ? 'הושלם ✓' : j.state==='fail' ? 'נכשל ב: ' + esc(j.failed || '') : ''}</div>
        <div class="bar"><i style="width:${pct}%"></i></div><div class="meta"><span>${j.done} מתוך ${j.total} שלבים</span>${timeOf(j)}</div>${j.state==='run' && j.began && j.end ? `<div class="meta"><span>רץ כבר</span><span data-began="${j.began}"></span></div>` : ''}
</div>`);
    });
    while(box.children.length > D.jobs.length) box.lastChild.remove();
  }
  setHtml($('foot'), 'שחרור עובר כך: בדיקה מקומית ← commit ← push ← בדיקות ובנייה ב-GitHub ← השחרור מפורסם. אין מה לעשות כאן - הדף מתעדכן לבד.<br>גרסאות אחרונות שפורסמו: <span dir="ltr">' + esc((D.recent||[]).join(' · ')) + '</span>' + (D.error ? `<div class="err">${esc(D.error)}</div>` : ''));
}
// the percentage rises smoothly at the pace the data says (percent per second), never goes back, and eases toward the real value
const PCT = {shown: 0, init: false};
function animPct(){
  if(!D) return;
  const now = Date.now() / 1000;
  const target = D.published ? 100 : Math.min(99.99, D.percent + (D.pct_rate || 0) * (now - D.at));
  if(!PCT.init || target < PCT.shown - 3){ PCT.shown = target; PCT.init = true; }
  else if(target > PCT.shown) PCT.shown += (target - PCT.shown) * 0.2;
  const v = D.published ? 100 : PCT.shown;
  setText($('ringpct'), v.toFixed(2) + '%');
  if(!D.published && !D.failed) document.title = v.toFixed(2) + '% · ' + D.target.replace('v','');      // the tab shows the same hundredths of a percent as the ring
  const off = (RING * (1 - v / 100)).toFixed(2);
  if($('ringfg').style.strokeDashoffset !== off) $('ringfg').style.strokeDashoffset = off;
}
const agoText = s => s < 5 ? 'עכשיו' : s < 60 ? 'לפני ' + Math.round(s) + ' שניות' : s < 3600 ? 'לפני ' + Math.round(s / 60) + ' דקות' : 'לפני ' + Math.round(s / 3600) + ' שעות';
function tick(){
  const now = Date.now() / 1000;
  if(!D) return;
  document.querySelectorAll('[data-at]').forEach(e => setText(e, agoText(now - e.dataset.at)));
  const act = D.activity || [];
  if(act.length){
    const old = now - act[0].at, quiet = old > 300 && !D.published;
    $('logcard').classList.toggle('stale', quiet);
    setText($('logstale'), quiet ? 'אין רשומה חדשה ביומן כבר ' + Math.round(old / 60) + ' דקות - העבודה אולי תקועה.' : '');
  }
  const age = now - D.at, live = $('live');
  const cls = 'live' + (age > 60 ? ' dead' : age > 15 ? ' stale' : '');
  if(live.className !== cls) live.className = cls;
  setText($('livetxt'), age < 8 ? 'חי · מתעדכן' : 'עודכן ' + agoText(age));
  setHtml($('stale'), age > 60 ? '<div class="warn dead"><b>הנתונים לא התעדכנו כבר ' + mmss(age) + '.</b> כנראה התוכנה שמעדכנת את הדף נעצרה, ולכן מה שרואים ישן. להפעיל אותה שוב: <code>python tools/release_status/status_page.py</code></div>'
    : age > 15 ? '<div class="warn"><b>אין עדכון כבר ' + Math.round(age) + ' שניות.</b> הדף חי וממתין לעדכון הבא; אם זה נמשך, יכול להיות שהמעדכן תקוע.</div>' : '');
  if(D.eta_end){
    const left = D.eta_end - now;
    setText($('etabig'), left > 0 ? mmss(left) : 'רגע…');
    setText($('etasub'), `בדיקות מקומיות ~${mmss(D.local_left)} · בנייה ב-GitHub ~${mmss(D.gh_left)} · לפי שחרורים קודמים (~${mmss(D.typical)})`);
  } else if(D.waiting){ setText($('etabig'), '—'); setText($('etasub'), D.dev ? 'הטיימר מתחיל כשהבדיקות מתחילות לרוץ' : 'הטיימר מתחיל כשהשחרור מופעל ב-GitHub'); }
  else { setText($('etabig'), D.published ? '✓' : '✕'); setText($('etasub'), D.published ? 'השחרור יצא' : 'משהו נכשל - ראה את הכרטיס האדום'); }
  document.querySelectorAll('[data-began][data-est]').forEach(e => setText(e, 'רץ ' + Math.round(now - e.dataset.began) + ' שניות מתוך ~' + Math.round(e.dataset.est)));
  document.querySelectorAll('[data-began]:not([data-est])').forEach(e => setText(e, 'רץ ' + mmss(now - e.dataset.began)));
  document.querySelectorAll('[data-pb]').forEach(e => { const w = Math.min(99, 100 * (now - e.dataset.pb) / Math.max(1, e.dataset.pe)); e.style.width = w.toFixed(1) + '%'; });
  document.querySelectorAll('[data-end]').forEach(e => { const l = e.dataset.end - now; setText(e, l > 0 ? '~' + mmss(l) + ' נותרו' : 'רגע…'); });
}
function fit(){
  const b = document.body; b.style.zoom = 1;
  const h = document.documentElement.scrollHeight, v = window.innerHeight;
  if(h > v + 2) b.style.zoom = Math.max(0.55, (v - 2) / h);
}
window.addEventListener('resize', fit);
function load(){
  const s = document.createElement('script'); s.src = 'status-data.js?t=' + Date.now();
  s.onload = () => { if(window.STATUS && (!D || window.STATUS.at !== D.at)){ D = window.STATUS; render(); fit(); } s.remove(); };
  s.onerror = () => s.remove(); document.head.appendChild(s);
}
D = window.STATUS || null; render(); tick(); fit(); animPct();
requestAnimationFrame(() => requestAnimationFrame(() => document.body.classList.add('ready')));
setInterval(load, 2000); setInterval(tick, 1000); setInterval(animPct, 250);
</script></body></html>"""


def reset(target):
    """Put the page of a finished release away (archive/<version>-<time>/) and start clean: no log, no tasks, no test results.
    Called by the page itself when the release is out and new work begins, or by hand: python tools/release_status/reset.py"""
    ARCHIVE.mkdir(exist_ok=True)
    keep = ARCHIVE / (target + time.strftime("-%Y%m%d-%H%M%S"))
    for f in (TODO, ACTIVITY, PROGRESS):
        try:
            if f.exists():
                keep.mkdir(exist_ok=True)
                (keep / f.name).write_bytes(f.read_bytes())
        except OSError:
            pass
    TODO.write_text("[]", "utf-8")
    ACTIVITY.write_text("[]", "utf-8")
    PROGRESS.unlink(missing_ok=True)
    CYCLE.write_text(json.dumps({"closed": target}), "utf-8")


def stable(x, key=None):
    """Round every number: an epoch to a whole second, anything else to a tenth. A float that differs in its 12th digit between two
    updates made the page see a 'change', rebuild its cards and flicker."""
    if isinstance(x, float):
        if key == "percent":
            return round(x, 3)
        if key == "pct_rate":
            return round(x, 6)
        return round(x) if abs(x) > 1e8 else round(x, 1)
    if isinstance(x, dict):
        return {k: stable(v, k) for k, v in x.items()}
    if isinstance(x, list):
        return [stable(v) for v in x]
    return x


def write(data):
    data = stable(data)
    tmp = DATA.with_suffix(".tmp")
    tmp.write_text("window.STATUS = " + json.dumps(data, ensure_ascii=False) + ";\n", "utf-8")
    for _ in range(5):
        try:
            os.replace(tmp, DATA)
            return
        except PermissionError:               # the browser is reading it this very moment
            time.sleep(0.2)


def main():
    me, born = Path(__file__).resolve(), Path(__file__).resolve().stat().st_mtime
    PAGE.write_text(TEMPLATE, "utf-8")
    if "--once" in sys.argv:
        write(collect())
        print(PAGE)
        return
    if not os.environ.pop("RELEASE_STATUS_RELOAD", "") and DATA.exists() and time.time() - DATA.stat().st_mtime < 8:
        print("another copy of the dashboard updater is already running: nothing to do", flush=True)      # one writer only
        return
    end = time.time() + 24 * 3600
    while time.time() < end:
        try:
            write(collect())                                # it keeps running after the release is out: the page resets itself for the next one
        except Exception as e:
            print("error:", e, flush=True)
        if me.stat().st_mtime != born:                      # this program was edited: run the new version
            print("changed on disk: restarting", flush=True)
            os.environ["RELEASE_STATUS_RELOAD"] = "1"                 # the new copy is this one, not "another one"
            os.execv(sys.executable, [sys.executable, str(me)])
        time.sleep(LOCAL_EVERY)


if __name__ == "__main__":
    main()
