"""Pack a finished build into the file that is attached to the GitHub release.

    python tools/make_platform_archive.py macos          dist/Handy2.app             -> dist/Handy2-<version>-macos.zip
    python tools/make_platform_archive.py linux          dist/Handy2/                -> dist/Handy2-<version>-linux-x64.tar.gz
    python tools/make_platform_archive.py nuitka         dist_nuitka/Handy2[.app]    -> dist/Handy2-<version>-<windows|macos|linux>-nuitka.(zip|tar.gz)

The macOS .app is zipped with ditto when it exists (keeps permissions and symlinks); otherwise with Python's zipfile.
"""
import hashlib
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import __version__  # noqa: E402


def platform_name():
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def archive_name(kind):
    """The file name for a kind of build. The workflow, the release notes and the tests rely on these names."""
    if kind == "macos":
        return f"Handy2-{__version__}-macos.zip"
    if kind == "linux":
        return f"Handy2-{__version__}-linux-x64.tar.gz"
    ext = "tar.gz" if platform_name() == "linux" else "zip"
    return f"Handy2-{__version__}-{platform_name()}-nuitka.{ext}"


def _zip_dir(src, out, arc_root):
    if shutil.which("ditto") and src.suffix == ".app":
        subprocess.run(["ditto", "-c", "-k", "--keepParent", "--sequesterRsrc", str(src), str(out)], check=True)
        return
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, Path(arc_root) / p.relative_to(src))   # write() keeps the file mode (executable bit)


def _tar_dir(src, out, arc_root):
    with tarfile.open(out, "w:gz", compresslevel=6) as t:
        t.add(src, arcname=arc_root)                              # keeps modes and symlinks


def source_dir(kind):
    if kind == "macos":
        return ROOT / "dist" / "Handy2.app"
    if kind == "linux":
        return ROOT / "dist" / "Handy2"
    app = ROOT / "dist_nuitka" / "Handy2"
    return app if app.is_dir() else next((ROOT / "dist_nuitka").glob("*.app"), app)


def main(kind):
    if kind not in ("macos", "linux", "nuitka"):
        raise SystemExit(__doc__)
    src = source_dir(kind)
    if not src.is_dir():
        raise SystemExit(f"{src} is missing: build it first")
    out = ROOT / "dist" / archive_name(kind)
    out.parent.mkdir(exist_ok=True)
    out.unlink(missing_ok=True)
    root_name = src.name if src.suffix == ".app" else "Handy2"
    (_tar_dir if out.name.endswith(".tar.gz") else _zip_dir)(src, out, root_name)
    print(f"{out}  {out.stat().st_size / 1048576:.1f} MB  sha256 {hashlib.sha256(out.read_bytes()).hexdigest()}")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
