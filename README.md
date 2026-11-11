# Oathmere

An exploration of a persistent, text-first medieval fantasy RPG inspired by the **depth** of player-driven games such as Torn City, not a clone of their content or mechanics.

**Central hypothesis:** a persistent world populated with autonomous NPCs can feel alive from day one, support an emerging human community, and help us test complex game economies before launch.

> **Status:** Oathmere is a playable, local-development prototype. Single-player JSON saves and an invite-gated, localhost-only SQLite multi-account mode exist. It is **not production ready** and must not be exposed directly to the internet.

## Product direction

Players enter an established medieval civilization where they may become adventurers, artisans, merchants, guild leaders, or political powers. The world should function without them but respond meaningfully to their decisions. Economic scarcity, factions, reputations, and geographically grounded resources create consequential interactions.

The NPC system is **hybrid**:

- **Rules-driven citizens:** farming, mining, travel, routine purchases, and other frequent inexpensive decisions.
- **Goal-directed agents:** strategic leaders, merchants, and notable characters who may later use language models for intermittent planning and dialogue.
- **Authoritative engine:** all economic transfers, inventory, combat, and territory changes are validated by the same game rules for humans and NPCs.

## Current active prototype

The **five-city world engine** is the active development target, modeling region-specific resources, asynchronous travel, companies, manufacturing, markets, quality equipment, combat, stamina, and progression. Gameplay rules are composed as independent systems using one shared domain world state. The original simple 200-citizen economy remains a reproducible baseline for comparison, not the foundation for future game features.

Run `python -m medieval_world_sim` to see the current regional manufacturing demonstration, or `python -m medieval_world_sim --scenario combat` to exercise combat. A seeded rules-based autonomous NPC experiment and a localhost multi-account development server are available. See [local setup](docs/MULTIPLAYER_LOCAL_DEVELOPMENT.md). Neither is an internet-ready hosted multiplayer service.

## Original single-settlement baseline (retained experiment)

This repository includes a **small, runnable, deterministic economy simulation** with farmers, woodcutters, miners, blacksmiths, and guards. It has fixed-price trading, a finite royal treasury, production, food consumption, daily summaries, and tests for core accounting invariants.

It intentionally **does not** include AI language models, diplomacy, or procedural storytelling. This *legacy baseline experiment* is separate from Oathmere's current web client, guilds, and human-account development mode. The simulation is a test harness, not a completed game and not proof the economy is balanced. Some failures (such as treasury exhaustion) are useful findings.

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

## New: lineages and the explored atlas

New players begin in Crownreach, select Human, Elf, Dwarf or Orc lineage,
and initially see only their known city through the map's fog of war.
Lineage provides small, server-calculated work and physical combat bonuses,
plus a unique passive trait at level 3. Exploring another city reveals it
permanently on that character's map. Older saves and local multiplayer
accounts choose a lineage once without losing historical progress.

See [Lineages and Exploration](docs/LINEAGES_AND_EXPLORATION.md) for rules,
compatibility, limitations and future dungeon/party plans.

## Geography-first world generator (prototype)

Oathmere now has a separate, seeded **world atlas generator** that builds terrain,
climate, rivers and geology before founding settlements, routing roads and placing
exploration sites. The v3 generator uses true six-neighbor hex topology,
hex-aligned coastlines, varied mountain uplift, shaded relief and terrain-aware
river meanders. It exports a clickable HTML tile inspector, static SVG map and versioned JSON manifest;
it does **not** replace the active five-city map or mutate existing saves.

```bash
python -m medieval_world_sim.worldgen --seed 7 --output generated-world
python -m unittest discover -s tests -p 'test_worldgen.py' -v
```

Open `generated-world/atlas.html` to inspect elevation, natural and road-adjusted
walking difficulty, estimated travel times and authored sites.
Open `generated-world/history.html` to step through six geography-driven
historical eras, including founded towns, trade roads, political leagues and
abandoned sites. See [Historical Development](docs/HISTORICAL_DEVELOPMENT.md). Every run also
exports `world-content.template.json`: copy it, edit settlement names,
ruin/dungeon coordinates or scheduled event locations, and pass it back using
`--content path/to/world-content.json` to regenerate the atlas.

