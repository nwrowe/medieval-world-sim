"""Durable SQLite schema evolution and replay of the shared multiplayer world.

This module owns the original command journal schema and historical replay.
The asset ledger and checkpoint modules own their additional tables and
recovery verification. New mechanics must retain versioned replay metadata.
No credentials, HTTP transport or client-generated world-time mutations here.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
import json
import secrets
import time

from ..core.commands import MULTIPLAYER_ACTIONS
from .session import ADVANCE_LIMIT, LEGACY_START_CITY, START_CITY
from . import ledger, checkpoint, npc_runtime

if TYPE_CHECKING:
    from .multiplayer import MultiplayerGame


# Preserve the existing action allowlist for replay; newly forbidden actions
# must remain readable through an explicit historical compatibility rule.
MULTI_ACTIONS = MULTIPLAYER_ACTIONS


def create_schema(game: MultiplayerGame) -> None:
    game.db.executescript("""
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
    columns = {column[1] for column in game.db.execute(
        "PRAGMA table_info(world_journal)")}
    if "recorded_at" not in columns:
        game.db.execute("ALTER TABLE world_journal ADD COLUMN recorded_at TEXT")
    if "flee_success" not in columns:
        game.db.execute("ALTER TABLE world_journal ADD COLUMN flee_success INTEGER")
    if "secure_roll" not in columns:
        game.db.execute("ALTER TABLE world_journal ADD COLUMN secure_roll INTEGER")
    if "server_clock" not in columns:
        game.db.execute("ALTER TABLE world_journal ADD COLUMN server_clock INTEGER")
    if "xp_version" not in columns:
        # Historic magic training must replay without retroactive level XP.
        game.db.execute("ALTER TABLE world_journal "
                        "ADD COLUMN xp_version INTEGER NOT NULL DEFAULT 1")
    if "regen_version" not in columns:
        # Existing advances replay with the original health regen rule.
        game.db.execute("ALTER TABLE world_journal "
                        "ADD COLUMN regen_version INTEGER NOT NULL DEFAULT 1")
    # Keep RNG secret out of public API responses and source-controlled seed.
    # Existing journals replay old results with their historical RNG; only
    # newly committed actions opt in to the keyed outcome algorithm.
    game.db.execute(
        "INSERT OR IGNORE INTO world_meta(name,value) VALUES('rng_key', ?)",
        (secrets.token_bytes(32),))
    game.db.execute(
        "CREATE INDEX IF NOT EXISTS journal_account_timestamp "
        "ON world_journal(actor_id,recorded_at)")
    game.db.execute(
        "CREATE INDEX IF NOT EXISTS journal_timestamp "
        "ON world_journal(recorded_at)")
    game._rng_key = game.db.execute(
        "SELECT value FROM world_meta WHERE name='rng_key'").fetchone()[0]
    game.db.execute(
        "INSERT OR IGNORE INTO world_meta(name,value) VALUES('clock_anchor', ?)",
        (str(int(time.time())).encode(),))
    game._clock_anchor = int(game.db.execute(
        "SELECT value FROM world_meta WHERE name='clock_anchor'").fetchone()[0])
    ledger.create_schema(game)
    checkpoint.create_schema(game)
    npc_runtime.create_schema(game)


def load_world(game: MultiplayerGame) -> None:
    game.world = game._seed_world()
    game.names = {}
    game.event_times = {}
    # A checkpoint restores the owned world and account projection; replay
    # only rows committed after that exact journal sequence.
    restored_seq = checkpoint.restore_latest(game)
    registered = set(game.names)
    rows = game.db.execute(
        "SELECT seq, kind, actor_id, action, payload, request_id, recorded_at, "
        "flee_success, secure_roll, server_clock, regen_version, xp_version "
        "FROM world_journal WHERE seq>? ORDER BY seq", (restored_seq,)).fetchall()
    for (seq, kind, actor_id, action, payload, request_id, recorded_at,
         flee_success, secure_roll, server_clock, regen_version, xp_version) in rows:
        if xp_version not in (1, 2):
            raise ValueError("Invalid recorded experience ruleset")
        params = json.loads(payload)
        prior_events = len(game.world.events)
        if kind == "join":
            if actor_id in registered:
                raise ValueError("Repeated registered actor")
            account = game.db.execute(
                "SELECT display_name FROM accounts WHERE actor_id=?",
                (actor_id,)).fetchone()
            if account is None:
                raise ValueError("Registered actor has no account")
            city = params.get("city", LEGACY_START_CITY)
            if city not in (LEGACY_START_CITY, START_CITY):
                raise ValueError("Invalid registered starting city")
            game._join_actor(actor_id, city, params.get("lineage"))
            game.names[actor_id] = account[0]
            registered.add(actor_id)
        elif actor_id not in registered:
            raise ValueError("Journal command before account registration")
        elif kind == "action":
            if action not in MULTI_ACTIONS:
                raise ValueError("Forbidden journal command")
            if action == "flee_duel":
                if flee_success is None:
                    game.world._legacy_flee_rules = True
                elif flee_success not in (0, 1):
                    raise ValueError("Invalid saved flee coin flip")
                else:
                    game.world._flee_success = bool(flee_success)
            if secure_roll not in (None, 0, 1):
                raise ValueError("Invalid recorded RNG policy")
            game.world._private_rng_key = game._rng_key if secure_roll == 1 else None
            game.world._legacy_magic_leveling_rules = xp_version == 1
            try:
                game.world.execute(actor_id, action, params, game._engine_id(
                    actor_id, request_id))
            finally:
                game.world._legacy_flee_rules = False
                game.world._flee_success = None
                game.world._private_rng_key = None
        elif kind == "advance":
            minutes = params.get("minutes")
            if (type(minutes) is not int or not 1 <= minutes <= ADVANCE_LIMIT
                    or server_clock not in (None, 0, 1)
                    or regen_version not in (1, 2, 3)):
                raise ValueError("Invalid journal time advancement")
            game.world._health_regen_version = regen_version
            try:
                game.world.advance(minutes)
            finally:
                game.world._health_regen_version = 3
        else:
            raise ValueError("Invalid journal kind")
        if recorded_at is not None:
            try:
                stamp = datetime.fromisoformat(recorded_at)
                if stamp.tzinfo is None:
                    raise ValueError("Timezone required")
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid saved action timestamp") from exc
            for event in game.world.events[prior_events:]:
                game.event_times[event.event_id] = recorded_at
    game.world.assert_invariants()
    if game.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] != len(registered):
        raise ValueError("Account and world registration journal differ")
    # The stream revision must remain stable after restart, as game
    # snapshots and browser reconnects use it to reject stale updates.
    count = game.db.execute("SELECT COUNT(*) FROM world_journal").fetchone()[0]
    game._journal_count = count
    game._revision = count
    ledger.initialize_or_verify(game)

