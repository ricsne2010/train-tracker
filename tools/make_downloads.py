#!/usr/bin/env python3
"""Build the two downloads attached to each GitHub release:

  dist/US-Train-Tracker-for-Mac.zip       Install Train Tracker.command + the Mac installer pieces
  dist/US-Train-Tracker-for-Windows.zip   Install Train Tracker.bat + the Windows installer pieces

Each holds the app (installed from the folder by the installer), the printable guide and a READ ME FIRST note.
The release workflow runs this; it also runs locally:  python3 tools/make_downloads.py
"""
import re
import stat
import time
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
GUIDE = ROOT / "docs" / "US-Train-Tracker-Install-Guide.pdf"
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "src/train_tracker/__init__.py").read_text()).group(1)

COMMON = ["pyproject.toml", "README.md", "LICENSE", "CHANGELOG.md", ".env.example"]

READ_ME = {
    "Mac": """US Train Tracker {v} for Mac
Designed and Created by Project Moon Pi

1. Install Python 3.10 or newer from https://www.python.org/downloads/ (once).
2. Double-click "Install Train Tracker.command".
   If macOS says it can't verify the developer: System Settings > Privacy & Security > Open Anyway.
3. Answer its two questions. It installs Train Tracker, starts it and opens the map.

Afterwards use Start Train Tracker and Stop Train Tracker on your Desktop (also in Applications > Train Tracker).
You can delete this folder once it's installed. The full guide is "US Train Tracker - Installation Guide.pdf".
""",
    "Windows": """US Train Tracker {v} for Windows
Designed and Created by Project Moon Pi

1. Install Python 3.10 or newer from https://www.python.org/downloads/ (once).
   In its installer, tick "Add python.exe to PATH".
2. Double-click "Install Train Tracker.bat".
   If Windows says it protected your PC: More info > Run anyway.
3. Answer its two questions. It installs Train Tracker, starts it and opens the map.
   If you choose phones, click Yes if Windows asks to allow changes (that opens the firewall for them).

Afterwards use Start Train Tracker and Stop Train Tracker on your Desktop (also in the Start menu).
You can delete this folder once it's installed. The full guide is "US Train Tracker - Installation Guide.pdf".
""",
}


def build(platform):
    top = f"US Train Tracker for {platform}"
    out = DIST / f"US-Train-Tracker-for-{platform}.zip"
    windows = platform == "Windows"
    files = [ROOT / f for f in COMMON]
    files += [p for p in sorted((ROOT / "src").rglob("*"))
              if p.is_file() and "__pycache__" not in p.parts and ".egg-info" not in str(p)]
    if windows:
        files += [ROOT / "Install Train Tracker.bat"] + sorted((ROOT / "installer/windows").glob("*.ps1"))
        files += sorted((ROOT / "installer/icons").glob("*.ico"))
    else:
        files += [ROOT / "Install Train Tracker.command"] + sorted((ROOT / "installer/mac").glob("*.sh"))
        files += sorted((ROOT / "installer/icons").glob("*.icns"))

    def add(z, name, data, executable=False):
        info = zipfile.ZipInfo(f"{top}/{name}", date_time=time.localtime()[:6])
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = ((0o755 if executable else 0o644) | stat.S_IFREG) << 16
        z.writestr(info, data)

    DIST.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w") as z:
        for f in files:
            name = f.relative_to(ROOT).as_posix()
            data = f.read_bytes()
            if f.suffix in (".bat", ".ps1"):              # Windows line endings, whatever the checkout has
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            add(z, name, data, executable=f.suffix in (".command", ".sh"))
        add(z, "US Train Tracker - Installation Guide.pdf", GUIDE.read_bytes())
        note = READ_ME[platform].format(v=VERSION)
        add(z, "READ ME FIRST.txt", note.replace("\n", "\r\n") if windows else note)
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB, {len(files) + 2} files)")
    return out


if __name__ == "__main__":
    for p in (sys.argv[1:] or ["Mac", "Windows"]):
        build(p)