See [World Generation](docs/WORLD_GENERATION.md) for geographic assumptions,
settlement and site rules, migration boundaries and recommended next phases.

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

## Autonomous NPC playtesting (opt-in)

Two optional simulated characters — **Explorer** and **Optimizer** — now
exercise validated gameplay actions using separate utility preferences. NPC
needs, bounded short-term memory and simple action-value learning remain cheap;
a separate observer produces structured evidence-based reports, either locally
or with an explicitly enabled external LLM critique. An LLM never decides or
executes game actions.

```bash
python -m medieval_world_sim.agents.demo --npcs 28 --days 8 --seed 42 --playtest --reflect-every 30 --report-file playtest-feedback.json
```

For longer, reproducible A/B comparisons over several seeds, run
`python -m medieval_world_sim.agents.compare --seeds 10 --days 30 --npcs 28 --report-file npc-compare.json`.
This produces per-seed income, completed-route profit and character-growth metrics.
The smaller `--seeds 3 --days 4` form is suitable for a quick check.

This is an **offline playtest harness**, separate from the new persistent
multiplayer NPC scheduler. The 15 existing named NPCs in local multiplayer
now autonomously gather, trade and fight with journaled, bounded server-only
decisions; Explorer and Optimizer remain isolated comparison agents. See [NPC playtesting](docs/NPC_PLAYTESTING.md)
for report fields, optional LLM configuration and limitations.

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

Travel requires carrying **12 units or fewer** without transport upgrades, including equipment; ordinary in-city inventory has no 20-unit cap. Stocking goods into market escrow, selling them, or consuming food can free cargo space.

```bash
python -m medieval_world_sim --scenario trade
python -m medieval_world_sim.agents.demo --npcs 50 --days 30 --seed 42 --json
```

See [regional trading and cargo](docs/REGIONAL_TRADING.md). Magic progression and combat spells have since been implemented; [the magic planning document](docs/MAGIC_PROGRESSION_PLAN.md) retains historical design context.

## Six-school magic progression foundation

A shared `MagicState` now tracks renewable mana, six independent school-XP tracks, Insight unlocks and a two-active-specialization loadout. Each school has a novice node, an applied node, two Tier III branches and two Tier IV mastery paths (37 nodes total, including Arcane Fundamentals). Spell practice spends **mana without any additional training cooldown** and earns just **one base school XP per attempt**, making mastery a long-term commitment governed by renewable mana. The Magic page's **100/100** tier bars now represent the actual practice ceilings (Tier I 80 school XP, then 180/420/1000), and each successive tier now requires the **previous tier to reach 100/100** before it can be unlocked with Insight. Older saved magic actions replay using their original unlock rules. Additional magical and combat effects are implemented; remaining proposals in the linked design document are not all complete.

```bash
python -m medieval_world_sim --scenario magic
```

Read the [magic progression architecture](docs/MAGIC_PROGRESSION_PLAN.md) for every branch, requirements and next integration steps.

## Housing and mounted travel

Characters can purchase and improve a city-based **room, cottage, townhouse, estate or manor**. Higher-tier homes provide up to **20% additional training XP** for magic, work shifts and combat performed in their home city, using fractional carryover so small XP rewards aren't rounded into runaway gains. Homes and upgrades have rising prices paid to the crown treasury.

Build a **stable** (Cottage+) for a horse (80% road travel time; 16 travel cargo units), or a **carriage house** (Estate+) for a carriage (60% travel time; 20 travel units). Without a vehicle, travel cargo remains 12 units; local inventory has no fixed 20-unit cap. Vehicles must be purchased and selected at your home. Docks and ships await water routes.

```bash
python -m medieval_world_sim --scenario housing
```

See [property and travel rules](docs/HOUSING_AND_TRANSPORT.md).

## Play the web prototype (phone or desktop)

**Security boundary:** Multiplayer login/cookies are served only on `127.0.0.1` in this phase. The separate single-player LAN mode uses a shared access code and HTTP; use it only on a trusted network. Neither mode is safe for public internet hosting.

