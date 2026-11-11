# Oathmere: geography-first world generation (prototype v4 terrain-aware roads)

This system produces a deterministic *candidate atlas* from a numerical seed. It is **not yet wired into live game worlds or saved journals**. The current five-city catalog, travel rules, city inventories, player discovery and existing saved worlds remain unchanged. This separation is deliberate: a map must be reviewed and versioned before it becomes the game's authoritative world.

## Generate and inspect

Requires Python 3.11+; uses only the standard library.

```bash
python -m medieval_world_sim.worldgen --seed 7 --width 80 --height 64 --cities 12 --sites 45 --output generated-world
```

Open the improved `generated-world/atlas.svg` in a browser and inspect `generated-world/world.json`. Each tile represents 3 km by default. The JSON contains the generator version and seed, elevation (m), temperature (°C), annual rainfall (mm), biome, geology, soil quality, hydrological flow and downstream drainage references, resource potential, settlement populations, inferred local production, road geometries, dirt/cobbled surfaces and travel times, and candidate wilderness sites.

### Reading the hex atlas

The v3 atlas uses **pointy-top hexagonal cells** with odd-row offsets and
**six-way adjacency** shared by river drainage and land-road pathfinding.
A nominal 3 km step and an 80×64 hex survey cover approximately 240×168 km.
Geographic coordinates remain integer (x, y) cell IDs; map pixel positions
are a rendering projection, not game-state authority.

- Pale dashed edges show individual hexes. Coastlines and their dark green
  fringe follow **actual edges between land and sea cells**, never smoothed
  zero-elevation contours that cut diagonally across cells.
- Shaded relief comes from elevation; 300 m contour isolines, slope hachures
  and snow-tipped summit symbols distinguish highland geology.
- Coastlines combine multiple noise frequencies to form bays, inlets and
  headlands. The principal mountain axis now wanders, breaks into varying
  ridge heights and widths, and has secondary spurs and passes.
- Rivers follow the **priority-flood drainage graph**, but visible lowland
  reaches use smooth, deterministic bends, including a consistent shared
  confluence point for each tile. High-gradient streams stay comparatively
  straight. Visual sinuosity does **not** alter hydrological volume or
  river-related gameplay rules.
- Cobblestone capital approaches, dirt secondary roads, fords, and constructed
  bridges use the same hex-coordinate projection as rivers and settlements.
  Roads connect only along shared hex edges. Mountain routing penalizes steep
  grades, excessive climbing, and high-altitude construction so a nearby lower
  saddle is favored over a direct summit crossing. River entry carries an
  infrastructure cost scaled by flow: the builder prefers a short detour or
  shallow ford but accepts a bridge when the alternative is too circuitous.
  The routing cost is *not* travel time: the cost of constructing an existing
  bridge does not make its eventual journey artificially slow.
- The JSON manifest records `crossings`, `bridges`, and `fords` separately
  for each road. In the atlas, shallow fords use a small marker and actual
  constructed bridges display their deck.

This is not a tectonic/geological timescale simulator. The coast/ridge
variability is procedural and physically motivated, not plate-dynamics-derived.
Likewise, river bends are visualized within their drain corridors; a later
geomorphology pass can integrate erosion, braided streams, lakes and deltas.

**Migration note:** v4 changes road geometry, crossing classification and
travel times for a given seed. Generated v3 manifests must not be reinterpreted
as v4 or used to overwrite existing saves. The 80×64 hex topology remains
unchanged, as do the terrain and settlement locations for a given seed.
The existing five-city gameplay runtime remains separate.

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
## v4 road-planning regression tests

The standalone worldgen tests include synthetic hex maps with one low mountain
saddle, an isolated river obstacle with a short dry detour, an upstream ford
versus a downstream deep crossing, and an unavoidable bridge. All use the same
A* and cost rules as the atlas. The test suite also checks that cost of bridge
construction does not inflate minutes traveled on an already built road.
