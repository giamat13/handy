"""Update from GitHub releases (https://github.com/giamat13/handy/releases). Adapted from photag's updater.

check()     : asks the GitHub API for the latest release and compares its tag with the running version
download()  : fetches the installer asset and VERIFIES it (size and SHA-256 from GitHub's asset digest, or from a
              "<asset>.sha256" file next to it) before it is ever run
launch()    : starts the Inno Setup installer silently with /update=1 (which restarts the app afterwards); from source or in
              the portable build it only tells the caller to open the release page
reconcile() : at every start-up, settles an update that was started earlier (see "Interrupted updates")

Interrupted updates (power loss, the installer being killed, the PC shutting down mid-way):
  * the update is installed OVER the existing app (no uninstall first); settings live outside the program folder
  * before the installer starts, the program folder is copied to %LOCALAPPDATA%\\Handy2\\update\\rollback and verified; a
    journal (pending.json) says what was about to happen
  * the installer writes done.flag when it has finished copying the new version
  * if the flag is missing the update did not finish: the next start of the app -- or, if the program itself is broken, a
    RunOnce script that Windows runs at the next sign-in -- puts the saved program folder back

Safety: the installer is only ever downloaded from this repository's release URLs, and an asset with no checksum is never
installed automatically (the user is sent to the release page instead).
"""
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from version import FULL_VERSION, REPO, __version__

ASSET_RE = re.compile(r"^Handy2Setup.*\.exe$", re.I)
CHECK_EVERY = 24 * 3600          # seconds between automatic checks while the app stays open
STALE_AFTER = 10 * 60            # a started update with no done.flag after this long is treated as failed
RUNONCE_KEY = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
RUNONCE_NAME = "Handy2-update-recovery"
BLOCKED_WINERRORS = (4551, 1260, 4556)   # "an Application Control policy has blocked this file" and its relatives


class UpdateError(Exception):
    pass


class BlockedError(UpdateError):
    """The downloaded installer exists but Windows refused to run it (the app keeps running, nothing was changed)."""


# tests point these at a mock, so they are read at call time
def _api() -> str:
    return os.environ.get("HANDY_UPDATE_API", "https://api.github.com").rstrip("/")


def _allowed() -> str:
    return os.environ.get("HANDY_UPDATE_ALLOW_PREFIX") or f"https://github.com/{REPO}/releases/download/"


def parse_version(s: str) -> tuple:
    """"v2.10.2" -> (2, 10, 2, 1); a missing part is 0; a pre-release suffix ("-beta.2") sorts before the release itself and
    PRE 2 above PRE 1."""
    m = re.match(r"\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(.*)$", s or "")
    if not m:
        return (0, 0, 0, 0, 0)
    nums = tuple(int(x or 0) for x in m.groups()[:3])
    suffix = m.group(4).strip()
    if suffix.startswith("-"):
        n = re.search(r"(\d+)", suffix)
        return nums + (0, int(n.group(1)) if n else 0)
    return nums + (1, 0)


def is_newer(latest: str, current: str = FULL_VERSION) -> bool:
    return parse_version(latest) > parse_version(current)


def running_is_prerelease() -> bool:
    return parse_version(FULL_VERSION)[3] == 0


def is_portable() -> bool:
    return getattr(sys, "frozen", False) and (Path(sys.executable).resolve().parent / "portable.txt").exists()


def _ssl() -> ssl.SSLContext:
    return ssl.create_default_context()


def _get(url: str, timeout: float = 10) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"Handy2/{__version__}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
        return r.read()


def _pick_asset(assets: list) -> dict | None:
    cands = [a for a in assets if ASSET_RE.match(a.get("name", ""))]
    if not cands:
        return None
    a = next((x for x in cands if x["name"].lower() == "handy2setup.exe"), cands[0])
    digest = (a.get("digest") or "").removeprefix("sha256:") or None
    sidecar = next((x for x in assets if x.get("name") == a["name"] + ".sha256"), None)
    return {"name": a["name"], "url": a.get("browser_download_url", ""), "size": a.get("size"),
            "sha256": digest if digest and re.fullmatch(r"[0-9a-f]{64}", digest) else None,
            "sha256_url": sidecar.get("browser_download_url") if sidecar else None}


def _is_pre(rel: dict) -> bool:
    return bool(rel.get("prerelease")) or parse_version(rel.get("tag_name") or "")[3] == 0


