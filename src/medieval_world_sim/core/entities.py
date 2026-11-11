"""Shared actor, company, market and event domain entities.

Entities hold state; authoritative game rules live in systems.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from ..catalog import CAPITAL
from ..combat import MAX_STAMINA

@dataclass
class Vitals:
    hp: int = 24
    max_hp: int = 24
    stamina: int = MAX_STAMINA
    max_stamina: int = MAX_STAMINA
    defeated_until: int | None = None
    hunger: int = 0  # 0=well fed; 3=hungry, no lethal starvation in prototype


@dataclass
class Progression:
    level: int = 1
    level_xp: int = 0
    combat_xp: int = 0
    strength: int = 1
    defense: int = 1


@dataclass
class WorkStats:
    manual: int = 10
    intelligence: int = 10
    endurance: int = 10
    shifts: int = 0
    experience: dict[str, int] = field(default_factory=dict)


@dataclass
class MagicState:
    # Magical ability and progression are distinct from combat and work stats.
    mana: int = 100
    max_mana: int = 100
    school_xp: dict[str, int] = field(default_factory=dict)
    unlocked: set[str] = field(default_factory=lambda: {"arcane_fundamentals"})
    insight: int = 0
    insight_earned: int = 0
    attempts: int = 0
    attuned_paths: tuple[str, ...] = ()
    last_attunement_minute: int | None = None
    # One server-authoritative, per-school practice session every two hours.
    # Old saves decode with this field defaulting to an empty schedule.
    next_practice_minute: dict[str, int] = field(default_factory=dict)
    road_charm: int = 0
    ward_charge: int = 0


@dataclass
class HousingState:
    city: str | None = None
    tier: str | None = None
    facilities: set[str] = field(default_factory=set)
    vehicles: set[str] = field(default_factory=set)
    active_vehicle: str | None = None
    # Fixed-point XP bonus residue per skill domain, always between 0 and 99.
    xp_remainders: dict[str, int] = field(default_factory=dict)


@dataclass
class TravelState:
    destination: str | None = None
    arrival_minute: int | None = None
    ready_minute: int = 0
    departure_minute: int | None = None
    route_hexes: tuple[tuple[int, int], ...] = ()
    route_revealed_index: int = 0


@dataclass
class Cooldowns:
    """Absolute simulation minute when each independent cooldown expires."""
    job: int = 0
    food: int = 0
    potion: int = 0


@dataclass
class Actor:
    """One character model for human and NPC controllers.

    Deprecated flat-field properties remain to avoid breaking existing scripts.
    New systems should use .vitals, .progression and .travel.
    """
    id: str
    kind: str
    city: str = CAPITAL
    gold: int = 100
    inventory: dict[str, int] = field(default_factory=dict)
    gear_ids: list[int] = field(default_factory=list)
    equipped: dict[str, int] = field(default_factory=dict)
    hostile: bool = False
    pvp_opt_in: bool = False
    vitals: Vitals = field(default_factory=Vitals)
    progression: Progression = field(default_factory=Progression)
    travel: TravelState = field(default_factory=TravelState)
    work: WorkStats = field(default_factory=WorkStats)
    magic: MagicState = field(default_factory=MagicState)
    housing: HousingState = field(default_factory=HousingState)
    # Keep new fields at the end to preserve historical positional constructor calls.
    storage: dict[str, dict[str, int]] = field(default_factory=dict)
    cooldowns: Cooldowns = field(default_factory=Cooldowns)
    # Old saves/accounts remain unselected until their owner chooses once.
    lineage: str = "human"
    lineage_selected: bool = False
    discovered_cities: set[str] = field(default_factory=set)
    explored_hexes: set[int] = field(default_factory=set)
    stored_gear: dict[str, list[int]] = field(default_factory=dict)

    @property
    def hp(self) -> int:
        return self.vitals.hp

    @hp.setter
    def hp(self, value: int) -> None:
        self.vitals.hp = value

    @property
    def max_hp(self) -> int:
        return self.vitals.max_hp

    @max_hp.setter
    def max_hp(self, value: int) -> None:
        self.vitals.max_hp = value

    @property
    def stamina(self) -> int:
        return self.vitals.stamina

    @stamina.setter
    def stamina(self, value: int) -> None:
        self.vitals.stamina = value

    @property
    def max_stamina(self) -> int:
        return self.vitals.max_stamina

    @max_stamina.setter
    def max_stamina(self, value: int) -> None:
        self.vitals.max_stamina = value

    @property
    def defeated_until(self) -> int | None:
        return self.vitals.defeated_until

    @defeated_until.setter
    def defeated_until(self, value: int | None) -> None:
        self.vitals.defeated_until = value

    @property
    def level(self) -> int:
        return self.progression.level

    @level.setter
    def level(self, value: int) -> None:
        self.progression.level = value

    @property
    def level_xp(self) -> int:
        return self.progression.level_xp

    @level_xp.setter
    def level_xp(self, value: int) -> None:
        self.progression.level_xp = value

    @property
    def combat_xp(self) -> int:
        return self.progression.combat_xp

    @combat_xp.setter
    def combat_xp(self, value: int) -> None:
        self.progression.combat_xp = value

    @property
    def strength(self) -> int:
        return self.progression.strength

    @strength.setter
    def strength(self, value: int) -> None:
        self.progression.strength = value

    @property
    def defense(self) -> int:
        return self.progression.defense

    @defense.setter
    def defense(self, value: int) -> None:
        self.progression.defense = value

    @property
    def destination(self) -> str | None:
        return self.travel.destination

    @destination.setter
    def destination(self, value: str | None) -> None:
        self.travel.destination = value

    @property
    def arrival_minute(self) -> int | None:
        return self.travel.arrival_minute

    @arrival_minute.setter
    def arrival_minute(self, value: int | None) -> None:
        self.travel.arrival_minute = value

    @property
    def ready_minute(self) -> int:
        return self.travel.ready_minute

    @ready_minute.setter
    def ready_minute(self, value: int) -> None:
        self.travel.ready_minute = value


@dataclass
class DuelState:
    attacker_id: str
    defender_id: str
    round: int = 0
    first_attack: bool = False
    pending_ward: int = 0
    xp_earned: int = 0
    log: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Wage:
    gold: int = 0
    item: str | None = None
    quantity: int = 0


@dataclass
class Company:
    id: str
    owner_id: str
    industry: str
    city: str = CAPITAL
    gold: int = 0
    inventory: dict[str, int] = field(default_factory=dict)
    employees: dict[str, Wage] = field(default_factory=dict)
    gear_ids: list[int] = field(default_factory=list)
    facility_level: int = 1
    shifts_completed: int = 0
    perks: tuple[str, ...] = ()
    job_offers: dict[str, Wage] = field(default_factory=dict)
    daily_units_sold: int = 0
    daily_revenue: int = 0


@dataclass
class Offer:
    id: int
    seller_id: str
    city: str
    item: str
    quantity: int  # resources held in escrow, not in seller inventory
    unit_price: int
    gear_id: int | None = None  # exact non-fungible item, if equipment offer


@dataclass(frozen=True)
class WorldEvent:
    minute: int
    kind: str
    details: tuple
    event_id: int = 0
    action_id: str | None = None
    schema_version: int = 1
    data: dict[str, object] = field(default_factory=dict)


