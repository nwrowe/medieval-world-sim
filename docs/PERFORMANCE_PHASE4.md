# Phase 4 — measured multiplayer performance and scaling boundaries

Oathmere's Phase 4 work reduces unnecessary data copies, live payload size,
and SQLite asset-write amplification without changing the compositional
gameplay engine or the durable Phase 3 ownership/receipt/checkpoint model.

## Code changes

| Component | Phase 4 optimization | Preserved safety boundary |
| --- | --- | --- |
| `core/transactions.py` + `web/multiplayer.py` | One rollback snapshot in the outer serialized multiplayer transaction instead of a redundant nested engine snapshot | Standalone engine commands retain their own rollback copy; SQL or invariant failures restore the entire world |
| `web/projection.py`, `web/social.py` | Narrow activity projections are cached per actor for a committed journal revision (maximum 32); presence overlays copied user rows | Chronicle, players, combat and chat remain private or scoped as before |
| `web/live_delta.py` + `web/server.py` | First SSE message is full; later messages send changed top-level keys or only changed presence IDs/statuses | Actor identity, revision ordering, authenticated cookie, host checks and origin restrictions are unchanged |
| `web/ledger.py` | Update only changed asset/escrow rows instead of deleting and reinserting all holdings on every chat/action | Complete ownership projection, durable receipts, atomic commit and startup reconciliation remain authoritative |
| `benchmarks/phase4_load.py` | Repeatable local authenticated HTTP concurrency workload | Uses real CSRF/cookies and server rules; localhost-only, never opens a public port |

The Phase 4 work is on `main`; the recovered cache/presence and
post-commit safety corrections are staged separately for review.

## Repeatable benchmark

From the repository root with Python 3.11:

```bash
python -m pip install -e .
python benchmarks/phase4_load.py --users 4 --actions 6 --workers 4
python benchmarks/phase4_load.py --users 8 --actions 8 --workers 8
```

The CI workflow also executes four-user and eight-user cases as
non-regression smoke benchmarks. The script reports request latency (p50/p95/p99/max), throughput,
total elapsed time, response sizes, peak Python `tracemalloc` memory,
durable receipts and journal rows. Any missing receipt or unsuccessful HTTP
mutation fails the run; noisy per-run timing does not fail CI until a
controlled performance baseline is established.

**Method:** each registered test account makes authenticated global-chat
mutations through the real local HTTP server; request concurrency is bounded
by the thread pool. Requests exercise host routing, session cookies, CSRF,
command validation, the global multiplayer lock, full-state rollback,
SQLite journal, asset ledger, receipt writes, and response serialization.
Account creation/login and initial database setup are outside timed actions.
A chat-heavy profile is a useful transaction stress test but **not** a
representative all-feature player mix. Simulated 30-day NPC-economy tests
remain separate functional regressions, not throughput measurements.

**Interpreting results:** these measurements are specific to the hardware,
Python version, work mix and current server settings; do not extrapolate them
to thousands of internet users. For comparisons, rerun the same command
at least three times on the same machine and report the median measured
p95 and throughput, plus uncertainty. Real online load also needs login,
world travel, market trades, battles, SSE readers and network delay.

## First measured CI baseline

The following is **one actual GitHub Actions Linux runner sample** from the
4-user / 6-actions / 4-worker profile on the pre-optimization main baseline
(baseline main before Phase 4 optimization; merge `66e3d07`), not a guaranteed capacity ceiling:

| Measurement | Observed |
| --- | ---: |
| Successful authenticated action requests | 24 / 24 |
| Throughput | 29.39 requests/s |
| HTTP latency p50 / p95 / p99 | 135.85 / 140.64 / 144.60 ms |
| HTTP latency maximum | 145.46 ms |
| HTTP response body p50 / p95 | 41,684 / 43,025 bytes |
| Python `tracemalloc` peak | 1.0 MiB |
| Final journal rows / action receipts | 28 / 24 |

