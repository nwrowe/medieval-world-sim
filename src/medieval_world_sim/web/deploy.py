"""Start the single-player prototype behind a managed HTTPS reverse proxy.

Designed for a SINGLE service instance and a persistent mounted disk, not
multiplayer hosting. A missing access code is fatal, not silently public.
"""
import os
import sys
from .server import main


def start() -> None:
    token = os.environ.get("GAME_ACCESS_TOKEN", "")
    if len(token) < 20 or token.strip() != token:
        sys.exit("GAME_ACCESS_TOKEN must be a secure secret at least 20 characters long")
    port = os.environ.get("PORT", "10000")
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        sys.exit("PORT must be a valid TCP port")
    save_dir = os.environ.get("GAME_SAVE_DIR", "/var/data")
    if not os.path.isabs(save_dir):
        sys.exit("GAME_SAVE_DIR must be an absolute persistent disk path")
    main([
        "--host", "0.0.0.0",
        "--port", port,
        "--access-token", token,
        "--save", os.path.join(save_dir, "medieval-world-save.json"),
    ])


if __name__ == "__main__":
    start()
