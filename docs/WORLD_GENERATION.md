# Oathmere: geography-first world generation (prototype v1)

This system produces a deterministic *candidate atlas* from a numerical seed. It is **not yet wired into live game worlds or saved journals**. The current five-city catalog, travel rules, city inventories, player discovery and existing saved worlds remain unchanged. This separation is deliberate: a map must be reviewed and versioned before it becomes the game's authoritative world.

## Generate and inspect

Requires Python 3.11+; uses only the standard library.

```bash
python -m medieval_world_sim.worldgen --seed 42 --width 80 --height 56 --cities 12 --sites 45 --output generated-world
```

Open `generated-world/atlas.svg` in a browser and inspect `generated-world/world.json`. Each tile represents 3 km by default. The JSON contains the generator version and seed, elevation (m), temperature (°C), annual rainfall (mm), biome, geology, soil quality, hydrological flow, resource potential, settlement populations, inferred local production, road geometries and travel times, and candidate wilderness sites.

**Generation pipeline** (in this order):

1. **Geological structure:** a noise-modulated coastline, mountain chain and foothill relief determine elevation and rock type. Each seed changes physical geography.
2. **Climate:** latitude, lapse rate, proximity to the sea, regional moisture variation and orographic rain shadow drive annual temperature and rainfall. Biomes follow these fields.
3. **Hydrology and ecology:** a depression-safe priority-flood drainage network creates directional watersheds and river accumulation. Soil and natural resources derive from rainfall, biomes, elevation and geology. Ore favors igneous/metamorphic highlands; coal favors sheltered sedimentary basins; grain, herbs, timber and grazing differ by local conditions.
4. **Settlement formation:** candidate sites score farmland, freshwater, raw material diversity, approachable slopes and access to yet-unserved territory. Settlements are spread across the reachable mainland. A central economic site becomes Crownreach, rather than assigning a random town the capital role. Other names and livelihoods follow their setting.
5. **Roads and trade:** a minimum spanning network joins all towns; terrain-sensitive land paths avoid ocean and penalize steep slopes, wetlands and river crossings. Secondary links provide alternate routes. Road length and estimated walking time come from each actual path, not predetermined city IDs.
6. **Exploration:** dungeon and point-of-interest candidates follow environmental affordances: limestone caverns, mineral mines, old-growth shrines, wetland crypts, summit ruins, remote river temples, road watchtowers and bandit camps near trade corridors. Clues and danger ratings are derived, not arbitrary room contents.

## Important design boundaries

- **Potential vs. inventory:** resources per tile express geology/ecology, not immediately harvestable stock. Town `production` gives a proposed *hourly flow rate* estimated from nearby potential; the current game economy keeps using its existing balances until migration. Do not convert potential directly to items or gold.
- **Static seed:** deterministic generation is for **world creation**, not re-running on server restart. Future game worlds should persist a reviewed map snapshot, generator version and content hash; events then modify authoritative world state without ever re-rolling geology or sites.
- **Authoritative exploration:** SVG and JSON are designer previews only. Player discoveries, site access, loot, combat, dungeon completion and fog-of-war must be stored and validated server-side. Public assets are not a security boundary.
- **Lakes/islands and transport:** this first pass selects settlement locations on the largest land-connected mainland. Navigable waterways, island cities, ports, ferries, ocean trade and formal bridges need explicit routing and economics before activation.
- **Approximations:** climate is not a numerical weather model; drainage uses grid-scale flow, not real erosion or groundwater. Site names are archetypes, not complete dungeons. No kingdom borders, political history, danger ecology, instanced rooms or generated quest chains yet. The same biome can contain several very different local scenes.

## Suggested next phases

1. **World review and locking:** generate a curated set of seeds, inspect their atlas and travel burden, select one as Oathmere canon (or use separate seeds per realm/server). Add validated world manifest and named geographic regions.
2. **World-engine adapter:** replace `CITIES`/`ROADS` static lookups behind a `WorldGeography` interface, supply the selected versioned manifest at new-world creation, and keep existing five-city saves on their original catalog. Route NPCs, pricing and regeneration through authoritative geography.
3. **Local exploration vertical slice:** one region, one procedurally sited dungeon entrance, a 3–5-node handcrafted room template, risk/reward, persistent discovery and an NPC quest hook. Validate before expanding dungeon counts.
4. **Politics and history:** rivers and passes define trade chokepoints; land suitability and old routes create settlements/ruins across historical eras. Factions and wars should interact with those constraints, not retroactively draw geography around their needs.
5. **Map client:** render generated terrain/roads at the correct coordinates, server-filter points of interest and discoveries, and lift fog by traversed map cells or region-level visibility rather than pre-disclosed hard-coded destinations.

## Tests

```bash
python -m unittest discover -s tests -p 'test_worldgen.py' -v
```

Covers seed reproducibility, terrain and resource invariants, mainland settlements, road connectivity/walkability, dungeon siting, schema serialization and SVG output. A 100-seed smoke test was also run over 64×44 maps without generation failures.
