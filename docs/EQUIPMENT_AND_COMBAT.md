# Equipment Quality, Gear Ownership, and Combat — v0

This document covers the deterministic **five-city** experiment. Values and combat rules are balancing placeholders, not a complete PvP design.

## Individually generated equipment

Every durable item (sword, axe, bow, shield, armor, pickaxe) has a unique item ID, type, quality **1–100**, current/max durability, and an auditable creation origin. Materials, grain, and healing potions remain stackable commodities; potions are not wearable gear.

| Quality | Rarity |
|---|---|
| 1–19 | Rough |
| 20–39 | Common |
| 40–59 | Fine |
| 60–79 | Superior |
| 80–94 | Masterwork |
| 95–100 | Legendary |

Crafting rolls a deterministic, skewed quality based on world seed, worker, company, time, and item ID. New crafted equipment ranges from **20 to 100**, with exceptional items unusual (around 2% at 95+ under this provisional distribution). In the future a *crafting skill*, workshop upgrades, rare ingredients, and crafted materials can influence the roll.

Gear quality affects battle effectiveness. Suggested resale value increases nonlinearly with quality and is also discounted for wear; it is an **indicative valuation, not enforced market pricing**. Items listed at markets are escrowed by unique ID, so sellers cannot accidentally sell or equip the item twice. Quality and durability travel with the item when traded or paid as wages.

## Permanent capital starter vendor

A royal outfitter in **Crownreach** sells an inexhaustible supply of poor quality-10 durable gear at fixed introductory prices. Its selection includes all current durable gear types. It is explicitly a **gameplay source**, not a resource-preserving workshop. Every purchase is logged, and all gold paid is moved into a separate crown account rather than quietly deleted. The royal outfitter does **not** buy back goods.

This is an intentional safety valve to make weapons and armor accessible when player production is thin or a cartel hoards iron. Starter gear is much weaker and has half its normal durability, giving player-made gear useful advantages. Capital travel is still required to buy it.

## Equipping

Actors can own multiple distinct pieces of gear and equip by item ID. Current slots: **weapon**, **body**, **offhand**, and **tool**. Equipping new gear replaces the previous item in that slot without destroying it. Only owned, unbroken, non-escrowed gear can be equipped. Selling equipped gear automatically unequips it. Tools do not replace attack weapons.

## Combat and demand

- An attacker must equip a weapon and be in the same city as the target.
- Civilian NPCs are safe; only NPCs flagged \`hostile\` may be attacked. Human-vs-human PvP requires both parties to opt in.
- One strike deals at least 1 damage. Stronger and higher-quality weapons increase attack, and equipped body armor/shields mitigate incoming damage.
- A surviving defender with a weapon automatically counterattacks. Both sides lose durability on used equipment.
- Hits grant combat XP; winning a fight transfers at most **10 gold** from the defeated enemy's *existing gold account*. The winner cannot loot the same defeated body again during recovery.
- Attack cooldown: **5 simulation minutes**; defeat recovery: **60 simulation minutes**, restoring health. Gold is never minted by combat.
- At zero durability, gear breaks and disappears from the world, creating ongoing demand for manufacturing and trading replacements.

These are *basic PvE mechanics*, not a competitive combat balance specification. Better gear changes outcomes without making quality-10 starter gear useless. Later, hits/skill, tactics, team battles, item condition repairs, and gear drop mechanics can deepen the system.

### Economic design choice

Gold rewards are real transfers from another participant's wallet. That is sustainable in terms of conservation, but would eventually drain hostile NPC wallets. A future option is a **treasury-funded bounty contract**, with explicit budgets, reward limits, and NPC earnings. No invisible payout faucet is included in this experiment.

Likewise, permanent starter supplies deliberately introduce equipment into the world. Because the produced items are low quality and wear quickly, they should not undermine regional manufacturing, but that hypothesis needs testing.

## Known limitations and future tests

- No persistent state or secure network authentication. IDs are trusted inside this local simulation only.
- No autonomous NPC combat decisions, NPC revenue/jobs for bandits, world-wide reputation, leveling bonuses, repair system, healing mechanics, death penalties, or resource-specific crafting quality yet.
- A wage contract references an item type, not a particular promised minimum quality. Equipment wages currently choose the company's lowest-quality eligible piece.
- No item provenance chain beyond creation origin and world events; durable event persistence and replay are future work.
- Direct game-object mutation is possible in a Python test harness; a production server must encapsulate all state mutations.
- No gold rewards for repeated hits. Combat XP rewards hits; gold transfers occur only on defeat.
- **Attack rewards don't guarantee profitability:** players may lose more in starter replacement costs than they win, which creates strategic choices and demand.

## Run

\`\`\`bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m medieval_world_sim.regional_demo
PYTHONPATH=src python -m medieval_world_sim.combat_demo
\`\`\`

This is a **stacked change** on top of the five-city prototype (PR #9). Review/merge the five-city model first, then the quality/combat features.
