"""Release machinery: the version scheme (2.X.Y), the Windows version resource, and that the workflow, installer and
build files agree with each other. No camera needed."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import make_version_info  # noqa: E402
import version  # noqa: E402

SCHEME = re.compile(r"^2\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def read(rel):
    return (ROOT / rel).read_text("utf-8")


def test_version_follows_the_scheme():
    assert SCHEME.match(version.__version__), version.__version__


def test_full_version_is_plain_without_a_prerelease_file():
    if version.PRE == 0:
        assert version.FULL_VERSION == version.__version__


def test_prerelease_number_is_added():
    pf = ROOT / "_prerelease.py"
    had = pf.read_bytes() if pf.exists() else None
    try:
        pf.write_text("PRE = 3\n", "utf-8")
        out = subprocess.run(
            [sys.executable, "-c", "from version import __version__ as v, FULL_VERSION as f; print(v, f)"],
            cwd=str(ROOT), capture_output=True, text=True,
        ).stdout.split()
        assert out == [version.__version__, f"{version.__version__}-beta.3"]
    finally:
        pf.unlink(missing_ok=True) if had is None else pf.write_bytes(had)


def test_write_prerelease_writes_nothing_for_a_regular_release():
    pf = ROOT / "_prerelease.py"
    had = pf.read_bytes() if pf.exists() else None
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "write_prerelease.py")], cwd=str(ROOT),
                       capture_output=True, text=True, env={**__import__("os").environ, "PRERELEASE": "false"})
    assert r.returncode == 0 and not pf.exists()
    if had is not None:
        pf.write_bytes(had)


def test_windows_version_resource():
    vt = make_version_info.version_tuple
    assert vt("2.1.0") == (2, 1, 0, 0)
    assert vt("2.1.3-beta.2") == (2, 1, 3, 0)
    assert vt("v2.10.1") == (2, 10, 1, 0)
    assert all(0 <= x < 65536 for x in vt("2.1.0"))


def test_garbage_version_stops_the_build():
    try:
        make_version_info.version_tuple("nonsense")
    except SystemExit:
        return
    raise AssertionError("garbage version was accepted")


def test_release_notes_exist_for_the_current_version():
    assert (ROOT / "docs" / f"release-notes-v{version.__version__}.md").is_file()


def test_workflow_matches_the_build_files():
    wf = read(".github/workflows/release.yml")
    iss = read("installer.iss")
    spec = read("Handy2.spec")
    assert "Handy2Setup" in wf and "OutputBaseFilename=Handy2Setup" in iss
    assert "Handy2.spec" in wf and 'name="Handy2"' in spec
    assert "Handy2-*-portable.zip" in wf and "Handy2-{__version__}-portable.zip" in read("tools/make_portable.py")
    assert "needs: [tests, build]" in wf          # nothing is published unless the tests pass
    assert "version.py" in wf and "REPO" in read("version.py")


def test_every_file_the_build_needs_exists():
    for rel in ("Handy2.spec", "installer.iss", "build.bat", "LICENSE", "THIRD_PARTY_NOTICES.md", "icon.png",
                "requirements.txt", "requirements-dev.txt", "run.py", "updater.py", "update_ui.py", "tools/make_icon.py",
                "tools/make_version_info.py", "tools/make_portable.py", "tools/write_prerelease.py"):
        assert (ROOT / rel).is_file(), rel
