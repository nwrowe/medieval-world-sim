# Food, workforce quality, and finite city demand

This proposal is implemented on `feat/food-company-quality-city-demand` and builds on [autonomous NPCs](AUTONOMOUS_NPCS.md).

## Material and company catalog

Existing gatherables include ore, coal, stone, timber, herbs, grain, and hides. We added **meat** to Goldmeadow and **vegetables** to Greenhollow. Existing factories remain data-defined; three new finished-product chains are:

| Company | Inputs | Finished output | Primary buyer |
|---|---|---|---|
| Bakery | 2 grain | 3 bread | Players, NPCs, local households |
| Tavern | 1 bread + 1 meat + 1 vegetables | 2 prepared meals | Players, NPCs, local households |
| Apothecary | 2 herbs | 1 healing potion | Players, NPCs, local households |
| Forge | 1 steel + 1 timber | 1 quality-bearing sword | Players, NPCs, local households |
| Leatherworker | 2 leather | 1 quality-bearing leather armor | Players, NPCs, local households |

The original steelworks, tannery, sawmill, bowyer, armorer, shieldmaker, and toolmaker recipes are retained. No new company subclasses are needed.

## Recovery

A character tracks life, stamina, and a small nonlethal `hunger` meter (0–3). Hunger increases by one per simulated day. Food is a useful buff, not yet a hard survival requirement.

- Bread: +1 life, +10 stamina, −1 hunger.
- Prepared meal: +2 life, +20 stamina, −2 hunger.
- Healing potion: +8 life.

Effects never exceed maximum life or stamina; consumed goods leave the inventory. Defeated characters still cannot act until recovering, so a defeated player cannot instantly resurrect with a potion. Consumption uses the same authorized `execute` command path as combat.

## Working experience, facilities, company quality

Every actor has a `WorkStats` component with Manual, Intelligence, Endurance, an actual-shifts count, and industry-specific experience. A successful paid shift grants one occupation XP (two with a **training** perk). Each fifth shift adds one relevant work stat. Shift requirements still consume real company ingredients and transfer real wages.

The company-quality score uses current employee work effectiveness, its facility level, and completed production shifts. It is capped to 0–100 and exposed as 1–5 stars. The score affects simulated daily demand; occupation XP and facilities modestly improve actual crafted gear quality. A lucky crafting roll can still outperform a higher-rated facility.

Company owners can:
- Offer an employment contract, which the worker must accept before becoming employed.
- Change an existing employee's wage. A suggested wage is computed from actual industry effectiveness, but the owner sets the offered pay.
- Choose perks: `training` improves occupation experience but costs the company an additional 1 gold per worked shift, paid to the audited crown treasury; `meal` provides real bread inventory when available; `medical` provides a stocked healing potion when available.
- Upgrade facilities 1→5 by paying an increasing gold cost to an explicit treasury account.
- Inspect company quality and suggested wages.

The legacy immediate `hire` call is preserved for existing tests and NPC seeding, but **new player-facing hiring should use offer/accept**.

## Abstract city customers

Each city contains a **funded household wallet** separate from individual simulated NPCs. At world creation, the prototype endows Crownreach with 3,600 gold for 500 abstract residents and the other cities with 600 gold each for 120 residents. This opening money is *included in initial global money*. No gold is minted by sales.

On each simulated day boundary, city households can buy actual manufactured products from businesses located in their city, within:
1. The city's finite remaining household wallet;
2. A per-day spending cap proportional to population;
3. Product demand based on company quality and a deterministic seeded ±1 demand roll;
4. Company-owned finished stock, including existing market escrow; 
5. A bounded price relative to item and product quality.

Stock is **removed** when sold, and money moves from `CityState.household_gold` to `Company.gold`. Individually tracked gear and escrow IDs are retired from the playable item registry on abstract household purchase, preventing double-sales. The economic event ledger records a `city_sale` with city, company, item, price, star rating, and day.

These are **sales receipts**, not unconditional passive gold or fully calculated profit. Wages, bought inputs and facility costs remain real costs; nothing is sold if the company produces no goods or the city's wallet runs dry.

## Limitations / next economic experiment

The household endowments are a **finite test fixture**, not durable economic replenishment. After enough days, consumption can exhaust their wallets; players buying and selling, rent, taxes, public salaries, seasonal changes and additional economic flows still need design. Future reports should distinguish **revenue, labor expense, input cost, inventory assets, and actual profit**.

No player starvation penalties, combat potion cooldowns, concurrent online server, employee retention model, actual city-population simulation, or dynamic price discovery are implied by this prototype.