def check(cfg: dict) -> dict:
    """Latest release info + whether it is newer. Never raises: a failed check is just {"available": False, "error": ...}.
    Pre-releases are offered only in tester mode (cfg["beta_channel"]) or while running a pre-release."""
    out = {"current": FULL_VERSION, "available": False, "latest": None, "notes": "", "page": f"https://github.com/{REPO}/releases",
           "asset": None, "skipped": False, "error": None, "prerelease": False}
    beta = bool(cfg.get("beta_channel")) or running_is_prerelease()
    try:
        if beta:
            # GitHub's "latest" endpoint skips pre-releases, so tester mode takes the newest release of any kind
            rels = json.loads(_get(f"{_api()}/repos/{REPO}/releases?per_page=5"))
            rel = rels[0] if rels else {}
        else:
            rel = json.loads(_get(f"{_api()}/repos/{REPO}/releases/latest"))
    except urllib.error.HTTPError as e:
        out["error"] = f"HTTP {e.code}" + (" (no releases yet)" if e.code == 404 else "")
        return out
    except Exception as e:
        out["error"] = str(getattr(e, "reason", e))[:200]
        return out
    tag = rel.get("tag_name") or ""
    out.update(latest=tag.lstrip("vV"), notes=rel.get("body") or "", page=rel.get("html_url") or out["page"],
               asset=_pick_asset(rel.get("assets") or []))
    out["prerelease"] = bool(tag) and _is_pre(rel)
    out["available"] = bool(tag) and is_newer(tag, FULL_VERSION)
    out["skipped"] = out["available"] and cfg.get("update_skipped") == out["latest"]
    if out["available"]:
        out["notes"] = _notes_since(FULL_VERSION) or out["notes"]
    return out


def _notes_since(current: str) -> str:
    """Release notes of every version newer than `current`, newest first, so updating across several versions at once
    shows everything that changed."""
    try:
        rels = json.loads(_get(f"{_api()}/repos/{REPO}/releases?per_page=20"))
    except Exception:
        return ""
    newer = [r for r in rels if is_newer(r.get("tag_name") or "", current)]
    if len(newer) <= 1:
        return (newer[0].get("body") or "") if newer else ""
    return "\n\n".join(f"## {r.get('tag_name', '')}\n\n{r.get('body') or ''}" for r in newer)


def _expected_sha(asset: dict) -> str | None:
    if asset.get("sha256"):
        return asset["sha256"]
    if asset.get("sha256_url") and asset["sha256_url"].startswith(_allowed()):
        m = re.search(r"\b([0-9a-fA-F]{64})\b", _get(asset["sha256_url"]).decode("utf-8", "replace"))
        return m.group(1).lower() if m else None
    return None


def can_install(info: dict) -> bool:
    a = info.get("asset")
    return bool(a and a["url"].startswith(_allowed()) and (a["sha256"] or a["sha256_url"]))


def state_dir() -> Path:
    """Where the update journal, the rollback copy and the installer's done.flag live (survives restarts)."""
    env = os.environ.get("HANDY_UPDATE_STATE_DIR")
    d = Path(env) if env else Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Handy2" / "update"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "Handy2-update"
    d.mkdir(parents=True, exist_ok=True)
    return d


def hard_exit():
    """End this process now (TerminateProcess does not wait for DLL exit code that can hang)."""
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.TerminateProcess(k.GetCurrentProcess(), 0)
        except Exception:
            pass
    os._exit(0)


def download(info: dict, on_progress=None) -> dict:
    """Download + verify the installer of `info` (from check()). Returns {"path", "version", "sha256", "bytes"}; raises UpdateError."""
    if not info.get("available"):
        raise UpdateError("No update available")
    a = info.get("asset")
    if not can_install(info):
        raise UpdateError("The installer can't be verified automatically. Download it from the release page")
    want = _expected_sha(a)
    if not want:
        raise UpdateError("The installer can't be verified automatically. Download it from the release page")
    dest = download_dir() / f"Handy2Setup-{info['latest']}.exe"
    part = dest.with_suffix(".part")
    for old in download_dir().glob("Handy2Setup-*"):          # leftovers of earlier updates
        if old != part:
            old.unlink(missing_ok=True)
    h = hashlib.sha256()
    done, total = 0, a.get("size") or 0
    try:
        req = urllib.request.Request(a["url"], headers={"User-Agent": f"Handy2/{__version__}"})
        with urllib.request.urlopen(req, timeout=30, context=_ssl()) as r, open(part, "wb") as f:
            total = total or int(r.headers.get("Content-Length") or 0)
            while chunk := r.read(1 << 20):
                f.write(chunk); h.update(chunk); done += len(chunk)
                if on_progress:
                    on_progress(done, total)
    except Exception as e:
        part.unlink(missing_ok=True)
        raise UpdateError(f"Download failed: {str(e)[:200]}")
    size = part.stat().st_size
    if a.get("size") and size != a["size"]:
        part.unlink(missing_ok=True)
        raise UpdateError(f"The downloaded file is incomplete ({size} of {a['size']} bytes)")
    if h.hexdigest() != want:
        part.unlink(missing_ok=True)
        raise UpdateError("The downloaded file does not match its signature (SHA-256). It was deleted and not installed")
    os.replace(part, dest)
    return {"path": str(dest), "version": info["latest"], "sha256": want, "bytes": size}


