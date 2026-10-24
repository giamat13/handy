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
    # nothing is published unless the tests and the Windows build pass; the other targets are optional
    assert "needs.tests.result == 'success'" in wf and "needs.build.result == 'success'" in wf
    assert "needs: [tests, build, build-macos, build-linux, build-nuitka]" in wf
    assert "version.py" in wf and "REPO" in read("version.py")


def test_every_target_has_a_job_and_a_file_name_the_publish_job_expects():
    wf = read(".github/workflows/release.yml")
    for job in ("build:", "build-macos:", "build-linux:", "build-nuitka:", "publish:"):
        assert f"\n  {job}" in wf, job
    for name in ("Handy2-NSIS-Setup-", "-macos.zip", "-linux-x64.tar.gz", "-windows-nuitka.zip", "-macos-nuitka.zip",
                 "-linux-nuitka.tar.gz"):
        assert name in wf, name
    assert "Handy2-NSIS-Setup-" in read("installer.nsi")
    assert "Handy2.app" in read("Handy2.spec") and "BUNDLE" in read("Handy2.spec")


def test_the_single_file_exe_is_attached_to_every_release():
    wf = read(".github/workflows/release-onefile.yml")
    assert "workflows: [release]" in wf and "types: [completed]" in wf        # runs by itself after a successful release
    assert "workflow_dispatch" in wf and "Handy2-onefile.spec" in wf          # and by hand for a given tag
    assert "Handy2-${VERSION}-onefile.exe" in wf and "gh release upload" in wf
    assert "name: release" in read(".github/workflows/release.yml").splitlines()[0]   # the name the trigger waits for
    import updater
    assert not updater.ASSET_RE.match(f"Handy2-{version.__version__}-onefile.exe")  # the updater never takes it as the installer


def test_archive_names_match_the_workflow():
    import make_platform_archive as mpa
    v = version.__version__
    assert mpa.archive_name("macos") == f"Handy2-{v}-macos.zip"
    assert mpa.archive_name("linux") == f"Handy2-{v}-linux-x64.tar.gz"
    assert mpa.archive_name("nuitka").startswith(f"Handy2-{v}-") and "-nuitka." in mpa.archive_name("nuitka")


def test_the_updater_never_picks_another_installer():
    """Only the Inno Setup installer is downloaded by the in-app updater; the NSIS one must not match its pattern."""
    import updater
    assert updater.ASSET_RE.match("Handy2Setup.exe")
    assert not updater.ASSET_RE.match(f"Handy2-NSIS-Setup-{version.__version__}.exe")
    assert not updater.ASSET_RE.match(f"Handy2-{version.__version__}-macos.zip")


def test_every_build_ships_the_web_ui_and_the_icons():
    spec, one = read("Handy2.spec"), read("Handy2-onefile.spec")
    for text in (spec, one):
        assert '("web", "web")' in text and '("icon.ico", ".")' in text and '("icon.png", ".")' in text
        assert "pystray" in text and "customtkinter" not in text.replace("# ", "")
    assert 'icon="icon.ico"' in spec and 'icon="icon.ico"' in one                  # the EXE's own icon
    assert "--include-data-dir" in read("tools/build_nuitka.py") and "web" in read("tools/build_nuitka.py")
    req = read("requirements.txt")
    assert "pystray" in req and "customtkinter" not in req


def test_the_installers_keep_the_settings_folder_alone():
    iss, nsi = read("installer.iss"), read("installer.nsi")
    assert "%APPDATA%\\Handy " in iss and "APPDATA" not in nsi.split("Section", 1)[1]   # nothing in the sections touches APPDATA


def test_every_file_the_build_needs_exists():
    for rel in ("Handy2.spec", "installer.iss", "installer.nsi", "build.bat", "LICENSE", "THIRD_PARTY_NOTICES.md", "icon.png",
                "requirements.txt", "requirements-dev.txt", "run.py", "app.py", "webui.py", "render.py", "window.py", "tray.py",
                "update_service.py", "updater.py", "web/index.html", "web/style.css", "web/app.js", "icon.ico", "tools/make_icon.py",
                "tools/make_version_info.py", "tools/make_portable.py", "tools/write_prerelease.py",
                "tools/build_nuitka.py", "tools/make_platform_archive.py"):
        assert (ROOT / rel).is_file(), rel
