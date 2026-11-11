"""Deterministic inland-water and potential navigation survey.

Lakes are true depressions in the hex elevation field, found by priority flood.
Navigation is *potential*: no player sailing or ship inventory exists yet.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from heapq import heappop, heappush

from .hexgrid import neighbors

LAKE_MIN_DEPTH_M = 18
LAKE_MIN_TILES = 3
LAKE_MAX_TILES = 125
BARGE_MIN_FLOW = 220
BARGE_MAX_DROP_M = 85


@dataclass(frozen=True)
class Waterway:
    id: str
    kind: str  # sea, lake or navigable river reach
    tiles: tuple[tuple[int, int], ...]
    length_km: float
    vessel: str  # coastal vessel, lake boat or river barge


def survey_water(tiles, width: int, height: int, cell_km: float = 3.0):
    """Mark standing inland lakes and navigable water, without changing height.

    Each lake footprint is composed of connected depression cells at least
    18 m below its spill level. Tiny one-cell artifacts and massive unresolved
    closed-basin seas are excluded; those need finer-resolution basin modelling.
    """
    n = width * height
    ground = [t.elevation_m for t in tiles]
    spill = [0.0] * n
    seen = [False] * n
    queue = []
    for y in range(height):
        for x in range(width):
            i = y * width + x
            if ground[i] <= 0 or x in (0, width - 1) or y in (0, height - 1):
                seen[i] = True
                spill[i] = ground[i]
                heappush(queue, (float(ground[i]), i))
    while queue:
        surface, i = heappop(queue)
        for nx, ny in neighbors(i % width, i // width, width, height):
            j = ny * width + nx
            if not seen[j]:
                seen[j] = True
                spill[j] = max(float(ground[j]), surface + .001)
                heappush(queue, (spill[j], j))

    candidate = {i for i in range(n)
                 if ground[i] > 0 and spill[i] - ground[i] >= LAKE_MIN_DEPTH_M}
    lakes = set()
    while candidate:
        start = min(candidate)
        candidate.remove(start)
        component = {start}
        frontier = [start]
        while frontier:
            i = frontier.pop()
            for nx, ny in neighbors(i % width, i // width, width, height):
                j = ny * width + nx
                if j in candidate:
                    candidate.remove(j)
                    component.add(j)
                    frontier.append(j)
        # Large basins are left as terrain pending a separate inland-sea pass.
        if LAKE_MIN_TILES <= len(component) <= LAKE_MAX_TILES:
            lakes.update(component)

    result = []
    for i, t in enumerate(tiles):
        if t.elevation_m <= 0:
            result.append(replace(t, waterbody="sea", navigable=True))
        elif i in lakes:
            result.append(replace(t, biome="lake", river=False, soil=0, resources={},
                                  waterbody="lake", navigable=True))
        else:
            parent = t.drains_to
            drop = (max(0, t.elevation_m - tiles[parent[1] * width + parent[0]].elevation_m)
                    if parent is not None else 10**9)
            barge = t.river and t.flow >= BARGE_MIN_FLOW and drop <= BARGE_MAX_DROP_M
            result.append(replace(t, waterbody="river" if t.river else "land",
                                  navigable=barge))
    result = tuple(result)
    waterways = _waterway_networks(result, width, height, cell_km)
    return result, waterways


def _waterway_networks(tiles, width: int, height: int, cell_km: float):
    """Expose connected navigation networks, rather than disconnected symbols."""
    candidate = {i for i, t in enumerate(tiles) if t.navigable}
    networks = []
    while candidate:
        start = min(candidate)
        candidate.remove(start)
        found = {start}
        frontier = [start]
        while frontier:
            i = frontier.pop()
            for nx, ny in neighbors(i % width, i // width, width, height):
                j = ny * width + nx
                if j in candidate:
                    candidate.remove(j)
                    found.add(j)
                    frontier.append(j)
        members = sorted(found)
        tags = {tiles[i].waterbody for i in members}
        kind = "sea" if "sea" in tags else "lake" if "lake" in tags else "river"
        if kind == "river" and len(members) < 3:
            continue  # Do not advertise isolated rapids as navigable reaches.
        vessel = {"sea": "coastal vessel", "lake": "lake boat",
                  "river": "river barge"}[kind]
        network = tuple((i % width, i // width) for i in members)
        networks.append(Waterway(f"waterway-{len(networks)+1:03d}", kind,
                                 network, round(len(members)*cell_km, 1), vessel))
    return tuple(networks)
