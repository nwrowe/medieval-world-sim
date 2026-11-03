"""Single owned mutable state aggregate for the five-city game engine."""
from dataclasses import dataclass, field

from .entities import Actor, Company, Offer, WorldEvent, DuelState
from .cities import CityState
from ..equipment import GearItem
from ..systems.guilds import Guild, WarRecord


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
    church_healed_day: dict[str, int] = field(default_factory=dict)
    horses: dict[str, list[str]] = field(default_factory=dict)
    riding_xp: dict[str, int] = field(default_factory=dict)
    last_race_minute: dict[str, int] = field(default_factory=dict)
    race_results: dict[str, dict] = field(default_factory=dict)
    guilds: dict[str, Guild] = field(default_factory=dict)
    next_guild_id: int = 1
    wars: dict[str, WarRecord] = field(default_factory=dict)
    merit_claims: dict[str, set[str]] = field(default_factory=dict)
    merit_balance: dict[str, int] = field(default_factory=dict)
    merit_upgrades: dict[str, set[str]] = field(default_factory=dict)
