"""Quantified foot-travel difficulty for the generated hex world.

Terrain is immutable natural geography; roads apply an infrastructure discount.
Difficulty is 1..100 for dry land and None for sea/lakes (not on-foot walkable).
This is a survey forecast and does not replace live five-city travel rules.
"""
from __future__ import annotations

from dataclasses import replace
from math import ceil

from .hexgrid import neighbors
from .society import _crossing_kind

BIOME_DIFFICULTY = {
    "grassland": 17, "steppe": 22, "desert": 26,
    "forest": 33, "taiga": 40, "rainforest": 52,
    "hills": 43, "tundra": 48, "wetland": 60,
    "mountain": 73, "alpine": 90,
}


def _clamp(value: float) -> int:
    return max(1, min(100, int(round(value))))


def _natural_difficulty(tile, tiles, width: int, height: int) -> int | None:
    """Walking cost derived from terrain, elevation, slope and ground cover."""
    if tile.elevation_m <= 0 or tile.waterbody in ("sea", "lake"):
        return None
    elevations = [
        tiles[ny * width + nx].elevation_m
        for nx, ny in neighbors(tile.x, tile.y, width, height)
        if tiles[ny * width + nx].elevation_m > 0
    ]
    # Smooth local grade proxy: a short steep section counts, but one distant
    # summit should not dominate an otherwise level valley.
    grades = sorted(abs(h - tile.elevation_m) for h in elevations)
    steep = grades[-2] if len(grades) >= 2 else grades[-1] if grades else 0
    base = BIOME_DIFFICULTY.get(tile.biome, 32)
    slope_penalty = min(29, (steep / 85) ** 0.9 * 3.8)
    altitude_penalty = min(16, max(0, tile.elevation_m - 850) / 130)
    river_penalty = 5 if tile.river else 0
    return _clamp(base + slope_penalty + altitude_penalty + river_penalty)


def minutes_per_hex(difficulty: int, cell_km: float = 3.0) -> float:
    """Survey walking minutes for one equal-length hex edge.

    At 3 km resolution, level unpaved ground is about 45 minutes, cobblestone
    approaches about 30, and high rugged mountains can exceed 2 hours.
    """
    if type(difficulty) is not int or not 1 <= difficulty <= 100:
        raise ValueError("Dry-land difficulty must be an integer from 1 to 100")
    if not 0.5 <= cell_km <= 25:
        raise ValueError("Cell distance must be 0.5..25 km")
    return cell_km * 15.0 * (0.55 + difficulty / 45.0)


def path_minutes(tiles, width: int, path, cell_km: float = 3.0) -> int:
    """Compute time from the exact road/terrain difficulty of each crossed hex."""
    total = 0.0
    for a, b in zip(path, path[1:]):
        ta, tb = tiles[a[1] * width + a[0]], tiles[b[1] * width + b[0]]
        if ta.travel_difficulty is None or tb.travel_difficulty is None:
            raise ValueError("A foot journey cannot cross an ocean or lake")
        step = (ta.travel_difficulty + tb.travel_difficulty) / 2
        # The per-hex model is interpolated for the shared edge.
        total += cell_km * 15 * (0.55 + step / 45)
        if _crossing_kind(ta, tb) == "ford":
            total += 10  # Wading, unloading gear; bridges add no extra delay.
    return max(1, ceil(total)) if len(path) > 1 else 0


def survey_land_access(tiles, roads, width: int, height: int, cell_km: float):
    """Return new, road-aware tile records and recomputed road travel times."""
    surfaces = {}
    for road in roads:
        for position in road.path:
            if position not in surfaces or road.surface == "cobblestone":
                surfaces[position] = road.surface
    revised = []
    for tile in tiles:
        natural = _natural_difficulty(tile, tiles, width, height)
        surface = surfaces.get((tile.x, tile.y))
        if natural is None:
            revised.append(replace(tile, natural_difficulty=None,
                                   travel_difficulty=None, road_surface=None))
            continue
        effective = natural
        if surface == "cobblestone":
            effective = max(5, _clamp(natural * .24))
        elif surface == "dirt":
            effective = max(12, _clamp(natural * .55))
        revised.append(replace(tile, natural_difficulty=natural,
                               travel_difficulty=effective,
                               road_surface=surface))
    result = tuple(revised)
    new_roads = tuple(replace(road, travel_minutes=path_minutes(result, width,
                                                                road.path, cell_km))
                      for road in roads)
    return result, new_roads
