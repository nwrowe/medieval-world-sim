# Oathmere Architecture — Local Development Prototype

This document describes the current implementation, not a proposed hosted service.
Oathmere has a deterministic, five-city game engine and two different persistence
adapters: local single-player JSON replay and localhost-only multi-account SQLite
journal replay. Neither is production/public-internet hosting.

## Code ownership

| Area | Owned responsibility |
| --- | --- |
| `core/entities.py`, `core/state.py` | Actor components and authoritative world state |
| `core/engine.py` | Domain facade, actor access control, command execution, invariants |
| `core/commands.py` | Typed command names, exact payload fields, single/multi exposure |
| `core/transactions.py` | Rollback of in-memory domain actions and gold transfers |
| `systems/` | Individual gameplay rules: travel/recovery, market, company, combat/duels, magic, housing, curriculum, chat, trades, guilds |
| `web/session.py` | Single-player JSON save journal, validation and replay |
| `web/multiplayer.py` | Local accounts, SQLite replay, sessions, server clock, activity/presence |
| `web/server.py`, `web/rate_limit.py` | HTTP transport, auth/cookie/CSRF checks, rate limiting and SSE |
| `web/static/` | Dependency-free browser interface; projection of server state only |
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
- **Local multi-account:** `MultiplayerGame` authenticates accounts to SQLite,
  stores commands and trusted clock advances with replay metadata, and
  guards duplicate request IDs. This mode is restricted to localhost, with
  invite-gated registration by default.
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
5. Prefer typed, focused components. Avoid deeper inheritance, additional
   god-objects, and copying state into long-lived UI caches.
6. Extend the lint rules in `pyproject.toml` incrementally as legacy code
   is cleaned; new modules should conform from their first commit.

## Validation

```bash
python -m pip install -e .
python -m pip install ruff==0.9.10
ruff check src tests
python -m unittest discover -s tests -v
node --check src/medieval_world_sim/web/static/app.js
```

The GitHub Actions workflow also runs deterministic CLI and NPC-economy
smoke tests. Tests prove regressions were not detected; they do not establish
production-scale concurrency, correctness or security.
