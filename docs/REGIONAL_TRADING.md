# Regional trading and cargo rules

Regional merchants provide a simple, intentionally **partly artificial** price differential on top of existing player/company escrow listings. This is intended to make travel and commerce viable even with few human players.

## Trade quotes

For raw materials, a city quotes two prices:
- **Buy from merchant**: the player pays the city's *ask* and receives actual stocked units.
- **Sell to merchant**: the player receives the city's *bid*, paid out of that city's finite household treasury.

Producing cities deliberately have lower asks for their specialties; Crownreach deliberately posts higher bids for those goods. Other nonproducing cities quote intermediate premiums. Examples, prior to any scarcity adjustments:

| Resource | Source city | Source player purchase | Crownreach player sale | Gross margin / unit |
|---|---|---:|---:|---:|
| Iron ore | Ironvale | 5 gold | 8 gold | 3 |
| Coal | Emberfall | 5 | 8 | 3 |
| Timber | Greenhollow | 4 | 7 | 3 |
| Grain | Goldmeadow | 3 | 6 | 3 |
| Hides | Goldmeadow | 5 | 8 | 3 |
| Herbs | Greenhollow | 4 | 7 | 3 |
| Stone | Emberfall | 3 | 6 | 3 |

**Gross margin is not guaranteed profit**. Buyers must pay their own costs, carry goods to the destination, find municipal purchasing capacity and city funds, and accept the bid on arrival. Both the bid and ask are inspectable using \`world.regional_quote(city, item)\`.

The immediate buying and selling spread within one city is **negative** for the trader. Prices adjust modestly with inventory scarcity or excess stock; they are stable and explainable, not a random gold generator.

## Asset controls

- Municipal inventories are physical units, separated by city and resource. They begin with a small opening stock and are **not** minted when someone buys from the merchant.
- Once per day, a city can restock up to six units of each locally sourced material **by consuming actual regional deposits**. That restock competes with active gatherers for the same materials.
- The city buys at most **16 units** and sells at most **16 units** of merchant goods per day, across all commodities, resetting at midnight. Municipal storage is capped at **32 units of each raw commodity**.
- City spending comes from its existing, finite household gold (the same gold account used by background residents); there is no merchant subsidy or unbacked unlimited demand.
- Successful purchases and sales are atomic, idempotent via \`WorldEngine.execute\`, and recorded as typed \`regional_bought\` or \`regional_sold\` events.
- Companies and users can still trade via local player markets; merchants are an alternative trading venue, not an automatic market-maker for everything.
- These direct municipal merchant actions are presently restricted to *characters*, not company-owned cargo logistics.

## Travel cargo limits

**In-city carry limit: 20 units. Travel limit: 12 units.**

Each stackable unit and each physical equipment piece occupies one cargo unit, including equipped gear. Before departure, \`WorldEngine.start_travel\` rejects any character carrying over 12 units. The player may unload, sell or consume goods locally before setting out. No remote transactions are allowed while traveling.

This count-based cargo model is a deliberately simple first iteration; differentiated weight, pack animals, wagon upgrades, hired caravan services, escort risk, and ambushes are future features. When implemented, they should remain bounded and priced so unlimited free carrying isn't possible.

## NPC haulers and reproducible economics

Hauler NPCs observe a detached, public regional price board, buy stock in resource-producing cities only if Crownreach has a higher funded bid, travel physically, and sell carried stock. Their decisions are still seeded and rule-driven; there is no new learning model. Simulation results now include the number and gold volume of municipal trades and hauler cash changes.

\`\`\`bash
python -m medieval_world_sim.agents.demo --npcs 50 --days 30 --seed 42 --json
python -m unittest discover -s tests -v
\`\`\`

**Next system after regional commerce:** mana and magic progression. See [Magic progression design](MAGIC_PROGRESSION_PLAN.md).
