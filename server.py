"""Jarvis v1 - local, read-only dashboard of the Claude Code setup.

Usage: python server.py [port]   (default 7777, bound to 127.0.0.1 only)
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jarvis.inventory import collect

STATIC = Path(__file__).parent / "static"


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
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

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
