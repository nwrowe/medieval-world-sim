"""Versioned, non-executable SQLite checkpoints for deterministic world recovery.

Checkpoints are a *derived durability accelerator*, never a replacement for
the committed journal/receipt/asset ledger. A strict allowlist of dataclasses
prevents arbitrary Python object construction from stored payloads.

A checkpoint contains the full world state except in-memory command receipts,
which are independently durable in SQLite. A verified checkpoint is followed
by replay of only its journal tail; the final world must reconcile exactly
against the transactional asset ledger and receipts.
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import TYPE_CHECKING

from ..content.catalog import CitySpec
from ..core.cities import CityState
from ..core.entities import (Actor, Company, Cooldowns, DuelState, HousingState,
                             MagicState, Offer, Progression, TravelState, Vitals,
                             Wage, WorkStats, WorldEvent)
from ..core.state import WorldState
from ..equipment import GearItem
from ..systems.chat import ChatMessage, ChatRoom
from ..systems.curriculum import CourseEnrollment
from ..systems.guilds import Guild, WarRecord
from ..systems.trades import TradeAssets, TradeProposal

if TYPE_CHECKING:
    from .multiplayer import MultiplayerGame

CHECKPOINT_VERSION = 1
CHECKPOINT_INTERVAL = 50
MAX_BYTES = 32 * 1024 * 1024
MAX_DEPTH = 70

_MODEL_CLASSES = (WorldState, Actor, Company, Cooldowns, DuelState,
                  HousingState, MagicState, Offer, Progression, TravelState,
                  Vitals, Wage, WorkStats, WorldEvent, CitySpec, CityState,
                  GearItem, ChatMessage, ChatRoom, CourseEnrollment,
                  Guild, WarRecord, TradeAssets, TradeProposal)
_MODELS = {model.__name__: model for model in _MODEL_CLASSES}
if len(_MODELS) != len(_MODEL_CLASSES):
    raise RuntimeError("Ambiguous world checkpoint model names")


def _encode(value, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("Checkpoint object nesting exceeds safe depth")
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Checkpoint contains nonfinite number")
        return value
    if is_dataclass(value) and type(value) in _MODEL_CLASSES:
        return {"tag": "model", "name": type(value).__name__,
                "values": {f.name: _encode(getattr(value, f.name), depth + 1)
                           for f in fields(value)}}
    if type(value) is list:
        return {"tag": "list", "items": [_encode(x, depth + 1) for x in value]}
    if type(value) is tuple:
        return {"tag": "tuple", "items": [_encode(x, depth + 1) for x in value]}
    if type(value) in (set, frozenset):
        items = [_encode(x, depth + 1) for x in value]
        items.sort(key=lambda v: json.dumps(v, sort_keys=True, allow_nan=False))
        return {"tag": "set", "items": items}
    if type(value) is dict:
        items = [[_encode(k, depth + 1), _encode(v, depth + 1)]
                 for k, v in value.items()]
        items.sort(key=lambda v: json.dumps(v[0], sort_keys=True, allow_nan=False))
        return {"tag": "dict", "items": items}
    raise ValueError("Checkpoint contains unsupported object type")


def _decode(value, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("Checkpoint nesting exceeds safe depth")
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is not dict:
        raise ValueError("Invalid checkpoint node")
    tag = value.get("tag")
    if tag == "model" and set(value) == {"tag", "name", "values"}:
        cls = _MODELS.get(value["name"])
        if cls is None or type(value["values"]) is not dict:
            raise ValueError("Unknown checkpoint class")
        expected = {f.name for f in fields(cls)}
        present = set(value["values"])
        # Only allow explicitly defaultable Actor fields added after the
        # original schema; all other model/schema drift must still fail.
        migration_fields = {"lineage", "lineage_selected", "discovered_cities", "stored_gear"}
        magic_migration = {"next_practice_minute"}
        if (present != expected and not (
                cls is Actor and present <= expected and
                expected - present <= migration_fields) and not (
                cls is MagicState and present <= expected and
                expected - present <= magic_migration)):
            raise ValueError("Checkpoint class schema has changed")
        return cls(**{name: _decode(node, depth + 1)
                      for name, node in value["values"].items()})
    if tag in ("list", "tuple", "set", "dict") and set(value) == {"tag", "items"}:
        if type(value["items"]) is not list:
            raise ValueError("Invalid checkpoint collection")
        items = value["items"]
        if tag == "dict":
            pairs = []
            for pair in items:
                if type(pair) is not list or len(pair) != 2:
                    raise ValueError("Invalid checkpoint mapping item")
                pairs.append((_decode(pair[0], depth + 1),
                              _decode(pair[1], depth + 1)))
            output = dict(pairs)
            if len(output) != len(pairs):
                raise ValueError("Duplicate checkpoint dictionary keys")
            return output
        decoded = [_decode(node, depth + 1) for node in items]
        if tag == "list":
            return decoded
        if tag == "tuple":
            return tuple(decoded)
        if len(set(decoded)) != len(decoded):
            raise ValueError("Duplicate checkpoint set items")
        return set(decoded)
    raise ValueError("Unknown checkpoint node type")


def create_schema(game: MultiplayerGame) -> None:
    game.db.executescript("""
        CREATE TABLE IF NOT EXISTS world_checkpoints(
            journal_seq INTEGER PRIMARY KEY CHECK(journal_seq > 0),
            schema_version INTEGER NOT NULL,
            payload TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
    """)


def _journal_digest(game: MultiplayerGame, seq: int) -> str:
    """Attest the immutable journal prefix, including join and clock rows.

    This scan is substantially cheaper than applying historic gameplay,
    though a future chained hash index can make it O(1) per checkpoint.
    """
    sha = hashlib.sha256()
    for row in game.db.execute(
            "SELECT seq,kind,actor_id,action,payload,request_id,result_json,"
            "recorded_at,flee_success,secure_roll,server_clock,regen_version "
            "FROM world_journal WHERE seq<=? ORDER BY seq", (seq,)):
        sha.update(json.dumps(row, separators=(",", ":"), ensure_ascii=False,
                              allow_nan=False).encode("utf-8"))
        sha.update(b"\\n")
    return sha.hexdigest()


def save(game: MultiplayerGame, *, force: bool = False) -> int | None:
    """Write a checkpoint inside an already-open SQLite transaction."""
    seq = game.db.execute(
        "SELECT COALESCE(MAX(seq),0) FROM world_journal").fetchone()[0]
    if seq <= 0 or (not force and seq % CHECKPOINT_INTERVAL != 0):
        return None
    if game.db.execute(
            "SELECT 1 FROM world_checkpoints WHERE journal_seq=?", (seq,)).fetchone():
        return seq
    # SQLite durable_receipts owns idempotency. Dropping in-memory receipt
    # caches from checkpoints reduces size without weakening retry safety.
    state = replace(game.world.state, command_receipts={})
    snapshot = {"schema_version": CHECKPOINT_VERSION,
                "seq": seq, "state": _encode(state),
                "event_times": _encode(game.event_times),
                "journal_digest": _journal_digest(game, seq)}
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    if len(payload.encode("utf-8")) > MAX_BYTES:
        raise ValueError("World checkpoint exceeds size limit")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    game.db.execute(
        "INSERT INTO world_checkpoints(journal_seq,schema_version,payload,sha256,recorded_at)"
        " VALUES(?,?,?,?,?)",
        (seq, CHECKPOINT_VERSION, payload, digest,
         datetime.now(timezone.utc).isoformat()))
    # Bound snapshot storage: keep two recent recovery points, but never
    # delete an audit journal entry, durable receipt, or asset holding.
    game.db.execute(
        "DELETE FROM world_checkpoints WHERE journal_seq NOT IN "
        "(SELECT journal_seq FROM world_checkpoints "
        "ORDER BY journal_seq DESC LIMIT 2)")
    return seq


def restore_latest(game: MultiplayerGame) -> int:
    """Restore the latest valid checkpoint, or return zero for full replay.

    An invalid checkpoint does *not* trigger a silent fallback. Corruption
    must be investigated rather than replaying around a missing/tampered row.
    """
    row = game.db.execute(
        "SELECT journal_seq,schema_version,payload,sha256 FROM world_checkpoints "
        "ORDER BY journal_seq DESC LIMIT 1").fetchone()
    if row is None:
        return 0
    seq, version, payload, digest = row
    if version != CHECKPOINT_VERSION or type(payload) is not str:
        raise ValueError("Unsupported world checkpoint version")
    if len(payload.encode("utf-8")) > MAX_BYTES:
        raise ValueError("World checkpoint exceeds size limit")
    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != digest:
        raise ValueError("World checkpoint checksum mismatch")
    stored = json.loads(payload)
    if (type(stored) is not dict or set(stored) !=
            {"schema_version", "seq", "state", "event_times", "journal_digest"} or
            stored["schema_version"] != CHECKPOINT_VERSION or stored["seq"] != seq):
        raise ValueError("World checkpoint metadata mismatch")
    if seq > game.db.execute(
            "SELECT COALESCE(MAX(seq),0) FROM world_journal").fetchone()[0]:
        raise ValueError("Checkpoint is newer than command journal")
    if stored["journal_digest"] != _journal_digest(game, seq):
        raise ValueError("Checkpoint journal prefix checksum mismatch")
    state = _decode(stored["state"])
    event_times = _decode(stored["event_times"])
    if not isinstance(state, WorldState) or type(event_times) is not dict:
        raise ValueError("Checkpoint state type mismatch")
    if state.command_receipts:
        raise ValueError("Checkpoint contains untrusted in-memory receipts")
    actors = {actor_id for actor_id, actor in state.actors.items()
              if actor.kind == "human"}
    names = {}
    for actor_id in actors:
        row = game.db.execute(
            "SELECT display_name FROM accounts WHERE actor_id=?",
            (actor_id,)).fetchone()
        if row is None:
            raise ValueError("Checkpoint actor has no registered account")
        names[actor_id] = row[0]
    if len(state.events) and any(event.event_id != i + 1
                                 for i, event in enumerate(state.events)):
        raise ValueError("Checkpoint event IDs are not contiguous")
    # A legacy checkpoint predates the atlas. Preserve at least the
    # character's actual location, without fabricating historical visits.
    for actor in state.actors.values():
        actor.discovered_cities.add(actor.city)
    game.world.state = state
    game.names = names
    game.event_times = event_times
    game.world.assert_invariants()
    return seq
