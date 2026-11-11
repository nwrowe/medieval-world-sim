# Oathmere: geography-first world generation (prototype v8 regional economy)

This system produces a deterministic *candidate atlas* from a numerical seed. It is **not yet wired into live game worlds or saved journals**. The current five-city catalog, travel rules, city inventories, player discovery and existing saved worlds remain unchanged. This separation is deliberate: a map must be reviewed and versioned before it becomes the game's authoritative world.

## Generate and inspect

Requires Python 3.11+; uses only the standard library.

```bash
python -m medieval_world_sim.worldgen --seed 7 --width 80 --height 64 --cities 12 --sites 45 --output generated-world
```

Open `generated-world/atlas.html` for a **clickable, zoomable hex inspector**, or open the static `atlas.svg`; all geographic metadata is also exported in `world.json`. Each tile represents 3 km by default. The JSON contains the generator version and seed, elevation (m), temperature (°C), annual rainfall (mm), biome, geology, soil quality, hydrological flow and downstream drainage references, resource potential, settlement populations, inferred local production, road geometries, dirt/cobbled surfaces and travel times, and candidate wilderness sites.

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
- Rivers follow the **priority-flood drainage graph**, with smooth cubic
  curves sharing the upstream/downstream tangent at each confluence rather than
  independently oscillating segment midpoints. This reduces wave-like humps;
  meanders follow the actual drainage corridor. Visual sinuosity does **not** alter hydrological volume or
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

## v5: inland water, surveyed navigation and strategic landmarks

The CLI exports three review artifacts at once: `atlas.html` (self-contained
interactive survey), `atlas.svg` (static detailed relief), and `world.json`
(versioned structured world). No server or third-party Python libraries are
needed.

- Click any hex in `atlas.html` to inspect its underlying elevation,
  temperature, rainfall, soil, geology, production potential, waterways, roads,
  settlements, dungeon entrances and strategic landmarks. Zoom buttons and
  Ctrl+wheel aid inspection. The overlay does **not** mutate the world and is
  intended for designers, not players with fog of war.
- **Inland lakes** are identified from connected topographic depressions in a
  priority-flood spill-level survey. Tiny artifacts and very large closed
  basins are deliberately excluded until a more accurate basin/evaporation
  model exists. Lakes preserve their measured land elevation while receiving a
  lake biome, waterbody identity and blue hex tile color; shorelines follow the
  hex edges. Roads and towns cannot occupy flooded lake tiles.
- **Navigability candidates** use a connected-hex network: coastal water,
  inland lake tiles and sufficiently broad/gentle river reaches receive a
  potential navigation flag. The `waterways` manifest entry stores connected
  networks and a proposed vessel class. These are survey estimates, *not*
  ship actions, ports with functioning markets, or guaranteed end-to-end
  navigable commercial routes.
- **Strategic landmarks** are placed where built roads actually choose deep
  bridges and shallow fords, where roads negotiate low mountain saddles, or
  where a settlement can access sheltered sea or lake shore. Each has a
  coordinate, type, description and potential strategic importance. They can
  later support forts, tolls, caravan risk, fishing, shipping and quests, but
  they currently confer no gameplay benefits.

**Migration:** v5 adds `waterbody` and `navigable` tile attributes,
`waterways` and `landmarks` world collections and can adjust roads and
settlements to avoid lake tiles. Re-generating an existing v4 world is not a
save migration: preserve the original v4 snapshot until an explicit,
auditable game-world adapter is introduced.

## v6: sea-level coast, smooth river paths, travel difficulty and authored content

- **Elevation semantics:** All ocean hexes display **0 m sea-surface elevation**.
  Bathymetry is retained separately as `seabed_depth_m` (positive meters below
  sea level). Every dry-land hex has `elevation_m >= 1`; the sea/land border
  cannot strand a dry-colored tile at exactly 0 m. Inland lakes remain above
  sea level; their bed elevation is *not* the ocean's sea-surface elevation.
- **Rivers:** The renderer constructs cubic curves from shared drainage-node
  tangents, instead of adding a separate sine-wave midpoint to each hex.
  The water volumes, tributary topology and hex coordinates are unchanged.
- **Land walking difficulty:** Every dry-land hex has a 1–100
  `natural_difficulty` based on biome, elevation and local relief.
  `travel_difficulty` incorporates dirt and cobblestone road discounts, and
  `road_surface` identifies the infrastructure. Oceans and lakes have
  `null` land difficulty and cannot be walked across. The inspector now
  explicitly distinguishes **land travel difficulty** from the separate
  `navigable` watercraft *potential* flag.
- **Walking time:** `access.minutes_per_hex` converts road-adjusted
  difficulty into minutes per approximately 3 km hex step; road times are
  derived from these tile costs, with a small ford delay. This is a survey
  pacing model for future travel integration, **not yet the live player's
  journey clock**. Existing five-city saves and journey times are untouched.
