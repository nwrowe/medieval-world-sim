# Oathmere Architecture — Local Development Prototype

This document describes the current implementation, not a proposed hosted service.
Oathmere has a deterministic, five-city game engine and two different persistence
adapters: local single-player JSON replay and localhost-only multi-account SQLite
journal replay. Neither is production/public-internet hosting.

## Code ownership

| Area | Owned responsibility |
| --- | --- |
| `core/entities.py`, `core/state.py` | Actor components and authoritative world state |
| `core/engine.py`, `core/invariants.py` | Domain facade, actor access control, command execution, and separately owned state validation |
| `core/commands.py` | Typed command names, exact payload fields, single/multi exposure |
| `core/transactions.py` | Rollback of in-memory domain actions and gold transfers |
| `systems/` | Individual gameplay rules: travel/recovery, market, company, combat/duels, magic, housing, curriculum, chat, trades, guilds |
| `web/session.py`, `web/chronicle.py`, `web/projection.py` | JSON replay, Chronicle formatting and common actor-scoped browser snapshots |
| `web/multiplayer.py` | Shared lock/transaction boundary, trusted clock, command dispatch, event streams |
| `web/accounts.py` | Credentials, invite redemption, lockout, sessions and identities |
| `web/journal.py` | SQLite schema migrations and versioned multiplayer replay |
| `web/social.py` | Ephemeral presence and account-scoped chat/trade/status projections |
| `web/server.py`, `web/rate_limit.py` | HTTP transport, auth/cookie/CSRF checks, rate limiting and SSE |
| `web/static/app.js` | Client networking, session state, actions, live events and page navigation |
| `web/static/*-views.mjs` | World, city, community and character page templates with injected read-only context |
| `agents/`, `experiments/` | Seeded NPC policies and retained legacy simulations |
| `tests/` | Gameplay invariants, security/abuse regressions, replay and web contract tests |

The authoritative `WorldEngine` composes systems instead of creating parallel
single/multiplayer gameplay implementations. All human and NPC actors use the
same core entities and gameplay rules.

## Command boundary

`core/commands.py` is the **single registration point** for command names,
method dispatch, required parameter fields and exposure by web mode. The
server adapters derive their allowlists from it; adding a command in a
system is not enough to expose it to a browser.

`WorldEngine.execute(principal_id, action, params, action_id)` verifies
the complete parameter set and checks idempotency receipts. The principal
must come from a trusted server session, never a body-supplied actor ID.
The web layer additionally applies session/CSRF/host checks. Domain code
remains authoritative: browser data cannot directly mutate gold, items,
health or ownership.

## Persistence and security

- **Single player:** `GameSession` serializes a bounded action journal to
  JSON, writes it atomically, and replays with explicit historical ruleset
  versions. It is not a multi-user security boundary.
- **Local multi-account:** `MultiplayerGame` retains the serialized SQLite/world
  transaction boundary, trusted clock and command receipts. `accounts.py` owns
  password hashing, authentication and one-time invitations; `journal.py`
  owns schema evolution and versioned replay; `social.py` builds actor-scoped
  projections. This mode remains localhost-only, with invite-gated registration
  by default.
- **HTTP:** `GameHTTPServer` and `GameHandler` provide no public TLS,
  reverse-proxy trust or distributed rate limit. This is **not** an
  internet-ready deployment. SSE and presence are projections scoped to the
  authenticated actor.
- **Transactions:** The in-memory world still relies on copied
  `WorldState` for rollback. SQLite protects the journal in local
  multiplayer, but large-scale production requires finer-grained persistence,
  deployment hardening, and performance evaluation.

## Extension guidelines

1. Put game rules in the appropriate `systems/` module. Keep `core/engine.py`
   as a thin facade; avoid second gameplay implementations in the web layer.
2. Register command schema and web exposure together in `core/commands.py`.
   Test both permitted and prohibited modes and retry semantics.
3. Keep database credentials and identity in transport/auth modules. Never
   serialize private player inventory, finances, or internal keys to
   another player's projection.
4. When altering replayable mechanics, add a ruleset/journal version and
   tests for loading older saves.
5. Prefer typed, focused components. Keep browser rendering in the relevant
   `*-views.mjs` module and keep network calls, action handlers and mutable UI
   state in `app.js`. Avoid deeper inheritance, large generic service layers,
   and copying authoritative state into long-lived UI caches.
6. Extend the lint rules in `pyproject.toml` incrementally as legacy code
   is cleaned; new modules should conform from their first commit.

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
node tests/test_browser_views.mjs
node tests/test_feature_views.mjs
```

The GitHub Actions workflow also runs strict Ruff checks for the new
multiplayer service modules and deterministic CLI and NPC-economy smoke tests. Tests prove regressions were not detected; they do not establish
production-scale concurrency, correctness or security.
