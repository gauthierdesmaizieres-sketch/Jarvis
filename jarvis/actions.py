"""Local actions run from the dashboard (v2). Only server.py calls these, after
checking the request comes from the dashboard page itself.

Every action works on a folder Claude Code already knows (a project in the
inventory), never on an arbitrary path sent by the browser.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .inventory import CLAUDE_DIR, CLAUDE_JSON, _encode_project, _load_json

SETTINGS = CLAUDE_DIR / "settings.json"
SESSION_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


class ActionError(Exception):
    pass


def _project_key(claude_json, path):
    """Key of a project in ~/.claude.json (it uses forward slashes), or None."""
    target = os.path.normcase(os.path.normpath(path))
    return next((k for k in claude_json.get("projects") or {}
                 if os.path.normcase(os.path.normpath(k)) == target), None)


def _known_project(path):
    p = Path(path or "")
    known = (CLAUDE_DIR / "projects" / _encode_project(str(p))).is_dir() \
        or _project_key(_load_json(CLAUDE_JSON) or {}, p) is not None
    if not (p.is_absolute() and p.is_dir() and known):
        raise ActionError("projet inconnu")
    return p


def _exe(name):
    exe = shutil.which(name)
    if not exe:
        raise ActionError(f"« {name} » introuvable dans le PATH")
    return exe


def _write_json(path, data):
    """Atomic write with a backup next to the file, so a bad write never loses the config."""
    shutil.copy2(path, path.with_name(path.name + ".jarvis.bak"))
    tmp = path.with_name(path.name + ".jarvis.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _git(path, *args):
    r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, encoding="utf-8",
                       errors="replace", timeout=60, creationflags=NO_WINDOW)
    return (r.stdout + r.stderr).strip() or "(rien à signaler)"


def open_explorer(req):
    os.startfile(_known_project(req.get("path")))
    return "Dossier ouvert dans l'explorateur."


def open_editor(req):
    path = _known_project(req.get("path"))
    code = Path(_exe("code"))
    # code.cmd goes through cmd.exe, which misreads paths with & or ^: call the real exe.
    gui = code.parent.parent / "Code.exe"
    subprocess.Popen([str(gui if gui.is_file() else code), str(path)], creationflags=NO_WINDOW)
    return "Projet ouvert dans VS Code."


def claude_new(req):
    path = _known_project(req.get("path"))
    subprocess.Popen([_exe("claude")], cwd=path, creationflags=NEW_CONSOLE)
    return "Nouvelle session Claude Code lancée dans un terminal."


def claude_resume(req):
    path = _known_project(req.get("path"))
    sid = req.get("id") or ""
    if not SESSION_RE.match(sid) or not (CLAUDE_DIR / "projects" / _encode_project(str(path)) / f"{sid}.jsonl").is_file():
        raise ActionError("session inconnue pour ce projet")
    subprocess.Popen([_exe("claude"), "--resume", sid], cwd=path, creationflags=NEW_CONSOLE)
    return f"Session {sid[:8]} reprise dans un terminal."


def git_status(req):
    return _git(_known_project(req.get("path")), "status", "-sb")


def git_pull(req):
    return _git(_known_project(req.get("path")), "pull", "--ff-only")


def toggle_plugin(req):
    pid, enable = req.get("id"), bool(req.get("enable"))
    installed = (_load_json(CLAUDE_DIR / "plugins" / "installed_plugins.json") or {}).get("plugins", {})
    if pid not in installed:
        raise ActionError("plugin inconnu")
    settings = _load_json(SETTINGS)
    if settings is None:
        raise ActionError("settings.json illisible, rien n'a été écrit")
    settings.setdefault("enabledPlugins", {})[pid] = enable
    _write_json(SETTINGS, settings)
    return f"Plugin {pid} {'activé' if enable else 'désactivé'}. Effet à la prochaine session Claude Code."


def toggle_mcp(req):
    """Per-project switch, like /mcp in Claude Code: .mcp.json servers go in
    disabledMcpjsonServers, user and local servers in disabledMcpServers."""
    path = _known_project(req.get("path"))
    name, enable = req.get("name") or "", bool(req.get("enable"))
    data = _load_json(CLAUDE_JSON)
    if data is None:
        raise ActionError("~/.claude.json illisible, rien n'a été écrit")
    key = _project_key(data, path) or path.as_posix()
    cfg = data.setdefault("projects", {}).setdefault(key, {})
    mcp_json = (_load_json(path / ".mcp.json") or {}).get("mcpServers") or {}
    if name in mcp_json:
        field = "disabledMcpjsonServers"
    elif name in (data.get("mcpServers") or {}) or name in (cfg.get("mcpServers") or {}):
        field = "disabledMcpServers"
    else:
        raise ActionError("serveur MCP inconnu pour ce projet")
    disabled = [n for n in cfg.get(field, []) if n != name]
    cfg[field] = disabled if enable else disabled + [name]
    _write_json(CLAUDE_JSON, data)
    return f"MCP {name} {'activé' if enable else 'désactivé'} pour {path.name}. Effet à la prochaine session."


ACTIONS = {f.__name__: f for f in (open_explorer, open_editor, claude_new, claude_resume,
                                    git_status, git_pull, toggle_plugin, toggle_mcp)}


def run(req):
    action = ACTIONS.get(req.get("act"))
    if not action:
        raise ActionError("action inconnue")
    return action(req)
