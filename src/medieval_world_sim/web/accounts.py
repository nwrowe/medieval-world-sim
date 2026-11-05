"""Credential verification, invitation policy, and session storage.

This module has no direct HTTP access and only accepts the authenticated
multiplayer store explicitly. All writes continue through the caller's
serialized SQLite/world transaction boundary, preserving replay semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid

from ..errors import ActionError
from .session import START_CITY

MAX_ACCOUNTS = 100
INVITE_VALID_SECONDS = 7 * 86400
MAX_INVITES_PER_BATCH = 25
SESSION_SECONDS = 86400
PASSWORD_N = 1 << 15
PASSWORD_R = 8
PASSWORD_P = 1
MAX_FAILED_LOGINS = 6
LOGIN_COOLDOWN = 900
class AuthError(ActionError):
    """Untrusted or missing account credentials."""


@dataclass(frozen=True)
class Identity:
    actor_id: str
    username: str
    display_name: str
    csrf: str
def _digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt,
                          n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P, dklen=32,
                          maxmem=64 * 1024 * 1024)


def validate_registration(username, password, display_name):
    if (not isinstance(username, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]{2,23}", username)):
        raise ActionError("Username must be 3–24 letters, digits or underscores")
    if (not isinstance(display_name, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z '’-]{1,27}", display_name.strip())):
        raise ActionError("Character name must be 2–28 letters or spaces")
    if (not isinstance(password, str) or not 12 <= len(password) <= 128
            or "\x00" in password):
        raise ActionError("Password must contain 12–128 characters")
    return username.lower(), display_name.strip()


def issue_invites(game, count: int = 1) -> list[str]:
    """Operator-only administration; never expose through the HTTP server."""
    if type(count) is not int or not 1 <= count <= MAX_INVITES_PER_BATCH:
        raise ValueError("Invalid invitation batch size")
    codes = [secrets.token_urlsafe(24) for _ in range(count)]
    expiry = int(time.time()) + INVITE_VALID_SECONDS
    with game._lock:
        for code in codes:
            game.db.execute(
                "INSERT INTO registration_invites(digest,expires) VALUES(?,?)",
                (_digest(code), expiry))
    return codes


def register(game, username, password, display_name, invite: str | None, encode_json: Callable[[object], str]):
    username, display_name = game._validate_registration(
        username, password, display_name)
    salt = secrets.token_bytes(16)
    hashed = _password_hash(password, salt)
    actor_id = "player:" + uuid.uuid4().hex
    def perform():
        if game.db.execute(
            "SELECT COUNT(*) FROM accounts WHERE created_at>=?",
            (int(time.time()) - 86400,)).fetchone()[0] >= MAX_NEW_ACCOUNTS_PER_DAY:
            raise ActionError("Daily registration capacity reached")
        if game.require_invites:
            if not isinstance(invite, str) or not 20 <= len(invite) <= 128:
                raise ActionError("Valid invitation required")
            row = game.db.execute(
                "SELECT redeemed_by,expires FROM registration_invites WHERE digest=?",
                (_digest(invite),)).fetchone()
            if row is None or row[0] is not None or row[1] <= int(time.time()):
                raise ActionError("Invitation invalid, expired, or already used")
        if game.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] >= MAX_ACCOUNTS:
            raise ActionError("Development account limit reached")
        try:
            game.db.execute(
                "INSERT INTO accounts(actor_id, username, display_name, salt, "
                "password_hash, created_at) VALUES(?,?,?,?,?,?)",
                (actor_id, username, display_name, salt, hashed, int(time.time())))
        except sqlite3.IntegrityError:
            raise ActionError("Username or character name is already taken") from None
        game._join_actor(actor_id, START_CITY)
        game.names[actor_id] = display_name
        if game.require_invites:
            game.db.execute(
                "UPDATE registration_invites SET redeemed_by=? "
                "WHERE digest=? AND redeemed_by IS NULL",
                (actor_id, _digest(invite)))
        # New worlds may be idle for days before their first account joins.
        # Start the wall-clock timeline at the first actual registration.
        if len(game.names) == 1:
            game._clock_anchor = int(time.time())
            game.db.execute(
                "UPDATE world_meta SET value=? WHERE name='clock_anchor'",
                (str(game._clock_anchor).encode(),))
        game.db.execute(
            "INSERT INTO world_journal(kind, actor_id, payload, recorded_at) "
            "VALUES('join', ?, ?, ?)",
            (actor_id, encode_json({"city": START_CITY}),
             datetime.now(timezone.utc).isoformat()))
        return actor_id
    try:
        return game._tx(perform)
    except Exception:
        game.names.pop(actor_id, None)
        raise


def login(game, username: str, password: str):
    # Uniform error for missing usernames and bad passwords.
    if (not isinstance(username, str) or not isinstance(password, str)
            or len(username) > 24 or len(password) > 128):
        raise AuthError("Invalid username or password")
    normalized = username.lower()
    with game._lock:
        row = game.db.execute(
            "SELECT actor_id, salt, password_hash, failed_logins, blocked_until "
            "FROM accounts WHERE username=?", (normalized,)).fetchone()
        now = int(time.time())
        if row is None:
            # Avoid a fast user-enumeration path.
            _password_hash(password, b"not-a-real-account")
            raise AuthError("Invalid username or password")
        actor_id, salt, stored, failed, blocked = row
        if blocked > now:
            raise AuthError("Invalid username or password")
        correct = hmac.compare_digest(_password_hash(password, salt), stored)
        if not correct:
            failed += 1
            lockout = now + LOGIN_COOLDOWN if failed >= MAX_FAILED_LOGINS else 0
            game.db.execute("UPDATE accounts SET failed_logins=?, blocked_until=? "
                            "WHERE actor_id=?", (failed, lockout, actor_id))
            raise AuthError("Invalid username or password")
        game.db.execute("UPDATE accounts SET failed_logins=0, blocked_until=0 "
                        "WHERE actor_id=?", (actor_id,))
        return game._issue_session(actor_id)


def register_and_login(game, username, password, display_name,
                       invite: str | None = None):
    actor_id = game.register(username, password, display_name, invite)
    with game._lock:
        return game._issue_session(actor_id)


def _issue_session(game, actor_id: str):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    with game._lock:
        game.db.execute(
            "INSERT INTO sessions(digest, actor_id, csrf, expires) VALUES(?,?,?,?)",
            (_digest(token), actor_id, csrf, int(time.time()) + SESSION_SECONDS))
    return token, csrf


def identity(game, token: str | None) -> Identity | None:
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        return None
    with game._lock:
        row = game.db.execute(
            "SELECT a.actor_id, a.username, a.display_name, s.csrf "
            "FROM sessions s JOIN accounts a ON a.actor_id=s.actor_id "
            "WHERE s.digest=? AND s.expires>?",
            (_digest(token), int(time.time()))).fetchone()
    return Identity(*row) if row else None


def logout(game, token: str):
    with game._lock:
        game.db.execute("DELETE FROM sessions WHERE digest=?", (_digest(token),))
