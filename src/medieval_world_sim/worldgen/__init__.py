"""Seeded geography-first world generation, isolated from live game-state replay."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .society import ExplorationSite, Road, Settlement, generate_roads, generate_settlements, generate_sites
from .terrain import Tile, generate_terrain
from .hydrology import Waterway, survey_water
from .landmarks import Landmark, generate_landmarks
from .content import EventLocation, apply_content
from .access import survey_land_access
from .history import WorldHistory, generate_history
from dataclasses import replace

GENERATOR_VERSION = 7


@dataclass(frozen=True)
class GeneratedWorld:
    seed: int
    version: int
    width: int
    height: int
    cell_km: float
    tiles: tuple[Tile, ...]
    settlements: tuple[Settlement, ...]
    roads: tuple[Road, ...]
    sites: tuple[ExplorationSite, ...]
    waterways: tuple[Waterway, ...]
    landmarks: tuple[Landmark, ...]
    event_locations: tuple[EventLocation, ...] = ()
    history: WorldHistory | None = None

    def tile(self, x: int, y: int) -> Tile:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError("Outside generated map")
        return self.tiles[y * self.width + x]

    def to_dict(self) -> dict:
        """A self-contained, versioned snapshot for future explicit migration."""
        return asdict(self)


def generate_world(seed: int = 42, width: int = 80, height: int = 64,
                   cities: int = 12, sites: int = 45, cell_km: float = 3.0,
                   content: dict | None = None) -> GeneratedWorld:
    if type(seed) is not int or not -(2**31) <= seed < 2**31:
        raise ValueError("Seed must be a signed 32-bit integer")
    if not 0.5 <= cell_km <= 25:
        raise ValueError("cell_km must be 0.5..25")
    tiles, waterways = survey_water(generate_terrain(seed, width, height), width,
                                   height, cell_km)
    settlements = generate_settlements(tiles, width, height, cities)
    roads = generate_roads(tiles, width, height, settlements, cell_km)
    tiles, roads = survey_land_access(tiles, roads, width, height, cell_km)
    places = generate_sites(tiles, width, height, settlements, roads, sites)
    landmarks = generate_landmarks(tiles, width, height, settlements, roads, waterways)
    generated = GeneratedWorld(seed, GENERATOR_VERSION, width, height, cell_km,
                               tiles, settlements, roads, places, waterways, landmarks)
    authored = apply_content(generated, content) if content is not None else generated
    return replace(authored, history=generate_history(authored))


__all__ = ["GENERATOR_VERSION", "GeneratedWorld", "generate_world"]
