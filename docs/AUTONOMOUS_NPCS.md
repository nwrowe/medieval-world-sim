# Stochastic Rules-Based NPC Economy

## Architecture

The first autonomous population deliberately uses **cheap, explainable policies**, not a small neural network. Until we have a stable player economy and a meaningful long-horizon reward signal, reinforcement learning would risk learning shortcuts and amplifying economic exploits.

The `agents/` package contains:

- `observation.py`: immutable copies of the fields an NPC is allowed to observe. It never hands policies mutable WorldEngine entities.
- `policy.py`: role-based action candidates with bounded pricing rules, personal greed, risk-taking, exploration, and Gaussian utility-score noise.
- `runner.py`: seeded NPC population, scheduling, authoritative command dispatch, and economy metrics.
- `demo.py`: runnable accelerated scenario.

Policies follow **observe → propose → validate/execute**. Only `WorldEngine.execute(...)` performs runtime actions. NPCs do not modify their own money, inventories, equipment, companies, or the world clock. Every successful command has a unique idempotency key.

## Roles

| Role | Motivations and allowed behavior |
|---|---|
| Gatherer | Collect a region's raw material and sell it locally or carry it to the capital |
| Hauler | Purchase underpriced local materials, transport them, and resell in Crownreach |
| Company manager | Fund a company, monitor inventories, buy recipe inputs and offer products for sale |
| Worker | Perform paid shifts when company ingredients and funding are available |
| Adventurer | Purchase/equip crafted weapons and armor; occasionally fight other adventurers |

Four businesses are seeded at the capital: steelworks, forge, tannery, and leatherworking. A real ore → steel → sword and hides → leather → armor production chain is possible **without scripted trades**. Actor inventories, balances, and resource deposits follow the normal game rules, while company wage funds are finite.

## Where randomness enters

Each NPC has a reproducible personality: `greed` affects asking prices, `risk` affects propensity for combat, `curiosity` sometimes explores lower-scoring options, and `volatility` controls Gaussian noise added to candidate utilities. Higher-utility actions are favored, but NPCs aren't identical deterministic scripts.

The RNG seed is separate from the game engine's equipment-quality seed. With the same world seed, population, scheduling step, and simulation length, the experiment produces **exactly the same outcome**. Different seeds generate different personalities, decision orders, and results.

This is **stochastic utility-based planning**, not reinforcement learning. We may later compare it against a small contextual bandit using observed profit over time, but we should retain this as a transparent baseline.

## Run it

```bash
python -m medieval_world_sim.agents.demo --npcs 28 --days 6 --seed 42
python -m medieval_world_sim.agents.demo --npcs 50 --days 30 --seed 42 --json
python -m unittest discover -s tests -v
```

The simulation defaults to one NPC decision per **six simulated hours**. Travel and gathering cooldowns are still measured in world minutes. This coarse cadence keeps repeated world-snapshot transactions inexpensive for the experimental population. NPCs can have zero decisions during recovery, travel, or lack of viable opportunities.

Supported prototype population: 20–150 NPCs. `run(days, step_minutes)` can use finer cadence where performance permits.

## Metrics

The experiment reports total gold and conservation, market fills and trade volume, raw-material gathering, staffed production shifts, crafted equipment, gear purchases, company cash and profit relative to initial investment, actor gold distributions by profession, open-PvP attacks, idle proposals, and rejected actions.

**Important distinction:** Gold is moved between real in-game wallets or funded companies; trading does not mint gold. Raw deposits replenish according to regional rules. Crafted equipment consumes company inputs. Consequently, a high trade count alone does not establish a balanced economy.

## What is *not* implemented yet

- NPC hunger/food purchases, lodging, taxes, equipment maintenance, company dividends, personal debt or bankruptcy.
- Dynamic order-book price discovery; NPC price expectations are initially data-driven and bounded.
- Persistent player/NPC histories, serialized RNG state, durable replay, secure account authentication, or host-server ticking.
- Specialized NPC policies for guards, bandits, guild leaders, nobles, or diplomacy.
- Deep economic forecasting, formal RL training, or continuous skill learning.
- Strong anti-XP-farming or crime consequences. NPC combat policy presently only targets other adventurers, although the shared combat engine permits unrestricted attacks.

**Next experiment:** compare several 30-day random seeds, measure profitability and shortages, then introduce food demand and more reliable company liquidity *only if data motivates it*. The first simulation is an experiment, not evidence of a production-ready self-sustaining game economy.
