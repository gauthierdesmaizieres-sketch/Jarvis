"""Rebuild the public Jarvis page and push it to GitHub Pages if it changed.

Meant to run from a Claude Code hook after each turn: costs no tokens, and does
nothing (no commit, no push) unless a project, link, skill, MCP or commit changed.
"""

import subprocess
import sys
from pathlib import Path

from snapshot import PUBLIC_OUT, build

ROOT = Path(__file__).parent


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def main():
    if not build(public=True):
        return
    rel = PUBLIC_OUT.relative_to(ROOT).as_posix()
    git("add", rel)
    # Commit only the page, never whatever else is in progress in the repo.
    r = git("commit", "-q", "-m", "Jarvis en ligne : mise à jour automatique", "--", rel)
    if r.returncode != 0:
        sys.exit(f"commit échoué : {r.stderr.strip()}")
    r = git("push", "-q", "origin", "HEAD")
    if r.returncode != 0:
        sys.exit(f"push échoué : {r.stderr.strip()}")
    print("Jarvis en ligne mis à jour")


if __name__ == "__main__":
    main()
