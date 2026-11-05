"""Reproducible, observational Phase 4 local multiplayer benchmark.

Run: python -m benchmarks.phase4_multiplayer --accounts 40 --requests 80

Measures realistic same-process contention, full vs live projections, wire
bytes, and SQLite commands. It does not simulate geographically distributed
players, multi-process writers, TLS or production hosting. No strict timing
thresholds are asserted because shared CI runners have variable resources.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import tempfile
from time import perf_counter

from medieval_world_sim.web.multiplayer import MultiplayerGame


def metrics(samples: list[float]) -> dict:
    ordered = sorted(samples)
    if not ordered:
        return {"count": 0}
    return {
        "count": len(ordered),
        "p50_ms": round(statistics.median(ordered) * 1000, 3),
        "p95_ms": round(ordered[max(0, int((len(ordered) - 1) * 0.95))] * 1000, 3),
        "max_ms": round(ordered[-1] * 1000, 3),
    }


def timed(call, count: int):
    samples = []
    for _ in range(count):
        start = perf_counter()
        call()
        samples.append(perf_counter() - start)
    return metrics(samples)


def scenario(accounts: int, requests: int, workers: int, views: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="oathmere-phase4-") as folder:
        game = MultiplayerGame(Path(folder) / "benchmark.sqlite3",
                               require_invites=False, dev_fast_forward=True)
        try:
            players = [
                game.register(f"user{i:03d}", "benchmark secure password",
                              f"Hero {i:03d}")
                for i in range(accounts)
            ]
            viewing_actor = players[0]
            full_latency = timed(lambda: game.snapshot(viewing_actor), views)
            live_latency = timed(lambda: game.social_snapshot(viewing_actor), views)
            full_bytes = len(json.dumps(game.snapshot(viewing_actor),
                                        separators=(",", ":")).encode())
            live_first = game.social_snapshot(viewing_actor)
            live_bytes = len(json.dumps(live_first, separators=(",", ":")).encode())

            # A presence-only change is the main high-frequency SSE workload.
            game.presence_ping(players[1], True)
            live_second = game.social_snapshot(viewing_actor)
            if hasattr(__import__("medieval_world_sim.web.server",
                                  fromlist=["activity_delta"]), "activity_delta"):
                from medieval_world_sim.web.server import activity_delta
                wire = activity_delta(live_first, live_second)
                mode = "delta"
            else:
                wire = live_second
                mode = "full"
            changed_bytes = len(json.dumps(wire, separators=(",", ":")).encode())

            def command(i):
                actor_id = players[i % len(players)]
                started = perf_counter()
                game.action(actor_id, "send_chat",
                            {"kind": "global", "target": "",
                             "message": f"benchmark-{i}"},
                            f"bench-{i}")
                return perf_counter() - started

            started = perf_counter()
            with ThreadPoolExecutor(max_workers=workers) as executor:
                command_latency = list(executor.map(command, range(requests)))
            elapsed = perf_counter() - started
            # Read-only requests also contend with the serialized world lock.
            mixed_start = perf_counter()
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(
                        game.snapshot if i % 3 == 0 else game.social_snapshot,
                        players[i % len(players)])
                    for i in range(requests)
                ]
                for future in futures:
                    future.result()
            mixed_elapsed = perf_counter() - mixed_start

            # Reconciliation and recovery must still hold after the load.
            game.world.assert_invariants()
            game.close()
            game = MultiplayerGame(Path(folder) / "benchmark.sqlite3",
                                   require_invites=False, dev_fast_forward=True)
            game.world.assert_invariants()
            return {
                "accounts": accounts, "workers": workers, "requests": requests,
                "views": views, "full_snapshot": full_latency,
                "live_snapshot": live_latency,
                "full_snapshot_bytes": full_bytes,
                "live_initial_bytes": live_bytes,
                "live_changed_bytes": changed_bytes, "live_wire_mode": mode,
                "command": command_latency and metrics(command_latency),
                "command_throughput_per_s": round(requests / elapsed, 2),
                "mixed_read_throughput_per_s": round(requests / mixed_elapsed, 2),
                "maxrss_kb_linux": (
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    if platform.system() == "Linux" else None),
                "journal_entries": game._journal_count,
                "reconciled": True,
            }
        finally:
            game.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=int, default=40)
    parser.add_argument("--requests", type=int, default=80)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--views", type=int, default=32)
    args = parser.parse_args(argv)
    if not 2 <= args.accounts <= 80:
        parser.error("accounts must be between 2 and 80")
    if not 1 <= args.workers <= 32 or not 1 <= args.requests <= 400:
        parser.error("workers must be 1-32 and requests 1-400")
    if not 2 <= args.views <= 200:
        parser.error("views must be 2-200")
    result = scenario(args.accounts, args.requests, args.workers, args.views)
    print("PHASE4_BENCH_JSON=" + json.dumps({
        "python": platform.python_version(), "platform": platform.system(),
        "github_sha": os.environ.get("GITHUB_SHA", ""),
        **result
    }, sort_keys=True))


if __name__ == "__main__":
    main()
