"""Found settlements, then roads and wilderness sites from generated terrain."""
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import hypot, sqrt
from .terrain import RESOURCE_KEYS, Tile, neighbors
from .hexgrid import hex_distance

BIOME_PREFIX = {
    "forest": "Elder", "rainforest": "Viridian", "taiga": "Frost", "grassland": "Golden",
    "steppe": "Ash", "desert": "Dust", "hills": "Stone", "mountain": "Iron",
    "wetland": "Mist", "tundra": "Winter", "alpine": "High",
}
SUFFIX = ("ford", "mere", "vale", "watch", "hollow", "stead", "haven", "ridge", "brook", "fall")


@dataclass(frozen=True)
class Settlement:
    id: str
    name: str
    x: int
    y: int
    population: int
    livelihood: str
    water_access: str
    biome: str
    production: dict[str, int]  # inferred deposits / simulated hour, not starting stock


@dataclass(frozen=True)
class Road:
    a: str
    b: str
    path: tuple[tuple[int, int], ...]
    distance_km: float
    travel_minutes: int
    crossings: int
    surface: str = "dirt"  # inferred infrastructure, not a random decoration


@dataclass(frozen=True)
class ExplorationSite:
    id: str
    name: str
    kind: str
    x: int
    y: int
    danger: int
    biome: str
    clue: str


def _dist(a, b) -> float:
    return hypot(a.x - b.x, a.y - b.y)


def _nearby(tiles: tuple[Tile, ...], width: int, height: int, x: int, y: int, radius: int):
    for ny in range(max(0, y - radius), min(height, y + radius + 1)):
        for nx in range(max(0, x - radius), min(width, x + radius + 1)):
            if (nx - x) ** 2 + (ny - y) ** 2 <= radius ** 2:
                tile = tiles[ny * width + nx]
                if tile.elevation_m > 0:
                    yield tile


def _production(tiles, width, height, x, y) -> dict[str, int]:
    catchment = list(_nearby(tiles, width, height, x, y, 5))
    if not catchment:
        return {}
    result = {}
    for good in RESOURCE_KEYS:
        potential = sum(t.resources.get(good, 0) for t in catchment) / len(catchment)
        if potential >= 16:
            result[good] = min(4, max(1, int(round(potential / 23))))
    return result


def generate_settlements(tiles: tuple[Tile, ...], width: int, height: int,
                         count: int = 12) -> tuple[Settlement, ...]:
    if not 3 <= count <= 30:
        raise ValueError("City count must be 3..30")
    # Roads are land-only in v1. Keep founding sites on the largest connected
    # mainland until ports, boats and over-water travel exist.
    land = {(t.x, t.y) for t in tiles if t.elevation_m > 0}
    components = []
    while land:
        start = min(land)
        frontier = [start]
        component = {start}
        land.remove(start)
        while frontier:
            px, py = frontier.pop()
            for point in neighbors(px, py, width, height):
                if point in land:
                    land.remove(point)
                    component.add(point)
                    frontier.append(point)
        components.append(component)
    mainland = max(components, key=len)
    candidates = []
    for y in range(3, height - 3, 2):
        for x in range(3, width - 3, 2):
            tile = tiles[y * width + x]
            if (x, y) not in mainland or tile.elevation_m > 1450:
                continue
            surrounding = list(_nearby(tiles, width, height, x, y, 3))
            local_slope = max(abs(t.elevation_m - tile.elevation_m) for t in surrounding)
            if local_slope > 690:
                continue
            fresh = any(t.river for t in surrounding)
            sea = any(t.elevation_m <= 0 for t in
                      (tiles[ny * width + nx] for nx, ny in neighbors(x, y, width, height)))
            mean_soil = sum(t.soil for t in surrounding) / len(surrounding)
            product = _production(tiles, width, height, x, y)
            diversity = sum(v > 0 for v in product.values())
            score = (mean_soil * 0.33 + 15 * fresh + 7 * sea + diversity * 3.5
                     - local_slope * 0.025 - abs(tile.temperature_c - 13) * 0.5)
            candidates.append((score, x, y, fresh, sea, product))
    if len(candidates) < count:
        raise ValueError("Not enough inhabitable settlement locations")
    selected = []
    min_spacing = max(5, int(sqrt(width * height / count) * 0.65))
    for _ in range(count):
        while True:
            eligible = []
            for c in candidates:
                if any(hypot(c[1] - s[1], c[2] - s[2]) < min_spacing for s in selected):
                    continue
                gap = min((hypot(c[1] - s[1], c[2] - s[2]) for s in selected), default=15)
                # Coverage rewards distant basins; water/soil/resources are primary.
                spread = min(22, gap) * 1.3 if selected else 0
                represented = {k for s in selected for k in s[5]}
                novelty = sum(3 for k in c[5] if k not in represented)
                eligible.append((c[0] + spread + novelty, c))
            if eligible or min_spacing <= 2:
                break
            min_spacing -= 1
        if not eligible:
            raise ValueError("Map too small for requested settlements")
        selected.append(max(eligible, key=lambda t: (t[0], -t[1][2], -t[1][1]))[1])

    # Capital is chosen for access to the whole settlement network and nearby
    # productive lands; no settlement receives a randomly preassigned role.
    def capital_score(c):
        return (c[0] * 0.8 - sum(hypot(c[1] - s[1], c[2] - s[2]) for s in selected) / count * 2.2)
    capital = max(selected, key=capital_score)
    ordered = [capital] + sorted((c for c in selected if c is not capital), key=lambda c: (c[2], c[1]))
    settlements = []
    names = set()
    for idx, (_, x, y, fresh, sea, product) in enumerate(ordered):
        tile = tiles[y * width + x]
        if idx == 0:
            name, ident = "Crownreach", "crownreach"
        else:
            prefix = BIOME_PREFIX.get(tile.biome, "River")
            suffix = SUFFIX[(x * 3 + y * 7 + idx) % len(SUFFIX)]
            name = prefix + suffix
            if name in names:
                name += str(idx)
            ident = f"settlement-{idx:02d}"
        names.add(name)
        priorities = ("iron_ore", "coal", "timber", "grain", "stone", "herbs", "hides")
        primary = max(priorities, key=lambda r: (product.get(r, 0), -priorities.index(r)))
        livelihood = {"iron_ore": "mining", "coal": "mining", "stone": "quarrying",
                      "timber": "forestry", "grain": "farming", "herbs": "herbalism",
                      "hides": "ranching"}[primary] if product else "trade"
        population = int(75 + tile.soil * 2 + sum(product.values()) * 12 + (240 if idx == 0 else 0))
        settlements.append(Settlement(ident, name, x, y, population, livelihood,
                                      "river" if fresh else "coast" if sea else "wells",
                                      tile.biome, product))
    return tuple(settlements)


