"""Cut a release: bump the version, date the CHANGELOG, commit, and tag.

    .venv/bin/python tools/release.py 0.2.0
    git push && git push origin v0.2.0      # the Release workflow builds and publishes it

Move your notes under "## [Unreleased]" in CHANGELOG.md first; they become the release notes.
"""
import datetime
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "src" / "train_tracker" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
CO_AUTHOR = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"   # the project is built with Claude Code


def run(*cmd):
    subprocess.run(cmd, cwd=ROOT, check=True)


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        sys.exit("usage: release.py X.Y.Z")
    version = sys.argv[1]
    if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip():
        sys.exit("working tree not clean: commit or stash first")

    log = CHANGELOG.read_text()
    m = re.search(r"## \[Unreleased\]\n(.*?)(?=\n## \[)", log, re.S)
    if not m or not m.group(1).strip():
        sys.exit("nothing under ## [Unreleased] in CHANGELOG.md")
    today = datetime.date.today().isoformat()
    CHANGELOG.write_text(log.replace("## [Unreleased]\n", f"## [Unreleased]\n\n## [{version}] - {today}\n", 1))
    INIT.write_text(re.sub(r'__version__ = ".*"', f'__version__ = "{version}"', INIT.read_text()))

    run(sys.executable, "-m", "pytest", "-q")
    run("git", "add", str(INIT), str(CHANGELOG))
    run("git", "commit", "-m", f"Release v{version}\n\n{CO_AUTHOR}")
    run("git", "tag", "-a", f"v{version}", "-m", f"v{version}")
    print(f"\nTagged v{version}. Publish with:\n  git push && git push origin v{version}")


if __name__ == "__main__":
    main()
