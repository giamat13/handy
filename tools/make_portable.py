"""Build the portable ZIP: dist/Handy2/* + LICENSE + THIRD_PARTY_NOTICES.md + a "portable.txt" marker, zipped as
Handy2-<version>-portable.zip. No installer, nothing is written to this PC: the result runs from a USB stick or any folder and
keeps its settings in a "data" folder right beside Handy2.exe (see settings.py).

    build.bat                       (builds dist/Handy2 first)
    python tools/make_portable.py
"""
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import __version__  # noqa: E402

MARKER = """This file tells Handy 2 to run in portable mode: it keeps its settings in the "data" folder right here, next to
Handy2.exe, instead of your user profile. You can move or copy this whole folder (for example to a USB stick) and it keeps
working; just make sure Handy 2 is closed first. Delete this file to use the normal per-user location instead.
"""


def main() -> Path:
    dist = ROOT / "dist" / "Handy2"
    if not (dist / "Handy2.exe").is_file():
        raise SystemExit(f"{dist}\\Handy2.exe is missing: run the normal build first (build.bat, or pyinstaller Handy2.spec)")

    out_dir = ROOT / "dist"
    stage = out_dir / "Handy2-portable-stage"
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(dist, stage)
    shutil.copy2(ROOT / "LICENSE", stage / "LICENSE")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", stage / "THIRD_PARTY_NOTICES.md")
    (stage / "portable.txt").write_text(MARKER, "utf-8")
    (stage / "data").mkdir(exist_ok=True)

    out = out_dir / f"Handy2-{__version__}-portable.zip"
    out.unlink(missing_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, Path("Handy2") / p.relative_to(stage))
    shutil.rmtree(stage, ignore_errors=True)
    print(f"{out}  {out.stat().st_size / 1048576:.1f} MB  sha256 {hashlib.sha256(out.read_bytes()).hexdigest()}")
    return out


if __name__ == "__main__":
    main()
