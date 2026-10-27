"""mp_path.py: copying the MediaPipe models to an ASCII path (a non-ASCII user name breaks MediaPipe's file loading).
Synthetic folders only: no camera, no mediapipe."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mp_path  # noqa: E402


def make_modules(base):
    m = base / "modules" / "hand_landmark"
    m.mkdir(parents=True)
    (m / "hand_landmark_lite.tflite").write_bytes(b"model")
    return base / "modules"


def test_is_ascii():
    assert mp_path.is_ascii(r"C:\Users\furst\AppData")
    assert not mp_path.is_ascii("C:\\Users\\\u05d9\u05dc\u05d3\u05d9\u05dd\\AppData")


def test_mirror_copies_modules(tmp_path):
    src = make_modules(tmp_path / "src")
    root = tmp_path / "dst"
    assert mp_path.mirror_modules(str(src), [str(root)]) == str(root)
    assert (root / "mediapipe" / "modules" / "hand_landmark" / "hand_landmark_lite.tflite").read_bytes() == b"model"


def test_mirror_is_reused(tmp_path):
    src = make_modules(tmp_path / "src")
    root = tmp_path / "dst"
    mp_path.mirror_modules(str(src), [str(root)])
    (src / "hand_landmark" / "hand_landmark_lite.tflite").write_bytes(b"changed")
    mp_path.mirror_modules(str(src), [str(root)])
    assert (root / "mediapipe" / "modules" / "hand_landmark" / "hand_landmark_lite.tflite").read_bytes() == b"model"


def test_mirror_falls_back_to_next_root(tmp_path):
    src = make_modules(tmp_path / "src")
    blocker = tmp_path / "file"
    blocker.write_text("x")   # a root under a file cannot be created
    good = tmp_path / "good"
    assert mp_path.mirror_modules(str(src), [str(blocker / "sub"), str(good)]) == str(good)


def test_mirror_none_when_all_fail(tmp_path):
    src = make_modules(tmp_path / "src")
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert mp_path.mirror_modules(str(src), [str(blocker / "sub")]) is None
