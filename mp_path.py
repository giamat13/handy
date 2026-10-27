"""MediaPipe טוען את המודלים דרך קוד C++ שלא פותח נתיב עם אותיות שאינן ASCII (למשל שם משתמש בעברית).
כשהתקנת התוכנה בנתיב כזה, מעתיקים את תיקיית modules לנתיב ASCII ומפנים אליו את solution_base."""
import os
import shutil
import sys

from version import __version__


def is_ascii(path):
    return path.isascii()


def ascii_roots():
    """מקומות אפשריים לעותק, לפי סדר העדיפות."""
    roots = []
    for var in ("PROGRAMDATA", "PUBLIC"):
        base = os.environ.get(var)
        if base:
            roots.append(os.path.join(base, "Handy2", f"mediapipe-{__version__}"))
    if sys.platform == "win32":
        roots.append(os.path.join("C:\\", "Handy2", f"mediapipe-{__version__}"))
    return [r for r in roots if is_ascii(r)]


def mirror_modules(src_modules, roots):
    """מעתיק src_modules ל-<root>/mediapipe/modules בשורש ASCII הראשון שמצליח. מחזיר את השורש, או None."""
    for root in roots:
        dst = os.path.join(root, "mediapipe", "modules")
        try:
            if not os.path.isdir(dst):
                tmp = dst + ".tmp"
                shutil.rmtree(tmp, ignore_errors=True)
                shutil.copytree(src_modules, tmp)
                os.replace(tmp, dst)
            return root
        except OSError:
            continue
    return None


def fix():
    """קוראים לפני יצירת פתרונות MediaPipe. לא עושה כלום כשהנתיב כבר ASCII. מחזיר True כשהופנה לעותק."""
    import mediapipe.python.solution_base as sb

    here = os.path.abspath(sb.__file__)
    if is_ascii(here):
        return False
    mp_dir = os.path.dirname(os.path.dirname(here))   # .../mediapipe
    root = mirror_modules(os.path.join(mp_dir, "modules"), ascii_roots())
    if root is None:
        return False
    sb.__file__ = os.path.join(root, "mediapipe", "python", "solution_base.py")   # root_path נגזר מ-__file__ בזמן הקריאה
    return True
