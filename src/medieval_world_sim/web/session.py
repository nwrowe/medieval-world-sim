"""Single-player, safely replayable JSON action journal for the web prototype.

No pickle, direct actor mutation, or hidden gold injection. The existing world
engine is rebuilt by replaying validated actions. Saves are atomically replaced
after each successful step, with rollback on a storage failure.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import random
import secrets
import threading
import uuid

from ..catalog import CAPITAL, CITIES, GEOGRAPHY_FINGERPRINT
from ..core.engine import WorldEngine
from ..core.commands import SINGLE_PLAYER_ACTIONS
from ..core.entities import Actor
from ..content.magic_tree import MAX_MANA, STARTING_MANA
from ..errors import ActionError

# Presentation helpers remain available at their established import locations.
from .chronicle import event_category, _friendly_event, TRADE_EVENTS, COMBAT_EVENTS
from .projection import world_snapshot

SAVE_VERSION = 3
PLAYER_ID = "hero"
INITIAL_GOLD = 240
START_CITY = CAPITAL
MAX_RECORDS = 20000
ADVANCE_LIMIT = 1440
# Browser permissions are defined in the central command registry.
UI_ACTIONS = SINGLE_PLAYER_ACTIONS

# Stable, seed-based test characters. They are NPCs, not authenticated users.
NPC_NAMES = (
    "Aldric Thorn", "Bryn Ashford", "Corin Vale", "Dara Flint",
    "Elowen March", "Fenn Rowan", "Garrick Holt", "Hilda Moor",
    "Ivor Stone", "Jessa Reed", "Kellan Frost", "Liora Fen",
    "Marek Wolf", "Nessa Crow", "Orin Pike", "Petra Moss",
    "Quinn Briar", "Rhea Flint", "Soren West", "Talia Brook",
)


class SaveError(Exception):
    """An I/O or unsupported-save error, not a gameplay validation failure."""



from ..content.lineages import LINEAGES, select_lineage


class GameSession:
    def __init__(self, save_path: str | Path):
        self.save_path = Path(save_path).expanduser()
        self._lock = threading.RLock()
        self.world: WorldEngine | None = None
        self.name = ""
        self.seed = 42
        self.start_city = START_CITY
        self.lineage: str | None = None
        self.start_mana = STARTING_MANA
        self.npc_names: dict[str, str] = {}
        self.records: list[dict] = []
        self.event_times: dict[int, str] = {}
        if self.save_path.exists():
            self._load()

    @property
    def started(self) -> bool:
        return self.world is not None

    def _new_world(self) -> WorldEngine:
        rng = random.Random(self.seed)
        names = list(NPC_NAMES)
        rng.shuffle(names)
        hero = Actor(PLAYER_ID, "human", city=self.start_city, gold=INITIAL_GOLD)
        if self.lineage is not None:
            select_lineage(hero, self.lineage)
        actors = [hero]
        self.npc_names = {}
        for city in CITIES:
            for idx in range(3):
                npc_id = f"npc:{city}:{idx}"
                actors.append(Actor(npc_id, "npc", city=city, gold=rng.randint(50, 250)))
                self.npc_names[npc_id] = names.pop() if names else f"Wayfarer {len(self.npc_names) + 1}"
        world = WorldEngine(actors, seed=self.seed)
        if self.start_mana == MAX_MANA:
            # Preserve the original mana baseline when replaying old saves.
            for actor in world.actors.values():
                actor.magic.max_mana = MAX_MANA
                actor.magic.mana = MAX_MANA
        return world

    def create(self, name: str, lineage: str = "human") -> None:
        with self._lock:
            if self.started or self.save_path.exists():
                raise ActionError("A saved character already exists on this server")
            if not isinstance(name, str):
                raise ActionError("Character name must be text")
            name = name.strip()
            if not re.fullmatch(r"[A-Za-z][A-Za-z '’-]{1,27}", name):
                raise ActionError("Use 2–28 letters, spaces, hyphens or apostrophes")
            if not isinstance(lineage, str) or lineage not in LINEAGES:
                raise ActionError("Choose a valid lineage")
            self.name = name
            self.lineage = lineage
            self.seed = secrets.randbelow(2**31)
            self.start_city = START_CITY
            self.start_mana = STARTING_MANA
            self.world = self._new_world()
            try:
                self._save()
            except Exception:
                self.world = None
                raise

    def _document(self) -> dict:
        return {
            "version": SAVE_VERSION, "name": self.name, "seed": self.seed,
            "realm_fingerprint": GEOGRAPHY_FINGERPRINT,
            "start_city": self.start_city, "lineage": self.lineage,
            "start_mana": self.start_mana, "records": self.records,
        }

    def _save(self) -> None:
        path = self.save_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(self._document(), handle, separators=(",", ":"), ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise SaveError(f"Failed to save game: {exc}") from exc
        finally:
            temporary.unlink(missing_ok=True)

    def _load(self) -> None:
        try:
            with self.save_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if (type(data) is not dict or data.get("version") != SAVE_VERSION
                    or data.get("realm_fingerprint") != GEOGRAPHY_FINGERPRINT
                    or type(data.get("seed")) is not int
                    or type(data.get("name")) is not str
                    or type(data.get("records")) is not list):
                raise ValueError("Unknown save format")
            if len(data["records"]) > MAX_RECORDS:
                raise ValueError("Save journal exceeds prototype limits")
            self.seed = data["seed"]
            self.start_city = data.get("start_city")
            if self.start_city != START_CITY:
                raise ValueError("Unknown baseline starting city")
            self.lineage = data.get("lineage")
            self.start_mana = data.get("start_mana", MAX_MANA)
            if type(self.start_mana) is not int or self.start_mana not in (STARTING_MANA, MAX_MANA):
                raise ValueError("Invalid starting mana baseline")
            if self.lineage not in LINEAGES:
                raise ValueError("Unknown lineage in save")
            self.name = data["name"]
            self.world = self._new_world()
            for record in data["records"]:
                self._replay(record)
            self.world.assert_invariants()
            self.records = data["records"]
        except (OSError, ValueError, TypeError, KeyError, ActionError, AssertionError) as exc:
            self.world = None
            raise SaveError(f"Cannot open saved world at {self.save_path}: {exc}") from exc

    def _replay(self, record: dict) -> None:
        """Replay the current save format, refusing obsolete rule metadata."""
        if type(record) is not dict:
            raise ValueError("Invalid journal record")
        recorded_at = record.get("recorded_at")
        if type(recorded_at) is not str or len(recorded_at) > 40:
            raise ValueError("Invalid event timestamp")
        try:
            timestamp = datetime.fromisoformat(recorded_at)
            if timestamp.tzinfo is None:
                raise ValueError("Missing timestamp timezone")
        except ValueError as exc:
            raise ValueError("Invalid event timestamp") from exc
        before = len(self.world.events)
        if record.get("kind") == "advance" and set(record) == {
                "kind", "minutes", "recorded_at"}:
            self._advance_world(record["minutes"])
        elif record.get("kind") == "action":
            expected = {"kind", "name", "params", "id", "recorded_at"}
            name = record.get("name")
            if name == "wilderness_gather" and "gather_rule" in record:
                expected.add("gather_rule")
            if name == "flee_duel":
                expected.add("flee_success")
                if type(record.get("flee_success")) is not bool:
                    raise ValueError("Invalid saved flee roll")
                self.world._flee_success = record["flee_success"]
            if set(record) != expected or name not in UI_ACTIONS:
                raise ValueError("Unsupported journal action")
            if name == "wilderness_gather":
                rule = record.get("gather_rule", 1)
                if type(rule) is not int or rule not in (1, 2):
                    raise ValueError("Invalid wilderness gather policy")
                self.world._replay_legacy_wilderness = rule == 1
            try:
                self.world.execute(PLAYER_ID, name, record["params"], record["id"])
            finally:
                self.world._replay_legacy_wilderness = False
                self.world._flee_success = None
        else:
            raise ValueError("Unknown journal record")
        for event in self.world.events[before:]:
            self.event_times[event.event_id] = recorded_at

    def _record(self, record: dict) -> object:
        if self.world is None:
            raise ActionError("Create a character first")
        if len(self.records) >= MAX_RECORDS:
            raise ActionError("Save journal full; snapshotting is not implemented")
        snapshot = deepcopy(self.world.state)
        prior_events = len(self.world.events)
        try:
            if record["kind"] == "advance":
                result = self._advance_world(record["minutes"])
            else:
                if record.get("name") == "flee_duel":
                    self.world._flee_success = bool(secrets.randbits(1))
                try:
                    result = self.world.execute(
                        PLAYER_ID, record["name"], record["params"], record["id"])
                finally:
                    # Store this exact roll in the journal before clearing it.
                    if record.get("name") != "flee_duel":
                        self.world._flee_success = None
            stored_record = {**record, "recorded_at": datetime.now(timezone.utc).isoformat()}
            if record.get("name") == "flee_duel":
                stored_record["flee_success"] = bool(self.world._flee_success)
            if record.get("name") == "wilderness_gather":
                stored_record["gather_rule"] = 2
            self.records.append(stored_record)
            try:
                self._save()
            except Exception:
                self.records.pop()
                raise
            for event in self.world.events[prior_events:]:
                self.event_times[event.event_id] = stored_record["recorded_at"]
            self.world._flee_success = None
            return result
        except Exception:
            self.world.state = snapshot
            self.world._flee_success = None
            raise

    def action(self, name: str, params: dict, request_id: str) -> object:
        with self._lock:
            if name not in UI_ACTIONS:
                raise ActionError("This action is not available in the web prototype")
            if not isinstance(params, dict) or not isinstance(request_id, str) or not (
                1 <= len(request_id) <= 80
            ):
                raise ActionError("Invalid action request")
            if self.world is None:
                raise ActionError("Create a character first")
            # Duplicate request IDs replay their original outcome, never charge twice.
            if request_id in self.world.state.command_receipts:
                return self.world.execute(PLAYER_ID, name, params, request_id)
            return self._record({
                "kind": "action", "name": name, "params": params, "id": request_id,
            })

    def _advance_world(self, minutes: int) -> None:
        if type(minutes) is not int or not 1 <= minutes <= ADVANCE_LIMIT:
            raise ActionError("Time advancement must be 1–1440 minutes")
        if self.world.state.duels:
            raise ActionError("Finish or flee your duel before advancing world time")
        self.world.advance(minutes)

    def advance(self, minutes: int) -> None:
        with self._lock:
            self._record({"kind": "advance", "minutes": minutes})

    def snapshot(self) -> dict:
        with self._lock:
            return world_snapshot(self.world, PLAYER_ID, self.name, self.npc_names,
                                  {PLAYER_ID: self.name}, self.event_times, False)

