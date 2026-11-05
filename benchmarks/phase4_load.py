"""Repeatable local multiplayer HTTP load profile.

Run with PYTHONPATH=src python benchmarks/phase4_load.py --users 8 --actions 12.
A profile reports observed capacity; it is NOT proof of internet readiness.
No third-party packages, public network binding or browser automation.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import statistics
import tempfile
import threading
import time
import tracemalloc

from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web.server import GameHTTPServer


@contextmanager
def local_server(game):
    server = GameHTTPServer(("127.0.0.1", 0), None, multiplayer=game)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def timed_request(port, token, csrf, action, request_id):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    body = json.dumps({
        "action": action, "params": {
            "kind": "global", "target": "", "message": "load " + request_id
        }, "id": request_id}, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Cookie": "oathmere_session=" + token,
        "X-CSRF-Token": csrf,
    }
    begin = time.perf_counter_ns()
    try:
        conn.request("POST", "/api/action", body, headers)
        response = conn.getresponse()
        payload = response.read()
        latency_ms = (time.perf_counter_ns() - begin) / 1_000_000
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {payload[:160]!r}")
        return latency_ms, len(payload)
    finally:
        conn.close()


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def measure(users: int = 8, actions: int = 12, concurrency: int = 8) -> dict:
    if not (1 <= users <= 30 and 1 <= actions <= 35 and 1 <= concurrency <= 32):
        raise ValueError("Load sizes must stay inside local security and account limits")
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "load.sqlite3"
        game = MultiplayerGame(db, require_invites=False, dev_fast_forward=True)
        credentials = [
            game.register_and_login(
                "user" + str(i), "benchmark only password", "Test Player " + str(i))
            for i in range(users)
        ]
        tasks = [(i, j) for j in range(actions) for i in range(users)]
        # Include per-actor HTTP authentication, CSRF, canonical action
        # validation, SQL commits, asset materialization and response state.
        def call(pair, port):
            i, j = pair
            token, csrf = credentials[i]
            return timed_request(port, token, csrf,
                                 "send_chat", f"load-{i}-{j}")

        with local_server(game) as port:
            tracemalloc.start()
            start = time.perf_counter()
            try:
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    result = list(pool.map(lambda pair: call(pair, port), tasks))
            finally:
                duration = time.perf_counter() - start
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

        latency = [entry[0] for entry in result]
        body_bytes = [entry[1] for entry in result]
        expected = users + users * actions
        count = game.db.execute(
            "SELECT COUNT(*) FROM world_journal").fetchone()[0]
        receipts = game.db.execute(
            "SELECT COUNT(*) FROM durable_receipts").fetchone()[0]
        game.world.assert_invariants()
        if count != expected or receipts != users * actions:
            raise AssertionError("Load test failed durable receipt/journal accounting")
        game.close()
        return {
            "workload": "localhost HTTP: authenticated global chat mutations",
            "users": users, "concurrent_workers": concurrency,
            "actions_per_user": actions, "requests": len(result),
            "elapsed_s": round(duration, 3),
            "throughput_requests_s": round(len(result) / duration, 2),
            "latency_ms": {
                "p50": round(statistics.median(latency), 2),
                "p95": round(percentile(latency, 0.95), 2),
                "p99": round(percentile(latency, 0.99), 2),
                "maximum": round(max(latency), 2),
            },
            "http_response_bytes": {
                "p50": round(statistics.median(body_bytes), 0),
                "p95": round(percentile(body_bytes, 0.95), 0),
            },
            "python_tracemalloc_peak_mib": round(peak / (1024 * 1024), 2),
            "journal_rows": count, "durable_receipts": receipts,
            "error_count": 0,
            "interpretation": (
                "Single-process, local loopback development benchmark; not "
                "a distributed load test or public-hosting capacity guarantee."
            ),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=8)
    parser.add_argument("--actions", type=int, default=12)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    print(json.dumps(measure(args.users, args.actions, args.workers),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
