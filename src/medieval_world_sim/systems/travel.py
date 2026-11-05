from __future__ import annotations

import heapq
from ..catalog import CITIES, ROADS
from ..combat import STAMINA_REGEN_MINUTES
from ..content.magic_tree import MANA_REGEN_MINUTES
from ..errors import ActionError

HOUR = 60
HEALTH_REGEN_MINUTES = 3
LEGACY_HEALTH_REGEN_MINUTES = 10
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
        capacity = self.world.housing_system.travel_cargo_limit(actor)
        if load > capacity:
            raise ActionError(f"Travel cargo limit is {capacity} units; carrying {load}")
        time = self.world.housing_system.road_minutes(actor, time)
        if "roadcraft" in self.world.state.merit_upgrades.get(actor_id, set()):
            time = max(1, (time * 95 + 99) // 100)
        if actor.magic.road_charm:
            time = max(1, (time * (100 - actor.magic.road_charm) + 99) // 100)
            actor.magic.road_charm = 0
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
                    a.discovered_cities.add(a.city)
                    a.destination = None
                    a.arrival_minute = None
                    self.world._emit("arrived", actor_id, a.city)
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

