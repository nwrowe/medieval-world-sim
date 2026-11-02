# Decision Log (provisional)

## ADR-001: Simulation rules remain authoritative

**Proposed:** NPC policies and future language models request actions; the rules engine alone validates and applies state changes.

**Reason:** deterministic testing, fraud prevention, reproducibility, and shared fairness with human players.

## ADR-002: Rules first, model inference sparingly

**Proposed:** routine population behavior is deterministic or stochastic code; high-salience characters may use event-driven AI.

**Reason:** cost, latency, and simpler economic accounting. No inference provider commitment yet.

## ADR-003: NPCs are disclosed

**Proposed:** every NPC identity is presented as such; never inflate human activity metrics with simulated accounts.

**Reason:** build a trustworthy community, even if NPC personalities are rich.

## ADR-004: Python standard-library prototype

**Temporary:** test world logic in Python 3.11+ with no paid services or third-party packages.

**Reason:** fastest way to verify mechanical hypotheses. This does not lock in the production backend, UI, or database.

## ADR-005: Project remains private initially

**Proposed:** private during exploration; revisit licensing and publication deliberately.

**Reason:** design and business experiments are not yet ready for public release. No code license is included.

## ADR-006: Compose gameplay systems around one authoritative state (2026-11-02)

**Decision:** Use a `WorldEngine` with explicit domain entities and compositional gameplay systems for travel, extraction, business, trade and combat. Do not create occupation-specific or NPC-versus-human inheritance trees.

**Reason:** Enables independent systems to grow while reusing the same rules and avoiding two competing world representations. Keep `RegionalWorld` and older APIs as compatibility shims for existing scripts.

## ADR-007: Store cities as runtime state with catalog definitions (2026-11-02)

**Decision:** Keep names, resource rates and roads in static content definitions; hold mutable deposits and future settlement properties in individual `CityState` objects.

**Reason:** Local security, politics, shortages, ownership, population and markets can evolve by city without special-case logic in the central engine.

## ADR-008: Temporary rollback-safe in-memory command boundary (2026-11-02)

**Decision:** Maintain a single mutable `WorldState`, snapshot before public actions, restore on failure, and validate postconditions. Route gold transfers through a shared primitive. Support a whitelist command endpoint with idempotent action IDs and a process-level lock.

**Reason:** Detect and prevent partial state corruption while the prototype is small. This is explicitly *not* a substitute for database transactions, authentication or persistent replay in a real online game.

## ADR-009: Separate active engine from archived economic benchmark (2026-11-02)

**Decision:** Move the original fixed-price settlement into `experiments/legacy_economy.py`. Make the five-city demo the default CLI, while preserving the `--legacy` mode and imports.

**Reason:** Avoid maintaining two divergent production world models while keeping the research baseline reproducible.