# ------------------------------------------------------------------ safe install: journal, rollback copy, recovery
RECOVER_PS1 = r"""param([string]$StateDir, [int]$WaitPid = 0, [switch]$NoLaunch)
# Handy 2: put the previous program folder back if an update did not finish (see updater.py)
$ErrorActionPreference = 'Stop'
$log = Join-Path $StateDir 'recovery.log'
function Log($m) { Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format s), $m) }
$pj = Join-Path $StateDir 'pending.json'
if (-not (Test-Path $pj)) { exit 0 }
try { $j = Get-Content $pj -Raw -Encoding UTF8 | ConvertFrom-Json } catch { Log "unreadable journal: $_"; exit 1 }
if ($WaitPid -gt 0) { try { Wait-Process -Id $WaitPid -Timeout 60 } catch { } }
$deadline = (Get-Date).AddMinutes(5)       # an installer that is still running gets time to finish
while ((Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'Handy2Setup*' }) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
if (Test-Path (Join-Path $StateDir 'done.flag')) { Log 'update finished, nothing to restore'; exit 0 }
if (-not (Test-Path $j.backup_dir)) { Log 'no rollback copy found'; exit 1 }
Log ('restoring the previous version ' + $j.from_version)
# mirror the saved folder over the program folder: restores changed and deleted files, removes files a half-done update added;
# the uninstaller files (unins*) are left alone
& robocopy $j.backup_dir $j.app_dir /MIR /XF 'unins*.exe' 'unins*.dat' 'unins*.msg' /R:3 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Log ("robocopy failed, exit code " + $LASTEXITCODE); exit 1 }
Log 'restored'
Remove-Item $pj -Force
if (-not $NoLaunch) { Start-Process $j.exe }
"""


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _tree_fingerprint(root: Path) -> str:
    """Cheap fingerprint of a folder (names, sizes, times): tells whether a half-done update changed anything."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.lower().startswith("unins"):
            st = p.stat()
            h.update(f"{p.relative_to(root).as_posix()}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def _exe_path() -> Path:
    env = os.environ.get("HANDY_UPDATE_FAKE_EXE")          # tests: a stand-in for the installed program
    return Path(env) if env else Path(sys.executable)


def _write_json(path: Path, obj: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, path)                                    # all or nothing, even if the power goes now


def _runonce(set_it: bool, script: Path | None = None, state: Path | None = None):
    if sys.platform != "win32" or os.environ.get("HANDY_UPDATE_DRY_RUN"):
        return
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUNONCE_KEY) as k:
        if set_it:
            cmd = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{script}" -StateDir "{state}"'
            winreg.SetValueEx(k, RUNONCE_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, RUNONCE_NAME)
            except FileNotFoundError:
                pass


def prepare_rollback(installer: Path, to_version: str) -> dict:
    """Everything that makes an interrupted update harmless. Raises (and starts nothing) if it cannot be done."""
    d = state_dir()
    exe = _exe_path()
    if not exe.is_file():
        raise UpdateError("program file not found")
    app_dir = exe.parent
    rb = d / "rollback"
    shutil.rmtree(rb, ignore_errors=True)
    backup_dir = rb / "app"
    shutil.copytree(app_dir, backup_dir, ignore=shutil.ignore_patterns("unins*"))        # the whole program folder
    fingerprint = _tree_fingerprint(app_dir)
    if _sha(backup_dir / exe.name) != _sha(exe):
        raise UpdateError("rollback copy does not match the program")
    (d / "done.flag").unlink(missing_ok=True)
    (d / "just_failed.json").unlink(missing_ok=True)
    script = d / "recover.ps1"
    script.write_text(RECOVER_PS1, "utf-8-sig")             # BOM: Windows PowerShell 5 reads it as UTF-8
    journal = {"from_version": FULL_VERSION, "to_version": to_version, "installer": str(installer), "exe": str(exe),
               "app_dir": str(app_dir), "backup_dir": str(backup_dir), "fingerprint": fingerprint,
               "started": time.time(), "pid": os.getpid()}
    _write_json(d / "pending.json", journal)
    _runonce(True, script, d)
    return journal


def _clear_pending(d: Path, keep_flag: bool = False):
    (d / "pending.json").unlink(missing_ok=True)
    shutil.rmtree(d / "rollback", ignore_errors=True)
    if not keep_flag:
        (d / "done.flag").unlink(missing_ok=True)
    _runonce(False)


def reconcile() -> dict:
    """Run at every start. Settles an update that was started earlier:
    updated        - the installer finished and this is the new version (the UI says so)
    in_progress    - started a moment ago, the installer may still be running: leave everything alone
    failed_intact  - it never finished, but the program folder is exactly as before: nothing to restore
    restoring      - it never finished and the program folder changed: a recovery script puts the saved folder back
                     (this process ends a moment later and the script restarts the app)"""
    d = state_dir()
    pj = d / "pending.json"
    if not pj.exists():
        return {"state": "none"}
    try:
        j = json.loads(pj.read_text("utf-8"))
    except Exception:
        pj.unlink(missing_ok=True)
        return {"state": "none"}
    if (d / "done.flag").exists():
        if parse_version(FULL_VERSION) >= parse_version(j.get("to_version", "")):
            _write_json(d / "just_updated.json", {"from": j.get("from_version"), "to": j.get("to_version")})
            _clear_pending(d)
            return {"state": "updated", "from": j.get("from_version"), "to": j.get("to_version")}
        return {"state": "in_progress"}
    if time.time() - j.get("started", 0) < STALE_AFTER:
        return {"state": "in_progress"}
    app_dir = Path(j.get("app_dir", ""))
    if app_dir.is_dir() and _tree_fingerprint(app_dir) == j.get("fingerprint"):
        _write_json(d / "just_failed.json", {"to": j.get("to_version"), "restored": False})
        _clear_pending(d)
        return {"state": "failed_intact"}
    script = d / "recover.ps1"
    if not script.exists():
        script.write_text(RECOVER_PS1, "utf-8-sig")
    if os.environ.get("HANDY_UPDATE_DRY_RUN"):
        return {"state": "restoring", "dry_run": True}
    _write_json(d / "just_failed.json", {"to": j.get("to_version"), "restored": True})
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script),
                      "-StateDir", str(d), "-WaitPid", str(os.getpid())],
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0), close_fds=True)
    threading.Timer(1.5, hard_exit).start()                # the script waits for this process, puts the old folder back, restarts the app
    return {"state": "restoring"}


def pending_notice() -> dict:
    """What the UI should tell the user after a restart: {"updated": {...}|None, "failed": {...}|None}."""
    d = state_dir()
    read = lambda n: (json.loads((d / n).read_text("utf-8")) if (d / n).exists() else None)
    try:
        return {"updated": read("just_updated.json"), "failed": read("just_failed.json")}
    except Exception:
        return {"updated": None, "failed": None}


def ack_notice():
    d = state_dir()
    for n in ("just_updated.json", "just_failed.json"):
        (d / n).unlink(missing_ok=True)


def launch(path: str) -> dict:
    """Run the downloaded installer and quit so it can replace the files -- after making an interrupted install harmless.
    Returns {"mode": "installing"} (the caller closes the app; this process also ends by itself a second later),
    {"mode": "page"} (running from source or portable: the caller opens the release page) or {"mode": "dry-run", ...}."""
    p = Path(path)
    if not p.is_file() or p.parent != download_dir():
        raise UpdateError("not a downloaded update")
    dry = bool(os.environ.get("HANDY_UPDATE_DRY_RUN"))
    if dry and not os.environ.get("HANDY_UPDATE_FAKE_EXE"):
        return {"mode": "dry-run", "path": str(p)}
    if not dry and (sys.platform != "win32" or not getattr(sys, "frozen", False) or is_portable()):
        return {"mode": "page"}                      # source, portable, macOS or Linux build: no installer to run, open the release page
    m = re.search(r"Handy2Setup-(.+)\.exe$", p.name, re.I)
    journal = prepare_rollback(p, m.group(1) if m else "")
    if dry:
        return {"mode": "dry-run", "path": str(p), "journal": journal}
    d = state_dir()
    args = [str(p), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/update=1", f"/LOG={d / 'installer.log'}"]
    # detached and outside this process's job object: closing the app must not stop the installer
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        try:
            subprocess.Popen(args, creationflags=flags | 0x01000000, close_fds=True)         # CREATE_BREAKAWAY_FROM_JOB
        except OSError:
            subprocess.Popen(args, creationflags=flags, close_fds=True)
    except Exception as e:
        _clear_pending(d)                            # nothing started: nothing to roll back
        if getattr(e, "winerror", None) in BLOCKED_WINERRORS:
            raise BlockedError(str(e))               # Windows (Smart App Control / AppLocker) refused to run the unsigned installer
        raise UpdateError(str(e))
    threading.Timer(3.0, hard_exit).start()
    return {"mode": "installing"}
