"""Deterministic terrain, climate, drainage and geology; no game-state mutations.

All noise uses integer mixing rather than Python's process-randomized hash().
Water drains over a priority-flood depression-filled surface so rivers cannot loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import exp, sin

from .hexgrid import neighbors

SEA_LEVEL = 0
RESOURCE_KEYS = ("iron_ore", "coal", "stone", "timber", "herbs", "grain",
                 "hides", "vegetables", "meat")


@dataclass(frozen=True)
class Tile:
    x: int
    y: int
    elevation_m: int
    temperature_c: int
    rainfall_mm: int
    biome: str
    geology: str
    soil: int
    river: bool
    flow: int
    resources: dict[str, int]  # potential 0..100; not a mutable inventory
    drains_to: tuple[int, int] | None = None  # computed hydrological parent, not navigation
    waterbody: str = "land"  # land, sea, lake or river
    navigable: bool = False  # survey potential, not a live travel permission


def _hash(seed: int, x: int, y: int) -> float:
    n = (seed * 2654435761 + x * 374761393 + y * 668265263) & 0xFFFFFFFF
    n ^= n >> 13
    n = (n * 1274126177) & 0xFFFFFFFF
    n ^= n >> 16
    return n / 0xFFFFFFFF


def _noise(seed: int, x: float, y: float) -> float:
    ix, iy = int(x // 1), int(y // 1)
    fx, fy = x - ix, y - iy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a = _hash(seed, ix, iy) * (1 - fx) + _hash(seed, ix + 1, iy) * fx
    b = _hash(seed, ix, iy + 1) * (1 - fx) + _hash(seed, ix + 1, iy + 1) * fx
    return a * (1 - fy) + b * fy


def _fbm(seed: int, x: float, y: float) -> float:
    value, weight, total, frequency = 0.0, 1.0, 0.0, 3.0
    for octave in range(4):
        value += weight * _noise(seed + 107 * octave, x * frequency, y * frequency)
        total += weight
        weight *= 0.53
        frequency *= 2
    return value / total


def generate_terrain(seed: int, width: int, height: int) -> tuple[Tile, ...]:
    """Generate a landmass, orographic climate, drainage and resource potential."""
    if not 32 <= width <= 180 or not 24 <= height <= 140:
        raise ValueError("Terrain dimensions must be 32..180 by 24..140")
    n = width * height
    elevation, rain, temp, geology = [0] * n, [0] * n, [0] * n, [""] * n
    for y in range(height):
        yy = y / (height - 1)
        # The coast is a warped multi-scale boundary, not a single smoothed
        # north/south curve. Large bays coexist with smaller coves and headlands.
        coastal_sweep = _noise(seed + 3, yy * 3.0, 0)
        tidal_inlets = _noise(seed + 103, yy * 8.0, 0.37)
        coast = (0.055 + 0.14 * coastal_sweep + 0.07 * (tidal_inlets - 0.5)
                 + 0.027 * sin(yy * 26 + seed * .73))
        # The tectonic axis wanders and is interrupted by lower mountain passes.
        ridge = (0.51 + 0.085 * sin(yy * 7 + seed % 17)
                 + 0.10 * (_fbm(seed + 5, 0.35, yy * 2.5) - .5)
                 + 0.032 * sin(yy * 23 + seed * .37))
        ridge_width = 0.068 + 0.05 * _noise(seed + 127, yy * 5, 0.7)
        for x in range(width):
            i = y * width + x
            xx = x / (width - 1)
            # Coast perturbation depends on both axes. Erosion and local
            # topography can push the shoreline landward at isolated inlets.
            waterline = coast + 0.068 * (_fbm(seed + 131, xx * 2.8, yy * 2.8) - 0.5)
            relief = _fbm(seed + 11, xx * 1.7, yy * 1.7) - 0.5
            folds = _fbm(seed + 17, xx * 3.2, yy * 3.2)
            summit_noise = 1 - abs(2 * _fbm(seed + 139, xx * 5.1, yy * 5.1) - 1)
            primary = 1780 * exp(-((xx - ridge) / ridge_width) ** 2)
            spur_axis = ridge + 0.125 * sin(yy * 11 + seed * .31)
            spurs = 550 * exp(-((xx - spur_axis) / 0.057) ** 2)
            mountain = ((primary * (0.28 + 1.18 * folds) + spurs * summit_noise)
                        * (0.68 + 0.52 * _noise(seed + 149, yy * 10, xx * 1.7)))
            altitude = int(65 + max(0, xx - waterline) * 440 + mountain + relief * 850)
            if xx < waterline:
                altitude = -int(75 + (waterline - xx) * 1750)
            elevation[i] = altitude
            eastern_shadow = 1 / (1 + exp(-23 * (xx - ridge - 0.09)))
            rain[i] = max(100, int(1100 + 720 * (_fbm(seed + 23, xx, yy) - 0.5)
                                   - 680 * eastern_shadow + 150 * (1 - xx)))
            temp[i] = int(16 + (yy - 0.5) * 21 - max(0, altitude) / 190
                          + 5 * (_fbm(seed + 29, xx, yy) - 0.5))
            rock = _fbm(seed + 31, xx, yy)
            if altitude < 0:
                geology[i] = "seabed"
            elif altitude > 1250 or (altitude > 580 and rock > 0.52):
                geology[i] = "igneous" if rock > 0.56 else "metamorphic"
            elif 250 < altitude < 1000 and rock < 0.36:
                geology[i] = "limestone"
            elif altitude < 700 and xx > ridge + 0.08 and rock > 0.49:
                geology[i] = "coal_basin"
            else:
                geology[i] = "sedimentary"

    # Priority flood: each land tile receives a downstream predecessor with
    # strictly earlier visit order. Depression filling prevents cyclic rivers.
    seen = [False] * n
    downstream = [-1] * n
    order: list[int] = []
    heap: list[tuple[float, int]] = []
    for y in range(height):
        for x in range(width):
            i = y * width + x
            if elevation[i] < SEA_LEVEL or x in (0, width - 1) or y in (0, height - 1):
                seen[i] = True
                heappush(heap, (float(elevation[i]), i))
    while heap:
        surface, i = heappop(heap)
        order.append(i)
        for nx, ny in neighbors(i % width, i // width, width, height):
            j = ny * width + nx
            if not seen[j]:
                seen[j] = True
                downstream[j] = i
                heappush(heap, (max(float(elevation[j]), surface + 0.001), j))
    # Local precipitation, then accumulated upstream catchment flow.
    flow = [0] * n
    for i in reversed(order):
        if elevation[i] > 0:
            flow[i] += max(1, rain[i] // 350)
        parent = downstream[i]
        if parent >= 0:
            flow[parent] += flow[i]

    result = []
    for y in range(height):
        for x in range(width):
            i = y * width + x
            h, t, rainfall, rock = elevation[i], temp[i], rain[i], geology[i]
            river = h > 0 and flow[i] >= 72
            if h < 0:
                biome = "ocean"
            elif h > 1950:
                biome = "alpine"
            elif h > 1150:
                biome = "mountain"
            elif t < -2:
                biome = "tundra"
            elif river and h < 380 and rainfall > 900:
                biome = "wetland"
            elif rainfall < 480:
                biome = "desert" if t > 11 else "steppe"
            elif rainfall < 790:
                biome = "steppe" if h < 700 else "hills"
            elif h > 820:
                biome = "hills"
            elif t < 5:
                biome = "taiga"
            elif rainfall > 1450 and t > 18:
                biome = "rainforest"
            elif rainfall > 1080:
                biome = "forest"
            else:
                biome = "grassland"
            moist = min(100, rainfall // 15)
            soil = max(0, min(100, int(moist * 0.85 + (20 if river else 0)
                  + 20 * (_fbm(seed + 37, x / width, y / height) - 0.5)
                  - max(0, h - 400) / 31))) if h > 0 else 0
            nearby_woods = biome in ("forest", "taiga", "rainforest")
            pasture = biome in ("grassland", "steppe", "forest", "taiga")
            values = {
                "iron_ore": int(75 * _fbm(seed + 41, x / width, y / height)) if rock in ("igneous", "metamorphic") and h > 350 else 0,
                "coal": int(75 * _fbm(seed + 43, x / width, y / height)) if rock == "coal_basin" else 0,
                "stone": min(100, 20 + h // 30) if rock in ("igneous", "metamorphic", "limestone") and h > 0 else 0,
                "timber": 65 + min(30, rainfall // 80) if nearby_woods else 0,
                "herbs": min(90, 20 + moist // 2) if biome in ("forest", "wetland", "grassland") else 0,
                "grain": min(100, soil + 10) if biome in ("grassland", "forest") and t > 4 else 0,
                "hides": 55 if pasture else 0,
                "vegetables": soil if soil > 42 and t > 3 and biome in ("grassland", "forest", "wetland") else 0,
                "meat": 55 if pasture else 0,
            }
            result.append(Tile(x, y, h, t, rainfall, biome, rock, soil,
                               river, flow[i], {k: min(100, v) for k, v in values.items() if v >= 30},
                               ((downstream[i] % width, downstream[i] // width)
                                if h > 0 and downstream[i] >= 0 else None)))
    return tuple(result)
