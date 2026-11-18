# Gameplay Development — End-to-End Feature Checklist

This document is an implementation guide for the next playability phase, not a
claim that every existing engine system is player-ready. Keep the authoritative
game rules shared by human players and NPCs. Do not build tutorial-only copies.

## Where new work belongs

| Responsibility | Existing owner |
| --- | --- |
| Items, spells, contracts, recipes, location definitions | `content/`, with generated geography in `worldgen/` |
| Actor and world state, invariants, command registry | `core/` |
| Purchases, combat, travel, recovery, professions and other rules | `systems/` |
| Save/replay, durable ownership, authentication, projections, HTTP | `web/` Python adapters |
| Player actions, state transitions, visual presentation | `web/static/app.js` and the feature's `*-views.mjs` module |
| Regression and browser interaction contracts | `tests/` |

Domain code (`core/`, `systems/`, `content/`, `worldgen/`) must never import
the `web/` package. CI checks this static dependency boundary.

## Checklist for a playable mechanic

1. **Purpose and loop:** State what a player can do, what it costs, what it
   changes, and why it is worth repeating. Include cooldowns and failure
   behavior; NPCs must follow the same economic and combat constraints.
2. **Domain and state:** Put authoritative validation and mutation in
   `systems/`, exposing a thin `WorldEngine` method. Update `WorldState`
   or actor components only when needed, and expand invariants.
3. **Command exposure:** Register the exact parameters and allowed modes in
   `core/commands.py`. A registered engine method with empty `web_modes`
   is **not** a player-accessible feature. Do not enable a previously internal
   command without explicit authorization/abuse tests.
4. **Persistence and replay:** Test save/load and checkpoint restart, including
   interrupted or repeated requests. If an authoritative mechanic changes,
   create a fresh development baseline rather than retaining old gameplay
   execution paths; reject outdated saves instead of silently reinterpreting them.
5. **Server projection:** Expose only actor-authorized information. Never send
   private inventories, undiscovered map details, credentials or escrow terms
   to unrelated players. Confirm that the snapshot and live update agree.
6. **Browser experience:** Add the feature to its relevant `*-views.mjs`
   module, with a clear interaction, cost, result, error and recovery state.
   Keep networking and live-event handling centralized until a cohesive
   handler can be extracted without a behavior change.
7. **Tests:** Cover success, invalid inputs, insufficient resources,
   idempotency, authorization, concurrent access where applicable, replay
   compatibility, projection privacy and representative UI behavior.
8. **Playtest:** Verify the full action loop manually on the actual browser
   and after a page refresh. A rendering contract alone is not an end-to-end
   browser test.

A feature is **playtest-ready** only when the full player loop works and
continues working after restart; code or catalog presence alone does not count.

## Classification for the upcoming audit

Use these mutually exclusive labels, supported by test evidence:

- **Engine only:** Functional in simulations or via internal methods, but no
  authorized complete player interface.
- **Partially playable:** Some real player interactions exist, but an important
  part of the loop is missing, inconsistent or not persisted.
- **Playtest-ready:** End-to-end authoritative and restart-safe experience,
  with sufficient tests and understandable feedback.
- **Unverified:** Not yet inspected. Never infer readiness from a module name.

The audit should cover combat, magic, gathering, trade/markets, employment,
companies, equipment, exploration/travel, housing, university, guilds and
quests. The registry intentionally contains non-browser-exposed company,
employment and market actions; evaluate these as separate surfaces before
enabling them for users.

## Future introductory settlement

The desired settlement-to-city tutorial is a **consumer of finished mechanics**.
At present, generated `CITIES` settlements have city access; exploration
sites and landmarks do not have their own service permissions. Introduce
explicit per-location capabilities when building villages instead of
hardcoding an onboarding settlement into existing city checks.

Once objectives are implemented, record tutorial progression in authoritative
player state or a durable account-scoped record, not only in browser storage.
A welcome dialog may remain local UI state. The tutorial must be resumable,
versioned as needed, and incapable of minting assets through a shortcut path.

## Scope discipline

Prefer focused changes and tests over file-splitting for its own sake. The
remaining whole-world rollback copy, central browser coordinator, replay
compatibility branches and single-process persistence are known costs; address
them when a gameplay feature or measured performance bottleneck justifies it.
