# Architecture — Five-City Domain Engine

This is the **current prototype architecture**. It keeps a single authoritative in-memory world, deliberately without a distributed service stack.

## Package layout

```
src/medieval_world_sim/
  core/
    entities.py         Actor, Vitals, Progression, TravelState, Company, Wage, Offer, WorldEvent
    cities.py           Mutable CityState with separate CitySpec definitions
    state.py            Owned WorldState aggregate (one source of mutable truth)
    engine.py           WorldEngine and explicit game-command facade
    transactions.py     Rollback-safe in-memory actions and gold transfers
    events.py           Named, versioned audit event fields
  systems/
    travel.py           Roads, travel deadlines, time progression and recovery
    resources.py        Regional gathering and finite deposits
    companies.py        Company creation, employment, manufacturing, payroll
    market.py           Material/unique-equipment offers and escrow trading
    combat.py           Gear, damage, stamina, level progression and loot
  content/
    catalog.py          Five cities, road times, resources, industries and recipes
    equipment_specs.py  Base stats for weapons/armor/tools
  experiments/
    legacy_economy.py   Archived single-town baseline (separate economy)
  equipment.py          Unique item instances, quality and valuation functions
  regional_world.py     Backwards-compatible WorldEngine alias
  simulation.py         Backwards-compatible old World alias
  __main__.py           Regional demo by default, --legacy benchmark available
```

## Design boundaries

**Domain entities** carry data, with no special player vs NPC subclass. Every Actor is usable by either a human controller or a future NPC policy. Vital pools, progression and travel are grouped as components. Flat attribute accessors remain for older callers but new systems should prefer `actor.vitals`, `actor.progression` and `actor.travel`.

**City data** distinguishes static definitions in `content/catalog.py` from mutable `CityState` objects in `world.cities`. The compatibility `world.deposits` property views those city inventories. Additional markets, security, and local social structures can now be modeled per city.

**WorldEngine** owns a `WorldState` aggregate, validates principal/owner access, exposes the public game API, and delegates behavior to composed systems. Systems share the same authoritative state; they do not implement parallel world representations. The old `CombatMixin` inheritance is gone.

**Gameplay systems** should apply rules, not own independent copies of actor, market, or company state. Recipes and gear definitions should remain data, avoiding business-specific subclasses.

**Gold transfers** run through `transfer_gold` across company investment, payroll, marketplace trade, starter purchases, and combat loot. This is separate from the logic deciding *why* a transfer is made.

**Atomic actions** use snapshots of `WorldState` with rollback when a command fails or an invariant is violated. This is acceptable at prototype scale but expensive: deep-copy cost increases with world size and accumulated event logs. A production persistent server should use a transactional database, row-level/concurrency locks, and durable action IDs.

**Command entrypoint:** `world.execute(principal_id, action, params, action_id)` binds the actor executing an action and enforces an allowlist of commands, then stores an idempotency receipt. The lock prevents two concurrent retries of the same command running simultaneously **within one Python process**. The `principal_id` here is trusted input from a future server-side authenticated adapter—not client-submitted identity. Direct Python methods remain available for simulation/testing, and this is **not a production authentication solution**.

**Audit events** now have schema version, unique in-world sequence ID, optional action ID, and named structured fields, while retaining existing tuple-based `details` for compatibility. Event storage and replay are not yet persistent.

## Non-goals in this refactor

No gameplay values, travel times, item quality curves, combat formulas, XP curves, or recipe quantities were deliberately rebalanced. We have not introduced hosted databases, HTTP routes, accounts/login, NPC intelligence, autonomous action loops, or complete event-sourced replay.

## Next engineering work, in order

1. Add state persistence (SQLite for tests), durable command receipts, and replay-checkable events.
2. Replace whole-state snapshot rollback with true ACID transactions and idempotent service commands.
3. Introduce an authenticated API adapter that derives the acting player from the session, not payload IDs.
4. Give NPCs an `observe -> propose -> validate -> execute` policy interface; make policies untrusted callers of the same action APIs.
5. Expand bounded-simulation tests, concurrency/adversarial scenarios and transaction property tests.

## Run

```bash
python -m medieval_world_sim
python -m medieval_world_sim --scenario combat
python -m medieval_world_sim --legacy --citizens 200 --days 30 --seed 42 --json
PYTHONPATH=src python -m unittest discover -s tests -v
```
