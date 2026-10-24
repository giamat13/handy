"""Make icon.ico (the Windows icon of Handy2.exe and the installer) and icon.icns (the macOS app bundle) from icon.png.

    python tools/make_icon.py
"""
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

if __name__ == "__main__":
    src = Image.open(ROOT / "icon.png").convert("RGBA")
    side = max(src.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))  # pad to a square so the icon is not stretched
    square.paste(src, ((side - src.width) // 2, (side - src.height) // 2))
    out = ROOT / "icon.ico"
    square.save(out, format="ICO", sizes=SIZES)
    print(f"{out}  {out.stat().st_size / 1024:.0f} KB")
    for name in ("icon.png", "icon.ico"):  # web/ is self-contained (it also opens straight from the folder): it keeps its own copy of the icons
        shutil.copyfile(ROOT / name, ROOT / "web" / name)
    icns = ROOT / "icon.icns"
    square.resize((1024, 1024), Image.LANCZOS).save(icns, format="ICNS")
    print(f"{icns}  {icns.stat().st_size / 1024:.0f} KB")
