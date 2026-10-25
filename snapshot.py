"""Build a standalone copy of the dashboard with the inventory baked in.

Usage:
  python snapshot.py            ->  dist/jarvis.html  (private, for the claude.ai Artifact)
  python snapshot.py --public   ->  docs/index.html   (filtered, for GitHub Pages)

The file works without the local server, so it can be opened from a phone
while the PC is off.
"""

import json
import re
import sys
from pathlib import Path

from jarvis.inventory import collect

ROOT = Path(__file__).parent
SRC = ROOT / "static" / "index.html"
PRIVATE_OUT = ROOT / "dist" / "jarvis.html"
PUBLIC_OUT = ROOT / "docs" / "index.html"
STATS_OUT = ROOT / "docs" / "stats.json"
GENERATED_RE = re.compile(r'"generatedAt": "[^"]*"')

# The artifact host wraps the page in its own document skeleton.
SKELETON = [
    "<!doctype html>\n", '<html lang="fr">\n', "</html>\n", "<head>\n", "</head>\n",
    "<body>\n", "</body>\n", '<meta charset="utf-8">\n',
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n',
]


# Installable on the phone's home screen; manifest and icons live next to the page
# (docs/ for GitHub Pages, served from docs/ by server.py for the local page).
APP_HEAD = """<title>Jarvis</title>
<meta name="robots" content="noindex">
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#03070d">
<link rel="icon" href="icon-192.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Jarvis">"""


def public_stats(data):
    """The few counters a phone widget shows; public, and without a date so it only changes with them."""
    return {
        "projets": len(data["projects"]),
        "skills": len(data["skills"]) + sum(len(p["skills"]) for p in data["projects"]),
        "sessions": sum(p["sessionCount"] for p in data["projects"]) + data["scratchSessionCount"],
        "mcp": len(data["mcpServers"]) + sum(len(p["mcpServers"]) for p in data["projects"]),
        "plugins": len(data["plugins"]),
    }


def public_view(data):
    """Keep only what is fine on a public site, and only fields that change when
    something real changes (a project, a link, a commit), so a rebuild after an
    ordinary turn produces the same page and nothing gets pushed."""
    for p in data["projects"]:
        # Each publish commits here, so this repo's own last commit would re-trigger it forever.
        if p["git"] and Path(p["path"]).resolve() == ROOT.resolve():
            p["git"].pop("lastCommit", None)
        p["path"] = ""
        p["sessions"] = []
        p["disabledMcp"] = []
        p["links"] = [l for l in p["links"] if l["kind"] != "local"]
        p.pop("lastActivity", None)
        if p["git"]:
            p["git"].pop("dirtyFiles", None)
        for m in p["mcpServers"]:
            m.update(command=None, url=None, envKeys=[], headerKeys=[])
    for m in data["mcpServers"]:
        m.update(command=None, url=None, envKeys=[], headerKeys=[])
    for s in data["skills"]:
        s.update(usageCount=0, lastUsedAt=None, path="")
    for item in data["agents"] + data["commands"]:
        item["path"] = ""
    data["projects"].sort(key=lambda p: p["name"].lower())  # activity order changes every turn
    data["account"] = {}
    data["globalClaudeMd"] = None
    return data


def render(data, public):
    html = SRC.read_text(encoding="utf-8")
    if public:
        html = html.replace("<title>Jarvis</title>", APP_HEAD)
    else:
        for tag in SKELETON:
            html = html.replace(tag, "")
    payload = json.dumps(data, ensure_ascii=False, indent=0).replace("</", "<\\/")
    return html.replace("<script>\n", f"<script>window.JARVIS_DATA = {payload};</script>\n<script>\n", 1)


def build(public=False):
    """Write the page (and stats.json when public); return True when something other than the date changed."""
    data = collect()
    out = PUBLIC_OUT if public else PRIVATE_OUT
    html = render(public_view(data) if public else data, public)
    changed = False
    if public:
        stats = json.dumps(public_stats(data), ensure_ascii=False, indent=2)
        if not STATS_OUT.exists() or STATS_OUT.read_text(encoding="utf-8") != stats:
            STATS_OUT.write_text(stats, encoding="utf-8")
            changed = True
    old = out.read_text(encoding="utf-8") if out.exists() else ""
    if GENERATED_RE.sub("", old) == GENERATED_RE.sub("", html):
        return changed
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return True


if __name__ == "__main__":
    public = "--public" in sys.argv
    changed = build(public)
    print(f"{PUBLIC_OUT if public else PRIVATE_OUT}: {'mis à jour' if changed else 'inchangé'}")
