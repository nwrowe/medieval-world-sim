# Medieval World Simulation (working title)

An exploration of a persistent, text-first medieval fantasy RPG inspired by the **depth** of player-driven games such as Torn City, not a clone of their content or mechanics.

**Central hypothesis:** a persistent world populated with autonomous NPCs can feel alive from day one, support an emerging human community, and help us test complex game economies before launch.

> **Status:** Discovery / experimental prototype. No final game title, business model, server stack, or AI provider has been selected.

## Product direction

Players enter an established medieval civilization where they may become adventurers, artisans, merchants, guild leaders, or political powers. The world should function without them but respond meaningfully to their decisions. Economic scarcity, factions, reputations, and geographically grounded resources create consequential interactions.

The NPC system is **hybrid**:

- **Rules-driven citizens:** farming, mining, travel, routine purchases, and other frequent inexpensive decisions.
- **Goal-directed agents:** strategic leaders, merchants, and notable characters who may later use language models for intermittent planning and dialogue.
- **Authoritative engine:** all economic transfers, inventory, combat, and territory changes are validated by the same game rules for humans and NPCs.

## Current active prototype

The **five-city world engine** is the active development target, modeling region-specific resources, asynchronous travel, companies, manufacturing, markets, quality equipment, combat, stamina, and progression. Gameplay rules are composed as independent systems using one shared domain world state. The original simple 200-citizen economy remains a reproducible baseline for comparison, not the foundation for future game features.

Run `python -m medieval_world_sim` to see the current regional manufacturing demonstration, or `python -m medieval_world_sim --scenario combat` to exercise combat. A seeded rules-based autonomous NPC experiment is now available; there is still no online server or persistent multiplayer world.

## Original single-settlement baseline (retained experiment)

This repository includes a **small, runnable, deterministic economy simulation** with farmers, woodcutters, miners, blacksmiths, and guards. It has fixed-price trading, a finite royal treasury, production, food consumption, daily summaries, and tests for core accounting invariants.

It intentionally **does not** yet include AI language models, guilds, diplomacy, procedural storytelling, a web server, or real players. The simulation is a test harness, not a completed game and not proof the economy is balanced. Some failures (such as treasury exhaustion) are useful findings.

### Try it locally

Requires Python 3.11 or newer; no third-party dependencies.

```bash
python -m pip install -e .
python -m medieval_world_sim --legacy --citizens 200 --days 30 --seed 42
python -m unittest discover -s tests -v
```

For machine-readable results:

```bash
python -m medieval_world_sim --legacy --citizens 200 --days 30 --seed 42 --json
```

## Read next

- [Product brief](docs/PRODUCT_BRIEF.md) — audience, vision, principles, and open questions.
- [First baseline results](docs/BASELINE_RESULTS.md) — reproducible demonstration of treasury exhaustion and food affordability.
- [Simulation design](docs/SIMULATION_DESIGN.md) — NPC tiers, economic invariants, test goals.
- [Roadmap](docs/ROADMAP.md) — smallest useful milestones and exit criteria.
- [Risk register](docs/RISKS.md) — product and engineering risks.
- [Initial backlog](docs/BACKLOG.md) — proposed GitHub issues in priority order.
- [Decision log](docs/DECISIONS.md) — initial architectural decisions and assumptions.

## Principles

1. A compelling world even with few human players.
2. Human choices matter more than NPC theatrics.
3. One set of rules for the world: no AI-generated money or items.
4. Honest NPC identity: never disguise bots as human players.
5. Cheap, deterministic routine actions; selective model reasoning for consequential decisions.
6. Extendable, testable modules; avoid deep inheritance and a god-object controller.
7. Economy and combat integrity first; monetization must not destroy competitive fairness.

## Collaboration

This is an exploratory, initially private project. We should validate the core premise with small simulations and real player tests before investing heavily in lore, a large game world, or infrastructure.

No license is granted by this repository until one is explicitly selected.

## Experimental five-city economy (new)

A separate [five-city regional domain model](docs/FIVE_CITY_ECONOMY.md) now explores travel, finite resource deposits, local escrowed markets, NPC/human workers, company ownership, and company-funded wages. It powers the primary five-city demonstration; the original one-town economy remains a separate legacy experiment.

Run the regional tests with:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_regional_world.py' -v
```

To see a complete ore + coal → steel → sword transaction with travel and gold accounting:\n\n```bash\npython -m medieval_world_sim.regional_demo\n```\n\nOr run all tests via `python -m unittest discover -s tests -v`.

## Equipment quality and combat prototype

See [Equipment and Combat](docs/EQUIPMENT_AND_COMBAT.md). Durable weapons, armor, shields, and tools now have unique IDs, quality (1–100), durability, and owner/escrow accounting. Crownreach sells always-available rough starter gear for a fixed gold price. Players/NPCs may equip and trade gear; combat permits unarmed attacks, uses armor for defense, wears equipment, grants combat XP, and transfers a capped amount of existing enemy gold on victory.

```bash
python -m medieval_world_sim.combat_demo
python -m unittest discover -s tests -v
```

The original one-town simulator remains a separate baseline; these features extend the regional simulator only.

## Code organization

The **five-city WorldEngine** in `core/engine.py` is the primary model, using composed actor vitals/progression/travel components and mutable city state. Gameplay rules live in `systems/` (travel, resource extraction, companies, markets, combat), which operate on the authoritative world state. `regional_world.py` remains a compatibility import for existing scripts. The original toy economy is preserved in `experiments/legacy_economy.py`, with `simulation.py` as a compatibility module.

```bash
python -m medieval_world_sim             # five-city resource/manufacturing demonstration
python -m medieval_world_sim --scenario combat
python -m medieval_world_sim --legacy --citizens 200 --days 30 --seed 42 --json
```

See [Architecture](docs/ARCHITECTURE.md) for module boundaries and the in-memory transaction trade-offs.

## Autonomous NPC economy (rules-driven experiment)

Independent NPCs gather regional resources, carry or trade materials, manage capital companies, earn wages, craft quality-bearing gear, buy equipment, and sometimes fight. Each NPC receives a seeded personality (greed, curiosity, risk, Gaussian decision noise); the policy returns **action proposals**, not state changes. Every proposal executes through the authoritative game command interface. This is intentionally not yet reinforcement learning.

```bash
python -m medieval_world_sim.agents.demo --npcs 28 --days 6 --seed 42
python -m medieval_world_sim.agents.demo --npcs 50 --days 30 --seed 42 --json
```

See [autonomous NPC design](docs/AUTONOMOUS_NPCS.md) and [the 30-day economic experiment](docs/NPC_30DAY_RESULTS.md). The experiment exposes genuine shortages and financing failures; it is **not** proof of a balanced, self-sustaining economy.
