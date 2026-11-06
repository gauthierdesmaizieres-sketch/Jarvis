"""« Mes projets » : every project listed in projects.json, with last activity and git state.

Read-only: walks folders and runs read-only git commands, never writes anything.
"""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "projects.json"
SKIP = {"node_modules", ".git"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def latest_mtime(root):
    """Newest file modification time under root (seconds), skipping node_modules and .git."""
    newest = None
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            try:
                t = os.stat(os.path.join(dirpath, f)).st_mtime
            except OSError:
                continue  # vanished or locked file
            newest = t if newest is None or t > newest else newest
    return newest


def git_info(path):
    """Branch, last commit and uncommitted file count, or None if path isn't a git repo."""
    def run(*args):
        r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, encoding="utf-8",
                           errors="replace", timeout=30, creationflags=NO_WINDOW)
        return r.stdout.rstrip("\n") if r.returncode == 0 else None
    if not (Path(path) / ".git").exists():
        return None
    log = run("log", "-1", "--format=%cI%x00%s")  # None on a repo with no commit yet
    date, _, msg = log.partition("\0") if log else (None, "", None)
    status = run("status", "--porcelain")
    return {"branch": run("rev-parse", "--abbrev-ref", "HEAD"), "commitDate": date, "commitMsg": msg,
            "dirty": len(status.splitlines()) if status else 0}


def project(domain, name, path):
    p = Path(path)
    if not p.is_dir():
        return {"domain": domain, "name": name, "path": str(p), "exists": False}
    t = latest_mtime(p)
    return {"domain": domain, "name": name, "path": str(p), "exists": True, "git": git_info(p),
            "modified": datetime.fromtimestamp(t, timezone.utc).isoformat() if t else None}


def board(config=CONFIG, home=Path.home()):
    """All projects of the config, most recently active first (missing folders last)."""
    cfg = json.loads(Path(config).read_text(encoding="utf-8"))
    items = [(d, e["name"], home / e["path"]) for d, entries in cfg.items() if not d.startswith("_") for e in entries]
    with ThreadPoolExecutor(8) as pool:
        out = list(pool.map(lambda a: project(*a), items))
    return sorted(out, key=lambda r: r.get("modified") or "", reverse=True)


if __name__ == "__main__":
    print(json.dumps(board(), ensure_ascii=False, indent=1))
