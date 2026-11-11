"""Playable realm catalog sourced from the accepted geography-first generator.

The old five-city seed is intentionally retired for fresh worlds. A single
versioned seed (7) drives towns, local deposits, road connections and the map.
""" 
from dataclasses import dataclass

from .industry import (RAW_RESOURCES, PROCESSED_RESOURCES, EQUIPMENT,
                       CONSUMABLES, GOODS, RECIPES, Recipe)
from ..worldgen import generate_world

WORLD_SEED = 7
GEOGRAPHY = generate_world(seed=WORLD_SEED)
CAPITAL = "crownreach"


@dataclass(frozen=True)
class CitySpec:
    name: str
    deposits: dict[str, int]  # potential extraction per simulated hour
    population: int = 120


CITIES = {
    town.id: CitySpec(town.name, dict(town.production), town.population)
    for town in GEOGRAPHY.settlements
}
ROADS = {
    tuple(sorted((road.a, road.b))): road.travel_minutes
    for road in GEOGRAPHY.roads
}
if CAPITAL not in CITIES or len(CITIES) != len(GEOGRAPHY.settlements):
    raise RuntimeError("Invalid geographic town catalog")
