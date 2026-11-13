from __future__ import annotations

import heapq
from ..catalog import CITIES
from ..combat import STAMINA_REGEN_MINUTES
from ..content.magic_tree import MANA_REGEN_MINUTES
from ..errors import ActionError
from ..core.exploration import reveal_travel_progress, reveal, current_hex, sight_radius
from ..worldgen.hexgrid import hex_distance, neighbors

HOUR = 60
HEALTH_REGEN_MINUTES = 3
LEGACY_HEALTH_REGEN_MINUTES = 10
DEPOSIT_CAP = 24
TRAVEL_CARGO_LIMIT = 12  # Stricter than the 20-unit in-city inventory limit.


class TravelSystem:
    def __init__(self, world):
        self.world = world

    def travel_route(self, origin: str, destination: str):
        """Shortest route on geographically generated inter-town road edges.

        Returns travel minutes AND every traversed hex; the latter is persisted
        to reveal fog progressively instead of teleporting to a distant city.
        """
        if origin not in CITIES or destination not in CITIES:
            raise ActionError("Unknown city")
        home = self.world.geography_settlements[origin]
        if origin == destination:
            return 0, ((home.x, home.y),)
        edges = {city: [] for city in CITIES}
        for road in self.world.geography.roads:
            edges[road.a].append((road.b, road))
            edges[road.b].append((road.a, road))
        frontier = [(0, origin)]
        best = {origin: 0}
        previous = {}
        while frontier:
            time, city = heapq.heappop(frontier)
            if time != best[city]:
                continue
            if city == destination:
                legs = []
                node = destination
                while node != origin:
                    prev, road = previous[node]
                    leg = road.path if road.a == prev else tuple(reversed(road.path))
                    legs.append(leg)
                    node = prev
                joined = []
                for leg in reversed(legs):
                    joined.extend(leg if not joined else leg[1:])
                return time, tuple(joined)
            for neighbor, road in edges[city]:
                alt = time + road.travel_minutes
                if alt < best.get(neighbor, float("inf")):
                    best[neighbor] = alt
                    previous[neighbor] = (city, road)
                    heapq.heappush(frontier, (alt, neighbor))
        raise ActionError("No road to destination")

    def travel_minutes(self, origin: str, destination: str) -> int:
        return self.travel_route(origin, destination)[0]

    def available_destinations(self, actor) -> set[str]:
        """Book a caravan route to any settlement on the known road network.

        A destination's identity and exact location can remain fogged; the
        road planner can still book the journey. Every intervening hex is
        revealed only as the journey actually progresses through the world.
        """
        return set(CITIES) - {actor.city}

    def hex_minutes(self, actor, x: int, y: int) -> int:
        """A one-hex hike costs terrain-dependent simulated minutes.

        Normal play uses 3–12 minutes; one simulated minute is one real
        second in the explicit accelerated playtest mode. Quoting duration
        does not reveal any unvisited deposit or named landmark.
        """
        tile = self.world.geography.tile(x, y)
        difficulty = tile.travel_difficulty
        return max(3, min(12, 3 + int(difficulty) // 10))

    def terrain_routes(self, actor, goals=None):
        """Shortest dry-land routes, optionally ending once all goals are reached.

        Quoting a two-hex view should not traverse the entire 5,120-cell
        world. A requested distant site still uses exact shortest-path costs.
        Passing no goals retains exhaustive paths for diagnostics and tests.
        """
        start = current_hex(self.world, actor)
        width, height = self.world.geography.width, self.world.geography.height
        costs = {start: 0}
        previous = {}
        queue = [(0, start)]
        remaining = set(goals) if goals is not None else None
        while queue:
            cost, point = heapq.heappop(queue)
            if cost != costs[point]:
                continue
            if remaining is not None:
                remaining.discard(point)
                if not remaining:
                    break
            for nx, ny in neighbors(*point, width, height):
                tile = self.world.geography.tile(nx, ny)
                if tile.elevation_m <= 0 or tile.waterbody in ("sea", "lake"):
                    continue
                target = (nx, ny)
                total = cost + self.hex_minutes(actor, nx, ny)
                if total < costs.get(target, float("inf")):
                    costs[target] = total
                    previous[target] = point
                    heapq.heappush(queue, (total, target))
        return costs, previous

    def selectable_hexes(self, actor):
        """Visible nearby land plus permanently discovered towns and sites."""
        start = current_hex(self.world, actor)
        sight = sight_radius(self.world, actor)
        width, height = self.world.geography.width, self.world.geography.height
        target_positions = set()
        for y in range(max(0, start[1] - sight),
                       min(height, start[1] + sight + 1)):
            for x in range(max(0, start[0] - sight),
                           min(width, start[0] + sight + 1)):
                if hex_distance(start, (x, y)) <= sight:
                    tile = self.world.geography.tile(x, y)
                    if tile.elevation_m > 0 and tile.waterbody not in ("sea", "lake"):
                        target_positions.add((x, y))
        for site in (*self.world.geography.sites,
                     *self.world.geography.landmarks,
                     *self.world.geography.settlements):
            if site.y * width + site.x in actor.explored_hexes:
                tile = self.world.geography.tile(site.x, site.y)
                if tile.elevation_m > 0 and tile.waterbody not in ("sea", "lake"):
                    target_positions.add((site.x, site.y))
        return target_positions - {start}

    def quote_hex_routes(self, actor):
        """Publicly selectable destinations and precise authoritative costs."""
        if actor.destination is not None or actor.hp <= 0 or actor.defeated_until is not None:
            return []
        if any(actor.id in (d.attacker_id, d.defender_id)
               for d in self.world.state.duels.values()):
            return []
        destinations = self.selectable_hexes(actor)
        costs, _ = self.terrain_routes(actor, destinations)
        names = {}
        width = self.world.geography.width
        for place in (*self.world.geography.sites,
                      *self.world.geography.landmarks,
                      *self.world.geography.settlements):
            if place.y * width + place.x in actor.explored_hexes:
                names[(place.x, place.y)] = place.name
        return [{"x": x, "y": y, "minutes": costs[(x, y)],
                 "label": names.get((x, y), f"Hex {x}, {y}")}
                for x, y in sorted(destinations)
                if (x, y) in costs]

    def plan_hex_journey(self, actor, target):
        if target not in self.selectable_hexes(actor):
            raise ActionError("Destination is not visible or a discovered landmark")
        costs, previous = self.terrain_routes(actor, {target})
        if target not in costs:
            raise ActionError("No safe land route to this destination")
        start = current_hex(self.world, actor)
        route = [target]
        while route[-1] != start:
            route.append(previous[route[-1]])
        route.reverse()
        return costs[target], tuple(route)

    def start_travel(self, actor_id: str, destination: str) -> int:
        actor = self.world._actor(actor_id)
        city = self.world._at_city(actor)
        if destination not in self.available_destinations(actor):
            raise ActionError("Destination is not connected to the geographic road network")
        time, path = self.travel_route(city, destination)
        if not time:
            raise ActionError("Already in destination")
        load = sum(actor.inventory.values()) + len(actor.gear_ids)
        capacity = self.world.housing_system.travel_cargo_limit(actor)
        if load > capacity:
            raise ActionError(f"Travel cargo limit is {capacity} units; carrying {load}")
        time = self.world.housing_system.road_minutes(actor, time)
        if "roadcraft" in self.world.state.merit_upgrades.get(actor_id, set()):
            time = max(1, (time * 95 + 99) // 100)
        if actor.magic.road_charm:
            time = max(1, (time * (100 - actor.magic.road_charm) + 99) // 100)
            actor.magic.road_charm = 0
        if self.world.dev_travel_seconds:
            time = max(1, (time + 59) // 60)
        actor.travel.departure_minute = self.world.minute
        actor.travel.route_hexes = path
        actor.travel.route_durations = ()
        actor.travel.route_revealed_index = 0
        actor.travel.hex_target = None
        actor.destination = destination
        actor.arrival_minute = self.world.minute + time
        reveal(self.world, actor, path[0])
        self.world._emit("travel_started", actor.id, city, destination, actor.arrival_minute)
        return time

    def advance(self, minutes: int) -> None:
        self.world._nonnegative(minutes, "minutes")
        start_minute = self.world.minute
        end = self.world.minute + minutes
        # Refill each hourly boundary; record arrivals at their actual times.
        arrivals = sorted(
            (a.arrival_minute, a.id)
            for a in self.world.actors.values() if a.arrival_minute is not None and a.arrival_minute <= end
        )
        boundaries = set(range((self.world.minute // HOUR + 1) * HOUR, end + 1, HOUR))
        boundaries.update(time for time, _ in arrivals)
        for moment in sorted(boundaries):
            self.world.minute = moment
            if moment % 1440 == 0:
                for actor in self.world.actors.values():
                    actor.vitals.hunger = min(3, actor.vitals.hunger + 1)
                self.world.city_demand.settle_day(moment // 1440)
                self.world.regional_trade.replenish_daily()
            if moment % HOUR == 0:
                for city, spec in CITIES.items():
                    for item, rate in spec.deposits.items():
                        self.world.deposits[city][item] = min(DEPOSIT_CAP, self.world.deposits[city][item] + rate)
            for a in self.world.actors.values():
                if a.destination is not None:
                    reveal_travel_progress(self.world, a)
            for arrival, actor_id in arrivals:
                if arrival == moment:
                    a = self.world.actors[actor_id]
                    if a.travel.hex_target is not None:
                        target = a.travel.hex_target
                        a.wilderness_hex = target
                        for town in self.world.geography.settlements:
                            if (town.x, town.y) == target:
                                a.city = town.id
                                a.wilderness_hex = None
                                a.discovered_cities.add(town.id)
                                break
                        self.world._emit("hex_arrived", actor_id, *target)
                    else:
                        a.city = a.destination  # type: ignore[assignment]
                        a.discovered_cities.add(a.city)
                        self.world._emit("arrived", actor_id, a.city)
                    a.destination = None
                    a.arrival_minute = None
                    a.travel.departure_minute = None
                    a.travel.route_hexes = ()
                    a.travel.route_durations = ()
                    a.travel.route_revealed_index = 0
                    a.travel.hex_target = None
        # Regeneration is computed from elapsed discrete world-minute boundaries
        # and is independent of whether time is advanced in one or many steps.
        regen_ticks = end // STAMINA_REGEN_MINUTES - start_minute // STAMINA_REGEN_MINUTES
        mana_ticks = end // MANA_REGEN_MINUTES - start_minute // MANA_REGEN_MINUTES
        # Version 1: +1 HP / 10 min (historical). Version 2: +10% / 3 min,
        # but frozen HP in hospital and full HP on release. Version 3:
        # +10% / 3 min even in hospital, with independent release cooldown.
        # Replay versioning preserves exact prior saved-world outcomes.
        version = getattr(self.world, "_health_regen_version", 3)
        legacy = version == 1
        interval = LEGACY_HEALTH_REGEN_MINUTES if legacy else HEALTH_REGEN_MINUTES
        health_ticks = (end // interval - start_minute // interval
                        if not getattr(self.world, "_legacy_health_regen", False) else 0)
        self.world.minute = end
        for actor in self.world.actors.values():
            if actor.destination is not None:
                reveal_travel_progress(self.world, actor)
        self.world.curriculum_system.settle(end)
        for actor in self.world.actors.values():
            actor.stamina = min(actor.max_stamina, actor.stamina + regen_ticks)
            actor.magic.mana = min(actor.magic.max_mana, actor.magic.mana + mana_ticks)
            # HP recovery and the hospital lock are distinct in version 3:
            # HP can recover to full while the player remains hospitalized.
            if health_ticks and (version == 3 or
                                 (actor.defeated_until is None and actor.hp > 0)):
                gain_per_tick = 1 if legacy else (actor.max_hp + 9) // 10
                actor.hp = min(actor.max_hp, actor.hp + health_ticks * gain_per_tick)
            if actor.defeated_until is not None and actor.defeated_until <= end:
                if version < 3:
                    actor.hp = actor.max_hp
                actor.defeated_until = None
                self.world._emit("recovered", actor.id)
        self.world.assert_invariants()