- **Versioning:** This changes biome/coastline interpretation and road travel
  time estimates from v5. The generated map manifest version is **6**;
  previously saved v5 manifests must be kept as-is rather than regenerated.

### Edit city names and dungeon/ruin names and locations

The generated `world-content.template.json` is a *complete seed-specific,
plain-text JSON authoring file*. The keys are immutable IDs (e.g.
`crownreach`, `site-001`, `landmark-001`) and the fields contain the
current names and hex coordinates. The generator never requires you to edit
Python or corrupt generated terrain to revise story content.

1. Generate a seed: `python -m medieval_world_sim.worldgen --seed 7 --output seed7`.
2. Copy `seed7/world-content.template.json` to `seed7/world-content.json`.
3. Edit any `settlements.<id>.name`, `sites.<id>.name`,
   `sites.<id>.x/y`, `landmarks.<id>.name`, or `landmarks.<id>.x/y`.
   The hex coordinates are shown in the clickable atlas inspector.
4. Regenerate using `python -m medieval_world_sim.worldgen --seed 7
   --content seed7/world-content.json --output seed7-edited`.

To add a permanent ruin or dungeon, include an object in `additional_sites`:

```json
{
  "id": "custom-ash-crypt", "name": "Ash Crypt", "kind": "crypt",
  "x": 30, "y": 18, "danger": 5, "clue": "A sealed entrance above the pass"
}
```

That example coordinate is *illustrative*: use a **dry-land** coordinate from
`atlas.html` for the seed you actually selected. The generator validates
boundaries, dry land, stable unique IDs, types, difficulty/danger bounds and
world seed/generator version before applying changes. You can likewise add
`additional_landmarks` with `id`, `name`, `kind`, `x`, `y`,
`importance` (1–10), and `reason`.

To stage a seasonal or event-only location, use `event_locations`:

```json
{
  "id": "event-winter-market", "name": "Winter Market",
  "kind": "festival", "x": 30, "y": 18,
  "description": "A travelling seasonal market",
  "starts_at": "2026-12-01T00:00:00Z",
  "ends_at": "2026-12-08T00:00:00Z"
}
```

Events are visible to the *designer* atlas and persisted in exported JSON,
including their UTC schedule. **They do not yet appear/disappear in the live
multiplayer game**. That requires the future authoritative world adapter,
a restricted admin tool, and server-side event activation and authorization.
The offline JSON file is not a safe replacement for an authenticated game
command. Client-supplied map edits must never be accepted directly by the
multiplayer server.

Generated content is deterministic for a fixed seed, version, configuration
and authoring file. A revised map must be explicitly reviewed and published;
re-running it must never silently alter an existing playable world.

## v7: geography-driven historical chronicle

The atlas generator now exports `history.html` and a readable `chronicle.md`
along with the interactive
geographic `atlas.html`, static SVG and machine-readable world JSON.
The chronicle models six fictional eras (Year -600 to Year 400): founding
on fertile/water-accessible land, population changes under resource and
climate limits, trade via terrain-aware roads, the growth of political
leagues across accessible valleys, frontier disputes, and ruins/abandoned
hamlets with an explicit geographic or commercial explanation.

The historical map lets designers select an era to see *only the settlements
and routes existing by that date*, view settlement and political details and
read the turning points. It uses existing physical terrain without altering
hydrology or displacing authored sites. Custom names flow into history.

Historical records are **inference**, not active gameplay; population and
trade indices are not live player/NPC counts or gold. See
[Historical Development](HISTORICAL_DEVELOPMENT.md) for algorithms, schema,
limitations and planned phases. Generated-world version **7** keeps existing
v6 map snapshots intact; do not silently regenerate old saves.

## v8: town natural resources and industry import dependencies

Generated worlds now carry a `resource_profiles` record for each settlement.
This classifies **all nine existing raw materials** as primary, secondary or
not locally produced. It grounds every classification in the same five-hex
catchment used for the original production estimate, providing supporting hex
counts, mean potential and actual mapped geology/vegetation/soil evidence.

The generator also exports `town-resources.md` (town comparison and explanations)
and `town-resources.json` (typed data for an eventual economy adapter). Click
a town in `atlas.html` to inspect the same information and identify suggested
overland suppliers and raw-input requirements for the game's actual crafting
recipes. Intermediate goods such as steel are expanded into their upstream
iron/coal requirements. **Source potential is not warehouse stock, local
demand or guaranteed exportable surplus.** See
[Regional Resource Economy](REGIONAL_RESOURCES.md) for details.

The standalone geography generator is version **8**; old saved generated v7
manifests should be retained. This is **not yet integrated** with the five-city
playable economy, and it does not change accounts, markets, companies or
player inventories.
