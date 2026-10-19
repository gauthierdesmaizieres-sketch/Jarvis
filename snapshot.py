"""Build a standalone copy of the dashboard with the inventory baked in.

Usage: python snapshot.py   ->  dist/jarvis.html

The file works without the local server, so it can be published online and
opened from a phone while the PC is off. Republish it after running this.
"""

import json
from pathlib import Path

from jarvis.inventory import collect

ROOT = Path(__file__).parent
SRC = ROOT / "static" / "index.html"
OUT = ROOT / "dist" / "jarvis.html"

# The artifact host wraps the page in its own document skeleton.
SKELETON = [
    "<!doctype html>\n", '<html lang="fr">\n', "</html>\n", "<head>\n", "</head>\n",
    "<body>\n", "</body>\n", '<meta charset="utf-8">\n',
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
]


def build():
    html = SRC.read_text(encoding="utf-8")
    for tag in SKELETON:
        html = html.replace(tag, "")
    payload = json.dumps(collect(), ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("<script>\n", f"<script>window.JARVIS_DATA = {payload};</script>\n<script>\n", 1)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"{OUT} ({OUT.stat().st_size // 1024} Ko)")


if __name__ == "__main__":
    build()
