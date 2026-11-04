"""Single-process, localhost-only multi-account development backend.

Authenticates individual users against SQLite, ties sessions to immutable actor
IDs, and commits a shared-world command journal in the *same* SQLite transaction
as the account operation. This is a development bridge, not an internet-ready
multiplayer host or a substitute for a row-locked production database.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass, dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import random
import re
import secrets
import sqlite3
import threading
import time
import uuid

from ..catalog import CITIES
from ..core.engine import WorldEngine
from ..core.entities import Actor
from ..errors import ActionError
from .session import (GameSession, NPC_NAMES, START_CITY, INITIAL_GOLD,
                      ADVANCE_LIMIT, UI_ACTIONS, world_snapshot)

# Deliberately bounded until rate limiting, moderation and deployment hardening
# have been reviewed in a dedicated public-server milestone.
MAX_ACCOUNTS = 100
SESSION_SECONDS = 86400
PASSWORD_N = 1 << 15
PASSWORD_R = 8
PASSWORD_P = 1
MAX_FAILED_LOGINS = 6
LOGIN_COOLDOWN = 900
MAX_JOURNAL = 20000
# Real identities, not a shared access code, are necessary but not sufficient
# for public hosting. Keep this entire mode loopback-only.
MULTI_ACTIONS = UI_ACTIONS - {"enroll_course"} | {
    "propose_trade", "accept_trade", "close_trade",
}


class AuthError(ActionError):
    """Untrusted or missing account credentials."""


@dataclass(frozen=True)
class Identity:
    actor_id: str
    username: str
    display_name: str
    csrf: str


def _jsonable(value):
    return asdict(value) if is_dataclass(value) else value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt,
                          n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P, dklen=32,\n                          maxmem=64 * 1024 * 1024)


class MultiplayerGame:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # A single process owns the in-memory simulation. SQLite exclusive
        # locking prevents two processes independently committing stale worlds.
        self.db = sqlite3.connect(str(self.db_path), isolation_level=None,
                                  timeout=2.0, check_same_thread=False)
        try:
            self.db.execute("PRAGMA foreign_keys = ON")
            self.db.execute("PRAGMA locking_mode = EXCLUSIVE")
            self.db.execute("PRAGMA journal_mode = DELETE")
            self.db.execute("PRAGMA synchronous = FULL")
            self._create_schema()
            if os.name != "nt":
                os.chmod(self.db_path, 0o600)
            self._load_world()
        except Exception:
            self.db.close()
            raise

    def close(self):
        with self._lock:
            self.db.close()

    def _create_schema(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS accounts(
                actor_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at INTEGER NOT NULL,
                failed_logins INTEGER NOT NULL DEFAULT 0,
                blocked_until INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions(
                digest BLOB PRIMARY KEY,
                actor_id TEXT NOT NULL REFERENCES accounts(actor_id),
                csrf TEXT NOT NULL,
                expires INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS session_expiration ON sessions(expires);
            CREATE TABLE IF NOT EXISTS world_journal(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('join','action','advance')),
                actor_id TEXT NOT NULL REFERENCES accounts(actor_id),
                action TEXT,
                payload TEXT NOT NULL,
                request_id TEXT,
                result_json TEXT,
                UNIQUE(actor_id, request_id)
            );
        """)

    def _seed_world(self):
        rng = random.Random(42)
        names = list(NPC_NAMES)
        rng.shuffle(names)
        actors = []
        self.npc_names = {}
        for city in CITIES:
            for idx in range(3):
                npc_id = f"npc:{city}:{idx}"
                actors.append(Actor(npc_id, "npc", city=city, gold=rng.randint(50, 250)))
                self.npc_names[npc_id] = names.pop()
        return WorldEngine(actors, seed=42)

    def _join_actor(self, actor_id: str):
        if actor_id in self.world.actors:
            raise ValueError("Duplicate player registration in world")
        self.world.actors[actor_id] = Actor(actor_id, "human", city=START_CITY,
                                            gold=INITIAL_GOLD)
        self.world.state.initial_gold += INITIAL_GOLD
        self.world.assert_invariants()

    def _load_world(self):
        self.world = self._seed_world()
        self.names = {}
        self.event_times = {}
        registered = set()
        rows = self.db.execute(
            "SELECT kind, actor_id, action, payload, request_id FROM world_journal "
            "ORDER BY seq").fetchall()
        for kind, actor_id, action, payload, request_id in rows:
            params = json.loads(payload)
            if kind == "join":
                if actor_id in registered:
                    raise ValueError("Repeated registered actor")
                account = self.db.execute(
                    "SELECT display_name FROM accounts WHERE actor_id=?",
                    (actor_id,)).fetchone()
                if account is None:
                    raise ValueError("Registered actor has no account")
                self._join_actor(actor_id)
                self.names[actor_id] = account[0]
                registered.add(actor_id)
            elif actor_id not in registered:
                raise ValueError("Journal command before account registration")
            elif kind == "action":
                if action not in MULTI_ACTIONS:
                    raise ValueError("Forbidden journal command")
                self.world.execute(actor_id, action, params, self._engine_id(
                    actor_id, request_id))
            elif kind == "advance":
                minutes = params.get("minutes")
                if type(minutes) is not int or not 1 <= minutes <= ADVANCE_LIMIT:
                    raise ValueError("Invalid journal time advancement")
                self.world.advance(minutes)
            else:
                raise ValueError("Invalid journal kind")
        self.world.assert_invariants()
        if self.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] != len(registered):
            raise ValueError("Account and world registration journal differ")

    @staticmethod
    def _engine_id(actor_id: str, request_id: str) -> str:
        return hashlib.sha256((actor_id + ":" + request_id).encode("utf-8")).hexdigest()

    def _begin(self):
        self.db.execute("BEGIN IMMEDIATE")

    def _tx(self, action):
        """Both SQL persistence and world mutation succeed, or neither does."""
        with self._lock:
            previous = deepcopy(self.world.state)
            self._begin()
            try:
                result = action()
                self.world.assert_invariants()
                self.db.execute("COMMIT")
                return result
            except BaseException:
                self.db.execute("ROLLBACK")
                self.world.state = previous
                raise

    @staticmethod
    def _validate_registration(username, password, display_name):
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

    def register(self, username, password, display_name):
        username, display_name = self._validate_registration(
            username, password, display_name)
        salt = secrets.token_bytes(16)
        hashed = _password_hash(password, salt)
        actor_id = "player:" + uuid.uuid4().hex
        def perform():
            if self.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] >= MAX_ACCOUNTS:
                raise ActionError("Development account limit reached")
            try:
                self.db.execute(
                    "INSERT INTO accounts(actor_id, username, display_name, salt, "
                    "password_hash, created_at) VALUES(?,?,?,?,?,?)",
                    (actor_id, username, display_name, salt, hashed, int(time.time())))
            except sqlite3.IntegrityError:
                raise ActionError("Username or character name is already taken") from None
            self._join_actor(actor_id)
            self.names[actor_id] = display_name
            self.db.execute("INSERT INTO world_journal(kind, actor_id, payload) "
                            "VALUES('join', ?, '{}')", (actor_id,))
            return actor_id
        try:
            return self._tx(perform)
        except Exception:
            self.names.pop(actor_id, None)
            raise

    def login(self, username: str, password: str):
        # Uniform error for missing usernames and bad passwords.
        if (not isinstance(username, str) or not isinstance(password, str)
                or len(username) > 24 or len(password) > 128):
            raise AuthError("Invalid username or password")
        normalized = username.lower()
        with self._lock:
            row = self.db.execute(
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
                self.db.execute("UPDATE accounts SET failed_logins=?, blocked_until=? "
                                "WHERE actor_id=?", (failed, lockout, actor_id))
                raise AuthError("Invalid username or password")
            self.db.execute("UPDATE accounts SET failed_logins=0, blocked_until=0 "
                            "WHERE actor_id=?", (actor_id,))
            return self._issue_session(actor_id)

    def register_and_login(self, username, password, display_name):
        actor_id = self.register(username, password, display_name)
        with self._lock:
            return self._issue_session(actor_id)

    def _issue_session(self, actor_id: str):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        with self._lock:
            self.db.execute(
                "INSERT INTO sessions(digest, actor_id, csrf, expires) VALUES(?,?,?,?)",
                (_digest(token), actor_id, csrf, int(time.time()) + SESSION_SECONDS))
        return token, csrf

    def identity(self, token: str | None) -> Identity | None:
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            return None
        with self._lock:
            row = self.db.execute(
                "SELECT a.actor_id, a.username, a.display_name, s.csrf "
                "FROM sessions s JOIN accounts a ON a.actor_id=s.actor_id "
                "WHERE s.digest=? AND s.expires>?",
                (_digest(token), int(time.time()))).fetchone()
        return Identity(*row) if row else None

    def logout(self, token: str):
        with self._lock:
            self.db.execute("DELETE FROM sessions WHERE digest=?", (_digest(token),))

    def _count_journal(self):
        if self.db.execute("SELECT COUNT(*) FROM world_journal").fetchone()[0] >= MAX_JOURNAL:
            raise ActionError("Development command journal is full")

    def _existing_command(self, actor_id: str, request_id: str, kind: str,
                          action: str | None, payload: str):
        return self.db.execute(
            "SELECT kind, action, payload, result_json FROM world_journal "
            "WHERE actor_id=? AND request_id=?", (actor_id, request_id)).fetchone()

    def _run(self, actor_id: str, kind: str, name: str | None,
             params: dict, request_id: str):
        if (not isinstance(request_id, str) or not 1 <= len(request_id) <= 80
                or not isinstance(params, dict)):
            raise ActionError("Invalid command")
        payload = _canonical(params)
        if len(payload) > 8192:
            raise ActionError("Command exceeds size limit")
        def perform():
            if actor_id not in self.names:
                raise AuthError("Unknown player account")
            existing = self._existing_command(actor_id, request_id, kind, name, payload)
            if existing:
                prev_kind, prev_action, prev_payload, prev_result = existing
                if (prev_kind, prev_action, prev_payload) != (kind, name, payload):
                    raise ActionError("Request ID was reused with different parameters")
                return json.loads(prev_result)
            self._count_journal()
            if kind == "action":
                if name not in MULTI_ACTIONS:
                    raise ActionError("Unavailable multiplayer action")
                outcome = self.world.execute(actor_id, name, params,
                                             self._engine_id(actor_id, request_id))
            elif kind == "advance":
                if type(params.get("minutes")) is not int or set(params) != {"minutes"} or not (
                        1 <= params["minutes"] <= ADVANCE_LIMIT):
                    raise ActionError("Time advancement must be 1–1440 minutes")
                if self.world.state.duels:
                    raise ActionError("Finish active combat before advancing world time")
                self.world.advance(params["minutes"])
                outcome = None
            else:
                raise ActionError("Unknown command kind")
            encoded_result = _canonical(_jsonable(outcome))
            self.db.execute(
                "INSERT INTO world_journal(kind,actor_id,action,payload,request_id,result_json) "
                "VALUES(?,?,?,?,?,?)",
                (kind, actor_id, name, payload, request_id, encoded_result))
            return json.loads(encoded_result)
        return self._tx(perform)

    def action(self, actor_id: str, name: str, params: dict, request_id: str):
        return self._run(actor_id, "action", name, params, request_id)

    def advance(self, actor_id: str, minutes: int, request_id: str):
        return self._run(actor_id, "advance", None, {"minutes": minutes}, request_id)

    def snapshot(self, actor_id: str):
        with self._lock:
            if actor_id not in self.names:
                raise AuthError("Unknown account")
            result = world_snapshot(self.world, actor_id, self.names[actor_id],
                                    self.npc_names, self.names, {}, True)
            result["trades"] = self.world.trades_system.list_for(actor_id)
            return result
