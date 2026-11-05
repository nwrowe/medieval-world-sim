# Phase 4 — multiplayer performance and measured limits

Phase 4 improves the existing **single-process, localhost-only** multiplayer
implementation. It does not enable public internet hosting or a distributed
server. The game engine, SQLite journal, durable receipts, asset/escrow
reconciliation, and versioned checkpoint behavior remain authoritative.

## Reproducible workload

Run from the repository root, with Python 3.11+:

```bash
python -m pip install -e .
python -m benchmarks.phase4_multiplayer --accounts 40 --requests 80 --workers 12 --views 32
```

The benchmark creates an isolated temporary SQLite database, 40 player accounts
and the usual NPC world, then exercises 32 consecutive full snapshots and 32
live snapshots, an SSE presence update, 80 distinct chat commands submitted
by 12 simultaneous worker threads, and 80 mixed read requests. It restarts the
database and checks world invariants/recovery. Only the benchmark overrides the
daily registration limit to seed this world quickly; game server limits are
unchanged. Results are emitted as one `PHASE4_BENCH_JSON` record.

The harness deliberately measures Python game/SQLite processing rather than
HTTP network latency, TLS, browsers, geographic users, or distributed writers.

## Preliminary before/after measurements

GitHub Actions, November 5, 2026. Both runs used Linux and Python 3.11.18,
40 accounts, 12 workers, 80 commands, and 32 projection samples.

| Metric | Baseline | Combined Phase 4 (first measured revision) |
| --- | ---: | ---: |
| Committed action throughput | 72.75/s | 231.48/s |
| Concurrent action p50 | 159.043 ms | 47.744 ms |
| Concurrent action p95 | 181.471 ms | 67.257 ms |
| Live projection p50 | 1.352 ms | 0.031 ms |
| Live projection p95 | 1.384 ms | 0.036 ms |
| Mixed read throughput | 599.43/s | 2455.03/s |
| Full snapshot p50 | 1.362 ms | 0.700 ms |
| Full snapshot wire bytes | 47,311 | 47,311 |
| Initial live payload bytes | 11,763 | 11,763 |
| Presence-only wire bytes | 11,762 | 11,101 (before sparse patch) |
| Linux maximum RSS | 63,604 KiB | 63,712 KiB |

Evidence: [baseline CI run](https://github.com/nwrowe/medieval-world-sim/actions/runs/42042248288)
and [combined optimization CI run](https://github.com/nwrowe/medieval-world-sim/actions/runs/42042250199).

**Interpretation:** The first measured optimized implementation delivered about
3.2 times the action throughput and approximately 44 times lower median live
projection cost, with a roughly fourfold improvement in mixed-read throughput.
These are single-run, shared-CI observations and may not transfer to other
hardware or real players. RSS is essentially unchanged, so this is **not** a
demonstrated memory reduction. Later sparse-presence patch results should be
read from the latest CI benchmark, not substituted into this historical run.

## Changes with explicit safety ownership

1. The SSE server sends a complete, account-scoped frame on connection, then
   only changed fields. A presence-only revision uses narrow per-user
   `presence_updates` instead of resending the full roster. Existing
   `users` frames still carry complete roster information when city, HP
   or attack eligibility changes. The browser retains all omitted fields.
2. Social data is projected directly from the authoritative world, without
   computing unrelated market price tables, magic unlock trees, property and
   inventory summaries. Public roster, Chronicle and duel formatting remain
   shared with the full snapshot. Actor-scoped projections are cached for up
   to 32 players per committed journal revision; presence is overlaid on
   copied user rows so a player cannot influence another account's cache.
3. In multiplayer, one outer rollback snapshot and SQLite transaction now
   owns the atomic change; an inner decorated gameplay call does not take a
   second full-state copy. Single-player and journal replay keep their
   existing independent rollback behavior.
4. Completed command retries check durable receipts under the world lock
   before copying world state or opening a new SQLite transaction. Reused
   request IDs with different parameters remain forbidden.
5. The SQLite asset ledger writes only the rows whose ownership or quantity
   changed. Transactional receipts, escrow, startup reconciliation, snapshot
   integrity, and failure rollback are unchanged.
6. Trusted wall-clock advancement is already server-managed. The development
   `--dev-fast-forward` option remains explicitly local and disabled by
   default; clients cannot advance shared world time in normal mode.

## Provisional local performance targets

Use the same 40-account/12-worker workload before judging regressions:
- Action throughput around **150 commands/s or more** and p95 around
  **100 ms or lower** on a comparable CI runner.
- Live in-process projection p95 around **0.1 ms or lower** for a cached
  actor, with presence-only SSE payload well under **1 KiB**.
- Combined read throughput around **1,000 reads/s or more**.
- All economic conservation, retry, trade escrow, account privacy, restart
  and injected-failure tests must continue to pass.

These are *engineering targets*, not hard CI gates or production SLAs.
Collect multiple runs before treating deviations as regressions. Workload
mix matters: 80 mostly chat commands do not represent hundreds of
simultaneous trades, complex combat, or continuous world-clock advances.

## Known limits and next scaling boundary

- **One full-world deepcopy still remains per successful new multiplayer
  mutation.** Removing it requires a validated write-set/undo-log or fully
  authoritative per-asset transactional storage, not merely disabling
  rollback. This is deliberately retained to prevent gold or item loss on
  failed SQL commits.
- **One world lock and one SQLite writer** serialize all mutations. The
  deployment remains single-process with exclusive database ownership.
  Multiple gunicorn workers or several app servers are unsupported.
- Asset reconciliation still scans the holdings collection, and versioned
  checkpoint prefix hashing scans historical journal rows on checkpoint
  creation. Database size and journal lifetime remain important costs.
- The prototype explicitly caps **100 accounts**, **20 concurrent SSE
  connections**, and **20,000 journal records**, with additional daily
  signup/command limits. These are configured safety ceilings, not
  benchmark-established user capacity.
- SSE only delivers updates for authenticated actors. It is not a generic
  public event broker; client patches are projections, never authoritative
  requests to mutate the world.
- Production TLS, distributed locks, multiple database writers, external
  account recovery, long-duration soak testing, and realistic network
  benchmarks remain outside this local performance milestone.

**Bottom line:** Phase 4's safe incremental optimizations have measurable
benefits for the present prototype, but not a verified path to thousands of
simultaneous remote players. Public hosting and sharded/row-locked scale
would require a separately designed transactional service and comprehensive
concurrency testing.
