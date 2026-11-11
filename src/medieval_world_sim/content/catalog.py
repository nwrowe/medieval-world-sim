"""Playable realm catalog sourced from the accepted geography-first generator.

The old five-city seed is intentionally retired for fresh worlds. A single
versioned seed (7) drives towns, local deposits, road connections and the map.
""" 
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path

from .industry import (RAW_RESOURCES, PROCESSED_RESOURCES, EQUIPMENT,
                       CONSUMABLES, GOODS, RECIPES, Recipe)
from ..worldgen import generate_world
from ..worldgen.content import load_content

# Seed 7 is a development preview. Operators must choose a private seed
# for public worlds, otherwise a public repository could reveal all ruins.
try:
    WORLD_SEED = int(os.environ.get("OATHMERE_WORLD_SEED", "7"))
except ValueError as exc:
    raise RuntimeError("OATHMERE_WORLD_SEED must be a signed 32-bit integer") from exc
_CONTENT_FILE = os.environ.get("OATHMERE_WORLD_CONTENT", "").strip()
_AUTHORED = load_content(Path(_CONTENT_FILE)) if _CONTENT_FILE else None
GEOGRAPHY = generate_world(seed=WORLD_SEED, content=_AUTHORED)
GEOGRAPHY_FINGERPRINT = sha256(json.dumps({
    "version": GEOGRAPHY.version,
    "seed": WORLD_SEED,
    "width": GEOGRAPHY.width, "height": GEOGRAPHY.height,
    "cell_km": GEOGRAPHY.cell_km,
    "tiles": [(t.elevation_m, t.biome, t.geology, t.soil, t.river,
               t.flow, t.resources, t.waterbody, t.travel_difficulty)
              for t in GEOGRAPHY.tiles],
    "settlements": [(t.id, t.name, t.x, t.y, t.production)
                    for t in GEOGRAPHY.settlements],
    "roads": [(r.a, r.b, r.path, r.travel_minutes) for r in GEOGRAPHY.roads],
    "sites": [(s.id, s.name, s.x, s.y, s.kind) for s in GEOGRAPHY.sites],
    "landmarks": [(p.id, p.name, p.x, p.y, p.kind)
                  for p in GEOGRAPHY.landmarks],
    "events": [(ev.id, ev.name, ev.x, ev.y, ev.starts_at, ev.ends_at)
               for ev in GEOGRAPHY.event_locations],
}, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
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
