"""Read-only inventory of the local Claude Code setup.

Nothing in this module writes to disk. Secrets are never returned: MCP server
env values, headers and URL query strings are dropped, only their names are kept.
"""

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
CLAUDE_JSON = HOME / ".claude.json"
APPDATA = Path(os.environ.get("APPDATA", HOME / "AppData" / "Roaming"))
DESKTOP_CONFIG = APPDATA / "Claude" / "claude_desktop_config.json"

SCRATCH_MARKER = "scratch-workspaces"
REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _iso(ts):
    """Epoch seconds or milliseconds -> ISO string."""
    if ts is None:
        return None
    if ts > 1e12:
        ts /= 1000
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _frontmatter(md_path):
    """Minimal YAML frontmatter parser: top-level `key: value` lines only."""
    meta = {}
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return meta
    if not text.startswith("---"):
        return meta
    end = text.find("\n---", 3)
    if end == -1:
        return meta
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return meta


# --- Skills, commands, agents -------------------------------------------------

def _skills_in(skills_dir, source):
    out = []
    if not skills_dir.is_dir():
        return out
    for d in sorted(skills_dir.iterdir()):
        md = d / "SKILL.md"
        if md.is_file():
            meta = _frontmatter(md)
            out.append({
                "name": meta.get("name", d.name),
                "description": meta.get("description", ""),
                "source": source,
                "path": str(d),
            })
    return out


def _md_items_in(folder, source):
    out = []
    if not folder.is_dir():
        return out
    for md in sorted(folder.glob("*.md")):
        meta = _frontmatter(md)
        out.append({
            "name": meta.get("name", md.stem),
            "description": meta.get("description", ""),
            "source": source,
            "path": str(md),
        })
    return out


# --- MCP servers --------------------------------------------------------------

def _redact_server(name, cfg, scope):
    url = cfg.get("url")
    if url:
        parts = urlsplit(url)
        url = f"{parts.scheme}://{parts.netloc}{parts.path}"
    command = cfg.get("command")
    return {
        "name": name,
        "scope": scope,
        "type": cfg.get("type") or ("http" if url else "stdio"),
        "command": Path(command).name if command else None,
        "argCount": len(cfg.get("args") or []),
        "url": url,
        "envKeys": sorted((cfg.get("env") or {}).keys()),
        "headerKeys": sorted((cfg.get("headers") or {}).keys()),
    }


def _servers_from(mapping, scope):
    return [_redact_server(n, c or {}, scope) for n, c in (mapping or {}).items()]


# --- Projects & sessions ------------------------------------------------------

def _encode_project(path):
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def _first_prompt(jsonl):
    """First real user prompt of a session, without injected reminders."""
    try:
        with open(jsonl, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 200:
                    break
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("type") != "user" or rec.get("isSidechain"):
                    continue
                content = (rec.get("message") or {}).get("content")
                texts = [content] if isinstance(content, str) else [
                    c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"
                ]
                for t in texts:
                    t = REMINDER_RE.sub("", t).strip()
                    if t and not t.startswith("<"):
                        return t[:160]
    except OSError:
        pass
    return None


def _sessions_for(project_path):
    folder = CLAUDE_DIR / "projects" / _encode_project(project_path)
    if not folder.is_dir():
        return []
    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for i, f in enumerate(files):
        st = f.stat()
        out.append({
            "id": f.stem,
            "updatedAt": _iso(st.st_mtime),
            "sizeKb": round(st.st_size / 1024),
            # Reading prompts is the costly part: only for the most recent ones.
            "firstPrompt": _first_prompt(f) if i < 5 else None,
        })
    return out


def _git_info(path):
    if not (path / ".git").exists():
        return None
    def run(*args):
        try:
            r = subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                               encoding="utf-8", errors="replace", timeout=5)
            return r.stdout.strip() if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None
    status = run("status", "--porcelain")
    return {
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "lastCommit": run("log", "-1", "--format=%cI %s"),
        "dirtyFiles": len(status.splitlines()) if status else 0,
    }


