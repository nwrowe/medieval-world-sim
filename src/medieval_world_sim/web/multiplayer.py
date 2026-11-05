"""Single-process, localhost-only multi-account development backend.

Authenticates individual users against SQLite, ties sessions to immutable actor
IDs, and commits a shared-world command journal in the *same* SQLite transaction
as the account operation. This is a development bridge, not an internet-ready
multiplayer host or a substitute for a row-locked production database.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass, dataclass
from datetime import datetime, timezone, timedelta
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
from ..systems.cooldowns import remaining
from .session import (GameSession, NPC_NAMES, START_CITY, LEGACY_START_CITY, INITIAL_GOLD,
                      ADVANCE_LIMIT, UI_ACTIONS, world_snapshot)

# Deliberately bounded until rate limiting, moderation and deployment hardening
# have been reviewed in a dedicated public-server milestone.
MAX_ACCOUNTS = 100
INVITE_VALID_SECONDS = 7 * 86400
MAX_INVITES_PER_BATCH = 25
SESSION_SECONDS = 86400
PASSWORD_N = 1 << 15
PASSWORD_R = 8
PASSWORD_P = 1
MAX_FAILED_LOGINS = 6
LOGIN_COOLDOWN = 900
MAX_JOURNAL = 20000
MAX_NEW_ACCOUNTS_PER_DAY = 24
MAX_ACCOUNT_COMMANDS_PER_DAY = 400
MAX_CHAT_COMMANDS_PER_DAY = 100
MAX_GLOBAL_COMMANDS_PER_DAY = 4000
# Real identities, not a shared access code, are necessary but not sufficient
# for public hosting. Keep this entire mode loopback-only.
MULTI_ACTIONS = UI_ACTIONS - {"enroll_course"} | {
    "propose_trade", "accept_trade", "close_trade", "pvp_strike",
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
                          n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P, dklen=32,
                          maxmem=64 * 1024 * 1024)


class MultiplayerGame:
    def __init__(self, db_path: str | Path, *,
                 require_invites: bool = True,
                 dev_fast_forward: bool = False):
        self.require_invites = require_invites
        self.dev_fast_forward = dev_fast_forward
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._activity_changed = threading.Condition(self._lock)
        self._revision = 0
        self._journal_count = 0
        # Presence is ephemeral: never stored in the replay journal or
        # confused with the game-world clock.
        self._presence = {}
        self._presence_status = {}
        self._event_slots = threading.BoundedSemaphore(20)
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
            if self.dev_fast_forward:
                # The explicit local test override uses a manually accelerated
                # timeline. Do not also accrue elapsed wall time while it is on:
                # otherwise switching to secure mode would count time twice.
                self._clock_anchor = int(time.time())
                self.db.execute(
                    "UPDATE world_meta SET value=? WHERE name='clock_anchor'",
                    (str(self._clock_anchor).encode(),))
        except Exception:
            self.db.close()
            raise

    def close(self):
        with self._lock:
            self.db.close()

    def _create_schema(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS registration_invites(
                digest BLOB PRIMARY KEY,
                expires INTEGER NOT NULL,
                redeemed_by TEXT UNIQUE REFERENCES accounts(actor_id)
            );
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
            CREATE TABLE IF NOT EXISTS world_meta(
                name TEXT PRIMARY KEY,
                value BLOB NOT NULL
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
        # Previous multi-account databases lack an event wall-clock column.
        # Add it without rewriting or inventing timestamps for older rows.
        columns = {column[1] for column in self.db.execute(
            "PRAGMA table_info(world_journal)")}
        if "recorded_at" not in columns:
            self.db.execute("ALTER TABLE world_journal ADD COLUMN recorded_at TEXT")
        if "flee_success" not in columns:
            self.db.execute("ALTER TABLE world_journal ADD COLUMN flee_success INTEGER")
        if "secure_roll" not in columns:
            self.db.execute("ALTER TABLE world_journal ADD COLUMN secure_roll INTEGER")
        if "server_clock" not in columns:
            self.db.execute("ALTER TABLE world_journal ADD COLUMN server_clock INTEGER")
        if "regen_version" not in columns:
            # Existing advances replay with the original health regen rule.
            self.db.execute("ALTER TABLE world_journal "
                            "ADD COLUMN regen_version INTEGER NOT NULL DEFAULT 1")
        # Keep RNG secret out of public API responses and source-controlled seed.
        # Existing journals replay old results with their historical RNG; only
        # newly committed actions opt in to the keyed outcome algorithm.
        self.db.execute(
            "INSERT OR IGNORE INTO world_meta(name,value) VALUES('rng_key', ?)",
            (secrets.token_bytes(32),))
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS journal_account_timestamp "
            "ON world_journal(actor_id,recorded_at)")
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS journal_timestamp "
            "ON world_journal(recorded_at)")
        self._rng_key = self.db.execute(
            "SELECT value FROM world_meta WHERE name='rng_key'").fetchone()[0]
        self.db.execute(
            "INSERT OR IGNORE INTO world_meta(name,value) VALUES('clock_anchor', ?)",
            (str(int(time.time())).encode(),))
        self._clock_anchor = int(self.db.execute(
            "SELECT value FROM world_meta WHERE name='clock_anchor'").fetchone()[0])

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

    def _join_actor(self, actor_id: str, city: str = LEGACY_START_CITY):
        if actor_id in self.world.actors:
            raise ValueError("Duplicate player registration in world")
        self.world.actors[actor_id] = Actor(actor_id, "human", city=city,
                                            gold=INITIAL_GOLD)
        self.world.state.initial_gold += INITIAL_GOLD
        self.world.assert_invariants()

    def _load_world(self):
        self.world = self._seed_world()
        self.names = {}
        self.event_times = {}
        registered = set()
        rows = self.db.execute(
            "SELECT kind, actor_id, action, payload, request_id, recorded_at, "
            "flee_success, secure_roll, server_clock, regen_version "
            "FROM world_journal ORDER BY seq").fetchall()
        for (kind, actor_id, action, payload, request_id, recorded_at,
             flee_success, secure_roll, server_clock, regen_version) in rows:
            params = json.loads(payload)
            prior_events = len(self.world.events)
            if kind == "join":
                if actor_id in registered:
                    raise ValueError("Repeated registered actor")
                account = self.db.execute(
                    "SELECT display_name FROM accounts WHERE actor_id=?",
                    (actor_id,)).fetchone()
                if account is None:
                    raise ValueError("Registered actor has no account")
                city = params.get("city", LEGACY_START_CITY)
                if city not in (LEGACY_START_CITY, START_CITY):
                    raise ValueError("Invalid registered starting city")
                self._join_actor(actor_id, city)
                self.names[actor_id] = account[0]
                registered.add(actor_id)
            elif actor_id not in registered:
                raise ValueError("Journal command before account registration")
            elif kind == "action":
                if action not in MULTI_ACTIONS:
                    raise ValueError("Forbidden journal command")
                if action == "flee_duel":
                    if flee_success is None:
                        self.world._legacy_flee_rules = True
                    elif flee_success not in (0, 1):
                        raise ValueError("Invalid saved flee coin flip")
                    else:
                        self.world._flee_success = bool(flee_success)
                if secure_roll not in (None, 0, 1):
                    raise ValueError("Invalid recorded RNG policy")
                self.world._private_rng_key = self._rng_key if secure_roll == 1 else None
                try:
                    self.world.execute(actor_id, action, params, self._engine_id(
                        actor_id, request_id))
                finally:
                    self.world._legacy_flee_rules = False
                    self.world._flee_success = None
                    self.world._private_rng_key = None
            elif kind == "advance":
                minutes = params.get("minutes")
                if (type(minutes) is not int or not 1 <= minutes <= ADVANCE_LIMIT
                        or server_clock not in (None, 0, 1)
                        or regen_version not in (1, 2, 3)):
                    raise ValueError("Invalid journal time advancement")
                self.world._health_regen_version = regen_version
                try:
                    self.world.advance(minutes)
                finally:
                    self.world._health_regen_version = 3
            else:
                raise ValueError("Invalid journal kind")
            if recorded_at is not None:
                try:
                    stamp = datetime.fromisoformat(recorded_at)
                    if stamp.tzinfo is None:
                        raise ValueError("Timezone required")
                except (TypeError, ValueError) as exc:
                    raise ValueError("Invalid saved action timestamp") from exc
                for event in self.world.events[prior_events:]:
                    self.event_times[event.event_id] = recorded_at
        self.world.assert_invariants()
        if self.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] != len(registered):
            raise ValueError("Account and world registration journal differ")
        # The stream revision must remain stable after restart, as game
        # snapshots and browser reconnects use it to reject stale updates.
        self._journal_count = len(rows)
        self._revision = len(rows)

    @staticmethod
    def _engine_id(actor_id: str, request_id: str) -> str:
        return hashlib.sha256((actor_id + ":" + request_id).encode("utf-8")).hexdigest()

    def _begin(self):
        self.db.execute("BEGIN IMMEDIATE")

    def _tx(self, action):
        """Both SQL persistence and world mutation succeed, or neither does."""
        with self._lock:
            previous = deepcopy(self.world.state)
            previous_event_times = dict(self.event_times)
            previous_clock_anchor = self._clock_anchor
            self._begin()
            try:
                result = action()
                self.world.assert_invariants()
                self.db.execute("COMMIT")
                # Deduplicated command retries do not append a journal row:
                # they must not manufacture new activity revisions.
                revision = self.db.execute(
                    "SELECT COUNT(*) FROM world_journal").fetchone()[0]
                if revision != self._journal_count:
                    self._journal_count = revision
                    self._revision += 1
                    self._activity_changed.notify_all()
                return result
            except BaseException:
                try:
                    self.db.execute("ROLLBACK")
                finally:
                    # A storage rollback failure must never leave a mutated,
                    # uncommitted world visible to future requests.
                    self.world.state = previous
                    self.event_times = previous_event_times
                    self._clock_anchor = previous_clock_anchor
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

    def issue_invites(self, count: int = 1) -> list[str]:
        """Operator-only administration; never expose through the HTTP server."""
        if type(count) is not int or not 1 <= count <= MAX_INVITES_PER_BATCH:
            raise ValueError("Invalid invitation batch size")
        codes = [secrets.token_urlsafe(24) for _ in range(count)]
        expiry = int(time.time()) + INVITE_VALID_SECONDS
        with self._lock:
            for code in codes:
                self.db.execute(
                    "INSERT INTO registration_invites(digest,expires) VALUES(?,?)",
                    (_digest(code), expiry))
        return codes

    def register(self, username, password, display_name, invite: str | None = None):
        username, display_name = self._validate_registration(
            username, password, display_name)
        salt = secrets.token_bytes(16)
        hashed = _password_hash(password, salt)
        actor_id = "player:" + uuid.uuid4().hex
        def perform():
            if self.db.execute(
                "SELECT COUNT(*) FROM accounts WHERE created_at>=?",
                (int(time.time()) - 86400,)).fetchone()[0] >= MAX_NEW_ACCOUNTS_PER_DAY:
                raise ActionError("Daily registration capacity reached")
            if self.require_invites:
                if not isinstance(invite, str) or not 20 <= len(invite) <= 128:
                    raise ActionError("Valid invitation required")
                row = self.db.execute(
                    "SELECT redeemed_by,expires FROM registration_invites WHERE digest=?",
                    (_digest(invite),)).fetchone()
                if row is None or row[0] is not None or row[1] <= int(time.time()):
                    raise ActionError("Invitation invalid, expired, or already used")
            if self.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] >= MAX_ACCOUNTS:
                raise ActionError("Development account limit reached")
            try:
                self.db.execute(
                    "INSERT INTO accounts(actor_id, username, display_name, salt, "
                    "password_hash, created_at) VALUES(?,?,?,?,?,?)",
                    (actor_id, username, display_name, salt, hashed, int(time.time())))
            except sqlite3.IntegrityError:
                raise ActionError("Username or character name is already taken") from None
            self._join_actor(actor_id, START_CITY)
            self.names[actor_id] = display_name
            if self.require_invites:
                self.db.execute(
                    "UPDATE registration_invites SET redeemed_by=? "
                    "WHERE digest=? AND redeemed_by IS NULL",
                    (actor_id, _digest(invite)))
            # New worlds may be idle for days before their first account joins.
            # Start the wall-clock timeline at the first actual registration.
            if len(self.names) == 1:
                self._clock_anchor = int(time.time())
                self.db.execute(
                    "UPDATE world_meta SET value=? WHERE name='clock_anchor'",
                    (str(self._clock_anchor).encode(),))
            self.db.execute(
                "INSERT INTO world_journal(kind, actor_id, payload, recorded_at) "
                "VALUES('join', ?, ?, ?)",
                (actor_id, _canonical({"city": START_CITY}),
                 datetime.now(timezone.utc).isoformat()))
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

    def register_and_login(self, username, password, display_name,
                           invite: str | None = None):
        actor_id = self.register(username, password, display_name, invite)
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

    def _tick_world_clock(self) -> None:
        """Reconcile trusted server wall time in capped, replayable increments.

        World time may be advanced by the server's own clock, never by an
        untrusted HTTP request. The development override retains historical
        fast-forward behavior so existing demos/tests can move time quickly.
        """
        if self.dev_fast_forward:
            return
        with self._lock:
            if not self.names:
                return
            now = int(time.time())
            minutes = min(max(0, now - self._clock_anchor) // 60, ADVANCE_LIMIT)
            if minutes == 0:
                return
            old_anchor = self._clock_anchor
            new_anchor = old_anchor + minutes * 60
            actor_id = next(iter(self.names))
            prior_events = len(self.world.events)
            timestamp = datetime.now(timezone.utc).isoformat()
            def perform():
                self._count_journal()
                self.world.advance(minutes)
                self.db.execute(
                    "INSERT INTO world_journal(kind,actor_id,payload,request_id,"
                    "result_json,recorded_at,server_clock,regen_version) "
                    "VALUES('advance',?,?,?,?,?,1,3)",
                    (actor_id, _canonical({"minutes": minutes}),
                     f"__clock__:{old_anchor}", "null", timestamp))
                self.db.execute(
                    "UPDATE world_meta SET value=? WHERE name='clock_anchor'",
                    (str(new_anchor).encode(),))
                for event in self.world.events[prior_events:]:
                    self.event_times[event.event_id] = timestamp
            self._tx(perform)
            self._clock_anchor = new_anchor

    def _check_journal_budget(self, actor_id: str, name: str | None) -> None:
        """Limit journal exhaustion using server timestamps, not user time."""
        since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        own = self.db.execute(
            "SELECT COUNT(*) FROM world_journal "
            "WHERE actor_id=? AND recorded_at>=? AND kind IN ('action','advance') "
            "AND COALESCE(server_clock,0)=0",
            (actor_id, since)).fetchone()[0]
        if own >= MAX_ACCOUNT_COMMANDS_PER_DAY:
            raise ActionError("Daily account action limit reached")
        world = self.db.execute(
            "SELECT COUNT(*) FROM world_journal "
            "WHERE recorded_at>=? AND kind IN ('action','advance') "
            "AND COALESCE(server_clock,0)=0", (since,)).fetchone()[0]
        if world >= MAX_GLOBAL_COMMANDS_PER_DAY:
            raise ActionError("Daily shared-world command limit reached")
        if name == "send_chat":
            chat = self.db.execute(
                "SELECT COUNT(*) FROM world_journal WHERE actor_id=? "
                "AND action='send_chat' AND recorded_at>=?",
                (actor_id, since)).fetchone()[0]
            if chat >= MAX_CHAT_COMMANDS_PER_DAY:
                raise ActionError("Daily chat limit reached")

    def _run(self, actor_id: str, kind: str, name: str | None,
             params: dict, request_id: str):
        if (not isinstance(request_id, str) or not 1 <= len(request_id) <= 80
                or request_id.startswith("__clock__:")
                or not isinstance(params, dict)):
            raise ActionError("Invalid command")
        self._tick_world_clock()
        if kind == "advance" and not self.dev_fast_forward:
            raise ActionError("World time advances automatically; manual fast-forward is disabled")
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
            self._check_journal_budget(actor_id, name)
            prior_events = len(self.world.events)
            recorded_at = datetime.now(timezone.utc).isoformat()
            flee_success = None
            secure_roll = 0
            if kind == "action":
                if name == "pvp_strike":
                    # Keep historical journal replay compatible, but prevent
                    # new clients bypassing the shared turn-based duel rules.
                    raise ActionError("Use start_duel for player combat")
                if name not in MULTI_ACTIONS:
                    raise ActionError("Unavailable multiplayer action")
                if name == "flee_duel":
                    flee_success = secrets.randbits(1)
                    self.world._flee_success = bool(flee_success)
                if name in ("practice_magic", "race_horse"):
                    secure_roll = 1
                    self.world._private_rng_key = self._rng_key
                try:
                    outcome = self.world.execute(actor_id, name, params,
                                                 self._engine_id(actor_id, request_id))
                finally:
                    self.world._flee_success = None
                    self.world._private_rng_key = None
            elif kind == "advance":
                if type(params.get("minutes")) is not int or set(params) != {"minutes"} or not (
                        1 <= params["minutes"] <= ADVANCE_LIMIT):
                    raise ActionError("Time advancement must be 1–1440 minutes")
                # An attacker must not freeze the entire shared-world clock by
                # opening a PvP duel and going offline. NPC turn-based fights
                # retain their historical time-advance restriction.
                if any(self.world.actors[duel.defender_id].kind == "npc"
                       for duel in self.world.state.duels.values()):
                    raise ActionError("Finish active NPC combat before advancing world time")
                self.world.advance(params["minutes"])
                outcome = None
            else:
                raise ActionError("Unknown command kind")
            encoded_result = _canonical(_jsonable(outcome))
            self.db.execute(
                "INSERT INTO world_journal("
                "kind,actor_id,action,payload,request_id,result_json,recorded_at,"
                "flee_success,secure_roll,regen_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (kind, actor_id, name, payload, request_id,
                 encoded_result, recorded_at, flee_success, secure_roll,
                 3 if kind == "advance" else 1))
            for event in self.world.events[prior_events:]:
                self.event_times[event.event_id] = recorded_at
            return json.loads(encoded_result)
        return self._tx(perform)

    def action(self, actor_id: str, name: str, params: dict, request_id: str):
        return self._run(actor_id, "action", name, params, request_id)

    def advance(self, actor_id: str, minutes: int, request_id: str):
        return self._run(actor_id, "advance", None, {"minutes": minutes}, request_id)

    def _presence_state(self, actor_id: str, now: float) -> str:
        entry = self._presence.get(actor_id)
        if entry is None or now - entry[0] >= 90:
            return "offline"
        return "active" if entry[1] else "away"

    def _refresh_presence(self) -> None:
        now = time.monotonic()
        changed = False
        for actor_id in self.names:
            current = self._presence_state(actor_id, now)
            if self._presence_status.get(actor_id, "offline") != current:
                self._presence_status[actor_id] = current
                changed = True
        if changed:
            self._revision += 1
            self._activity_changed.notify_all()

    def presence_ping(self, actor_id: str, visible: bool) -> None:
        """A session-verified browser reports foreground/hidden every 25 sec."""
        if type(visible) is not bool:
            raise ActionError("Invalid presence visibility")
        with self._activity_changed:
            if actor_id not in self.names:
                raise AuthError("Unknown account")
            self._presence[actor_id] = (time.monotonic(), visible)
            self._refresh_presence()

    def presence_logout(self, actor_id: str) -> None:
        with self._activity_changed:
            self._presence.pop(actor_id, None)
            self._refresh_presence()

    def _annotate_presence(self, projection: dict) -> None:
        self._refresh_presence()
        for user in projection["users"]:
            if user["kind"] == "human":
                user["presence"] = self._presence_status.get(user["id"], "offline")

    def _social_view(self, actor_id: str, projection: dict | None = None) -> dict:
        """Account-scoped streaming data; never broadcast raw world state."""
        if projection is None:
            projection = world_snapshot(self.world, actor_id,
                                        self.names[actor_id], self.npc_names,
                                        self.names, self.event_times, True)
        actor = self.world._actor(actor_id)
        self._annotate_presence(projection)
        chat = self.world.chat_system.view(actor_id)
        for channel in chat["channels"]:
            if channel["kind"] == "direct":
                channel["label"] = self.names.get(channel["target"], "Player")
        for message in chat["messages"]:
            message["sender_name"] = self.names.get(
                message["sender"], message["sender"])
        trades = self.world.trades_system.list_for(actor_id)
        for proposal in trades:
            proposal["maker_name"] = self.names.get(proposal["maker"], "Player")
            proposal["recipient_name"] = self.names.get(proposal["recipient"], "Player")
            for side in ("offer", "request"):
                # Offered equipment is visible to the recipient; requested
                # equipment details belong only to the requested owner.
                # A maker must not probe other people's gear by guessing IDs.
                can_inspect = side == "offer" or actor_id == proposal["recipient"]
                proposal[side + "_gear"] = [
                    {"id": gid, "kind": self.world.gear[gid].kind,
                     "quality": self.world.gear[gid].quality,
                     "durability": self.world.gear[gid].durability}
                    for gid in proposal[side]["gear_ids"]
                    if can_inspect and gid in self.world.gear
                ]
        return {
            "actor_id": actor_id, "revision": self._revision,
            "chat": chat, "trades": trades, "minute": self.world.minute,
            "next_world_tick_seconds": self._next_world_tick_seconds(),
            "users": projection["users"], "events": projection["events"],
            "duel": projection["duel"], "last_duel": projection["last_duel"],
            "course_active": self.world.curriculum_system.view(actor_id)["active"],
            "player_status": {
                "hp": actor.hp, "max_hp": actor.max_hp,
                "stamina": actor.stamina, "max_stamina": actor.max_stamina,
                "mana": actor.magic.mana, "max_mana": actor.magic.max_mana,
                "gold": actor.gold, "city": actor.city,
                "defeated_until": actor.defeated_until,
                "health_next_sim_seconds": projection["player"]["health_next_sim_seconds"],
                "stamina_next_sim_seconds": projection["player"]["stamina_next_sim_seconds"],
                "mana_next_sim_seconds": projection["player"]["mana_next_sim_seconds"],
                "destination": actor.destination,
                "arrival_minute": actor.arrival_minute,
                "cooldowns": {
                    name: {"remaining_minutes": remaining(
                        actor, name, self.world.minute), "max_minutes": 1440}
                    for name in ("job", "food", "potion")
                },
            },
        }

    def _next_world_tick_seconds(self) -> int | None:
        if self.dev_fast_forward:
            return None
        return max(1, 60 - min(59, max(0, int(time.time()) - self._clock_anchor)))

    def social_snapshot(self, actor_id: str) -> dict:
        self._tick_world_clock()
        with self._lock:
            if actor_id not in self.names:
                raise AuthError("Unknown account")
            return self._social_view(actor_id)

    def next_activity_revision(self, since: int, timeout: float = 12.0) -> int:
        self._tick_world_clock()
        with self._activity_changed:
            self._refresh_presence()
            if since == self._revision:
                # Wake at the next trusted minute boundary, not up to
                # twelve seconds later, so regen and timers feel live.
                next_tick = self._next_world_tick_seconds()
                self._activity_changed.wait(
                    timeout=min(timeout, next_tick) if next_tick is not None else timeout)
        self._tick_world_clock()
        with self._activity_changed:
            self._refresh_presence()
            return self._revision

    def acquire_event_slot(self) -> bool:
        return self._event_slots.acquire(blocking=False)

    def release_event_slot(self):
        self._event_slots.release()

    def snapshot(self, actor_id: str):
        self._tick_world_clock()
        with self._lock:
            if actor_id not in self.names:
                raise AuthError("Unknown account")
            result = world_snapshot(self.world, actor_id, self.names[actor_id],
                                    self.npc_names, self.names,
                                    self.event_times, True)
            result["actor_id"] = actor_id
            social = self._social_view(actor_id, result)
            result["chat"] = social["chat"]
            result["trades"] = social["trades"]
            result["activity_revision"] = self._revision
            result["next_world_tick_seconds"] = self._next_world_tick_seconds()
            return result
