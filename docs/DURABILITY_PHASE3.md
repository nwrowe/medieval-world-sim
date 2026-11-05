# Phase 3 — durable multiplayer transactions and recovery

This is a description of Oathmere's local SQLite design. It is not a
production deployment endorsement. The existing hosted multiplayer limits
and lack of distributed locking still apply.

## Persistence ownership

The authoritative in-memory `WorldEngine` retains gameplay rules. Each
successful account or world mutation is serialized by `MultiplayerGame._tx`,
which commits four related durable records under one SQLite
`BEGIN IMMEDIATE`/COMMIT transaction:

1. **`world_journal`** retains the original command or time advancement and
   all historical replay flags. It remains an immutable audit source.
2. **`durable_receipts`** records the account-bound request ID, exact
   canonical payload and committed result linked to its journal sequence.
   Repeated requests return the original result without re-executing a move,
   transferring additional gold or creating additional activity.
3. **`asset_ledger`** contains current positive asset holdings, keyed by
   holder, location, asset type and item or gear ID. It covers crown funds,
   characters and companies, city merchant budgets, personal storage,
   market offers and locked bilateral-trade escrow. Every gear ID must have
   exactly one owner or escrow holder; all gold must reconcile to authorized
   issuance.
4. **`world_checkpoints`** stores a typed JSON snapshot of the world,
   its event timestamps, a schema version, the exact journal sequence, a
   payload digest, and a digest of the committed journal prefix.
   Checkpoints are written every 50 journal sequences, without pruning
   the complete journal. An operator can call
   `MultiplayerGame.create_checkpoint()` for an immediate checkpoint.

The SQLite transaction rolls back if any ledger, receipt, checkpoint or
journal write fails, and the in-memory world is restored from its pre-command
copy. A player cannot submit a checkpoint request through the HTTP API.

## Restart flow

1. Open SQLite with foreign keys and exclusive single-process locking.
2. Create new auxiliary tables if needed, without changing existing journal
   rows. An existing journal-only database is backfilled once, after a
   complete validated replay.
3. If there is a checkpoint, verify its schema and SHA-256 digest, plus the
   historical journal prefix digest. Decode only explicitly allowlisted
   dataclasses, sets, tuples, lists, and maps. No pickle, dynamic class import,
   or executable deserialization is used.
4. Restore the saved world and account-scoped metadata, then replay **only
   the journal tail** later than the checkpoint's sequence. Without a
   checkpoint, replay the complete journal.
5. Verify game invariants and independently compare the entire recovered
   asset/escrow ledger and request receipts to their SQLite materialization.
   Any mismatch fails startup rather than silently rewriting those records.

This preserves existing player accounts, world history, action results and
sessions. Checkpoints intentionally omit the engine's old in-memory receipt
cache: durable receipts are the authoritative idempotency record.

## Failure and concurrency tests

The Phase 3 tests cover:

- Account-bound idempotent retries, including simultaneous duplicate requests
  from multiple threads
- Gold escrow reservation and acceptance without double spending
- Injected failure **after** durable ledger writes or checkpoint insertion,
  confirming atomic rollback of SQL and in-memory world
- Legacy database migration and restart reconciliation
- Restart from checkpoints with only later commands replayed
- Persistent open trade escrow across checkpoint recovery
- Corrupt materialized assets, receipts, checkpoint bytes and historical
  journal prefix detection

GitHub Actions continues to run the unit, lint, browser and extended
deterministic economy tests.

## Explicit boundaries and limitations

This is a deliberately incremental durability architecture, not yet a
high-throughput production database:

- `WorldEngine` remains authoritative during a running process. The asset
  table is a **transactional materialized record**, not a second mutable
  command surface. Direct SQL edits are never permitted as gameplay actions.
- Each mutation still deep-copies world state for rollback and refreshes the
  materialized asset rows. These are known scaling costs reserved for Phase 4.
- SQLite's exclusive single-process lock is retained. Multi-process writers,
  distributed transactions and row-level locking are not supported.
- Journal prefix hashing reads history to verify integrity, although normal
  gameplay replay can skip the prefix. A chained hash index or segment proofs
  can further improve this at scale.
- SHA-256 detects accidental and unsanctioned single-record corruption, not
  malicious modifications by someone with unrestricted database-file access
  who can rewrite both data and digests.
- No journal pruning, account recovery, production TLS, or external hosting is
  introduced. Back up the entire SQLite database (not individual tables).

These limitations are intentional: durable ownership, idempotency and
recoverability must be correct before replacing whole-state copying or
optimizing notifications in Phase 4.
