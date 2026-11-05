"""Deterministic, bounded and durable NPC controller for the local multiplayer world.

NPCs have no credentials and never enter the player command allowlist. Each
successful action is committed beside its triggering advance in npc_steps.
Replay re-executes only recorded, whitelisted NPC commands, never the policy.
The separate cognition cache is an optimization and is durably updated in
the same SQLite transaction as the advance, NPC actions and asset ledger.
"""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from dataclasses import asdict, fields
from hashlib import sha256
import json
import random
from typing import TYPE_CHECKING

from ..catalog import CAPITAL, CITIES
from ..errors import ActionError
from ..agents.cognition import DecisionTrace, NPCMemory, TradeRoute
from ..agents.observation import observe
from ..agents.policy import NPCProfile, RuleBasedPolicy

if TYPE_CHECKING:
    from .multiplayer import MultiplayerGame

# Policy is deliberately narrower than the full WorldEngine command registry.
NPC_ACTIONS = frozenset({
    "travel", "gather", "post_offer", "accept_offer", "regional_buy",
    "regional_sell", "consume", "buy_starter_gear", "equip",
    "attack", "store_goods", "retrieve_goods",
})
MAX_ACTIONS_PER_ADVANCE = 3
DECISION_INTERVAL_MINUTES = 180
MAX_NPCS = 80
MAX_RUNTIME_BYTES = 24 * 1024
MAX_BATCH_BYTES = 8 * 1024
RUNTIME_VERSION = 1


def create_schema(game: MultiplayerGame) -> None:
    game.db.executescript("""
        CREATE TABLE IF NOT EXISTS npc_steps(
            journal_seq INTEGER PRIMARY KEY
                REFERENCES world_journal(seq) ON DELETE RESTRICT,
            payload TEXT NOT NULL CHECK(length(payload) <= 8192)
        );
        CREATE TABLE IF NOT EXISTS npc_runtime(
            npc_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL CHECK(length(payload) <= 24576),
            due_minute INTEGER NOT NULL CHECK(due_minute >= 0),
            updated_seq INTEGER NOT NULL
                REFERENCES world_journal(seq)
        );
    """)


def _profiles(game: MultiplayerGame) -> tuple[NPCProfile, ...]:
    profiles = []
    for actor_id, actor in sorted(game.world.actors.items()):
        if actor.kind != "npc":
            continue
        # Permanent home and role come from the seeded actor's stable ID,
        # not its current destination; a traveler stays a hauler on restart.
        parts = actor_id.split(":")
        if (len(parts) != 3 or parts[0] != "npc"
                or parts[1] not in CITIES or parts[2] not in ("0", "1", "2")):
            raise ValueError("Unrecognized seeded NPC")
        home, slot = parts[1], int(parts[2])
        role = ("adventurer" if slot == 2 or (home == CAPITAL and slot == 0)
                else "hauler" if slot == 1
                else "gatherer")
        resource = (next(iter(CITIES[home].deposits))
                    if role == "gatherer" else None)
        digest = sha256(actor_id.encode("utf-8")).digest()
        profiles.append(NPCProfile(
            actor_id, role, home=home, resource=resource,
            greed=.7 + digest[0] / 255 * .7,
            risk=.12 + digest[1] / 255 * .4,
            curiosity=.1 + digest[2] / 255 * .5,
            volatility=.25 + digest[3] / 255 * 1.2))
    if len(profiles) > MAX_NPCS:
        raise ValueError("Too many persistent NPCs")
    return tuple(profiles)


