# Simulation Architecture — v0 Exploration

## Separation of concerns

1. **State and rules:** canonical actor inventories, resources, currency, ownership, and all validated transfers. Every action has preconditions and explicit results.
2. **Simulation clock:** deterministic ticks for production, consumption, market orders, training, and travel.
3. **Behavior policy:** routine NPCs use compact rules; notable agents may eventually use planner/LLM proposals, but never change state directly.
4. **Event log and analytics:** every economic transfer and meaningful outcome is logged; snapshots support replay, balance analysis, and diagnostics.
5. **Human interface (later):** thin web/mobile client calls server-authorized commands using the same rules.

```
Human commands   NPC policy decisions   Strategic AI proposals (future)
             \           |            /
                Action validation
                       |
                World state engine
                  /          \
           Event log       Metrics
```

## Current toy model

- One settlement with five occupations: farmer, woodcutter, miner, blacksmith, guard.
- Food, wood, iron, and swords; integer gold; fixed notional prices.
- Producers make goods each simulated day; smiths buy inputs and craft swords; citizens eat food; guards are paid by the treasury; the treasury buys swords.
- A seeded pseudo-random stream shuffles initial occupations and trade priority.
- Gold transfers only among citizens and the treasury; it is never created during a tick.
- The market may run out of funding. This is intentional: it reveals why fiscal sinks/sources and stable demand must be modeled.

## Non-negotiable invariants

- No actor has negative gold, inventory, or other resources.
- Gold is conserved within the closed-world prototype unless an explicit mint/sink is later added and audited.
- Inventory moves through validated production, consumption, or transfer rules.
- NPC identity is distinct from human identity; no bot disguises itself as a human.
- Simulation can be repeated from a seed, version, and initial world state.

## What should come next

1. Replace hard-coded prices with explicit bids, asks, inventories, and matching (while retaining rules and conservation invariants).
2. Add geographic markets with travel time, transportation costs, and risk.
3. Introduce transaction ledger persistence (probably SQLite first), idempotent commands, and replayable events.
4. Define an NPC policy interface: `observe -> propose_action`, then validate and execute.
5. Use strategic agents only for rare, consequential choices: trading treaties, guild policy, war, important dialogue.
6. Instrument wealth inequality, shortages, commodity velocity, price dispersion, starvation, bankruptcies, and treasury health.
7. Build accelerated scenarios, including hoarding, coordinated market manipulation, shortages, and guild monopolies.
8. Only after these are credible, introduce a player-controlled avatar and a minimal browser UI.

## Known limitations of this prototype

- Fixed prices and scripted roles do not constitute adaptive economic AI.
- No saving/loading or durable logs yet; output exists only for the current run.
- Occupation and behavior do not change, there is no wage market for most roles, and all citizens are equally informed.
- No population dynamics, political structures, equipment wear, taxation, resource geography, combat, or social relations.
- Automated simulation cannot establish player enjoyment, retention, acquisition cost, or willingness to pay.
