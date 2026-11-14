"""Local actions run from the dashboard (v2). Only server.py calls these, after
checking the request comes from the dashboard page itself.

Every action works on a folder Claude Code already knows (a project in the
inventory), never on an arbitrary path sent by the browser.
"""

import ctypes
import json
import os
import re
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .inventory import CLAUDE_DIR, CLAUDE_JSON, NAMES_FILE, _encode_project, _load_json, collect, project_configs

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


def _git_projects():
    return sorted((Path(p) for p in project_configs() if (Path(p) / ".git").exists()), key=lambda p: p.name.lower())


def git_pull_all(req):
    with ThreadPoolExecutor(8) as pool:
        results = pool.map(lambda p: f"■ {p.name}\n{git_pull({'path': str(p)})}", _git_projects())
    return "\n\n".join(results) or "Aucun projet git."


def _repo_report(path, fetch):
    def run(*args):
        r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, encoding="utf-8",
                           errors="replace", timeout=60, creationflags=NO_WINDOW)
        return r.stdout.rstrip() if r.returncode == 0 else None  # porcelain lines start with a space
    if fetch:
        run("fetch", "--quiet")
    counts = run("rev-list", "--left-right", "--count", "@{u}...HEAD")
    behind, ahead = map(int, counts.split()) if counts else (None, None)
    status = run("status", "--porcelain")
    return {"name": path.name, "path": str(path), "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": status.splitlines() if status else [], "ahead": ahead, "behind": behind,
            "upstream": run("rev-parse", "--abbrev-ref", "@{u}"),
            "branches": (run("for-each-ref", "--format=%(refname:short)", "refs/heads") or "").splitlines()}


def git_overview(fetch=False):
    """Branch, changes, commits ahead/behind upstream and local branches of every git project."""
    with ThreadPoolExecutor(8) as pool:
        return list(pool.map(lambda p: _repo_report(p, fetch), _git_projects()))


def chat_command(req):
    """argv and folder for one chat turn with `claude -p`; the message goes on stdin.

    No permission bypass: anything that would ask for a confirmation is refused
    (--permission-prompts none), so Claude can read and answer but not, say, edit
    files or run commands that the user's settings don't already allow.
    """
    path = _known_project(req.get("path"))
    message = (req.get("message") or "").strip()
    if not message or len(message) > 20000:
        raise ActionError("message vide ou trop long")
    argv = [_exe("claude"), "-p", "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--permission-prompts", "none"]
    sid = req.get("session") or ""
    if sid:
        if not SESSION_RE.match(sid) or not (CLAUDE_DIR / "projects" / _encode_project(str(path)) / f"{sid}.jsonl").is_file():
            raise ActionError("session inconnue pour ce projet")
        argv += ["--resume", sid]
    return argv, path, message


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


def rename_link(req):
    """Name of a quick-access tile, kept in names.json. An empty name restores the project's."""
    project, url, name = req.get("project"), req.get("url"), (req.get("label") or "").strip()
    if len(name) > 40 or not name.isprintable():
        raise ActionError("nom trop long (40 caractères au plus)")
    if not any(l["url"] == url for p in collect()["projects"] if p["name"] == project for l in p["links"]):
        raise ActionError("lien inconnu")
    names = _load_json(NAMES_FILE)
    if names is None:
        raise ActionError("names.json illisible, rien n'a été écrit")
    links = names.setdefault(project, {})
    if name:
        links[url] = name
    else:
        links.pop(url, None)
    if not links:
        del names[project]
    _write_json(NAMES_FILE, names)
    return f"Renommé en « {name} »." if name else f"Nom d'origine rétabli : {project}."


def chat_events(line, state):
    """Events for the page from one line of `claude -p --output-format stream-json`.

    Text arrives as partial deltas; a complete assistant message only adds its
    text when no delta came for it (e.g. "Not logged in"). `state` carries that.
    """
    try:
        rec = json.loads(line)
    except ValueError:
        return [{"error": line.strip()}] if line.strip() else []
    kind = rec.get("type")
    if kind == "stream_event":
        e = rec.get("event") or {}
        if e.get("type") == "content_block_delta" and (e.get("delta") or {}).get("type") == "text_delta":
            state["streamed"] = True
            return [{"text": e["delta"]["text"]}]
    elif kind == "assistant":
        out = []
        for c in (rec.get("message") or {}).get("content") or []:
            if c.get("type") == "text" and not state.get("streamed"):
                out.append({"text": c.get("text", "")})
            elif c.get("type") == "tool_use":
                out.append({"tool": c.get("name")})
        state["streamed"] = False
        return out
    elif kind == "system" and rec.get("subtype") == "init":
        return [{"session": rec.get("session_id")}]
    elif kind == "result":
        return [{"done": True, "session": rec.get("session_id"), "cost": rec.get("total_cost_usd"),
                 "error": rec.get("result") if rec.get("is_error") else None}]
    return []


# --- v5: drive the PC. A closed list of actions, never a free command line. ---

def start_menu():
    """Installed apps: name -> Start menu shortcut (user entries win over all-users ones)."""
    roots = [Path(os.environ.get(v, "")) / r"Microsoft\Windows\Start Menu\Programs" for v in ("ProgramData", "APPDATA")]
    return {p.stem: p for r in roots if r.is_dir() for p in r.rglob("*.lnk")
            if not re.search(r"uninstall|désinstall", p.stem, re.I)}


def pc_open(req):
    lnk = start_menu().get(req.get("name"))
    if not lnk:
        raise ActionError("application inconnue")
    os.startfile(lnk)
    return f"{lnk.stem} ouvert."


VOLUME_KEYS = {"up": (0xAF, 5), "down": (0xAE, 5), "mute": (0xAD, 1)}  # one key press = 2 %


def pc_volume(req):
    key, presses = VOLUME_KEYS.get(req.get("dir"), (None, 0))
    if not key:
        raise ActionError("réglage du son inconnu")
    for _ in range(presses):
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key, 0, 2, 0)  # key up
    return {"up": "Son monté.", "down": "Son baissé.", "mute": "Son coupé ou remis."}[req["dir"]]


def _sleep():
    ctypes.windll.powrprof.SetSuspendState(False, False, False)  # sleep, not hibernate


def pc_power(req):
    mode = req.get("mode")
    if mode == "lock":
        ctypes.windll.user32.LockWorkStation()
        return "PC verrouillé."
    if mode == "sleep":
        threading.Timer(1, _sleep).start()  # let the answer reach the page first
        return "Mise en veille…"
    if mode in ("shutdown", "cancel"):
        args = ["/s", "/t", "60"] if mode == "shutdown" else ["/a"]
        r = subprocess.run(["shutdown", *args], capture_output=True, encoding="utf-8", errors="replace",
                           creationflags=NO_WINDOW)
        if r.returncode:
            raise ActionError((r.stdout + r.stderr).strip() or "shutdown a échoué")
        return "Arrêt du PC dans 60 s (« Annuler l'arrêt » pour l'empêcher)." if mode == "shutdown" else "Arrêt annulé."
    raise ActionError("action d'alimentation inconnue")


ACTIONS = {f.__name__: f for f in (open_explorer, open_editor, claude_new, claude_resume,
                                    git_status, git_pull, git_pull_all, toggle_plugin, toggle_mcp, rename_link,
                                    pc_open, pc_volume, pc_power)}


def run(req):
    action = ACTIONS.get(req.get("act"))
    if not action:
        raise ActionError("action inconnue")
    return action(req)
