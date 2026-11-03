"""Local, single-player HTTP server for the responsive web client.

Run:
    python -m medieval_world_sim.web
    python -m medieval_world_sim.web --host 0.0.0.0 --port 8765

The second form is ONLY for trusted local Wi-Fi. It requires an access token,
printed to the console, and does not provide HTTPS or remote hosting.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from ..errors import ActionError
from .session import GameSession, SaveError

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
MAX_JSON_BYTES = 16 * 1024


def _serializable(result):
    if is_dataclass(result):
        return asdict(result)
    return result


class GameHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, game: GameSession, token: str | None = None):
        self.game = game
        self.token = token
        super().__init__(address, GameHandler)


class GameHandler(BaseHTTPRequestHandler):
    server: GameHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Do not print caller-supplied request paths or auth secrets to logs.
        pass

    def _write(self, code: int, payload: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self'; script-src 'self'; "
                         "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                         "base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, code: int, value):
        payload = json.dumps(value, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        self._write(code, payload, "application/json; charset=utf-8")

    def _authorized(self) -> bool:
        if self.server.token is None or secrets.compare_digest(
                self.headers.get("X-Game-Token", ""), self.server.token):
            return True
        self._json(401, {"error": "Access code required or incorrect"})
        return False

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        parsed = urlsplit(origin)
        # Modern browsers present Origin for cross-site POSTs.
        if parsed.scheme not in ("http", "https") or parsed.netloc != self.headers.get("Host"):
            self._json(403, {"error": "Cross-origin requests not permitted"})
            return False
        return True

    def _body(self) -> dict:
        length = self.headers.get("Content-Length")
        if (length is None or not length.isdecimal()
                or not 0 < int(length) <= MAX_JSON_BYTES):
            raise ValueError("Invalid or oversized JSON request")
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            raise ValueError("Content-Type must be application/json")
        value = json.loads(self.rfile.read(int(length)))
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/api/health":
            self._json(200, {"ok": True, "mode": "single-player"})
        elif route == "/api/state":
            if self._authorized():
                self._json(200, self.server.game.snapshot())
        elif route in ASSETS:
            filename, mime = ASSETS[route]
            payload = files("medieval_world_sim.web").joinpath("static", filename).read_bytes()
            self._write(200, payload, mime)
        else:
            self._json(404, {"error": "Not found"})

    def do_POST(self):
        route = urlsplit(self.path).path
        if not route.startswith("/api/"):
            self._json(404, {"error": "Not found"})
            return
        if not self._same_origin() or not self._authorized():
            return
        try:
            data = self._body()
            if route == "/api/new":
                if set(data) != {"name"}:
                    raise ActionError("Character request must contain name only")
                self.server.game.create(data["name"])
                result = {"created": True}
            elif route == "/api/action":
                if set(data) != {"action", "params", "id"}:
                    raise ActionError("Invalid action request fields")
                result = _serializable(self.server.game.action(
                    data["action"], data["params"], data["id"]))
            elif route == "/api/advance":
                if set(data) != {"minutes"}:
                    raise ActionError("Time advancement requires minutes only")
                self.server.game.advance(data["minutes"])
                result = None
            else:
                self._json(404, {"error": "Not found"})
                return
            self._json(200, {"result": result, "state": self.server.game.snapshot()})
        except (ActionError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except SaveError as exc:
            self._json(500, {"error": str(exc)})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Play Medieval World in a web browser")
    parser.add_argument("--host", default="127.0.0.1",
                        help="127.0.0.1 (default), or 0.0.0.0 for trusted local Wi-Fi")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--save", default=str(Path.home() / ".medieval-world-sim" / "save.json"),
                        help="Single-player JSON action journal")
    parser.add_argument("--access-token", default=None,
                        help="Optional access code; auto-generated for LAN binds")
    args = parser.parse_args(argv)
    # Deliberately no public TLS, hosting, or multiplayer support.
    if args.host not in ("127.0.0.1", "localhost", "0.0.0.0"):
        parser.error("Only localhost or explicitly trusted LAN binding is supported")
    if not 1 <= args.port <= 65535:
        parser.error("Port out of range")
    token = args.access_token
    if args.host == "0.0.0.0" and not token:
        token = secrets.token_urlsafe(18)
    session = GameSession(args.save)
    with GameHTTPServer((args.host, args.port), session, token) as server:
        print(f"Medieval World web server: http://127.0.0.1:{server.server_port}", flush=True)
        print(f"Save: {Path(args.save).expanduser()}", flush=True)
        if args.host == "0.0.0.0":
            print(f"Trusted LAN only: open http://YOUR_COMPUTER_LAN_IP:{server.server_port} "
                  "from your phone", flush=True)
        if token:
            print(f"Game access code: {token}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
