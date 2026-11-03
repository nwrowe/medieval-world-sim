"""Single owned mutable state aggregate for the five-city game engine."""
from dataclasses import dataclass, field

from .entities import Actor, Company, Offer, WorldEvent, DuelState
from .cities import CityState
from ..equipment import GearItem


@dataclass
class WorldState:
    actors: dict[str, Actor]
    cities: dict[str, CityState]
    companies: dict[str, Company] = field(default_factory=dict)
    offers: dict[int, Offer] = field(default_factory=dict)
    gear: dict[int, GearItem] = field(default_factory=dict)
    minute: int = 0
    seed: int = 42
    next_gear_id: int = 1
    next_offer_id: int = 1
    crown_gold: int = 0
    initial_gold: int = 0
    events: list[WorldEvent] = field(default_factory=list)
    command_receipts: dict[str, tuple] = field(default_factory=dict)
    duels: dict[str, DuelState] = field(default_factory=dict)
    last_duels: dict[str, dict] = field(default_factory=dict)
