"""Authoritative, durable hex discovery and fog-of-war projections.

All sensitive locations and terrain resources are filtered by the server
before delivery to any client. Only coarse gray relief is public to everyone.
"""
from __future__ import annotations

from . import entities
from ..worldgen.hexgrid import hex_distance

BASE_SIGHT = 2
MAX_SIGHT = 4


def sight_radius(world, actor: entities.Actor) -> int:
    upgrades = world.state.merit_upgrades.get(actor.id, set())
    return BASE_SIGHT + int("awareness_1" in upgrades) + int("awareness_2" in upgrades)


def current_hex(world, actor: entities.Actor) -> tuple[int, int]:
    path = actor.travel.route_hexes
    start = actor.travel.departure_minute
    end = actor.arrival_minute
    if actor.destination is not None and path and start is not None and end is not None:
        duration = max(1, end - start)
        elapsed = max(0, min(duration, world.minute - start))
        step = min(len(path) - 1, elapsed * (len(path) - 1) // duration)
        return path[step]
    settlement = world.geography_settlements[actor.city]
    return (settlement.x, settlement.y)


def nearby_indices(geography, x: int, y: int, radius: int) -> set[int]:
    """Exact six-way hex neighborhood, clipped to world bounds."""
    found = set()
    for ny in range(max(0, y - radius), min(geography.height, y + radius + 1)):
        for nx in range(max(0, x - radius), min(geography.width, x + radius + 1)):
            if hex_distance((x, y), (nx, ny)) <= radius:
                found.add(ny * geography.width + nx)
    return found


def reveal(world, actor: entities.Actor, point: tuple[int, int]) -> None:
    """Called on spawn, a traveled hex, or an Awareness purchase—not by a read."""
    x, y = point
    actor.explored_hexes.update(nearby_indices(world.geography, x, y,
                                               sight_radius(world, actor)))
    for town in world.geography.settlements:
        if hex_distance(point, (town.x, town.y)) <= sight_radius(world, actor):
            actor.discovered_cities.add(town.id)


def reveal_travel_progress(world, actor: entities.Actor) -> None:
    """Reveal every traversed hex exactly once, even for large time jumps."""
    path = actor.travel.route_hexes
    if not path or actor.arrival_minute is None or actor.travel.departure_minute is None:
        return
    total = max(1, actor.arrival_minute - actor.travel.departure_minute)
    elapsed = max(0, min(total, world.minute - actor.travel.departure_minute))
    last = min(len(path) - 1, elapsed * (len(path) - 1) // total)
    for i in range(actor.travel.route_revealed_index + 1, last + 1):
        reveal(world, actor, path[i])
    actor.travel.route_revealed_index = max(last, actor.travel.route_revealed_index)


def public_relief(geography) -> str:
    """A non-secret grayscale surface: water, lowlands, hills, mountains.

    Deliberately excludes resources, roads, towns, ruins, water routes, and
    exact elevations. This is safe to give to an unexplored character.
    """
    def tone(t):
        if t.waterbody in ("sea", "lake"):
            return "0"
        if t.elevation_m >= 1450:
            return "4"
        if t.elevation_m >= 750:
            return "3"
        if t.elevation_m >= 250:
            return "2"
        return "1"
    return "".join(tone(tile) for tile in geography.tiles)


def map_projection(world, actor: entities.Actor) -> dict:
    """Only reveal information within the actor's *durable* explored set."""
    geography = world.geography
    pos = current_hex(world, actor)
    visible = nearby_indices(geography, *pos, sight_radius(world, actor))
    observed = actor.explored_hexes
    # A never-seen hex is public relief only; no resource, exact elevation,
    # settlement position/name or site data is included in this response.
    roads = set()
    edges = set()
    for road in geography.roads:
        for a, b in zip(road.path, road.path[1:]):
            ia = a[1] * geography.width + a[0]
            ib = b[1] * geography.width + b[0]
            if ia in observed and ib in observed:
                edge = (ia, ib) if ia < ib else (ib, ia)
                edges.add(edge)
                roads.update((ia, ib))
    landmarks = {}
    for site in geography.sites:
        index = site.y * geography.width + site.x
        if index in observed:
            landmarks.setdefault(index, []).append({"name":site.name,"kind":site.kind})
    for mark in geography.landmarks:
        index = mark.y * geography.width + mark.x
        if index in observed:
            landmarks.setdefault(index, []).append({"name":mark.name,"kind":mark.kind})
    details = []
    for index in sorted(observed):
        tile = geography.tiles[index]
        details.append({
            "i": index, "biome": tile.biome,
            "elevation_m": tile.elevation_m,
            "road": index in roads,
            "resources": dict(tile.resources),
            "sites": landmarks.get(index, []),
            "visible": index in visible,
        })
    towns = [{
        "id": town.id, "name": town.name, "x": town.x, "y": town.y,
        "current": town.id == actor.city and actor.destination is None,
    } for town in geography.settlements
        if town.y * geography.width + town.x in observed]
    return {
        "width": geography.width, "height": geography.height,
        "relief": public_relief(geography),
        "tiles": details,
        "roads": [list(edge) for edge in sorted(edges)],
        "towns": towns, "position": list(pos),
        "sight_radius": sight_radius(world, actor),
        "explored_count": len(observed), "total_hexes": len(geography.tiles),
    }
