# Five-City Economic Sandbox (Prototype v1)

**Status:** first implementation under review. Names, intervals, and recipes are initial balancing placeholders.

## Map and geographic scarcity

| Settlement | Role | New regional deposits / simulated hour | Road to capital |
|---|---|---|---|
| Crownreach | Capital, market and manufacturing | No natural deposit | — |
| Ironvale | Ore mining | 3 iron ore | 90 minutes |
| Emberfall | Coal and stone | 3 coal, 2 stone | 70 minutes |
| Greenhollow | Forestry and alchemy | 3 timber, 2 herbs | 45 minutes |
| Goldmeadow | Farming and ranching | 3 grain, 2 hides | 60 minutes |

Travel between two satellite settlements routes through Crownreach (e.g., Ironvale → Emberfall = 160 minutes). Each deposit begins with 8 units and replenishes up to 24 units. Gathering is limited to 2 units per hour per actor. No resource can be gathered from a city that does not produce it.

These are **simulation clock minutes**. No one must wait 90 minutes to run automated tests. The future server will use persistent real-time deadlines; the simulator can fast-forward with a command.

## Catalog

**Raw:** iron ore, coal, stone, timber, herbs, grain, hides.

**Processed:** steel, leather, planks.

**Equipment:** sword, axe, shield, plate armor, leather armor, bow, pickaxe, healing potion.

Only resources with recipes can currently be crafted; grain, stone, and some equipment are reserved for later consumption/building systems. The recipe IDs and categories are deliberately data-driven so adding a new item does not require rewriting the world engine.

| Capital business | Inputs per worker shift | Output |
|---|---|---|
| Steelworks | 2 iron ore + 1 coal | 1 steel |
| Tannery | 2 hides | 1 leather |
| Sawmill | 2 timber | 2 planks |
| Forge | 1 steel + 1 timber | 1 sword |
| Weaponsmith | 1 steel + 1 timber | 1 axe |
| Shieldmaker | 2 planks + 1 steel | 1 shield |
| Armorer | 3 steel + 1 leather | 1 plate armor |
| Leatherworker | 2 leather | 1 leather armor |
| Bowyer | 2 planks | 1 bow |
| Toolmaker | 1 steel + 1 timber | 1 pickaxe |
| Apothecary | 2 herbs | 1 healing potion |

These are gameplay recipes, not metallurgical or historical accuracy claims. Some future processes (ore smelting, fuel, time, equipment quality) should be split further **if** they create interesting strategic decisions.

## User journey (implemented at domain level)

1. A player or disclosed NPC travels to Ironvale and gathers ore.
2. The traveler carries ore to Crownreach in 90 simulated minutes.
3. Traveler posts a market offer. Goods are moved into city-held escrow.
4. A player- or NPC-owned steelworks buys the offer from its own balance.
5. A contracted worker completes one shift consuming **2 ore + 1 coal**. The company receives steel, worker receives gold or agreed goods from company stock.
6. Steelworks sells the steel; a forge purchases it, adds timber and a shift of labor, and makes a sword.
7. A sword can be sold or given to a worker as wages in kind.

The actor \`kind\` is \`human\` or \`npc\`, but the exact same rules apply.

## Economic and authority rules

- **Gold is conserved:** starting actor gold moves to company capital during founding, and subsequently flows through escrowed offers and payroll. Never award wages from nowhere.
- **Production is explicit:** regional deposits regenerate at bounded rates, gathering transfers from city deposits into character inventories, and crafting consumes specified input quantities before producing output.
- **Physical location matters:** traveling actors cannot gather, start travel again, post offers, or accept offers. Offers remain in their posted city even if the seller travels away.
- **City-held escrow:** offered goods leave seller inventory immediately. A seller must return to listing city to cancel and reclaim unsold goods. Partial fills work.
- **Authority:** human/NPC actors can control themselves; only a company owner can post offers, buy goods, or hire on behalf of a company. Workers can only perform valid, hired shifts.
- **Payroll:** contracts may pay gold, equipment/materials, or both; payroll must be funded. Owner investment creates the company account, not gold.
- **Inventory:** 20 carried units per character in the prototype, unlimited company storage. This is an intentionally simple placeholder for weight, cargo vehicles, and warehouse fees.
- **Failure semantics:** invalid actions raise \`ActionError\` without mutating currency, escrow, or materials. Domain actions are synchronous in-memory operations. Server authorization and database atomicity are not implemented yet.

## Not implemented yet

- No automated NPC trading/travel decisions; NPCs can use these actions, but require policies to choose them.
- No public REST/UI, persistence, action IDs, market matching, or asynchronous job runner.
- No direct company scrip yet. "Company money" will need an explicit design for backing, convertibility, transfer rules, and bankruptcy. Otherwise every firm could create infinite purchasing power.
- No nutrition/food, taxes, rent, production equipment, skill progression, item quality, scarcity-priced markets, shipment theft, city-specific shops, or combat.
- Resource regeneration does not represent depletion of minerals across years, and the initial production rates are not balanced.
- The legacy one-town economy simulation remains available as a separate benchmark.

## Next experiment

Add a simple NPC **merchant policy** that sees posted local offers, purchasing opportunities, and travel times, then chooses whether to gather, trade, work, or move. Follow with several scenarios (trade blockade, coal scarcity, insolvency), before introducing LLM-backed leader behavior.

Run tests:

\`\`\`bash
PYTHONPATH=src python -m unittest discover -s tests -v
\`\`\`
