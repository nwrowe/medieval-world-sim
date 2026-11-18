"""Single current-format SQLite journal and deterministic world recovery.

Old development databases are rejected, not silently migrated. Checkpoints,
durable receipts and the asset ledger remain authoritative for safe restarts.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
import json
import secrets
import time

from ..core.commands import MULTIPLAYER_ACTIONS
from ..catalog import GEOGRAPHY_FINGERPRINT
from .session import ADVANCE_LIMIT, START_CITY
from . import ledger, checkpoint, npc_runtime

if TYPE_CHECKING:
    from .multiplayer import MultiplayerGame


# The same command allowlist applies to writes and current-format replay.
MULTI_ACTIONS = MULTIPLAYER_ACTIONS
BASELINE_REVISION = b"1"


def create_schema(game: MultiplayerGame) -> None:
    # Refuse pre-baseline databases before making changes to their schema.
    existing = game.db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_journal'"
    ).fetchone()
    if existing:
        meta = game.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_meta'"
        ).fetchone()
        revision = (game.db.execute(
            "SELECT value FROM world_meta WHERE name='baseline_revision'").fetchone()
                    if meta else None)
        if revision is None or revision[0] != BASELINE_REVISION:
            raise ValueError("Pre-baseline multiplayer data is unsupported; "
                             "start a new empty database file")
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
            recorded_at TEXT,
            flee_success INTEGER CHECK(flee_success IN (0,1)),
            server_clock INTEGER CHECK(server_clock IN (0,1)),
            UNIQUE(actor_id, request_id)
        );
    """)
    game.db.execute(
        "INSERT OR IGNORE INTO world_meta(name,value) VALUES('baseline_revision',?)",
        (BASELINE_REVISION,))
    # Worlds are intentionally fresh. Never replay an account journal against
    # a silently changed terrain/road/resource snapshot: that can invalidate
    # positions, inventories and player discoveries.
    current = GEOGRAPHY_FINGERPRINT.encode("ascii")
    recorded = game.db.execute(
        "SELECT value FROM world_meta WHERE name='realm_fingerprint'").fetchone()
    if recorded is not None:
        if recorded[0] != current:
            raise ValueError("Realm geography changed; start a fresh database "
                             "or explicitly migrate the authoritative world")
    else:
        active = game.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        journaled = game.db.execute("SELECT COUNT(*) FROM world_journal").fetchone()[0]
        if active or journaled:
            raise ValueError("Existing multiplayer data predates the new geography. "
                             "Use a new database file for the fresh realm.")
        game.db.execute(
            "INSERT INTO world_meta(name,value) VALUES('realm_fingerprint', ?)",
            (current,))
    # A replayed travel command must use the same duration scaling that was
    # active when it committed; otherwise journeys and exploration diverge.
    speed = b"seconds" if game.dev_travel_seconds else b"normal"
    saved_speed = game.db.execute(
        "SELECT value FROM world_meta WHERE name='travel_clock_mode'").fetchone()
    if saved_speed is not None and saved_speed[0] != speed:
        raise ValueError("Travel clock mode changed for this saved realm. "
                         "Use a separate database for --dev-seconds-travel.")
    if saved_speed is None:
        prior_actions = game.db.execute(
            "SELECT COUNT(*) FROM world_journal").fetchone()[0]
        if prior_actions and game.dev_travel_seconds:
            raise ValueError("Cannot enable seconds travel on a database "
                             "with previously recorded normal journeys")
        game.db.execute(
            "INSERT INTO world_meta(name,value) VALUES('travel_clock_mode', ?)",
            (speed,))
    # Existing journal rows were committed under the previous gathering
    # price. Record the last old sequence once, at schema initialization.
    # Fresh databases use zero; all subsequently appended actions use rule 2.
    old_seq = game.db.execute(
        "SELECT COALESCE(MAX(seq),0) FROM world_journal").fetchone()[0]
    game.db.execute(
        "INSERT OR IGNORE INTO world_meta(name,value) VALUES('gather_rule_legacy_end',?)",
        (str(old_seq).encode(),))
    game._legacy_gather_end = int(game.db.execute(
        "SELECT value FROM world_meta WHERE name='gather_rule_legacy_end'"
    ).fetchone()[0])
    # Preserve original site rewards on existing journal rows, even if
    # an old reward exceeded the player's carrying limit.
    game.db.execute(
        "INSERT OR IGNORE INTO world_meta(name,value) VALUES('site_reward_legacy_end',?)",
        (str(old_seq).encode(),))
    game._legacy_site_reward_end = int(game.db.execute(
        "SELECT value FROM world_meta WHERE name='site_reward_legacy_end'"
    ).fetchone()[0])
    # RNG secrets are never returned to clients or committed to source.
    game.db.execute(
        "INSERT OR IGNORE INTO world_meta(name,value) VALUES('rng_key', ?)",
        (secrets.token_bytes(32),))
    game.db.execute(
        "CREATE INDEX IF NOT EXISTS journal_account_timestamp "
        "ON world_journal(actor_id,recorded_at)")
    game.db.execute(
        "CREATE INDEX IF NOT EXISTS journal_timestamp "
        "ON world_journal(recorded_at)")
    # A compact partial index avoids scanning thousands of automatic clock
    # rows whenever checking the lifetime player-command quota.
    game.db.execute(
        "CREATE INDEX IF NOT EXISTS journal_player_command_budget "
        "ON world_journal(seq) WHERE COALESCE(server_clock,0)=0")
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
    # Older join records lack start_mana; replay their original initial
    # capacity, including NPCs, without changing new registrations.
    join_payloads = game.db.execute(
        "SELECT payload FROM world_journal WHERE kind='join'").fetchall()
    old_mana = any("start_mana" not in json.loads(row[0])
                   for row in join_payloads)
    game.world = game._seed_world(old_mana=old_mana)
    game.names = {}
    game.event_times = {}
    # A checkpoint restores the owned world and account projection; replay
    # only rows committed after that exact journal sequence.
    restored_seq = checkpoint.restore_latest(game)
    registered = set(game.names)
    rows = game.db.execute(
        "SELECT seq, kind, actor_id, action, payload, request_id, recorded_at, "
        "flee_success, server_clock "
        "FROM world_journal WHERE seq>? ORDER BY seq", (restored_seq,)).fetchall()
    for (seq, kind, actor_id, action, payload, request_id, recorded_at,
         flee_success, server_clock) in rows:
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
            city = params.get("city")
            if city != START_CITY:
                raise ValueError("Invalid registered starting city")
            game._join_actor(actor_id, city, params.get("lineage"),
                             params.get("start_mana", 100))
            game.names[actor_id] = account[0]
            registered.add(actor_id)
        elif actor_id not in registered:
            raise ValueError("Journal command before account registration")
        elif kind == "action":
            if action not in MULTI_ACTIONS:
                raise ValueError("Forbidden journal command")
            if action == "flee_duel":
                if flee_success not in (0, 1):
                    raise ValueError("Missing saved flee coin flip")
                game.world._flee_success = bool(flee_success)
            elif flee_success is not None:
                raise ValueError("Unexpected saved flee roll")
            game.world._private_rng_key = (
                game._rng_key if action in ("practice_magic", "race_horse", "investigate_site") else None)
            game.world._replay_legacy_wilderness = (
                action == "wilderness_gather" and seq <= game._legacy_gather_end)
            game.world._replay_legacy_site_reward = (
                action == "investigate_site" and seq <= game._legacy_site_reward_end)
            try:
                game.world.execute(actor_id, action, params, game._engine_id(
                    actor_id, request_id))
            finally:
                game.world._replay_legacy_wilderness = False
                game.world._replay_legacy_site_reward = False
                game.world._flee_success = None
                game.world._private_rng_key = None
        elif kind == "advance":
            minutes = params.get("minutes")
            if (type(minutes) is not int or not 1 <= minutes <= ADVANCE_LIMIT
                    or server_clock not in (None, 0, 1)):
                raise ValueError("Invalid journal time advancement")
            game.world.advance(minutes)
            npc_runtime.replay(game, seq)
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

