"""Hotkey and script bindings: validation, and that nothing ever goes through a shell. No keyboard, nothing is launched."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import commands  # noqa: E402


# --- hotkeys ---------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Ctrl+C", ("ctrl", "c")),
    ("alt+TAB", ("alt", "tab")),
    ("Win+D", ("cmd", "d")),
    ("shift+ctrl+t", ("ctrl", "shift", "t")),          # סדר קבוע: ctrl, alt, shift, win
    ("F5", ("f5",)),
    ("ctrl + alt + delete", ("ctrl", "alt", "delete")),
    ("ctrl+plus", ("ctrl", "+")),
    ("Escape", ("esc",)),
])
def test_valid_hotkeys(text, expected):
    assert commands.parse_hotkey(text) == expected


@pytest.mark.parametrize("text", [
    "", "   ", "ctrl", "ctrl+", "+c", "ctrl+ctrl+c", "a+b", "ctrl+nonsense", "f25", "ctrl+c; calc", "ctrl+c&calc",
    "x" * 100, "ctrl+\n", None, 5,
])
def test_invalid_hotkeys_are_rejected(text):
    with pytest.raises(ValueError):
        commands.parse_hotkey(text)


def test_hotkey_text_is_readable():
    assert commands.hotkey_text(("ctrl", "shift", "t")) == "Ctrl+Shift+T"


class FakeKeyboard:
    def __init__(self, fail_on=None):
        self.log, self.fail_on = [], fail_on

    def press(self, k):
        if k == self.fail_on:
            raise RuntimeError("boom")
        self.log.append(("down", k))

    def release(self, k):
        self.log.append(("up", k))


def test_press_hotkey_holds_the_modifiers_around_the_key():
    pytest.importorskip("pynput.keyboard")
    from pynput.keyboard import Key
    kb = FakeKeyboard()
    commands.press_hotkey(kb, ("ctrl", "shift", "t"))
    assert kb.log == [("down", Key.ctrl), ("down", Key.shift), ("down", "t"), ("up", "t"), ("up", Key.shift), ("up", Key.ctrl)]


def test_press_hotkey_releases_modifiers_even_when_it_fails():
    pytest.importorskip("pynput.keyboard")
    from pynput.keyboard import Key
    kb = FakeKeyboard(fail_on="c")
    with pytest.raises(RuntimeError):
        commands.press_hotkey(kb, ("ctrl", "c"))
    assert ("up", Key.ctrl) in kb.log                      # Ctrl לא נשאר לחוץ


def test_a_key_this_system_does_not_have_is_refused_before_anything_is_pressed(monkeypatch):
    pytest.importorskip("pynput.keyboard")
    import pynput.keyboard
    from types import SimpleNamespace
    # macOS has no Key.insert: the keys it does have must still work, and a missing one is refused before Ctrl goes down
    monkeypatch.setattr(pynput.keyboard, "Key", SimpleNamespace(ctrl="CTRL", alt="ALT", shift="SHIFT", cmd="CMD", tab="TAB"))
    kb = FakeKeyboard()
    commands.press_hotkey(kb, ("ctrl", "tab"))
    assert kb.log == [("down", "CTRL"), ("down", "TAB"), ("up", "TAB"), ("up", "CTRL")]
    with pytest.raises(ValueError):
        commands.press_hotkey(kb, ("ctrl", "insert"))
    assert len(kb.log) == 4


# --- scripts ---------------------------------------------------------------

def make_exe(tmp_path, name="tool.cmd" if os.name == "nt" else "tool.sh"):
    p = tmp_path / name
    p.write_text("echo hi\n")
    p.chmod(0o755)
    return p


def test_split_args_keeps_quoted_spaces_and_does_not_expand():
    assert commands.split_args('-a "b c" d') == ["-a", "b c", "d"]
    assert commands.split_args("$HOME %PATH% `x` ; rm") == ["$HOME", "%PATH%", "`x`", ";", "rm"]  # רק טקסט, לא מפורש
    assert commands.split_args("") == []
    with pytest.raises(ValueError):
        commands.split_args('"open')
    with pytest.raises(ValueError):
        commands.split_args(" ".join("a" * 40))


def test_a_valid_script_is_accepted(tmp_path):
    exe = make_exe(tmp_path)
    assert commands.parse_script(str(exe), '--x "a b"') == {"path": str(exe), "args": '--x "a b"'}
    assert commands.parse_script(f'"{exe}"')["path"] == str(exe)         # מירכאות סביב הנתיב מותרות


@pytest.mark.parametrize("path", ["", "tool.exe", "relative/tool.exe", "C:/does/not/exist.exe", "/does/not/exist"])
def test_a_missing_or_relative_path_is_rejected(path):
    with pytest.raises(ValueError):
        commands.parse_script(path)


def test_a_directory_is_not_a_program(tmp_path):
    with pytest.raises(ValueError):
        commands.parse_script(str(tmp_path))


def test_control_characters_are_rejected(tmp_path):
    exe = make_exe(tmp_path)
    with pytest.raises(ValueError):
        commands.parse_script(str(exe), "a\nb")
    with pytest.raises(ValueError):
        commands.parse_script(str(exe) + "\x00")


def test_batch_files_reject_shell_metacharacters_in_args(tmp_path):
    bat = tmp_path / "x.bat"
    bat.write_text("@echo off\n")
    bat.chmod(0o755)
    for bad in ("a & calc", "a | b", "%PATH%", "a > out", "^x", "(x)"):
        with pytest.raises(ValueError):
            commands.parse_script(str(bat), bad)
    assert commands.parse_script(str(bat), "plain args 123")


def test_run_script_uses_an_argument_list_and_no_shell(tmp_path):
    exe = make_exe(tmp_path)
    seen = {}

    def fake_popen(argv, **kw):
        seen["argv"], seen["kw"] = argv, kw
        return "proc"

    out = commands.run_script({"path": str(exe), "args": 'one "two words" ; calc'}, popen=fake_popen)
    assert out == "proc"
    assert seen["argv"] == [str(exe), "one", "two words", ";", "calc"]      # ";" ו-calc הם סתם ארגומנטים
    assert isinstance(seen["argv"], list) and seen["kw"]["shell"] is False
    assert seen["kw"]["cwd"] == str(tmp_path)


def test_run_script_checks_again_before_running(tmp_path):
    exe = make_exe(tmp_path)
    binding = {"path": str(exe), "args": ""}
    exe.unlink()                                                             # נמחק אחרי שההגדרה נשמרה
    with pytest.raises(ValueError):
        commands.run_script(binding, popen=lambda *a, **k: pytest.fail("must not run"))


def test_powershell_scripts_run_through_powershell_with_a_file_argument(tmp_path):
    ps1 = tmp_path / "x.ps1"
    ps1.write_text("1\n")
    argv = commands.build_argv({"path": str(ps1), "args": "a b"})
    assert argv[0] in ("powershell", "pwsh") and "-File" in argv and argv[-2:] == ["a", "b"]