def _pack_memory(memory: NPCMemory) -> str:
    value = {
        "version": RUNTIME_VERSION,
        "attempts": dict(memory.attempts),
        "successes": dict(memory.successes),
        "failures": dict(memory.failures),
        "values": dict(memory.values),
        "decision_count": memory.decision_count,
        "idle_count": memory.idle_count,
        "stagnant_count": memory.stagnant_count,
        "last_action": memory.last_action,
        "last_city": memory.last_city,
        "repeat_count": memory.repeat_count,
        "visited": sorted(memory.visited),
        "noteworthy": dict(memory.noteworthy),
        "sequence": memory.sequence,
        "active_route": (asdict(memory.active_route)
                         if memory.active_route else None),
        "trade_cycles": list(memory.trade_cycles)[-12:],
        "trade_completed": memory.trade_completed,
        "trade_net_profit": memory.trade_net_profit,
        "trade_loss_cycles": memory.trade_loss_cycles,
        "trade_abandoned": memory.trade_abandoned,
        "pending_cargo": list(memory.pending_cargo)[-12:],
        "combat_loot": memory.combat_loot,
        "combat_victories": memory.combat_victories,
        "recent": [asdict(record) for record in list(memory.recent)[-20:]],
    }
    output = json.dumps(value, separators=(",", ":"), sort_keys=True,
                        allow_nan=False)
    if len(output.encode("utf-8")) > MAX_RUNTIME_BYTES:
        raise ValueError("NPC memory exceeds bounded durable storage")
    return output


def _unpack_memory(payload: str) -> NPCMemory:
    if type(payload) is not str or len(payload.encode("utf-8")) > MAX_RUNTIME_BYTES:
        raise ValueError("Invalid NPC runtime size")
    value = json.loads(payload)
    if type(value) is not dict or value.get("version") != RUNTIME_VERSION:
        raise ValueError("Unsupported NPC memory version")
    expected = {
        "version", "attempts", "successes", "failures", "values",
        "decision_count", "idle_count", "stagnant_count", "last_action",
        "last_city", "repeat_count", "visited", "noteworthy", "sequence",
        "active_route", "trade_cycles", "trade_completed",
        "trade_net_profit", "trade_loss_cycles", "trade_abandoned",
        "pending_cargo", "combat_loot", "combat_victories", "recent",
    }
    if set(value) != expected:
        raise ValueError("Invalid durable NPC memory fields")
    m = NPCMemory()
    for key in ("attempts", "successes", "failures", "noteworthy"):
        raw = value[key]
        if (type(raw) is not dict or len(raw) > 80
                or any(type(k) is not str or len(k) > 80 or
                       type(v) is not int or not 0 <= v <= 1000000
                       for k, v in raw.items())):
            raise ValueError("Invalid NPC action counters")
        setattr(m, key, Counter(raw))
    values = value["values"]
    if (type(values) is not dict or len(values) > 80
            or any(type(k) is not str or len(k) > 80
                   or type(v) not in (int, float) or not -4 <= v <= 4
                   for k, v in values.items())):
        raise ValueError("Invalid NPC learned values")
    m.values = values
    for key in ("decision_count", "idle_count", "stagnant_count",
                "repeat_count", "sequence", "trade_completed",
                "trade_loss_cycles", "trade_abandoned",
                "combat_loot", "combat_victories"):
        number = value[key]
        if type(number) is not int or not 0 <= number <= 1000000:
            raise ValueError("Invalid NPC counter")
        setattr(m, key, number)
    if (type(value["trade_net_profit"]) is not int
            or abs(value["trade_net_profit"]) > 100000000):
        raise ValueError("Invalid NPC profit counter")
    m.trade_net_profit = value["trade_net_profit"]
    for key in ("last_action", "last_city"):
        if type(value[key]) is not str or len(value[key]) > 100:
            raise ValueError("Invalid NPC string")
        setattr(m, key, value[key])
    if (type(value["visited"]) is not list or len(value["visited"]) > len(CITIES)
            or any(city not in CITIES for city in value["visited"])):
        raise ValueError("Invalid NPC city memory")
    m.visited = set(value["visited"])
    route = value["active_route"]
    if route is not None:
        if type(route) is not dict or set(route) != {
            f.name for f in fields(TradeRoute)}:
            raise ValueError("Invalid NPC trade route")
        if (route["source"] not in CITIES or route["destination"] not in CITIES
                or route["item"] not in CITIES[route["source"]].deposits
                or any(type(route[k]) is not int or route[k] < 0
                       for k in ("quantity", "remaining", "cost", "start_minute",
                                 "revenue", "recovery_attempts"))):
            raise ValueError("Invalid NPC trade objective")
        m.active_route = TradeRoute(**route)
    for key, maxlen in (("trade_cycles", 24), ("pending_cargo", 24)):
        raw = value[key]
        if type(raw) is not list or len(raw) > 24 or any(type(x) is not dict for x in raw):
            raise ValueError("Invalid NPC trade evidence")
        setattr(m, key, deque(raw, maxlen=maxlen))
    recent = value["recent"]
    if type(recent) is not list or len(recent) > 20:
        raise ValueError("Invalid NPC recent decisions")
    expected_trace = {f.name for f in fields(DecisionTrace)}
    if any(type(t) is not dict or set(t) != expected_trace for t in recent):
        raise ValueError("Invalid NPC decision traces")
    m.recent = deque((DecisionTrace(**t) for t in recent), maxlen=48)
    return m


