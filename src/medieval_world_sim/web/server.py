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
from http.cookies import SimpleCookie
from importlib.resources import files
import json
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit

from ..errors import ActionError
from .session import GameSession, SaveError
from .multiplayer import MultiplayerGame, AuthError, SESSION_SECONDS

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/world-map.svg": ("world-map.svg", "image/svg+xml"),
}
MAX_JSON_BYTES = 16 * 1024


def _serializable(result):
    if is_dataclass(result):
        return asdict(result)
    return result


class GameHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, game: GameSession | None, token: str | None = None,
                 colab_preview: bool = False, multiplayer: MultiplayerGame | None = None):
        if multiplayer is not None and address[0] not in ("127.0.0.1", "localhost"):
            raise ValueError("Multi-account development mode is localhost-only")
        if multiplayer is not None and (token is not None or colab_preview):
            raise ValueError("Multi-account mode cannot use server access codes or frames")
        self.game = game
        self.multiplayer = multiplayer
        self.token = token
        self.colab_preview = colab_preview
        super().__init__(address, GameHandler)


class GameHandler(BaseHTTPRequestHandler):
    server: GameHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Do not print caller-supplied request paths or auth secrets to logs.
        pass

    def _write(self, code: int, payload: bytes, content_type: str,
               extra_headers: dict[str, str] | None = None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if not self.server.colab_preview:
            self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        # Colab's port proxy is displayed inside a cross-origin notebook
        # iframe. Its ancestor chain may include changing Google domains, so
        # iframe support must be an explicit local-only opt-in.
        csp = ("default-src 'self'; style-src 'self'; script-src 'self'; "
               "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
               "base-uri 'none'")
        if not self.server.colab_preview:
            csp += "; frame-ancestors 'none'"
        self.send_header("Content-Security-Policy", csp)
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, code: int, value, extra_headers=None):
        payload = json.dumps(value, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        self._write(code, payload, "application/json; charset=utf-8",
                    extra_headers=extra_headers)

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
        value = json.loads(self.rfile.read(int(length)),\n                           parse_constant=lambda x: (_ for _ in ()).throw(\n                               ValueError("Non-finite JSON values are forbidden")))
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    def _multi_host_valid(self) -> bool:
        """Reject DNS-rebinding Host headers even on a loopback listener."""
        raw = self.headers.get("Host", "")
        try:
            host = urlsplit("http://" + raw)
            allowed = (host.hostname in ("localhost", "127.0.0.1")
                       and host.port == self.server.server_port
                       and not host.username and not host.password)
        except ValueError:
            allowed = False
        if not allowed:
            self._json(403, {"error": "Invalid local host"})
        return allowed

    def _multi_cookie(self) -> str | None:
        raw = self.headers.get("Cookie", "")
        if len(raw) > 2048:
            return None
        try:
            cookie = SimpleCookie()
            cookie.load(raw)
            return cookie["oathmere_session"].value if "oathmere_session" in cookie else None
        except Exception:
            return None

    def _multi_identity(self):
        token = self._multi_cookie()
        if token is None:
            return None
        return self.server.multiplayer.identity(token)

    def _multi_auth(self, *, csrf=False):
        identity = self._multi_identity()
        if identity is None:
            self._json(401, {"error": "Sign in to continue"})
            return None
        if csrf and not secrets.compare_digest(
                self.headers.get("X-CSRF-Token", ""), identity.csrf):
            self._json(403, {"error": "Invalid request protection token"})
            return None
        return identity

    @staticmethod
    def _session_cookie(token: str | None) -> str:
        # HTTP is allowed ONLY on loopback. Do not deploy this cookie on a LAN.
        value = token or ""
        return (f"oathmere_session={value}; Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age={SESSION_SECONDS if token else 0}")

    def _multi_get(self, route: str):
        if not self._multi_host_valid():
            return
        if route == "/api/health":
            self._json(200, {"ok": True, "mode": "multi-account-local"})
        elif route == "/api/auth/session":
            identity = self._multi_identity()
            self._json(200, {"authenticated": identity is not None,
                             "csrf": identity.csrf if identity else None,
                             "username": identity.username if identity else None})
        elif route == "/api/state":
            identity = self._multi_auth()
            if identity:
                self._json(200, self.server.multiplayer.snapshot(identity.actor_id))
        elif route in ASSETS:
            filename, mime = ASSETS[route]
            payload = files("medieval_world_sim.web").joinpath(
                "static", filename).read_bytes()
            self._write(200, payload, mime)
        else:
            self._json(404, {"error": "Not found"})

    def _multi_post(self, route: str):
        if not self._multi_host_valid() or not self._same_origin():
            return
        try:
            data = self._body()
            if route == "/api/auth/register":
                if set(data) != {"username", "password", "display_name"}:
                    raise ActionError("Invalid registration fields")
                token, csrf = self.server.multiplayer.register_and_login(
                    data["username"], data["password"], data["display_name"])
                identity = self.server.multiplayer.identity(token)
                self._json(200, {"result": {"registered": True}, "csrf": csrf,
                                 "state": self.server.multiplayer.snapshot(identity.actor_id)},
                           {"Set-Cookie": self._session_cookie(token)})
                return
            if route == "/api/auth/login":
                if set(data) != {"username", "password"}:
                    raise ActionError("Invalid sign-in fields")
                token, csrf = self.server.multiplayer.login(
                    data["username"], data["password"])
                identity = self.server.multiplayer.identity(token)
                self._json(200, {"result": {"logged_in": True}, "csrf": csrf,
                                 "state": self.server.multiplayer.snapshot(identity.actor_id)},
                           {"Set-Cookie": self._session_cookie(token)})
                return
            identity = self._multi_auth(csrf=True)
            if identity is None:
                return
            if route == "/api/auth/logout":
                if data:
                    raise ActionError("Sign-out has no request fields")
                self.server.multiplayer.logout(self._multi_cookie())
                self._json(200, {"result": {"logged_out": True}},
                           {"Set-Cookie": self._session_cookie(None)})
                return
            if route == "/api/action":
                if set(data) != {"action", "params", "id"}:
                    raise ActionError("Invalid action request fields")
                result = self.server.multiplayer.action(
                    identity.actor_id, data["action"], data["params"], data["id"])
            elif route == "/api/advance":
                if set(data) != {"minutes", "id"}:
                    raise ActionError("Advancement requires minutes and request ID")
                result = self.server.multiplayer.advance(
                    identity.actor_id, data["minutes"], data["id"])
            else:
                self._json(404, {"error": "Not found"})
                return
            self._json(200, {"result": result,
                             "state": self.server.multiplayer.snapshot(identity.actor_id)})
        except AuthError:
            self._json(401, {"error": "Invalid username or password"})
        except (ActionError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except (sqlite3.Error, OSError):
            self._json(500, {"error": "Unable to store multiplayer action"})

    def do_GET(self):
        route = urlsplit(self.path).path
        if self.server.multiplayer is not None:
            self._multi_get(route)
            return
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
        if self.server.multiplayer is not None:
            self._multi_post(route)
            return
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
    parser = argparse.ArgumentParser(description="Play Oathmere in a web browser")
    parser.add_argument("--host", default="127.0.0.1",
                        help="127.0.0.1 (default), or 0.0.0.0 for trusted local Wi-Fi")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--save", default=str(Path.home() / ".medieval-world-sim" / "save.json"),
                        help="Single-player JSON action journal")
    parser.add_argument("--multiplayer-db", default=None,
                        help="Opt-in localhost-only SQLite shared-world and accounts database")
    parser.add_argument("--access-token", default=None,
                        help="Optional access code; auto-generated for LAN binds")
    parser.add_argument("--colab-preview", action="store_true",
                        help="Permit Colab notebook iframe preview; localhost only")
    args = parser.parse_args(argv)
    # Deliberately no public TLS, hosting, or multiplayer support.
    if args.host not in ("127.0.0.1", "localhost", "0.0.0.0"):
        parser.error("Only localhost or explicitly trusted LAN binding is supported")
    if not 1 <= args.port <= 65535:
        parser.error("Port out of range")
    if args.colab_preview and args.host not in ("127.0.0.1", "localhost"):
        parser.error("--colab-preview must use localhost, not a LAN bind")
    if args.multiplayer_db:
        if args.host not in ("127.0.0.1", "localhost"):
            parser.error("--multiplayer-db is localhost-only; no public/LAN auth yet")
        if args.colab_preview or args.access_token:
            parser.error("--multiplayer-db cannot use --access-token or --colab-preview")
        multi = MultiplayerGame(args.multiplayer_db)
        try:
            with GameHTTPServer((args.host, args.port), None,
                                multiplayer=multi) as server:
                print(f"Oathmere multi-account local server: http://127.0.0.1:{server.server_port}", flush=True)
                print(f"Database: {Path(args.multiplayer_db).expanduser()}", flush=True)
                print("Development only: localhost. Do NOT expose directly to the internet.",
                      flush=True)
                print("Press Ctrl+C to stop.", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        finally:
            multi.close()
        return
    token = args.access_token
    if args.host == "0.0.0.0" and not token:
        token = secrets.token_urlsafe(18)
    session = GameSession(args.save)
    with GameHTTPServer((args.host, args.port), session, token,
                        colab_preview=args.colab_preview) as server:
        print(f"Oathmere web server: http://127.0.0.1:{server.server_port}", flush=True)
        print(f"Save: {Path(args.save).expanduser()}", flush=True)
        if args.host == "0.0.0.0":
            print(f"Trusted LAN only: open http://YOUR_COMPUTER_LAN_IP:{server.server_port} "
                  "from your phone", flush=True)
        if token:
            print(f"Game access code: {token}", flush=True)
        if args.colab_preview:
            print("Colab iframe preview enabled (local-only; do not expose publicly)",
                  flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