The multiplayer development server can now schedule its named NPCs during
trusted world-time advances and safely persist/replay those actions and
bounded cognition on restart. Humans retain exclusive account credentials
and API command authority. Combat and earned magic school XP both advance
character levels; money and combat-loot rules are unchanged. See
[local multi-account development](docs/MULTIPLAYER_LOCAL_DEVELOPMENT.md).

The project includes a **responsive browser client** for single-player and localhost multi-account development. The Python world engine remains authoritative; the browser sends the same validated actions and displays its actual prices, inventory, travel time and magic progression. A JSON action journal automatically saves after every successful action and reconstructs the world when restarted. No frontend framework or external service is needed.

```bash
python -m pip install -e .
python -m medieval_world_sim.web
```

Open **http://127.0.0.1:8765** in your desktop browser. Create a character in Crownreach, travel to Goldmeadow to gather grain, and try trading, studying magic and upgrading your home.

**To play on a phone on the same trusted Wi-Fi network**, run the server on the computer with:

```bash
python -m medieval_world_sim.web --host 0.0.0.0 --port 8765
```

Then open `http://YOUR_COMPUTER_LAN_IP:8765` on the phone and enter the **game access code printed on the computer**. Keep the server running while using the phone. This LAN mode uses ordinary HTTP, so **do not expose it on the internet**. This token-gated single-player LAN mode is separate from the localhost-only multi-account server; neither is ready for public hosting. Firewalls may need an inbound LAN rule.

## Experimental local multi-account mode (invite-gated, loopback-only)

To create separate player accounts on the **same computer**, with a shared world backed by SQLite, use:

```powershell
python -m medieval_world_sim.web --multiplayer-db "$HOME\\.medieval-world-sim\\multi-dev.sqlite3"
```

New accounts now require a one-time operator invitation. After account registration, the player chooses a lineage on a separate welcome screen, then enters the world using **Enter Oathmere**. To issue two codes, stop the server and run `python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-dev.sqlite3" --issue-invites 2`, then restart the server and give one printed code to each player. Existing accounts simply sign in. For the original unrestricted local demo and rapid time travel, explicitly append `--dev-open-registration --dev-fast-forward` to the server command; **do not use those flags for untrusted players**. Passwords are salted and hashed; sessions and actions are tied to the authenticated player. This **localhost-only development mode** is not suitable for public hosting or LAN HTTP. It does not modify or import your single-player save. The shared-world SQLite database now also stores durable, account-bound request receipts, asset and escrow ownership, and versioned snapshots. On restart, Oathmere verifies the durable records, restores the latest checkpoint if present and replays only the remaining journal tail. See [Phase 3 Durability](docs/DURABILITY_PHASE3.md), [Local Multi-Account Development](docs/MULTIPLAYER_LOCAL_DEVELOPMENT.md) and [Phase 1 Security Hardening](docs/SECURITY_PHASE1.md) for mechanics, setup and limitations.

The default save location is `~/.medieval-world-sim/save.json`. To use another save, start the server with `--save /path/to/save.json`. This is a bounded single-player prototype; do not edit the journal by hand. See [web client instructions](docs/WEB_CLIENT.md) for features and limits.

### Google Colab preview

For a Colab notebook iframe, start the web server with `--colab-preview` on `127.0.0.1`, then call `output.serve_kernel_port_as_iframe(8765, height=850)`. The ordinary server still blocks framing by default. See [the Colab instructions](docs/WEB_CLIENT.md#google-colab-notebook-preview) for a complete setup, persistent Drive saves and security limitations.

### Hosted private playtest on Render

To play from any phone or desktop without Colab or leaving your own PC running, see [Render deployment](docs/RENDER_DEPLOYMENT.md). The checked-in `render.yaml` provisions a **paid**, single-instance HTTPS web service with a persistent save disk. You must provide a private `GAME_ACCESS_TOKEN` through the Render dashboard. **Do not deploy the single-player game publicly without this token.** This is not multiplayer hosting; review Render's charges before confirming deployment.
