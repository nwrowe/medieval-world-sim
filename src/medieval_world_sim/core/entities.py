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


@dataclass
class Progression:
    level: int = 1
    level_xp: int = 0
    combat_xp: int = 0
    strength: int = 1
    defense: int = 1


@dataclass
class TravelState:
    destination: str | None = None
    arrival_minute: int | None = None
    ready_minute: int = 0


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


