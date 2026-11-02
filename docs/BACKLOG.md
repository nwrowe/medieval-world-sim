# Initial GitHub Issue Backlog

Each item below can become a focused GitHub issue once the repository exists.

## P0 — Foundation

1. **Define falsifiable design hypotheses** — Agree on target player, retention signals, and what a successful first human session looks like. Deliver: one-page test plan.
2. **Specify world actions and invariants** — Document authoritative transfers, tick order, exhaustion, and transactions. Deliver: action spec + unit tests.
3. **Economic metrics dashboard** — Plot food supply, gold distribution, starvation, treasury exhaustion, and sword production for multiple seeds. Deliver: repeatable metrics and scenario report.
4. **Persistence and deterministic replay** — Add SQLite state/events, stable action IDs, idempotent execution, exact replay by seed. Deliver: save/reload/replay test.

## P1 — NPC and economy experiments

5. **Market order book** — Replace fixed prices with bids/asks and matching, prevent artificial resource creation. Deliver: exchange tests.
6. **NPC policy interface** — Create pluggable `observe -> propose -> validate` policies without granting policies direct world mutation. Deliver: two interchangeable policies.
7. **Multi-settlement geography** — Add regional resources, caravans, distance, and transport risk. Deliver: one trade-route simulation.
8. **Adversarial simulation scenarios** — Test cartel pricing, hoarding, resource monopoly, treasury collapse, mass hunger, and malicious invalid actions. Deliver: scenario regression suite.
9. **Strategic-agent experiment** — Compare scripted and model-assisted noble/merchant decisions with bounded budgets and audit logs. Deliver: cost/benefit report (no provider lock-in).

## P2 — First human experience

10. **Browser-playable vertical slice** — Create one mobile-friendly town with inventory, work, trading, and local feed. Deliver: human player can affect simulation.
11. **NPC disclosure and interaction UX** — Clear NPC badges and appropriate dialogue boundaries. Deliver: testable interface.
12. **Usability and retention pilot** — Invite 20–30 players, collect qualitative feedback and human-only session metrics. Deliver: go/no-go evidence.

## Later

Guild politics, contested resources, combat, alchemy, long-term progression, player-owned land, moderation, anti-cheat, monetization studies.
