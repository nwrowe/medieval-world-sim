# Oathmere Architecture — Local Development Prototype

This document describes the current implementation, not a proposed hosted service.
Oathmere has one authoritative game engine backed by a seeded, geography-first
realm. The default development atlas is seed 7 with 12 generated settlements;
`content/catalog.py` derives the playable `CITIES` and `ROADS` from that atlas.
The number of settlements is not an engine constant. The two persistence
adapters are local single-player JSON replay and localhost-only multi-account
SQLite journal replay. Neither is production/public-internet hosting.

## Code ownership

| Area | Owned responsibility |
| --- | --- |
| `worldgen/`, `content/`, `content/catalog.py` | Generated terrain/settlements/roads, authored content overlays, and derived playable definitions |
| `core/entities.py`, `core/state.py` | Actor components and authoritative world state |
| `core/engine.py`, `core/invariants.py` | Domain facade, actor access control, command execution, and separately owned state validation |
| `core/commands.py` | Typed command names, exact payload fields, single/multi exposure |
| `core/transactions.py` | Rollback of in-memory domain actions and gold transfers |
| `systems/` | Individual gameplay rules: travel/recovery, market, company, combat/duels, magic, housing, curriculum, chat, trades, guilds |
| `web/session.py`, `web/chronicle.py`, `web/projection.py` | JSON replay, Chronicle formatting and common actor-scoped browser snapshots |
| `web/multiplayer.py` | Shared lock/transaction boundary, trusted clock, command dispatch, event streams |
| `web/accounts.py` | Credentials, invite redemption, lockout, sessions and identities |
| `web/journal.py` | SQLite command-journal schema and historical command replay, including checkpoint-tail replay |
| `web/ledger.py` | Atomically materialized gold, item and gear ownership/escrow plus durable request receipts |
| `web/checkpoint.py` | Versioned, checksum-attested typed JSON world snapshots and bounded restart recovery |
| `web/social.py` | Ephemeral presence and account-scoped chat/trade/status projections |
| `web/server.py`, `web/rate_limit.py` | HTTP transport, auth/cookie/CSRF checks, rate limiting and SSE |
| `web/static/app.js` | Client networking, session state, actions, live events and page navigation |
| `web/static/*-views.mjs` | World, city, community and character page templates with injected read-only context |
| `agents/`, `experiments/` | Seeded NPC policies and retained legacy simulations |
| `tests/` | Gameplay invariants, security/abuse regressions, replay and web contract tests |

The authoritative `WorldEngine` composes systems instead of creating parallel
single/multiplayer gameplay implementations. All human and NPC actors use the
same core entities and gameplay rules.

## Locations and gameplay access

The generated atlas contains settlements, roads, exploration sites and landmarks.
Currently, entries in `CITIES` are full settlements with city-service access;
`_at_city` deliberately blocks those services while traveling or in wilderness.
Sites and landmarks are not independent service-bearing villages today. A
future starting hamlet should use explicit location/service capabilities, not
special-case tutorial rules or a second simulated game world. See
[gameplay development](GAMEPLAY_DEVELOPMENT.md).

## Command boundary

`core/commands.py` is the **single registration point** for command names,
method dispatch, required parameter fields and exposure by web mode. The
server adapters derive their allowlists from it; adding a command in a
system is not enough to expose it to a browser. Some registered engine methods
are intentionally *not* browser-exposed (including company/employment and
player market actions). Their presence alone is not evidence of a playable UI.

`WorldEngine.execute(principal_id, action, params, action_id)` verifies
the complete parameter set and checks idempotency receipts. The principal
must come from a trusted server session, never a body-supplied actor ID.
The web layer additionally applies session/CSRF/host checks. Domain code
remains authoritative: browser data cannot directly mutate gold, items,
health or ownership.

## Persistence and security

- **Single player:** `GameSession` serializes a bounded action journal to
  JSON, writes it atomically, and replays current-format commands only.
  Earlier development saves are refused rather than migrated. It is not a
  multi-user security boundary.
- **Local multi-account:** `MultiplayerGame` retains the serialized SQLite/world
  transaction boundary and trusted clock. `accounts.py` owns authentication
  and invitations. `journal.py` owns historical commands and replay; `ledger.py`
  records ownership and durable request receipts within the same SQLite commit;
  `checkpoint.py` restores versioned world state and replays only subsequent
  commands. `social.py` builds actor-scoped projections. See
  [Phase 3 durability](DURABILITY_PHASE3.md). This mode remains localhost-only.
- **HTTP:** `GameHTTPServer` and `GameHandler` provide no public TLS,
  reverse-proxy trust or distributed rate limit. This is **not** an
  internet-ready deployment. SSE and presence are projections scoped to the
  authenticated actor.
- **Transactions:** The in-memory world still relies on copied
  `WorldState` for rollback, while SQLite atomically commits journal entries,
  materialized asset/escrow ownership, receipts and periodic checkpoints.
  Startup reconciles all records and fails on divergence. Whole-state copies,
  materialization scans and one-process locking remain Phase 4 scaling limits.

## Extension guidelines

1. Put game rules in the appropriate `systems/` module. Keep `core/engine.py`
   as a delegating facade; avoid second gameplay implementations in the web layer.
   `core/`, `systems/`, `content/` and `worldgen/` must not import `web/`.
2. Register command schema and web exposure together in `core/commands.py`.
   Test both permitted and prohibited modes and retry semantics.
3. Keep database credentials and identity in transport/auth modules. Never
   serialize private player inventory, finances, or internal keys to
   another player's projection.
4. Current-format persistence must remain restart-safe and deterministic.
   Development saves from earlier revisions are intentionally unsupported:
   make breaking changes explicit, bump the format marker as appropriate, and
   test that older data fails without being modified or silently upgraded.
5. Prefer typed, focused components. Keep browser rendering in the relevant
   `*-views.mjs` module. `app.js` currently coordinates networking, live state,
   actions and navigation; extract cohesive handlers/state as each feature is
   developed rather than expanding that file indefinitely. Avoid deeper
   inheritance, large generic service layers, and copying authoritative state
   into long-lived UI caches.
6. Extend the lint rules in `pyproject.toml` incrementally as legacy code
   is cleaned; new modules should conform from their first commit.
7. Use the [gameplay development checklist](GAMEPLAY_DEVELOPMENT.md) to verify
   UI access, authorized commands, persistence, multiplayer visibility and
   feedback before calling a mechanic player-ready.

## Phase 4 performance guidance

See [Phase 4 measured performance](PERFORMANCE_PHASE4.md) for reproducible
authenticated HTTP benchmarks, configured local-server capacity limits,
and documented remaining transaction, checkpoint and event-stream hot spots.

## Validation

```bash
python -m pip install -e .
python -m pip install ruff==0.9.10
ruff check src tests
python -m unittest discover -s tests -v
node --check src/medieval_world_sim/web/static/app.js
node --check src/medieval_world_sim/web/static/community-views.mjs
node --check src/medieval_world_sim/web/static/city-views.mjs
node --check src/medieval_world_sim/web/static/character-views.mjs
node --check src/medieval_world_sim/web/static/activity-state.mjs
node tests/test_activity_state.mjs
node tests/test_browser_views.mjs
node tests/test_feature_views.mjs
```

The GitHub Actions workflow also runs strict Ruff checks for the command and
architecture-boundary tests, selected multiplayer service modules, and
reproducible CLI and NPC-economy smoke tests. Tests prove regressions were not detected; they do not establish
production-scale concurrency, correctness or security.
