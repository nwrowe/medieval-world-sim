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
