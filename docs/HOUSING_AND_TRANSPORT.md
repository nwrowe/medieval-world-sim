# Housing, property training bonuses and travel vehicles

**Status:** Implemented in feature PR, not yet merged. This is a small authoritative property and transportation foundation, not a real-estate trading economy.

## Home tiers

Each character may purchase **one home in the city where they currently are** and upgrade it later at that location. Upgrading pays only the difference between cumulative prices. Real gold moves from the character to the existing crown treasury. Homes cannot yet be resold, rented to others, relocated, or shared; no passive income is generated.

| Home tier | Cumulative price | Local training XP bonus | Facilities supported |
|---|---:|---:|---|
| Rented Room | 90g | 0% | None |
| Cottage | 350g | 5% | Stable |
| Townhouse | 1,100g | 10% | Stable |
| Estate | 3,600g | 15% | Stable, carriage house |
| Manor | 10,000g | 20% | Stable, carriage house; docks planned |

Training bonuses apply to *actual* magical practice, paid work shifts, and combat XP **only when the activity occurs in the city of the owned house**. Bonuses are capped by existing school/work XP ceilings. They do not increase wages, mana, combat damage, or earned gold.

To avoid rounding up every one-point work shift to two points, each character tracks an integer 0–99 fractional XP remainder **per skill domain**. Ten work shifts at a 10% home bonus grant 11 occupation XP instead of 10, not 20. Bonus fractions are kept for the next real action. Thus the displayed percentage accurately matches long-run earned XP.

## Facilities and vehicles

A transportation facility is a separately purchased improvement to an eligible home. A vehicle is likewise purchased, stored and selected at that property. Purchases draw actual character gold into the crown treasury.

| Facility | Build cost | Minimum home |
|---|---:|---|
| Stable | 180g | Cottage |
| Carriage House | 550g | Estate |

| Vehicle | Price | Facility required | Road travel time | Travel cargo cap |
|---|---:|---|---:|---:|
| On foot | Free | None | 100% | 12 units |
| Horse | 250g | Stable | 80% | 16 units |
| Carriage | 950g | Carriage House | 60% | 20 units |

Travel continues to use *real existing roads*, with the vehicle modifier applied to the shortest baseline journey and rounded up to whole minutes. For Crownreach → Ironvale, this means 90 minutes walking, 72 riding, or 54 in a carriage.

Physical travel limits count every unit of stackable inventory **and each piece of equipment**, including equipped items. The existing **20-unit in-city inventory ceiling remains unchanged**. Vehicles carry no additional, unowned inventory, do not teleport goods, and cannot be selected or parked while away from the home property or traveling. A selected vehicle follows its character until they return home and park or change it.

**Docks and boats are intentionally deferred.** The current five-city map only defines road connections. We should establish actual waterways and dock-access cities first, rather than inventing arbitrary sea-route bonuses.

## World APIs

- \`world.housing_view(actor_id)\`: frozen projection of property, upgrades, active vehicle, bonus and cargo capacity.
- \`world.buy_home(actor_id, tier)\`, \`world.upgrade_home(actor_id, tier)\`.
- \`world.build_home_facility(actor_id, facility)\`, \`world.buy_vehicle(actor_id, vehicle)\`, \`world.select_vehicle(actor_id, vehicle_or_none)\`.
- \`world.estimated_travel_minutes(actor_id, destination)\`: personal route time including current vehicle.
- Validated mutating actions are available from the same idempotent \`WorldEngine.execute\` allowlist as the rest of the game.
- The \`HousingSystem.training_xp(actor, base, domain)\` helper centralizes local training math across Work, Magic and Combat, rather than duplicating bonuses in their systems.

\`\`\`bash
python -m medieval_world_sim --scenario housing
python -m unittest discover -s tests -v
\`\`\`

## Future ideas

- Player-to-player sale and renting, property upkeep, shared family homes and guild halls.
- Property-specific equipment/storage, guest access, and resource/XP policies; prevent using multiple houses to stack training bonuses.
- Horses/wagons as actual durable assets, transport upkeep, injuries or road hazards, vehicle theft or escorts.
- Docks, ships and ferries once the world has navigable waterways; shipping must conserve cargo, travel time and economic budget.
- Future variations in training bonus by magical school / profession, with a limit on multiplicative modifiers from perks.

All amounts and speed percentages are **starting game-balance proposals**, not final tuning.
