"""Jarvis - local dashboard of the Claude Code setup, with actions (v2).

Usage: python server.py [port]   (default 7777, bound to 127.0.0.1 only)

POST /api/action only runs for the dashboard page itself: the Host and Origin
headers must be this server, and the request must carry the token this process
put in the page. Another website open in the browser can't read that token.
"""

import hmac
import json
import secrets
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jarvis import actions
from jarvis.inventory import collect

STATIC = Path(__file__).parent / "static"
TOKEN = secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/inventory":
            body = json.dumps(collect(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        elif path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_text(encoding="utf-8").replace(
                "<script>\n", f'<script>window.JARVIS_TOKEN = "{TOKEN}";</script>\n<script>\n', 1)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def _local(self):
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        # Host blocks DNS rebinding, Origin blocks other sites, the token blocks everything else.
        return (self.headers.get("Host") in hosts
                and self.headers.get("Origin") in {f"http://{h}" for h in hosts}
                and hmac.compare_digest(self.headers.get("X-Jarvis-Token", ""), TOKEN))

    def do_POST(self):
        if self.path != "/api/action":
            return self._send(404, b"not found", "text/plain")
        if not self._local():
            return self._send(403, b"forbidden", "text/plain")
        try:
            req = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 10000)))
            status, out = 200, {"ok": True, "output": actions.run(req)}
        except actions.ActionError as e:
            status, out = 400, {"ok": False, "error": str(e)}
        except (ValueError, OSError, AttributeError, subprocess.SubprocessError) as e:
            status, out = 500, {"ok": False, "error": f"{type(e).__name__}: {e}"}
        self._send(status, json.dumps(out, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        sys.stderr.write("[jarvis] " + fmt % args + "\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7777
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Jarvis running on http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
