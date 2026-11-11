"""Strategic landmarks inferred from navigability and real built road alignments."""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from .hexgrid import hex_distance, neighbors
from .society import _crossing_kind


@dataclass(frozen=True)
class Landmark:
    id: str
    name: str
    kind: str  # mountain_pass, ford, bridge, harbor, lake_landing
    x: int
    y: int
    importance: int  # 1..10; future trade/quest weight, not a live reward
    reason: str


def generate_landmarks(tiles, width, height, settlements, roads, waterways):
    """Derive crossings, relief bottlenecks and sheltered shores.

    Every marker is grounded in generated tile geometry. Harbor selection is
    based on available shore, navigability and shelter, never a random city role.
    """
    def tile(x, y):
        return tiles[y * width + x]

    named = []
    occupied = set()

    def add(kind, name, x, y, importance, reason):
        key = (kind, x, y)
        if key in occupied:
            return
        occupied.add(key)
        named.append(Landmark(f"landmark-{len(named)+1:03d}", name, kind, x, y,
                              min(10, max(1, importance)), reason))

    # The routes chosen by the construction pathfinder define the *actual*
    # crossings. Do not invent bridges at rivers that a road went around.
    crossing_count = {}
    for road in roads:
        for a, b in zip(road.path, road.path[1:]):
            kind = _crossing_kind(tile(*a), tile(*b))
            if kind:
                crossing_count[(kind, b)] = crossing_count.get((kind, b), 0) + 1
    for (kind, (x, y)), usage in sorted(crossing_count.items(),
                                       key=lambda v: (v[0][1][1], v[0][1][0], v[0][0])):
        flow = tile(x, y).flow
        add(kind, "Stone Bridge" if kind == "bridge" else "Shallow Ford",
            x, y, min(10, 3 + usage + flow // 450),
            "A trade route crosses a deep channel using a built bridge"
            if kind == "bridge" else
            "A trade route takes advantage of a shallow, naturally fordable reach")

    # Pass candidates are low local saddles between higher mountain shoulders.
    # Distinct roads can share passes, so deduplicate in a few-hex radius.
    passes = []
    for road in roads:
        for x, y in road.path[1:-1]:
            here = tile(x, y)
            if not 340 <= here.elevation_m <= 1850:
                continue
            heights = [tile(nx, ny).elevation_m
                       for nx, ny in neighbors(x, y, width, height)]
            higher = [h for h in heights if h > here.elevation_m + 270]
            if len(higher) < 2:
                continue
            relief = max(heights) - here.elevation_m
            passes.append((relief - here.elevation_m * .06, x, y, here.elevation_m))
    pass_sites = []
    for score, x, y, elevation in sorted(passes, reverse=True):
        if any(hex_distance((x, y), pt) < 5 for pt in pass_sites):
            continue
        add("mountain_pass", "Highland Pass", x, y,
            3 + min(7, int(score / 200)),
            f"A lower route through high ground near {elevation} m elevation")
        pass_sites.append((x, y))
        if len(pass_sites) >= 12:
            break

    # Site a landing on accessible *land* beside genuinely navigable water.
    # Small naturally protected inlets beat exposed headlands at equal distance.
    for settlement in settlements:
        candidates = []
        sx, sy = settlement.x, settlement.y
        for y in range(max(0, sy - 5), min(height, sy + 6)):
            for x in range(max(0, sx - 5), min(width, sx + 6)):
                d = hex_distance((sx, sy), (x, y))
                if d > 5:
                    continue
                here = tile(x, y)
                if here.elevation_m <= 0 or here.waterbody == "lake":
                    continue
                around = [tile(nx, ny) for nx, ny in neighbors(x, y, width, height)]
                ocean = sum(t.waterbody == "sea" for t in around)
                inland = sum(t.waterbody == "lake" for t in around)
                if not (ocean or inland):
                    continue
                kind = "harbor" if ocean else "lake_landing"
                # 1–3 wet neighbor hexes tends to be a sheltered coast.
                wet = ocean if ocean else inland
                shelter = 3 if 1 <= wet <= 3 else 0
                candidates.append((shelter + 5 * bool(ocean) - d
                                   - here.elevation_m / 220, x, y, kind))
        if candidates:
            _, x, y, kind = max(candidates, key=lambda q: (q[0], -q[2], -q[1]))
            add(kind, f"{settlement.name} {'Harbor' if kind == 'harbor' else 'Landing'}",
                x, y, 8 if settlement.id == "crownreach" else 5,
                "A sheltered coastline near a settlement"
                if kind == "harbor" else "Freshwater landing with access to local trade")
    return tuple(named)
