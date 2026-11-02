# Exploration Roadmap

## M0 — Hypothesis and design alignment (now)

**Deliverables:** product brief, core invariants, smallest simulation, runnable tests, risk register.

**Exit criteria:** 3 falsifiable hypotheses, a named target player experience, and consensus on what NPCs can and cannot do.

## M1 — Credible economic sandbox

Implement order-driven local markets, balanced inflows/outflows, production/consumption, inventory sinks, persistence, replay, and scenario sweeps. Generate charts of supply, poverty, prices, and inequality across seeded runs.

**Exit criteria:** economic conservation tests pass; major failure modes are visible and explainable rather than hidden in scripted adjustments.

## M1b — Regional merchants and magic progression

Introduce regional merchant bid/ask pricing, bounded city inventory, travel cargo limits and profitable hauler routes. Next, prototype a shared mana pool and multiple magical skills: low-level paid magical jobs, mana regeneration and advanced uses in healing, crafting, trading and combat.

**Exit criteria:** merchant trading remains bounded by finite city funds and inventory; real NPCs complete profitable trade loops; spells earn gold only from funded clients and have measurable, skill-gated utility.

See [regional trading](REGIONAL_TRADING.md) and [mana-based magic plan](MAGIC_PROGRESSION_PLAN.md).

## M2 — Hybrid NPC behavior

Introduce policy interfaces, agent goals, memory/reputation, low-frequency strategic planning, bounded decision budgets, and guardrails. Compare baseline rule NPCs with model-assisted agents in the *same* scenarios.

**Exit criteria:** agent actions demonstrably improve realism or engagement proxy metrics without excessive cost or rule bypasses.

## M3 — Human intervention slice

Add one playable town in a mobile-friendly browser. Permit jobs, buying/selling, one combat loop, and social interaction with disclosed NPC characters.

**Exit criteria:** external testers understand their choices and voluntarily return. Measure human retention separately from NPC events.

## M4 — Small private alpha

Invite a limited cohort. Expand guild contracts, resource geography, rivalries, and player-versus-player economic competition. Stress-test moderation, exploit handling, account integrity, and fairness.

**Exit criteria:** observed retention and meaningful human-driven social activity justify further investment.

## Explicitly out of scope for now

Full lore production, procedural dialogue everywhere, native mobile apps, large combat inventory, world-spanning politics, cash shop, and production hosting optimization.
