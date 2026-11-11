# Oathmere — Geography-Driven Town Resource Economy

The key purpose of procedural geography is **regional economic specialization**.
Each town must have believable natural advantages, secondary production and
shortages. These differences should create commercial opportunities for a
future deep industrial economy, without arbitrarily distributing goods.

## What the survey provides

Generate a world:

```bash
PYTHONPATH=src python -m medieval_world_sim.worldgen --seed 7 --output seed7
```

Open **`seed7/town-resources.md`** for a town-by-town overview:

| Field | Meaning |
| --- | --- |
| Primary | The town's two strongest locally produced raw resources (or fewer if little exists) |
| Secondary | Other raw resources with plausible local production |
| Lacking | Raw resources with **zero modeled local production** under the current survey |
| Geographic justification | Actual supporting hex count, local geology or biome/soil evidence, mean resource potential |
| Estimated extraction | Existing proposed resource units/hour, **not local stock or export surplus** |
| Industry dependencies | Existing crafting recipe input requirements expanded through processing chains |
| Supplier candidates | Another town with plausible output, connected by generated roads, with estimated travel time |

Click a city in **`seed7/atlas.html`** or use the **Jump to a settlement**
selector to see the same resource profile alongside the actual surrounding
hexes. Export **`seed7/town-resources.json`** for typed machine-readable
data that a future economy adapter can consume. It declares its own schema
version, seed, generator version and units; the profile data is also retained
in the general `world.json` manifest.

## What makes the assessment geographic

Each settlement's original resource production is estimated from the
**same five-hex catchment** used during city founding. Resource potential
comes from the actual elevation, geology, biomes, rainfall and soil maps.

- Iron ore is present on suitable igneous/metamorphic rock in highland terrain.
- Coal appears in coal-bearing basins.
- Stone is supported by quarryable rock and upland geology.
- Timber requires forest, taiga or rainforest.
- Herbs grow in appropriate forests, wetlands or grasslands.
- Grain requires sufficient soil fertility and mild temperature.
- Hides and meat depend on grazing/pasture habitat.
- Vegetables depend on fertile, temperate soils.

The report never invents a favorable resource: a primary or secondary resource
must exist in the *current* town's generated `production` dictionary with
positive capacity. Every one of the game's nine canonical raw resource IDs is
classified **exactly once**. The 'lacking' category signals a shortage in
*local extraction capacity*, **not** literal absence, depleted inventory or a
permanent ban on locating goods there. Evidence is not freeform AI lore:
it quotes the number of real supporting map hexes and their dominant geology,
habitat, or mean fertile soil measurements.

## Supply chains: industries consume real inputs

The survey imports the authoritative **13 existing company recipes** from
`medieval_world_sim.content.catalog.RECIPES`; there is no separate duplicate
ingredient catalog. For each candidate industry, the generator expands
processed ingredients into their underlying raw requirements.

Examples:

| Business | Raw material chain per craft | Economic consequence |
| --- | --- | --- |
| Steelworks | 2 iron ore + 1 coal | Iron-producing towns without coal must import it |
| Forge | 2 iron ore + 1 coal + 1 timber (steel made upstream) | Blacksmiths need metal fuel and wood, locally or through trade |
| Sawmill | 2 timber | Forest towns have a plausible local advantage |
| Bakery | 2 grain | Farming towns can build a flour-to-bread economy |
| Armorer | 6 iron ore + 3 coal + 2 hides | Metal and leather supply must be coordinated across production chains |

Recipe expansion reflects the currently defined recipes and their output
yields. The full industry opportunity matrix records which raw inputs can
be sourced locally and which would need imports. **A suggested industry is
not an existing company, and an import need is not actual demand.**

For every missing raw resource that another generated settlement can
potentially produce, the survey chooses a supplier candidate using the
actual road graph, estimated travel minutes and source production rate.
These routes are proposals: they do not create trades, manufacture surplus,
move inventory, charge gold, or grant player access to discovered deposits.

## Design boundary for future economic integration

The complete game economy should have distinct layers:

1. **Deposits / natural capacity:** stable geology/ecology and this regional
   resource survey. This changes only with explicit geography revisions,
   depletion rules or environmental events.
2. **Extraction:** actual businesses, labor, equipment, efficiency and
   operating costs determine how much of the potential becomes new stock.
3. **Demand:** manufacturing recipes, population consumption, construction,
   maintenance and events determine how much local output is used.
4. **Market inventory:** physical stock at each city, including imports,
   exports, purchases, spoilage and storage costs.
5. **Transport:** actual caravans and future ships spend travel time,
   capacity, risk and money to move material between cities; high-value
   chokepoints and shorter routes should matter.
6. **Prices and trade incentives:** scarcity is defined by **actual stock,
   production and demand**, not just by a missing resource rating.

The existing five-city `content.catalog.CITIES` and active game servers
remain unchanged. Generated town IDs are not yet authoritative live city
IDs. Do not directly replace production, inventories or prices in old saves:
the geographic-world adapter and migration/replay rules are a separate step.

## Regression guarantees

The worldgen test suite checks that every town classifies all nine raw
resources, the resource tiers match genuine production rates, the supporting
hex counts and mean potentials match the map, the industrial input DAG
matches the actual recipes, supplier candidates genuinely produce the
missing material and have connected road travel times, reports retain
their world version, and renaming Crownreach does not alter its deposits.

**Version 8** adds `resource_profiles` to generated manifests; old v7
candidate atlases are not overwritten or reinterpreted. The resource report
and clickable inspector are designer views, not player discoveries.