[CI benchmark run](https://github.com/nwrowe/medieval-world-sim/actions/runs/42046993675)

`tracemalloc` captures traced Python allocations during the timed section,
not total RSS or SQLite-native memory. The benchmark includes full HTTP
response snapshots, so the large response bytes are expected. This baseline
must be repeated on a consistent host to assess performance improvements
rather than attributing incidental GitHub runner variance to code changes.

## Two-load concurrency comparison

A second GitHub Actions runner sample on the same baseline code measured the
two workload sizes in one workflow:

| Metric | 4 users / 4 workers | 8 users / 8 workers |
| --- | ---: | ---: |
| Successful HTTP requests | 24 / 24 | 64 / 64 |
| Throughput (requests/s) | 35.92 | 28.50 |
| p50 latency | 109.89 ms | 276.60 ms |
| p95 latency | 116.06 ms | 309.54 ms |
| p99 latency | 116.60 ms | 317.20 ms |
| p95 response body | 43,025 bytes | 49,712 bytes |
| Peak traced Python allocations | 0.98 MiB | 1.70 MiB |

[Two-load workflow](https://github.com/nwrowe/medieval-world-sim/actions/runs/42047967867)

Throughput declined and per-request latency rose at higher concurrency in
this sample, consistent with the single serialized world lock and more world
history being copied and projected. This is an *observation*, not a
controlled causal attribution. The four-user results also differ from the
earlier sample on the same baseline, illustrating why repeated controlled
runs matter before declaring a performance improvement or choosing targets.

## Recovered original 40-account engine-side benchmark

The original interrupted Phase 4 run used **a different workload** from the
HTTP benchmark above: direct `MultiplayerGame.action` calls in a 40-account
world with 12 workers and 80 commands. It separately measured full and live
projections and the *actual serialized SSE payload* for a presence change.

Run the recovered harness in the same environment on both revisions:

```bash
python -m benchmarks.phase4_multiplayer --accounts 40 --requests 80 --workers 12 --views 32
python -m benchmarks.phase4_multiplayer --accounts 80 --requests 120 --workers 16 --views 32
```

These results were verified from surviving GitHub Actions logs:

| Earlier run | Accounts / workers | Commands/s | Command p95 | Live p95 | Presence bytes |
|---|---|---:|---:|---:|---:|
| [Original baseline](https://github.com/nwrowe/medieval-world-sim/actions/runs/42042248288) | 40 / 12 | 72.75 | 181.47 ms | 1.384 ms | 11,762 |
| [Original optimized](https://github.com/nwrowe/medieval-world-sim/actions/runs/42042920123) | 40 / 12 | 123.79 | 115.07 ms | 0.074 ms | 158 |
| [Later original optimized](https://github.com/nwrowe/medieval-world-sim/actions/runs/42044594569) | 40 / 12 | 211.67 | 167.33 ms | 0.051 ms | 158 |
| [Original stress probe](https://github.com/nwrowe/medieval-world-sim/actions/runs/42044594569) | 80 / 16 | 129.86 | 498.59 ms | 0.063 ms | 158 |

The original performance work was left in open PRs
[#50](https://github.com/nwrowe/medieval-world-sim/pull/50),
[#51](https://github.com/nwrowe/medieval-world-sim/pull/51), and
[#52](https://github.com/nwrowe/medieval-world-sim/pull/52).
The recovered code selectively restores the cached activity view and tiny
presence patches; the already-merged main branch retains its independent
transaction-copy and incremental-ledger optimizations.

**Do not compare these commands/second figures directly to the HTTP test.**
The HTTP test performs authentication, CSRF, JSON serialization, and transmits
the whole browser-state response. The original benchmark calls the in-process
game API. These are observational samples from different GitHub-hosted
runners, with significant throughput variation even for an unchanged
workload. A 40-account world is not the same as 40 concurrent HTTP sessions.

## Existing hard limits, not measured capacity

- **100 registered accounts** in this development world
- **20 concurrent live SSE connections**
- **20,000 journal entries**, plus existing per-account/global daily quotas
- A **single writer process** and one in-process serialized world lock
- A **single SQLite connection** with exclusive lock and durable commits
- Multiplayer mode remains **loopback-only**; there is no public hosting
  or distributed authentication/rate limit infrastructure

These values are explicit configuration limits, **not proven safe concurrency
targets**. A green CI run validates correctness under its small test load,
not the maximum safe player count.

## Remaining architecture costs

Phase 4 optimizes avoidable work, but it deliberately does **not** claim to
have removed the last whole-world rollback copy. Correctly eliminating it
requires transactional per-entity mutations or reversible domain changes
covering all gameplay systems, including inventory, gear, escrow, time,
and NPC actions. The world-invariant scan, ledger reconciliation projection,
journal-prefix hashing at checkpoint creation and single-process lock also
remain O(world/history) hot spots.

Recommended follow-on milestones are instrumented per-action profiling at
larger world sizes, a journal/asset change-set API that preserves rollback
and conservation, actor-specific indexing for Chronicle/chat queries, and
measured queue-depth/backpressure thresholds before considering production
multi-process hosting.

## Trusted clock

Server-managed world time was already introduced in the security phase.
Ordinary multiplayer clients cannot advance the shared clock. The
`--dev-fast-forward` override is exclusively for local development and tests;
it is not a public-hosting feature. Phase 4 preserves that policy.