def _path(tiles: tuple[Tile, ...], width: int, height: int, start, goal):
    """A* on traversable land. Slope, swamp and river crossings cost time."""
    si, gi = start[1] * width + start[0], goal[1] * width + goal[0]
    queue = [(0., si)]
    best = {si: 0.}
    previous = {}
    while queue:
        _, i = heappop(queue)
        if i == gi:
            route = [i]
            while route[-1] != si:
                route.append(previous[route[-1]])
            return tuple((j % width, j // width) for j in reversed(route)), best[i]
        ix, iy = i % width, i // width
        for nx, ny in neighbors(ix, iy, width, height):
            j = ny * width + nx
            target, source = tiles[j], tiles[i]
            if target.elevation_m <= 0:
                continue
            distance = 1.0  # Every hex edge is one tile-to-tile step.
            slope = abs(target.elevation_m - source.elevation_m)
            cost = distance * (1 + min(4, slope / 440) + (0.55 if target.biome == "wetland" else 0)
                               + (0.20 if target.river and not source.river else 0))
            proposed = best[i] + cost
            if proposed < best.get(j, float("inf")):
                best[j] = proposed
                previous[j] = i
                heuristic = hex_distance((nx, ny), goal)
                heappush(queue, (proposed + heuristic, j))
    raise ValueError("No land route between settlements")


def generate_roads(tiles: tuple[Tile, ...], width: int, height: int,
                   settlements: tuple[Settlement, ...], cell_km: float = 3.0) -> tuple[Road, ...]:
    """Minimum spanning network, plus high-value bypasses where detours are large."""
    connected = {0}
    connections = []
    while len(connected) < len(settlements):
        options = ((hypot(settlements[a].x - settlements[b].x, settlements[a].y - settlements[b].y), a, b)
                   for a in connected for b in range(len(settlements)) if b not in connected)
        _, a, b = min(options)
        connections.append((min(a, b), max(a, b)))
        connected.add(b)
    # Trade bypasses reward complementary local resources, not arbitrary city roles.
    # Distance still matters: a rich market should not justify an implausible road.
    extras = []
    for i, a in enumerate(settlements):
        for j, b in enumerate(settlements):
            if j <= i or (i, j) in connections:
                continue
            distance = _dist(a, b)
            complement = sum(abs(a.production.get(k, 0) - b.production.get(k, 0))
                             for k in RESOURCE_KEYS)
            extras.append((distance / (1 + 0.10 * complement), distance, i, j))
    for _, distance, a, b in sorted(extras):
        if len(connections) >= len(settlements) + max(1, len(settlements) // 6):
            break
        if distance < 23:
            connections.append((a, b))
    roads = []
    for a, b in connections:
        origin, dest = settlements[a], settlements[b]
        path, weighted_cells = _path(tiles, width, height, (origin.x, origin.y), (dest.x, dest.y))
        geometric = len(path) - 1  # Hex edges all have equal physical length.
        crossings = sum(tiles[y * width + x].river and not tiles[py * width + px].river
                        for (px, py), (x, y) in zip(path, path[1:]))
        # High-volume capital approaches earn stone paving; secondary routes
        # remain dirt. Mountain gradients and long construction routes discourage
        # expensive paving. This is an initial proxy for historical traffic.
        includes_capital = "crownreach" in (origin.id, dest.id)
        grades = [abs(tiles[y * width + x].elevation_m -
                      tiles[py * width + px].elevation_m)
                  for (px, py), (x, y) in zip(path, path[1:])]
        roughness = sum(grades) / max(1, len(grades))
        paved = (includes_capital and min(origin.population, dest.population) >= 190
                 and geometric * cell_km <= 135 and roughness <= 210)
        roads.append(Road(origin.id, dest.id, path, round(geometric * cell_km, 1),
                          max(1, int(weighted_cells * cell_km / 4 * 60)), crossings,
                          "cobblestone" if paved else "dirt"))
    return tuple(roads)


def generate_sites(tiles: tuple[Tile, ...], width: int, height: int,
                   settlements: tuple[Settlement, ...], roads: tuple[Road, ...],
                   count: int = 45) -> tuple[ExplorationSite, ...]:
    if not 0 <= count <= 200:
        raise ValueError("Exploration site count must be 0..200")
    road_tiles = {pt for road in roads for pt in road.path}
    ranked = []
    for y in range(2, height - 2, 2):
        for x in range(2, width - 2, 2):
            tile = tiles[y * width + x]
            if tile.elevation_m <= 0:
                continue
            away = min(hypot(x - s.x, y - s.y) for s in settlements)
            if away < 3:
                continue
            close_to_road = any((nx, ny) in road_tiles for nx in range(x - 2, x + 3)
                                 for ny in range(y - 2, y + 3))
            options = []
            if tile.geology == "limestone" and tile.elevation_m > 230:
                options.append((90, "cavern", "Limestone Caverns", "sinkholes and underground passages"))
            if tile.resources.get("iron_ore", 0) > 30 and tile.elevation_m > 550:
                options.append((85, "abandoned_mine", "Abandoned Mine", "exposed ore seams"))
            if tile.biome in ("forest", "taiga", "rainforest") and away > 6:
                options.append((86, "forest_shrine", "Forgotten Shrine", "old-growth woodland"))
            if tile.biome == "wetland":
                options.append((88, "sunken_crypt", "Sunken Crypt", "marshy ground and high water"))
            if tile.biome in ("alpine", "mountain") and away > 7:
                options.append((80, "summit_ruin", "Summit Observatory", "remote mountain peaks"))
            if close_to_road and away > 5:
                options.append((67, "bandit_camp", "Bandit Encampment", "nearby merchant traffic"))
            if close_to_road and away > 3 and tile.biome in ("grassland", "hills", "steppe"):
                options.append((72, "ruined_watch", "Ruined Watchtower", "an old defensive road crossing"))
            if tile.river and away > 5:
                options.append((78, "river_temple", "River Temple", "a remote river bend"))
            for strength, kind, name, clue in options:
                ranked.append((strength + min(away, 20) * 0.8 + tile.resources.get("stone", 0) / 20,
                               x, y, kind, name, clue, away))
    ranked.sort(key=lambda r: (-r[0], r[2], r[1], r[3]))
    taken = []
    sites = []
    kinds: dict[str, int] = {}
    # Density limit stops a mineral-rich ridge from becoming 40 identical mines.
    # Different dungeon archetypes still require appropriate real terrain.
    max_each = max(3, (count + 6) // 7)
    for _, x, y, kind, name, clue, away in ranked:
        if len(sites) >= count:
            break
        if kinds.get(kind, 0) >= max_each or any(hypot(x - px, y - py) < 3.5 for px, py in taken):
            continue
        tile = tiles[y * width + x]
        danger = max(1, min(10, 1 + int(away / 3) + (2 if tile.elevation_m > 1100 else 0)))
        sites.append(ExplorationSite(f"site-{len(sites) + 1:03d}", name, kind, x, y,
                                     danger, tile.biome, clue))
        kinds[kind] = kinds.get(kind, 0) + 1
        taken.append((x, y))
    return tuple(sites)
