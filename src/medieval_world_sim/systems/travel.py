from __future__ import annotations

import heapq
from ..catalog import CITIES, ROADS
from ..combat import STAMINA_REGEN_MINUTES
from ..errors import ActionError

HOUR = 60
DEPOSIT_CAP = 24
TRAVEL_CARGO_LIMIT = 12  # Stricter than the 20-unit in-city inventory limit.


class TravelSystem:
    def __init__(self, world):
        self.world = world

    def travel_minutes(self, origin: str, destination: str) -> int:
        if origin not in CITIES or destination not in CITIES:
            raise ActionError("Unknown city")
        if origin == destination:
            return 0
        edges: dict[str, list[tuple[str, int]]] = {city: [] for city in CITIES}
        for (a, b), time in ROADS.items():
            edges[a].append((b, time))
            edges[b].append((a, time))
        frontier = [(0, origin)]
        best = {origin: 0}
        while frontier:
            time, city = heapq.heappop(frontier)
            if city == destination:
                return time
            if time != best[city]:
                continue
            for neighbor, minutes in edges[city]:
                alt = time + minutes
                if alt < best.get(neighbor, float("inf")):
                    best[neighbor] = alt
                    heapq.heappush(frontier, (alt, neighbor))
        raise ActionError("No road to destination")

    def start_travel(self, actor_id: str, destination: str) -> int:
        actor = self.world._actor(actor_id)
        city = self.world._at_city(actor)
        time = self.world.travel_minutes(city, destination)
        if time == 0:
            raise ActionError("Already in destination")
        load = sum(actor.inventory.values()) + len(actor.gear_ids)
        if load > TRAVEL_CARGO_LIMIT:
            raise ActionError(f"Travel cargo limit is {TRAVEL_CARGO_LIMIT} units; carrying {load}")
        actor.destination = destination
        actor.arrival_minute = self.world.minute + time
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
            for arrival, actor_id in arrivals:
                if arrival == moment:
                    a = self.world.actors[actor_id]
                    a.city = a.destination  # type: ignore[assignment]
                    a.destination = None
                    a.arrival_minute = None
                    self.world._emit("arrived", actor_id, a.city)
        # Regeneration is computed from elapsed discrete world-minute boundaries
        # and is independent of whether time is advanced in one or many steps.
        regen_ticks = end // STAMINA_REGEN_MINUTES - start_minute // STAMINA_REGEN_MINUTES
        self.world.minute = end
        for actor in self.world.actors.values():
            actor.stamina = min(actor.max_stamina, actor.stamina + regen_ticks)
            if actor.defeated_until is not None and actor.defeated_until <= end:
                actor.hp = actor.max_hp
                actor.defeated_until = None
                self.world._emit("recovered", actor.id)
        self.world.assert_invariants()

