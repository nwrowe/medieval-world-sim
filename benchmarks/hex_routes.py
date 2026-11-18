"""Reproducible, non-gating comparison of legacy and road-aware hex routing.

Usage: PYTHONPATH=src python benchmarks/hex_routes.py
All trials use the same generated world and reachable goal sets. Timing is
environment-dependent; compare measurements on the same runner.
"""
from __future__ import annotations

from math import ceil
from statistics import median
from time import perf_counter
import tracemalloc

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.core.exploration import current_hex
from medieval_world_sim.worldgen.hexgrid import hex_distance


def measure(planner, actor, goals, mode, trials=12):
    results = []
    for _ in range(trials):
        planner.world._legacy_terrain_routing = mode == "legacy"
        if mode != "cached":
            planner._route_cache.clear()
        start = perf_counter()
        distances, _ = planner.terrain_routes(actor, goals)
        results.append(1000 * (perf_counter() - start))
        if not goals.issubset(distances):
            raise AssertionError("Routing omitted a reachable destination")
    planner.world._legacy_terrain_routing = False
    ordered = sorted(results)
    return median(ordered), ordered[ceil(0.95 * len(ordered)) - 1]


def main():
    world = WorldEngine([Actor("route-bench", "human", city=CAPITAL)])
    actor = world.actors["route-bench"]
    planner = world.travel
    origin = current_hex(world, actor)
    planner.road_edges()
    costs, _ = planner.terrain_routes(actor)
    reachable = sorted(p for p in costs if hex_distance(origin, p) > 9)
    if len(reachable) < 50:
        raise AssertionError("Need at least 50 reachable distant hexes")
    sample = reachable[::max(1, len(reachable) // 50)][:50]
    print("Hex-routing benchmark (ms): world cells=", len(world.geography.tiles),
          "reachable dry land=", len(costs))
    print("destinations,mode,p50_ms,p95_ms")
    for count in (5, 10, 50):
        goals = set(sample[:count])
        for mode in ("legacy", "cold", "cached"):
            p50, p95 = measure(planner, actor, goals, mode)
            print(f"{count},{mode},{p50:.3f},{p95:.3f}")
    # Peak incremental allocation for a single cold full-world quote tree.
    planner._route_cache.clear()
    tracemalloc.start()
    planner.terrain_routes(actor, set(sample))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print("peak_alloc_KiB=", round(peak / 1024, 1),
          "cached_origins=", len(planner._route_cache))


if __name__ == "__main__":
    main()
