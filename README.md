# Oathmere

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

## Company economy, food and city household sales (proposed PR)

The five-city engine now has **bread, prepared meals and healing potions** with validated recovery actions and a small nonlethal daily hunger meter. Bakery and tavern recipes join the existing apothecary, blacksmith and industrial production chains.

Characters gain industry-specific work experience, and companies calculate a **1–5-star effectiveness rating** from active worker attributes, facilities and completed shifts. Owners can offer employment for voluntary acceptance, set individual wages and perks, and pay for facility upgrades.

Once per simulated day, non-agent **city household buyers** purchase actual finished company inventory or market escrow up to both population-based demand and their finite seeded budgets. Household gold transfers to companies; items leave inventory; no passive gold is minted. The opening household endowment is included in total money and may run out, so economic sustainability still needs long-run testing.

See [company economy design and accounting](docs/COMPANY_ECONOMY.md) for recipes, pay, quality, nutrition and household-budget limits.

## Regional trading and physical travel cargo

Each city now has a funded merchant with a visible bid/ask for raw materials. Regional origin prices are deliberately lower than Crownreach's purchase bids, so players and autonomous haulers can **buy low, travel, and sell high**. Merchant purchases draw real goods from finite city stock; sales return goods to the city and draw gold from the existing city household account. Daily trading quotas and stock capacity prevent unlimited arbitrage.

Travel requires carrying **12 units or fewer**, including equipped gear; the existing **20-unit in-city** inventory limit still applies. Stocking goods into market escrow, selling them, or consuming food can free cargo space.

```bash
python -m medieval_world_sim --scenario trade
python -m medieval_world_sim.agents.demo --npcs 50 --days 30 --seed 42 --json
```

See [regional trading and cargo](docs/REGIONAL_TRADING.md). The **next planned system** is [mana and magical progression](docs/MAGIC_PROGRESSION_PLAN.md), with multiple skill paths, funded magic jobs, and useful combat/utility spells—not implemented yet.

## Six-school magic progression foundation

A shared `MagicState` now tracks renewable mana, six independent school-XP tracks, Insight unlocks and a two-active-specialization loadout. Each school has a novice node, an applied node, two Tier III branches and two Tier IV mastery paths (37 nodes total, including Arcane Fundamentals). Spell practice consumes mana, earns bounded school XP and is seeded/deterministic. Higher-level world effects and funded magical jobs are intentionally **not implemented yet**.

```bash
python -m medieval_world_sim --scenario magic
```

Read the [magic progression architecture](docs/MAGIC_PROGRESSION_PLAN.md) for every branch, requirements and next integration steps.

## Housing and mounted travel

Characters can purchase and improve a city-based **room, cottage, townhouse, estate or manor**. Higher-tier homes provide up to **20% additional training XP** for magic, work shifts and combat performed in their home city, using fractional carryover so small XP rewards aren't rounded into runaway gains. Homes and upgrades have rising prices paid to the crown treasury.

Build a **stable** (Cottage+) for a horse (80% road travel time; 16 travel cargo units), or a **carriage house** (Estate+) for a carriage (60% travel time; 20 travel units). Without a vehicle, travel cargo remains 12 units; the normal 20-unit city inventory limit remains. Vehicles must be purchased and selected at your home. Docks and ships await water routes.

```bash
python -m medieval_world_sim --scenario housing
```

See [property and travel rules](docs/HOUSING_AND_TRANSPORT.md).

## Play the web prototype (phone or desktop)

The project now includes a **responsive, local, single-player browser client**. The Python world engine remains authoritative; the browser sends the same validated actions and displays its actual prices, inventory, travel time and magic progression. A JSON action journal automatically saves after every successful action and reconstructs the world when restarted. No frontend framework or external service is needed.

```bash
python -m pip install -e .
python -m medieval_world_sim.web
```

Open **http://127.0.0.1:8765** in your desktop browser. Create a character in Goldmeadow and try gathering grain, selling it, traveling to Crownreach, studying magic and upgrading your home.

**To play on a phone on the same trusted Wi-Fi network**, run the server on the computer with:

```bash
python -m medieval_world_sim.web --host 0.0.0.0 --port 8765
```

Then open `http://YOUR_COMPUTER_LAN_IP:8765` on the phone and enter the **game access code printed on the computer**. Keep the server running while using the phone. This LAN mode uses ordinary HTTP, so **do not expose it on the internet**; public hosting, HTTPS, accounts and multiplayer are not supported yet. Firewalls may need an inbound LAN rule.

The default save location is `~/.medieval-world-sim/save.json`. To use another save, start the server with `--save /path/to/save.json`. This is a bounded single-player prototype; do not edit the journal by hand. See [web client instructions](docs/WEB_CLIENT.md) for features and limits.

### Google Colab preview

For a Colab notebook iframe, start the web server with `--colab-preview` on `127.0.0.1`, then call `output.serve_kernel_port_as_iframe(8765, height=850)`. The ordinary server still blocks framing by default. See [the Colab instructions](docs/WEB_CLIENT.md#google-colab-notebook-preview) for a complete setup, persistent Drive saves and security limitations.
