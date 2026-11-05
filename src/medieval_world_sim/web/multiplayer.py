"""Single-process, localhost-only multi-account development backend.

Authenticates individual users against SQLite, ties sessions to immutable actor
IDs, and commits a shared-world command journal in the *same* SQLite transaction
as the account operation. This is a development bridge, not an internet-ready
multiplayer host or a substitute for a row-locked production database.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import random
import secrets
import sqlite3
import threading
import time

from ..catalog import CITIES
from ..core.engine import WorldEngine
from ..core.commands import MULTIPLAYER_ACTIONS
from ..core.entities import Actor
from ..errors import ActionError
from ..systems.cooldowns import remaining
from .session import (GameSession, NPC_NAMES, START_CITY, LEGACY_START_CITY, INITIAL_GOLD,
                      ADVANCE_LIMIT, UI_ACTIONS, world_snapshot)
from . import social, accounts, journal, ledger, checkpoint
from .accounts import (AuthError, Identity, _digest, _password_hash,
                       MAX_ACCOUNTS, INVITE_VALID_SECONDS, MAX_INVITES_PER_BATCH,
                       SESSION_SECONDS, PASSWORD_N, PASSWORD_R, PASSWORD_P,
                       MAX_FAILED_LOGINS, LOGIN_COOLDOWN, MAX_NEW_ACCOUNTS_PER_DAY)

# Deliberately bounded until rate limiting, moderation and deployment hardening
# have been reviewed in a dedicated public-server milestone.
MAX_JOURNAL = 20000
MAX_ACCOUNT_COMMANDS_PER_DAY = 400
MAX_CHAT_COMMANDS_PER_DAY = 100
MAX_GLOBAL_COMMANDS_PER_DAY = 4000
# Real identities, not a shared access code, are necessary but not sufficient
# for public hosting. Keep this entire mode loopback-only.
# Legacy public alias; multiplayer exposure is declared per command.
MULTI_ACTIONS = MULTIPLAYER_ACTIONS


def _jsonable(value):
    return asdict(value) if is_dataclass(value) else value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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
        # The cache stores strictly actor-scoped activity at a committed
        # journal revision; presence changes are overlaid on fresh row copies.
        # It is non-durable and rebuilt after every process restart.
        self._live_activity_cache = {}
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

    def create_checkpoint(self) -> int | None:
        """Operator-only durable checkpoint; never expose via player HTTP."""
        with self._lock:
            self.world.assert_invariants()
            ledger.verify(self)
            self.db.execute("BEGIN IMMEDIATE")
            try:
                seq = checkpoint.save(self, force=True)
                self.db.execute("COMMIT")
                return seq
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def _create_schema(self):
        """Create and migrate the local SQLite journal schema."""
        journal.create_schema(self)

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
        """Replay the existing SQLite journal into the authoritative world."""
        journal.load_world(self)

    @staticmethod
    def _engine_id(actor_id: str, request_id: str) -> str:
        return hashlib.sha256((actor_id + ":" + request_id).encode("utf-8")).hexdigest()

    def _begin(self):
        self.db.execute("BEGIN IMMEDIATE")

    def _tx(self, action):
        """Atomically commit SQL and world state under a single rollback owner.

        Inspect the journal revision BEFORE committing. A post-commit query
        failure must never trigger in-memory rollback of already-durable gold,
        gear or escrow mutations.
        """
        with self._lock:
            previous = deepcopy(self.world.state)
            previous_event_times = dict(self.event_times)
            previous_clock_anchor = self._clock_anchor
            # Only the outer durable transaction may elide the nested
            # WorldEngine.atomic_action rollback copy. We still restore
            # the complete world on every exception, including SQL errors.
            if getattr(self.world, "_durable_tx_owns_rollback", False):
                raise RuntimeError("Nested multiplayer durable transaction")
            self._begin()
            self.world._durable_tx_owns_rollback = True
            try:
                result = action()
                self.world.assert_invariants()
                # The journal, durable receipts and current asset ownership
                # commit together, or all roll back with the world state.
                ledger.persist(self)
                checkpoint.save(self)
                # No database reads or changes should be needed after COMMIT.
                revision = self.db.execute(
                    "SELECT COUNT(*) FROM world_journal").fetchone()[0]
                self.db.execute("COMMIT")
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
            finally:
                self.world._durable_tx_owns_rollback = False
            # Notification is deliberately outside the rollback handler:
            # committed SQLite transactions cannot be undone in memory.
            if revision != self._journal_count:
                self._journal_count = revision
                self._revision += 1
                self._activity_changed.notify_all()
            return result

    @staticmethod
    def _validate_registration(username, password, display_name):
        return accounts.validate_registration(username, password, display_name)

    def issue_invites(self, count: int = 1) -> list[str]:
        return accounts.issue_invites(self, count)

    def register(self, username, password, display_name, invite: str | None = None):
        return accounts.register(self, username, password, display_name, invite, _canonical)

    def login(self, username: str, password: str):
        return accounts.login(self, username, password)

    def register_and_login(self, username, password, display_name,
                           invite: str | None = None):
        return accounts.register_and_login(self, username, password, display_name, invite)

    def _issue_session(self, actor_id: str):
        return accounts._issue_session(self, actor_id)

    def identity(self, token: str | None) -> Identity | None:
        return accounts.identity(self, token)

    def logout(self, token: str):
        return accounts.logout(self, token)

    def _count_journal(self):
        if self.db.execute("SELECT COUNT(*) FROM world_journal").fetchone()[0] >= MAX_JOURNAL:
            raise ActionError("Development command journal is full")

    def _existing_command(self, actor_id: str, request_id: str, kind: str,
                          action: str | None, payload: str):
        return self.db.execute(
            "SELECT kind, action, payload, result_json FROM durable_receipts "
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
        # A committed retry is a read-only receipt lookup. Check under the
        # same serialized world lock before allocating a rollback snapshot.
        # The transaction repeats this check, retaining race protection.
        with self._lock:
            if actor_id not in self.names:
                raise AuthError("Unknown player account")
            prior = self._existing_command(actor_id, request_id, kind, name, payload)
            if prior:
                prev_kind, prev_action, prev_payload, prev_result = prior
                if (prev_kind, prev_action, prev_payload) != (kind, name, payload):
                    raise ActionError("Request ID was reused with different parameters")
                return json.loads(prev_result)
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
        return social.presence_state(self, actor_id, now)

    def _refresh_presence(self) -> None:
        social.refresh_presence(self)

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
        social.annotate_presence(self, projection)

    def _social_view(self, actor_id: str, projection: dict | None = None) -> dict:
        return social.social_view(self, actor_id, projection)

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
