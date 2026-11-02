# Thirty-day economy results after food, company quality, and city demand

This is an accelerated **50-NPC, 30-day simulation**, seed 42, six-hour NPC decisions. It uses six owner-funded companies and five cities. All purchases, manufacturing, employment, inventory effects, and household sales run through the common world engine.

| Metric | Observed |
|---|---:|
| NPC-to-NPC or NPC-to-company market trades | 621 |
| Market trade volume | 8,690 gold |
| Theoretical household purchases (individual units) | 132 |
| Theoretical household purchasing volume | 3,599 gold |
| Gathered raw resources | 1,068 units |
| Company work shifts | 383 |
| Crafted equipment | 80 |
| Individually simulated NPC gear purchases | 7 |
| Meals or bread consumed by NPCs | 175 |
| Healing potions consumed by NPCs | 0 |
| Combat attacks | 5 |
| NPC wage changes | 14 |
| Facility upgrades | 12 |
| Invalid NPC actions | 0 |
| Total gold before and after | **12,460 / 12,460** |
| Unspent household wallet balance after day 30 | 2,401 gold |

## Company cash outcomes

Every company began with **430 gold** in owner-provided capital. The last observed cash and change relative to that starting amount:

| Company | Day-30 cash | Cash change |
|---|---:|---:|
| Bakery | 777 | +347 |
| Tannery | 520 | +90 |
| Forge | 397 | −33 |
| Steelworks | 186 | −244 |
| Leatherworker | 35 | −395 |
| Apothecary | 9 | −421 |

**These are cash changes, not net accounting profit**: they exclude the valuation of purchased ingredients, unsold inventory, owner equity, and capital equipment.

The apothecary retained substantial inventory and experienced very little demand for healing potions. We should improve player/NPC health needs and spending decisions before drawing conclusions about potion prices. Food demand provided the strongest recurring purchase incentive.

## Interpretation

The background city population helped real manufacturing companies turn stock into cash without creating individually simulated buyers. The engine **removed actual products** and debited finite household balances for each sale. The households are seeded with funds at world creation, so the long-run spending source is still finite, not a perpetual public subsidy.

The economy improved over the earlier four-company simulation, but this is **not yet a balanced mature world**: medical goods are under-consumed, certain manufacturing industries accumulate unsold stock, and background buyers will eventually deplete their wallets without replenishing economic flows.

This report is a single-seed baseline. Next compare multiple seeds and examine household budget depletion, business inventory turnover, employer wage burden, price discovery, and selective NPC use of potions.

Run:

```bash
python -m medieval_world_sim.agents.demo --npcs 50 --days 30 --seed 42 --json
```
