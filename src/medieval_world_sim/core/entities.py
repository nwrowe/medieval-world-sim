"""Shared actor, company, market and event domain entities.

Entities hold state; authoritative game rules live in systems.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from ..catalog import CAPITAL
from ..combat import MAX_STAMINA

@dataclass
class Actor:
    id: str
    kind: str  # "human" or "npc" (does not change authority or capabilities)
    city: str = CAPITAL
    gold: int = 100
    inventory: dict[str, int] = field(default_factory=dict)
    destination: str | None = None
    arrival_minute: int | None = None
    ready_minute: int = 0
    gear_ids: list[int] = field(default_factory=list)
    equipped: dict[str, int] = field(default_factory=dict)
    hp: int = 24
    max_hp: int = 24
    stamina: int = MAX_STAMINA
    max_stamina: int = MAX_STAMINA
    level: int = 1
    level_xp: int = 0
    combat_xp: int = 0
    strength: int = 1
    defense: int = 1
    defeated_until: int | None = None
    hostile: bool = False  # Preserved for later NPC behavior, not attack permissions.
    pvp_opt_in: bool = False  # Legacy field; not used to gate combat.


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