GITHUB_RE = re.compile(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$")
LINKS_FILE = Path(__file__).resolve().parent.parent / "links.json"


def _github_links(repo_dir, label_prefix=""):
    try:
        r = subprocess.run(["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    m = GITHUB_RE.search(r.stdout.strip()) if r.returncode == 0 else None
    if not m:
        return []
    owner, repo = m.groups()
    base = f"https://github.com/{owner}/{repo}"
    p = f"{label_prefix} · " if label_prefix else ""
    links = [
        {"label": f"{p}GitHub", "url": base, "kind": "repo"},
        {"label": f"{p}Changelog", "url": f"{base}/commits", "kind": "changelog"},
    ]
    if (repo_dir / ".github" / "workflows").is_dir():
        links.append({"label": f"{p}Actions", "url": f"{base}/actions", "kind": "ci"})
    # GitHub Pages is usually served from the root or /docs.
    if (repo_dir / "index.html").is_file() or (repo_dir / "docs" / "index.html").is_file():
        links.insert(0, {"label": f"{p}Site web", "url": f"https://{owner.lower()}.github.io/{repo}/", "kind": "web"})
    return links


def _local_links(folder, label_prefix=""):
    launch = _load_json(folder / ".claude" / "launch.json") or {}
    out = []
    for c in launch.get("configurations", []):
        url = c.get("url") or (f"http://localhost:{c['port']}" if c.get("port") else None)
        if url:
            name = c.get("name") or label_prefix or "local"
            out.append({"label": f"Local · {name}", "url": url, "kind": "local"})
    return out


def _project_links(path, name):
    """Links of a project: GitHub, Pages, local dev servers, plus links.json overrides.

    Git repos nested one level down (a project folder holding several apps) count too.
    """
    links = _github_links(path) + _local_links(path)
    for sub in sorted(path.iterdir()) if path.is_dir() else []:
        if sub.is_dir() and not sub.name.startswith(".") and (sub / ".git").exists():
            links += _github_links(sub, sub.name) + _local_links(sub, sub.name)
    manual = (_load_json(LINKS_FILE) or {}).get(name, [])
    links = [{**l, "kind": l.get("kind", "custom")} for l in manual] + links
    seen, unique = set(), []
    for l in links:
        if l["url"] not in seen:
            seen.add(l["url"])
            unique.append(l)
    return unique


def _project(path_str, cfg):
    path = Path(path_str)
    exists = path.is_dir()
    mcp = _servers_from(cfg.get("mcpServers"), "local")
    if exists:
        mcp_json = _load_json(path / ".mcp.json") or {}
        mcp += _servers_from(mcp_json.get("mcpServers"), "project")
    sessions = _sessions_for(path_str)
    return {
        "name": path.name,
        "path": str(path),
        "exists": exists,
        "hasClaudeMd": exists and ((path / "CLAUDE.md").is_file() or (path / ".claude" / "CLAUDE.md").is_file()),
        "git": _git_info(path) if exists else None,
        "links": _project_links(path, path.name) if exists else [],
        "mcpServers": mcp,
        "skills": _skills_in(path / ".claude" / "skills", "project") if exists else [],
        "agents": _md_items_in(path / ".claude" / "agents", "project") if exists else [],
        "commands": _md_items_in(path / ".claude" / "commands", "project") if exists else [],
        "sessionCount": len(sessions),
        "lastActivity": sessions[0]["updatedAt"] if sessions else None,
        "sessions": sessions[:10],
    }


# --- Entry point --------------------------------------------------------------

def collect():
    claude_json = _load_json(CLAUDE_JSON) or {}
    settings = _load_json(CLAUDE_DIR / "settings.json") or {}
    installed = (_load_json(CLAUDE_DIR / "plugins" / "installed_plugins.json") or {}).get("plugins", {})
    marketplaces = _load_json(CLAUDE_DIR / "plugins" / "known_marketplaces.json") or {}
    desktop = _load_json(DESKTOP_CONFIG) or {}
    enabled = settings.get("enabledPlugins", {})

    skills = _skills_in(CLAUDE_DIR / "skills", "user")
    agents = _md_items_in(CLAUDE_DIR / "agents", "user")
    commands = _md_items_in(CLAUDE_DIR / "commands", "user")

    plugins = []
    for plugin_id, installs in installed.items():
        for inst in installs:
            root = Path(inst.get("installPath", ""))
            source = f"plugin:{plugin_id.split('@')[0]}"
            p_skills = _skills_in(root / "skills", source)
            p_agents = _md_items_in(root / "agents", source)
            p_commands = _md_items_in(root / "commands", source)
            skills += p_skills
            agents += p_agents
            commands += p_commands
            plugins.append({
                "id": plugin_id,
                "version": inst.get("version"),
                "scope": inst.get("scope"),
                "enabled": bool(enabled.get(plugin_id)),
                "installedAt": inst.get("installedAt"),
                "skills": [s["name"] for s in p_skills],
                "agents": [a["name"] for a in p_agents],
                "commands": [c["name"] for c in p_commands],
            })

    usage = claude_json.get("skillUsage", {})
    for s in skills:
        u = usage.get(s["name"], {})
        s["usageCount"] = u.get("usageCount", 0)
        s["lastUsedAt"] = _iso(u.get("lastUsedAt"))

    projects = [
        _project(p, cfg or {})
        for p, cfg in (claude_json.get("projects") or {}).items()
        if SCRATCH_MARKER not in p and Path(p) != HOME / ".local" / "bin"
    ]
    projects.sort(key=lambda p: p["lastActivity"] or "", reverse=True)

    scratch_sessions = sum(
        len(list(d.glob("*.jsonl")))
        for d in (CLAUDE_DIR / "projects").glob(f"*{SCRATCH_MARKER}*") if d.is_dir()
    )

    global_md = CLAUDE_DIR / "CLAUDE.md"
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "account": {
            "email": (claude_json.get("oauthAccount") or {}).get("emailAddress"),
            "installMethod": claude_json.get("installMethod"),
            "autoUpdatesChannel": settings.get("autoUpdatesChannel"),
        },
        "globalClaudeMd": global_md.read_text(encoding="utf-8", errors="replace") if global_md.is_file() else None,
        "skills": skills,
        "agents": agents,
        "commands": commands,
        "plugins": plugins,
        "marketplaces": [
            {"name": n, "url": (m.get("source") or {}).get("url") or (m.get("source") or {}).get("repo"),
             "lastUpdated": m.get("lastUpdated")}
            for n, m in marketplaces.items()
        ],
        "mcpServers": _servers_from(claude_json.get("mcpServers"), "user")
                      + _servers_from(desktop.get("mcpServers"), "desktop"),
        "projects": projects,
        "scratchSessionCount": scratch_sessions,
    }


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2, ensure_ascii=False))
