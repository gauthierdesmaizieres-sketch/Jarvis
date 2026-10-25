"""Jarvis - local dashboard of the Claude Code setup, with actions (v2) and chat (v3).

Usage: python server.py [port]   (default 7777, bound to 127.0.0.1 only)

POST /api/action, POST /api/chat and the private GET routes (usage, search, git)
only run for the dashboard page itself: the Host and Origin headers must be this
server, and the request must carry the token this process put in the page.
Another website open in the browser can't read that token.
"""

import hmac
import json
import os
import secrets
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from jarvis import actions, history
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

    def _json(self, status, data):
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlsplit(self.path)
        path, qs = url.path, parse_qs(url.query)
        private = {
            "/api/usage": lambda: history.usage(),
            "/api/search": lambda: history.search(qs.get("q", [""])[0], min(int(qs.get("limit", ["50"])[0]), 200)),
            "/api/git": lambda: actions.git_overview(fetch=qs.get("fetch") == ["1"]),
        }
        if path in private:
            if not self._local():
                return self._send(403, b"forbidden", "text/plain")
            try:
                self._json(200, private[path]())
            except (ValueError, OSError, subprocess.SubprocessError) as e:
                self._json(500, {"error": f"{type(e).__name__}: {e}"})
        elif path == "/api/inventory":
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
        origins = {f"http://{h}" for h in hosts}
        # Browsers send no Origin on a same-origin GET; a cross-site GET can't add the token header.
        origin = self.headers.get("Origin", next(iter(origins)) if self.command == "GET" else None)
        # Host blocks DNS rebinding, Origin blocks other sites, the token blocks everything else.
        return (self.headers.get("Host") in hosts
                and origin in origins
                and hmac.compare_digest(self.headers.get("X-Jarvis-Token", ""), TOKEN))

    def do_POST(self):
        if self.path not in ("/api/action", "/api/chat"):
            return self._send(404, b"not found", "text/plain")
        if not self._local():
            return self._send(403, b"forbidden", "text/plain")
        try:
            req = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 100000)))
            if self.path == "/api/chat":
                return self._chat(*actions.chat_command(req))
            status, out = 200, {"ok": True, "output": actions.run(req)}
        except actions.ActionError as e:
            status, out = 400, {"ok": False, "error": str(e)}
        except (ValueError, OSError, AttributeError, subprocess.SubprocessError) as e:
            status, out = 500, {"ok": False, "error": f"{type(e).__name__}: {e}"}
        self._send(status, json.dumps(out, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _chat(self, argv, cwd, message):
        """Run one `claude -p` turn and stream it to the page as JSON lines."""
        env = os.environ
        if "CLAUDECODE" in env:  # started from inside Claude Code: the child must use the user's own login
            env = {k: v for k, v in env.items()
                   if k != "CLAUDECODE" and not k.startswith(("CLAUDE_CODE_", "CLAUDE_AGENT_SDK"))}
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                                creationflags=actions.NO_WINDOW)
        state = {}
        try:
            proc.stdin.write(message)
            proc.stdin.close()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()  # HTTP/1.0: no length, the body ends when the connection closes
            for line in proc.stdout:
                for ev in actions.chat_events(line, state):
                    self.wfile.write((json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()
        except ConnectionError:
            pass  # page closed or "Stop" clicked
        finally:
            proc.kill()
            proc.wait()

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