def load(game: MultiplayerGame) -> None:
    """Load durable cognition only after verified journal replay/checkpoint."""
    game._npc_memories = {}
    game._npc_due = {}
    profiles = _profiles(game)
    game._npc_profiles = profiles
    rows = game.db.execute(
        "SELECT npc_id,payload,due_minute,updated_seq FROM npc_runtime").fetchall()
    valid = {profile.id for profile in profiles}
    max_seq = game.db.execute(
        "SELECT COALESCE(MAX(seq),0) FROM world_journal").fetchone()[0]
    for npc_id, payload, due, seq in rows:
        if (npc_id not in valid or type(due) is not int or not 0 <= due <= 10**10
                or type(seq) is not int or not 1 <= seq <= max_seq):
            raise ValueError("Invalid durable NPC scheduler state")
        game._npc_memories[npc_id] = _unpack_memory(payload)
        game._npc_due[npc_id] = due
    # New installs and older worlds naturally seed a cognition profile. The
    # NPCs themselves already exist in the world's historic deterministic seed.
    for idx, profile in enumerate(profiles):
        game._npc_memories.setdefault(profile.id, NPCMemory())
        game._npc_due.setdefault(profile.id, game.world.minute + (idx // 3) + 1)


def _persist(game: MultiplayerGame, npc_id: str, seq: int) -> None:
    game.db.execute(
        "INSERT INTO npc_runtime(npc_id,payload,due_minute,updated_seq) "
        "VALUES(?,?,?,?) ON CONFLICT(npc_id) DO UPDATE SET "
        "payload=excluded.payload,due_minute=excluded.due_minute,"
        "updated_seq=excluded.updated_seq",
        (npc_id, _pack_memory(game._npc_memories[npc_id]),
         game._npc_due[npc_id], seq))


def step(game: MultiplayerGame, journal_seq: int) -> int:
    """Run at most three NPC decisions in a single already-open advance tx.

    Neither users nor the web API may supply NPC IDs, commands, schedules or
    RNG outcomes. Failed speculative commands restore a pre-action world copy
    and are stored only as cognition telemetry, not in replayable actions.
    """
    if not game.npc_enabled or not game.names:
        return 0
    due = sorted((game._npc_due[p.id], p.id, p)
                 for p in game._npc_profiles
                 if game.world.minute >= game._npc_due[p.id])
    batch = []
    for _, npc_id, profile in due[:MAX_ACTIONS_PER_ADVANCE]:
        memory = game._npc_memories[npc_id]
        before = observe(game.world, npc_id)
        # Stable independent stream for each individual NPC decision.
        seed = int.from_bytes(sha256(
            f"{game.world.seed}|{npc_id}|{memory.decision_count}|{game.world.minute}"
            .encode("utf-8")).digest()[:8], "big")
        proposal = RuleBasedPolicy(random.Random(seed)).choose(
            profile, before, memory)
        game._npc_due[npc_id] = game.world.minute + DECISION_INTERVAL_MINUTES
        if proposal is None:
            memory.record_idle(before.city)
            _persist(game, npc_id, journal_seq)
            continue
        if proposal.name not in NPC_ACTIONS:
            raise RuntimeError("Policy proposed a command outside server NPC capabilities")
        if proposal.name == "attack":
            target = game.world.actors.get(proposal.params.get("defender_id"))
            if target is None or target.kind != "npc":
                raise RuntimeError("Automated NPC combat cannot attack a human account")
        engine_id = f"npc-live:{journal_seq}:{npc_id}"
        snapshot = deepcopy(game.world.state)
        first_event = len(game.world.events)
        error = ""
        result = None
        try:
            game.world._private_rng_key = (
                game._rng_key if proposal.name == "practice_magic" else None)
            result = game.world.execute(
                npc_id, proposal.name, proposal.params, engine_id)
        except ActionError as exc:
            # WorldEngine may have mutated some fields before rejection; the
            # aborted command MUST NOT leak side effects into a committed tick.
            game.world.state = snapshot
            error = type(exc).__name__ + ": " + str(exc)
        finally:
            game.world._private_rng_key = None
        if not error:
            batch.append({
                "id": npc_id, "name": proposal.name,
                "params": proposal.params, "engine_id": engine_id,
                "secure_roll": proposal.name == "practice_magic",
            })
        actor = game.world.actors[npc_id]
        after = observe(game.world, npc_id)
        events = tuple(e.kind for e in game.world.events[first_event:]
                       if e.data.get("actor_id") == npc_id
                       or e.data.get("attacker_id") == npc_id)
        if proposal.name == "attack" and result is not None and result.opponent_defeated:
            events += ("combat_victory",)
        route_step = (memory.active_route is not None
                      or proposal.name in ("regional_buy", "accept_offer"))
        profit = memory.record_trade(before, after, proposal, error)
        memory.record(
            before, after, proposal, events, error,
            defer_trade_credit=route_step, trade_profit=profit)
        _persist(game, npc_id, journal_seq)
    if batch:
        payload = json.dumps(batch, sort_keys=True, separators=(",", ":"),
                             allow_nan=False)
        if len(payload.encode("utf-8")) > MAX_BATCH_BYTES:
            raise ValueError("NPC step batch exceeds journal limit")
        game.db.execute(
            "INSERT INTO npc_steps(journal_seq,payload) VALUES(?,?)",
            (journal_seq, payload))
    return len(batch)


def replay(game: MultiplayerGame, journal_seq: int) -> None:
    row = game.db.execute(
        "SELECT payload FROM npc_steps WHERE journal_seq=?", (journal_seq,)).fetchone()
    if row is None:
        return
    payload = row[0]
    if type(payload) is not str or len(payload.encode("utf-8")) > MAX_BATCH_BYTES:
        raise ValueError("Invalid NPC journal batch")
    items = json.loads(payload)
    if type(items) is not list or not 1 <= len(items) <= MAX_ACTIONS_PER_ADVANCE:
        raise ValueError("Invalid NPC journal batch size")
    for action in items:
        if (type(action) is not dict or set(action) !=
                {"id", "name", "params", "engine_id", "secure_roll"}):
            raise ValueError("Invalid NPC journal action")
        npc_id, name = action["id"], action["name"]
        if (type(npc_id) is not str or npc_id not in game.world.actors
                or game.world.actors[npc_id].kind != "npc"
                or type(name) is not str or name not in NPC_ACTIONS
                or type(action["params"]) is not dict
                or type(action["engine_id"]) is not str
                or action["engine_id"] != f"npc-live:{journal_seq}:{npc_id}"
                or type(action["secure_roll"]) is not bool
                or action["secure_roll"] != (name == "practice_magic")):
            raise ValueError("Forged or invalid NPC journal action")
        if name == "attack":
            target = game.world.actors.get(action["params"].get("defender_id"))
            if target is None or target.kind != "npc":
                raise ValueError("NPC journal cannot target a human account")
        game.world._private_rng_key = game._rng_key if action["secure_roll"] else None
        try:
            game.world.execute(npc_id, name, action["params"], action["engine_id"])
        finally:
            game.world._private_rng_key = None
