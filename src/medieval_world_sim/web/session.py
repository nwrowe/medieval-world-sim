"""Single-player, safely replayable JSON action journal for the web prototype.

No pickle, direct actor mutation, or hidden gold injection. The existing world
engine is rebuilt by replaying validated actions. Saves are atomically replaced
after each successful step, with rollback on a storage failure.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import random
import secrets
import threading
import uuid

from ..catalog import CAPITAL, CITIES, RAW_RESOURCES, GOODS, PROCESSED_RESOURCES, CONSUMABLES
from ..core.engine import WorldEngine
from ..core.entities import Actor
from ..content.housing import HOMES, HOME_ORDER, FACILITIES, VEHICLES
from ..content.magic_tree import SCHOOLS
from ..errors import ActionError
from ..equipment import GEAR, suggested_value, effective_attack, effective_defense
from ..systems.cooldowns import MAX_COOLDOWN_MINUTES, FOOD_MINUTES, POTION_MINUTES, remaining
from ..systems.track import HORSES, RACE_STAMINA_COST, RACE_ENTRY, RACE_COOLDOWN

SAVE_VERSION = 1
PLAYER_ID = "hero"
INITIAL_GOLD = 240
START_CITY = CAPITAL
LEGACY_START_CITY = "goldmeadow"
MAX_RECORDS = 20000
ADVANCE_LIMIT = 1440
UI_ACTIONS = {
    "travel", "gather", "regional_buy", "regional_sell",
    "consume", "buy_home", "upgrade_home", "build_home_facility",
    "buy_vehicle", "select_vehicle", "unlock_magic", "practice_magic",
    "attune_magic", "buy_starter_gear", "equip", "unequip",
    "complete_city_contract", "store_goods", "retrieve_goods",
    "start_duel", "duel_turn", "flee_duel", "cast_spell",
    "church_heal", "buy_racehorse", "race_horse",
    "found_guild", "invite_guild", "join_guild", "set_guild_role",
    "leave_guild", "claim_merit", "buy_merit_upgrade", "enroll_course",
    "enroll_course_choice", "send_chat", "create_chat_room",
}

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


TRADE_EVENTS = {"trade_proposed", "trade_settled", "trade_closed"}
COMBAT_EVENTS = {"pvp_strike", "duel_started", "duel_round",
                 "duel_finished", "duel_fled", "duel_defender_fled",
                 "duel_draw", "duel_flee_attempt", "combat", "spell_cast"}
UNIVERSITY_EVENTS = {"course_started", "course_tuition_paid", "course_completed",
                     "school_graduated", "school_capstone_perk", "school_martial_perk"}
TRAVEL_EVENTS = {"travel_started", "arrived"}
GUILD_EVENTS = {"guild_founded", "guild_invited", "guild_joined",
                "guild_role_changed", "guild_left"}
EQUIPMENT_EVENTS = {"gear_created", "gear_broken", "starter_purchase",
                    "equipped", "unequipped", "equipment_offered"}
PROPERTY_EVENTS = {"home_purchased", "home_upgraded", "home_facility_built",
                   "vehicle_purchased", "vehicle_selected"}
MAGIC_EVENTS = {"magic_unlocked", "magic_practiced", "magic_attuned"}
HEALTH_EVENTS = {"recovered", "consumed", "church_healed"}
RACING_EVENTS = {"horse_purchased", "horse_raced"}
PROGRESSION_EVENTS = {"level_up", "merit_claimed", "merit_upgrade"}
ECONOMY_EVENTS = {"regional_bought", "regional_sold", "gathered",
                  "goods_stored", "goods_retrieved", "city_contract_completed",
                  "offer_posted", "offer_filled", "offer_canceled", "city_sale",
                  "company_founded", "hired", "shift_completed", "job_offered",
                  "wage_changed", "worker_left", "perks_changed",
                  "facility_upgraded", "training_paid", "perk_awarded"}


def event_category(kind: str) -> str:
    """Stable Chronicle categories shared by single- and multi-player views."""
    for label, events in (
        ("Trade", TRADE_EVENTS), ("Combat", COMBAT_EVENTS),
        ("Travel", TRAVEL_EVENTS), ("University", UNIVERSITY_EVENTS),
        ("Guild", GUILD_EVENTS), ("Equipment", EQUIPMENT_EVENTS),
        ("Property", PROPERTY_EVENTS), ("Magic", MAGIC_EVENTS),
        ("Health", HEALTH_EVENTS), ("Racing", RACING_EVENTS),
        ("Progression", PROGRESSION_EVENTS), ("Economy", ECONOMY_EVENTS),
    ):
        if kind in events:
            return label
    return "Other"


def _trade_assets_text(assets) -> str:
    if not isinstance(assets, dict):
        return "unspecified assets"
    parts = []
    if assets.get("gold"):
        parts.append(f"{assets['gold']}g")
    for entry in assets.get("items", []):
        parts.append(f"{entry.get('quantity')} {entry.get('item')}")
    for gear_id in assets.get("gear_ids", []):
        parts.append(f"equipment #{gear_id}")
    return ", ".join(parts) if parts else "nothing"


def _friendly_event(event, *, gear_kinds=None, equipped_kinds=None,
                    recorded_at=None, human_names=None):
    """Short and safe display labels; the UI never executes event payloads."""
    info = event.data
    gear_kinds = gear_kinds or {}
    equipped_kinds = equipped_kinds or {}
    human_names = human_names or {}
    def who(account_id):
        return human_names.get(account_id, account_id)
    gear_kind = gear_kinds.get(info.get("gear_id"))
    readable = {
        "trade_proposed": (
            f"Trade #{info.get('trade_id')}: "
            f"{who(info.get('maker_id'))} offered to {who(info.get('recipient_id'))}: "
            f"offered {_trade_assets_text(info.get('offer'))}; "
            f"requested {_trade_assets_text(info.get('request'))}"
        ),
        "trade_settled": (
            f"Trade #{info.get('trade_id')} completed: "
            f"{who(info.get('maker_id'))} offered {_trade_assets_text(info.get('offer'))}; "
            f"{who(info.get('recipient_id'))} provided {_trade_assets_text(info.get('request'))}"
        ),
        "trade_closed": (
            f"Trade #{info.get('trade_id')} canceled by {who(info.get('actor_id'))}: "
            f"escrow returned to {who(info.get('maker_id'))}"
        ),
        "recovered": "Recovered from injuries",
        "level_up": f"Reached level {info.get('level')}",
        "gear_broken": f"{info.get('item')} broke",
        "gathered": f"Gathered {info.get('quantity')} {info.get('item')}",
        "travel_started": f"Departed for {info.get('destination')}",
        "arrived": f"Arrived in {info.get('city')}",
        "regional_bought": f"Bought {info.get('quantity')} {info.get('item')} for {info.get('total')}g",
        "regional_sold": f"Sold {info.get('quantity')} {info.get('item')} for {info.get('total')}g",
        "home_purchased": f"Purchased a {info.get('tier')}",
        "home_upgraded": f"Upgraded home to {info.get('tier')}",
        "home_facility_built": f"Built {info.get('facility')}",
        "vehicle_purchased": f"Purchased {info.get('vehicle')}",
        "vehicle_selected": f"Travel vehicle: {info.get('vehicle') or 'walking'}",
        "magic_unlocked": f"Unlocked {info.get('node_id')}",
        "magic_practiced": (
            f"Practiced {str(info.get('node_id', '')).replace('_', ' ').replace('.', ' / ')} "
            f"— {'succeeded' if info.get('success') else 'attempted'} "
            f"(+{info.get('xp_gained', 0)} XP, "
            f"-{info.get('mana_spent', 0)} mana"
            f"{', +' + str(info.get('insight_gained')) + ' Insight' if info.get('insight_gained') else ''})"
        ),
        "magic_attuned": "Updated advanced magic specializations",
        "consumed": f"Used {info.get('item')}",
        "starter_purchase": f"Purchased {str(info.get('item', 'equipment')).replace('_', ' ')} for {info.get('price', 0)}g",
        "equipped": f"Equipped {str(gear_kind or info.get('slot', 'gear')).replace('_', ' ')}",
        "unequipped": f"Unequipped {str(equipped_kinds.get(info.get('slot')) or info.get('slot') or 'gear').replace('_', ' ')}",
        "goods_stored": f"Stored {info.get('quantity')} {str(info.get('item')).replace('_',' ')} in {info.get('city')}",
        "goods_retrieved": f"Retrieved {info.get('quantity')} {str(info.get('item')).replace('_',' ')} from {info.get('city')}",
        "guild_founded": f"Founded the guild {info.get('name')}",
        "guild_invited": f"Guild invitation sent to {info.get('candidate_id')}",
        "guild_joined": f"Joined guild {info.get('guild_id')}",
        "guild_role_changed": f"Appointed {info.get('member_id')} as {info.get('role')}",
        "guild_left": f"Left guild {info.get('guild_id')}",
        "course_tuition_paid": f"Paid {info.get('gold')} gold to study {info.get('school')}",
        "course_started": f"Enrolled in {info.get('school')} course #{info.get('course_index', 0) + 1}",
        "course_completed": f"Finished {info.get('school')} course; +{info.get('bonus')} {info.get('stat')}",
        "school_graduated": f"Graduated from {info.get('school')}",
        "school_capstone_perk": f"{info.get('school')} capstone: +{info.get('bonus')} {info.get('stat')}",
        "school_martial_perk": f"{info.get('school')} martial training: +{info.get('bonus')} {info.get('stat')}",
        "merit_claimed": f"Achievement claimed: {info.get('achievement')}",
        "merit_upgrade": f"Merit upgrade purchased: {info.get('perk')}",
        "church_healed": f"Church healing restored {info.get('health_restored')} HP for {info.get('gold')} gold",
        "horse_purchased": f"Purchased {info.get('breed')} racehorse for {info.get('gold')} gold",
        "horse_raced": f"Raced {info.get('breed')}: place {info.get('placing')}, earned {info.get('xp')} riding XP and {info.get('prize')} gold",
        "pvp_strike": (f"Skirmish against {info.get('defender_id')}: "
                       f"{info.get('damage')} damage, "
                       f"{info.get('retaliation')} retaliated, "
                       f"{info.get('gold_looted')}g looted"),
        "duel_started": f"Challenge begun against {info.get('defender_id')}",
        "duel_round": (
            f"Combat round {info.get('round')}: {info.get('move')} "
            f"({info.get('damage')} damage, {info.get('retaliation')} returned)"
        ),
        "duel_finished": (
            f"{info.get('winner_id')} defeated {info.get('loser_id')} "
            f"and claimed {info.get('gold')} gold"
        ),
        "duel_flee_attempt": (
            f"Flee attempt (round {info.get('round')}): "
            f"{'escaped' if info.get('success') else 'failed'}; "
            f"{info.get('retaliation')} damage taken"
        ),
        "duel_fled": "Attacker retreated from combat",
        "duel_defender_fled": "Defending player withdrew from combat",
        "duel_draw": f"Combat ended in a draw after {info.get('round')} rounds",
        "spell_cast": f"Cast {info.get('node_id')}: {info.get('message')}",
        "city_contract_completed": (
            f"Completed {str(info.get('contract_id', '')).replace('_', ' ')} "
            f"(+{info.get('gold')}g, +{info.get('xp')} XP)"
        ),
    }
    return {
        "id": event.event_id,
        "kind": event.kind,
        "category": event_category(event.kind),
        "minute": event.minute,
        "text": readable.get(event.kind, event.kind),
        # Legacy records have no wall-time metadata. Never invent timestamps.
        "recorded_at": recorded_at,
    }


class GameSession:
    def __init__(self, save_path: str | Path):
        self.save_path = Path(save_path).expanduser()
        self._lock = threading.RLock()
        self.world: WorldEngine | None = None
        self.name = ""
        self.seed = 42
        self.start_city = START_CITY
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
        actors = [Actor(PLAYER_ID, "human", city=self.start_city, gold=INITIAL_GOLD)]
        self.npc_names = {}
        for city in CITIES:
            for idx in range(3):
                npc_id = f"npc:{city}:{idx}"
                actors.append(Actor(npc_id, "npc", city=city, gold=rng.randint(50, 250)))
                self.npc_names[npc_id] = names.pop()
        return WorldEngine(actors, seed=self.seed)

    def create(self, name: str) -> None:
        with self._lock:
            if self.started or self.save_path.exists():
                raise ActionError("A saved character already exists on this server")
            if not isinstance(name, str):
                raise ActionError("Character name must be text")
            name = name.strip()
            if not re.fullmatch(r"[A-Za-z][A-Za-z '’-]{1,27}", name):
                raise ActionError("Use 2–28 letters, spaces, hyphens or apostrophes")
            self.name = name
            self.seed = secrets.randbelow(2**31)
            self.start_city = START_CITY
            self.world = self._new_world()
            try:
                self._save()
            except Exception:
                self.world = None
                raise

    def _document(self) -> dict:
        return {
            "version": SAVE_VERSION, "name": self.name, "seed": self.seed,
            "start_city": self.start_city, "records": self.records,
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
                    or type(data.get("seed")) is not int
                    or type(data.get("name")) is not str
                    or type(data.get("records")) is not list):
                raise ValueError("Unknown save format")
            if len(data["records"]) > MAX_RECORDS:
                raise ValueError("Save journal exceeds prototype limits")
            self.seed = data["seed"]
            # Saves predating the Crownreach starting-city rule must continue
            # replaying from their original Goldmeadow spawn.
            self.start_city = data.get("start_city", LEGACY_START_CITY)
            if self.start_city not in CITIES:
                raise ValueError("Unknown initial city")
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
        if not isinstance(record, dict):
            raise ValueError("Invalid journal record")
        recorded_at = record.get("recorded_at")
        if recorded_at is not None:
            if not isinstance(recorded_at, str) or len(recorded_at) > 40:
                raise ValueError("Invalid event timestamp")
            try:
                timestamp = datetime.fromisoformat(recorded_at)
                if timestamp.tzinfo is None:
                    raise ValueError("Missing timestamp timezone")
            except ValueError as exc:
                raise ValueError("Invalid event timestamp") from exc
        before = len(self.world.events)
        valid_keys = set(record) - {"recorded_at", "ruleset"}
        if record.get("ruleset", 1) not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11) or type(record.get("ruleset", 1)) is not int:
            raise ValueError("Unknown action ruleset")
        if record.get("kind") == "advance" and valid_keys == {"kind", "minutes"}:
            self.world._legacy_health_regen = record.get("ruleset", 1) < 5
            self.world._legacy_equipment_wear = record.get("ruleset", 1) < 8
            try:
                self._advance_world(record["minutes"])
            finally:
                self.world._legacy_health_regen = False
                self.world._legacy_equipment_wear = False
        elif record.get("kind") == "action" and valid_keys == {"kind", "name", "params", "id"}:
            if record["name"] not in UI_ACTIONS:
                raise ValueError("Unsupported action in journal")
            self.world._legacy_equipment_wear = record.get("ruleset", 1) < 8
            self.world._legacy_curriculum_rules = (record.get("ruleset", 1) <= 8
                                                    and record["name"] == "enroll_course")
            self.world._legacy_guard_rules = record.get("ruleset", 1) < 8
            self.world._legacy_duel_rules = record.get("ruleset", 1) < 7
            self.world._legacy_flee_rules = (record.get("ruleset", 1) < 11
                                              and record["name"] == "flee_duel")
            self.world._legacy_magic_rules = record.get("ruleset", 1) == 1
            self.world._legacy_cooldown_rules = record.get("ruleset", 1) < 3
            try:
                self.world.execute(PLAYER_ID, record["name"], record["params"], record["id"])
            finally:
                self.world._legacy_equipment_wear = False
                self.world._legacy_curriculum_rules = False
                self.world._legacy_guard_rules = False
                self.world._legacy_duel_rules = False
                self.world._legacy_flee_rules = False
                self.world._legacy_magic_rules = False
                self.world._legacy_cooldown_rules = False
        else:
            raise ValueError("Unknown journal record")
        if recorded_at is not None:
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
                result = self.world.execute(
                    PLAYER_ID, record["name"], record["params"], record["id"])
            # Retain ruleset 3 for established actions; old journal assertions and
            # replay semantics must not shift when the new combat commands arrive.
            ruleset = (5 if record["kind"] == "advance" or
                       record.get("name") in {"church_heal", "buy_racehorse", "race_horse"}
                       else 4 if record.get("name") in
                       {"start_duel", "duel_turn", "flee_duel", "cast_spell"} else 3)
            if record.get("name") in {
                "found_guild", "invite_guild", "join_guild", "set_guild_role",
                "leave_guild", "claim_merit", "buy_merit_upgrade"
            }:
                ruleset = 6
            if record.get("name") in {"start_duel", "duel_turn", "flee_duel"}:
                ruleset = 8
            if record.get("name") == "flee_duel":
                ruleset = 11
            if record.get("name") == "enroll_course":
                ruleset = 8
            if record.get("name") == "enroll_course_choice":
                ruleset = 9
            if record.get("name") in {"send_chat", "create_chat_room"}:
                ruleset = 10
            stored_record = {**record, "ruleset": ruleset,
                             "recorded_at": datetime.now(timezone.utc).isoformat()}
            self.records.append(stored_record)
            try:
                self._save()
            except Exception:
                self.records.pop()
                raise
            for event in self.world.events[prior_events:]:
                self.event_times[event.event_id] = stored_record["recorded_at"]
            return result
        except Exception:
            self.world.state = snapshot
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
            # Historical records may still replay this command, but new web
            # requests must use the tuition-charging course-choice action.
            if name == "enroll_course":
                raise ActionError("Use the University's paid course enrollment")
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


def world_snapshot(w: WorldEngine | None, actor_id: str, name: str,
                   npc_names: dict[str, str], human_names: dict[str, str],
                   event_times: dict[int, str], multiplayer: bool) -> dict:
    """Present one player's authorized view from a shared or single-player world.

    Never serialize another player's inventory, gold, work/battle stats or
    private Chronicle events into this response. Both modes use one projection
    to avoid duplicating gameplay/UI calculations.
    """
    if w is None:
        return {"started": False}
    actor = w.actors[actor_id]
    housing = w.housing_view(actor_id)
    is_traveling = actor.destination is not None
    now = w.minute
    cargo = sum(actor.inventory.values()) + len(actor.gear_ids)
    places = []
    for city_id, city in CITIES.items():
        places.append({
            "id": city_id, "name": city.name, "is_current": city_id == actor.city,
            "minutes": (0 if is_traveling or actor.hp <= 0
                        else w.estimated_travel_minutes(actor_id, city_id)),
        })
    quote_list = [
        {**asdict(w.regional_quote(actor.city, item)),
         "locally_produced": item in CITIES[actor.city].deposits}
        for item in RAW_RESOURCES
    ]
    magic_nodes = [
        {**asdict(node), "prerequisites": list(node.prerequisites)}
        for node in w.magic_tree(actor_id)
    ]
    owned_gear = [
        {
            "id": gid, "kind": w.gear[gid].kind,
            "slot": GEAR[w.gear[gid].kind].slot,
            "quality": w.gear[gid].quality,
            "durability": w.gear[gid].durability,
            "max_durability": w.gear[gid].max_durability,
            "attack": effective_attack(w.gear[gid]),
            "defense": effective_defense(w.gear[gid]),
            "value": suggested_value(w.gear[gid]),
        }
        for gid in actor.gear_ids
    ]
    gear_catalog = [
        {"kind": kind, "slot": spec.slot, "price": spec.base_value,
         "attack": round(spec.attack * 0.85),
         "defense": round(spec.defense * 0.85),
         "durability": max(5, spec.max_durability // 2),
         "quality": 10}
        for kind, spec in GEAR.items()
    ]
    # Display all catalogued goods, not only currently stocked market items.
    # Unlisted crafted/consumable products have no merchant price; do not
    # invent supply or imply that NPC/player markets are live.
    world_items = []
    for item in sorted(GOODS | set(GEAR)):
        if item in RAW_RESOURCES:
            quotes = [w.regional_quote(city, item) for city in CITIES]
            buys = [q for q in quotes if q.sell_capacity > 0]
            sells = [q for q in quotes if q.buy_capacity > 0
                     and w.cities[q.city].gold >= q.player_sell_price]
            cheapest = min(buys, key=lambda q: (q.player_buy_price, q.city)) if buys else None
            highest = max(sells, key=lambda q: (q.player_sell_price, q.city)) if sells else None
            buy_data = ({"city": cheapest.city, "price": cheapest.player_buy_price}
                        if cheapest else None)
            sell_data = ({"city": highest.city, "price": highest.player_sell_price}
                         if highest else None)
        elif item in GEAR:
            buy_data = {"city": CAPITAL, "price": GEAR[item].base_value}
            sell_data = None
        else:
            buy_data = sell_data = None
        world_items.append({"id": item, "category": (
            "Equipment" if item in GEAR else
            "Processed" if item in PROCESSED_RESOURCES else
            "Consumable" if item in CONSUMABLES else "Resource"),
            "lowest_buy": buy_data, "highest_sell": sell_data,
            "market_value": None})
    resale_prices = {q["item"]: q["player_sell_price"] for q in quote_list}
    property_value = (HOMES[housing.tier].price if housing.tier else 0)
    facility_value = sum(FACILITIES[k].price for k in housing.facilities)
    vehicle_value = sum(VEHICLES[k].price for k in housing.vehicles)
    trade_goods_value = sum(
        quantity * resale_prices.get(item, 0)
        for item, quantity in actor.inventory.items()
    )
    # Ownership does not change when moving goods to local storage.
    for storage_city, goods in actor.storage.items():
        for item, quantity in goods.items():
            if quantity and item in RAW_RESOURCES:
                trade_goods_value += quantity * w.regional_quote(
                    storage_city, item).player_sell_price
    net_worth = (actor.gold + property_value + facility_value + vehicle_value
                 + trade_goods_value + sum(item["value"] for item in owned_gear))
    housing_data = {
        **asdict(housing),
        "facilities": list(housing.facilities),
        "vehicles": list(housing.vehicles),
    }
    gear_kinds = {}
    equipped_kinds = {}
    rendered_events = []
    for event in w.events:
        # A player's Chronicle must never expose another account's private
        # purchases, inventory changes, employment or other action history.
        if multiplayer:
            data = event.data
            participants = (
                (data.get("maker_id"), data.get("recipient_id"))
                if event.kind in TRADE_EVENTS else
                (data.get("attacker_id"), data.get("defender_id"),
                 data.get("winner_id"), data.get("loser_id"))
                if event.kind in COMBAT_EVENTS else
                (data.get("actor_id"),)
            )
            if actor_id not in participants:
                continue
        info = event.data
        if event.kind in ("starter_purchase", "gear_created"):
            gear_kinds[info.get("gear_id")] = info.get("item")
        if event.kind == "equipped":
            prior_slot = info.get("slot")
            rendered = _friendly_event(
                event, gear_kinds=gear_kinds,
                equipped_kinds=equipped_kinds,
                recorded_at=event_times.get(event.event_id),
                human_names=human_names)
            equipped_kinds[prior_slot] = gear_kinds.get(info.get("gear_id"), prior_slot)
        else:
            rendered = _friendly_event(
                event, gear_kinds=gear_kinds,
                equipped_kinds=equipped_kinds,
                recorded_at=event_times.get(event.event_id),
                human_names=human_names)
            if event.kind == "unequipped":
                equipped_kinds.pop(info.get("slot"), None)
        rendered_events.append(rendered)
    duel = w.state.duels.get(actor_id)
    duel_role = "attacker" if duel else None
    if multiplayer and not duel:
        duel = next((d for d in w.state.duels.values()
                     if d.defender_id == actor_id), None)
        if duel:
            duel_role = "defender"
    active_duel = None
    if duel:
        opponent_id = (duel.defender_id if duel_role == "attacker"
                       else duel.attacker_id)
        foe = w.actors[opponent_id]
        active_duel = {
            "opponent_id": foe.id,
            "opponent_name": npc_names.get(
                foe.id, human_names.get(foe.id, foe.id)),
            "opponent_hp": foe.hp, "opponent_max_hp": foe.max_hp,
            "round": duel.round, "log": list(duel.log),
            "pending_ward": duel.pending_ward if duel_role == "attacker" else 0,
            "role": duel_role,
            "max_rounds": 10 if w.actors[duel.defender_id].kind == "human" else None,
        }
    characters = [{
        "id": actor_id, "name": name, "city": actor.city, "level": actor.level,
        "kind": "human", "hp": actor.hp, "max_hp": actor.max_hp,
        "can_attack": False, "traveling": actor.destination is not None,
        "recovering_minutes": max(0, (actor.defeated_until or 0) - now),
    }]
    for npc_id, npc_name in npc_names.items():
        npc = w.actors[npc_id]
        characters.append({
            "id": npc.id, "name": npc_name, "city": npc.city,
            "level": npc.level, "kind": "npc", "hp": npc.hp, "max_hp": npc.max_hp,
            "can_attack": (
                npc.city == actor.city and npc.destination is None
                and npc.hp > 0 and actor.hp > 0 and not is_traveling
                and active_duel is None and not any(
                    npc.id in (d.attacker_id, d.defender_id)
                    for d in w.state.duels.values())
            ),
            "traveling": npc.destination is not None,
            "recovering_minutes": max(0, (npc.defeated_until or 0) - now),
        })
    if multiplayer:
        for human_id, human_name in human_names.items():
            if human_id == actor_id:
                continue
            other = w.actors[human_id]
            characters.append({
                "id": other.id, "name": human_name, "city": other.city,
                "level": other.level, "kind": "human",
                "hp": other.hp, "max_hp": other.max_hp,
                "can_attack": (
                    other.city == actor.city and other.destination is None
                    and other.hp > 0 and actor.hp > 0 and not is_traveling
                    and active_duel is None and not any(
                        other.id in (d.attacker_id, d.defender_id)
                        for d in w.state.duels.values())
                ),
                "traveling": other.destination is not None,
                "recovering_minutes": max(0, (other.defeated_until or 0) - now),
            })
    combat_moves = []
    for move in ("strike", "dagger", "fists"):
        if move == "strike" and "weapon" not in actor.equipped:
            continue
        if move == "dagger" and "secondary" not in actor.equipped:
            continue
        label, _, cost = w.combat.melee_option(actor, move)
        combat_moves.append({
            "move": move, "label": "Primary: " + label if move == "strike" else label,
            "stamina": cost, "available": actor.stamina >= cost,
        })
    return {
        "started": True, "name": name,
        "minute": now, "day": now // 1440 + 1,
        "days_played": now // 1440,
        "net_worth_estimate": net_worth,
        "net_worth_basis": "Gold plus purchase prices of property and vehicles, "
                           "local raw-goods resale quotes (including city storage), "
                           "and estimated equipment value",
        "gear": owned_gear,
        "equipment_catalog": gear_catalog,
        "world_items": world_items,
        "guilds": w.guild_system.view(actor_id),
        "merits": w.merit_system.view(actor_id),
        "training_hall": w.curriculum_system.view(actor_id),
        "chat": w.chat_system.view(actor_id),
        "equipped": dict(actor.equipped),
        "player": {
            "city": actor.city, "destination": actor.destination,
            "arrival_minute": actor.arrival_minute,
            "gold": actor.gold, "hp": actor.hp, "max_hp": actor.max_hp,
            "stamina": actor.stamina, "max_stamina": actor.max_stamina,
            "hunger": actor.vitals.hunger, "level": actor.level,
            "combat_xp": actor.combat_xp,
            "level_xp": actor.level_xp,
            "strength": actor.strength, "defense": actor.defense,
            "work": {
                "manual": actor.work.manual,
                "intelligence": actor.work.intelligence,
                "endurance": actor.work.endurance,
                "shifts": actor.work.shifts,
                "experience": dict(actor.work.experience),
            },
            "mana": actor.magic.mana, "max_mana": actor.magic.max_mana,
            "school_xp": dict(actor.magic.school_xp),
            "insight": actor.magic.insight,
            "attuned_paths": list(actor.magic.attuned_paths),
            "inventory": dict(actor.inventory),
            "stored_here": dict(actor.storage.get(actor.city, {})),
            "storage_cities": {
                city: sum(contents.values())
                for city, contents in actor.storage.items()
            },
            "cargo": cargo, "cargo_limit": housing.travel_cargo_limit,
            "ready_minute": actor.ready_minute,
            "cooldowns": {
                kind: {
                    "remaining_minutes": remaining(actor, kind, now),
                    "max_minutes": MAX_COOLDOWN_MINUTES,
                }
                for kind in ("job", "food", "potion")
            },
            "consumables": [
                {"item": item, "quantity": actor.inventory.get(item, 0),
                 "channel": ("food" if item in FOOD_MINUTES else "potion"),
                 "cooldown_minutes": FOOD_MINUTES.get(item, POTION_MINUTES.get(item, 0))}
                for item in (*FOOD_MINUTES, *POTION_MINUTES)
            ],
            "defeated_until": actor.defeated_until,
            "road_charm": actor.magic.road_charm,
            "ward_charge": actor.magic.ward_charge,
            # Simulation seconds: the world currently advances on player actions,
            # not elapsed real time. The client must label these honestly.
            "stamina_next_sim_seconds": (
                (5 - now % 5) * 60 if actor.stamina < actor.max_stamina else None),
            "mana_next_sim_seconds": (
                (10 - now % 10) * 60 if actor.magic.mana < actor.magic.max_mana else None),
            "health_next_sim_seconds": (
                (actor.defeated_until - now) * 60
                if actor.hp <= 0 and actor.defeated_until is not None else
                (10 - now % 10) * 60 if 0 < actor.hp < actor.max_hp else None),

        },
        "cities": places,
        "contracts": w.city_contracts.view(actor_id),
        "users": characters,
        "multiplayer": multiplayer,
        "duel": active_duel,
        "last_duel": w.state.last_duels.get(actor_id),
        "combat_stamina_cost": 0,
        "guard_stamina_cost": 2,
        "magic_stamina_cost": 6,
        "combat_moves": combat_moves,
        "church": {"price": 20, "available": (
            actor.hp > 0 and actor.hp < actor.max_hp and
            w.state.church_healed_day.get(actor_id) != now // 1440),
            "used_today": w.state.church_healed_day.get(actor_id) == now // 1440},
        "track": {"horses": [
            {"id": breed, "name": spec["name"], "price": spec["price"],
             "speed": spec["speed"], "stamina": spec["stamina"],
             "owned": breed in w.state.horses.get(actor_id, [])}
            for breed, spec in HORSES.items()
        ], "riding_xp": w.state.riding_xp.get(actor_id, 0),
           "last_result": w.state.race_results.get(actor_id),
           "race_cost": RACE_STAMINA_COST, "entry_fee": RACE_ENTRY,
           "cooldown_remaining": max(0, w.state.last_race_minute.get(
               actor_id, -RACE_COOLDOWN) + RACE_COOLDOWN - now)},
        "gatherable": dict(w.cities[actor.city].deposits),
        "quotes": quote_list,
        "housing": housing_data,
        "homes": [
            {"id": kind, **asdict(HOMES[kind])} for kind in HOME_ORDER
        ],
        "facilities": [
            {"id": kind, **asdict(spec)} for kind, spec in FACILITIES.items()
        ],
        "vehicles": [
            {"id": kind, **asdict(spec)} for kind, spec in VEHICLES.items()
        ],
        "magic_schools": list(SCHOOLS),
        "magic_nodes": magic_nodes,
        "events": rendered_events[-500:][::-1],
    }
