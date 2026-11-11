# Playable Realm — Generated Geography and Persistent Exploration

Phase 1 connects the geography-first atlas to the live, authoritative Oathmere
game. Phase 2 adds private persistent hex discovery and two Awareness merits.
These changes intentionally **retire the old five-city world**.

## Starting a new realm

Use a **new SQLite database** for multiplayer and a **new save file** for
single player. Neither old accounts nor existing character progress are
migrated. Don't delete old files without separately backing them up.

The generated map uses the Seed 7 survey by default for local development.
For a realm others will play, select a **private** signed 32-bit seed:

```sh
export OATHMERE_WORLD_SEED=781239    # Linux/macOS (example; choose privately)
# Windows PowerShell:
# $env:OATHMERE_WORLD_SEED = "781239"
```

Start the existing Oathmere web server against a **fresh** database/save
path. The resolved geographic fingerprint is stored in the save or SQLite
world metadata; running that database with a different generator version,
seed or physical map is rejected. Never expose a complete `world.json`
or the private seed to normal players: the designer exports include ruins
and resources that fog must conceal.

## Phase 1: authoritative geography

- The game city catalog is now assembled from the generated `GEOGRAPHY`
  settlements. Each settlement retains the stable generated ID, its own
  name, its natural resource extraction capacity, and the proposed population.
- City-to-city travel is routed via the generated road network, including
  mountain passes, fords, and built bridges. Road time comes from actual
  surveyed hex difficulty, with existing horse, carriage, roadcraft and magic
  modifiers applied only when booking the trip.
- Canonical crafting recipes and raw/processed goods are defined once in
  `content/industry.py`. Both the live game and geographic resource profile
  import that module; it does not invoke the world generator.
- Town-specific demand, companies, merchants, storage and inventory keep
  using the existing authoritative game transactions. This phase changes
  **where** resources can be extracted, not yet how businesses compete for
  them or how dynamic scarcity prices change.
- Existing capital-only company founding and other rules remain unless a
  specific later gameplay feature changes them.

## Phase 2: map discovery

A character's `explored_hexes` is a durable set of exact geographical
tile indices, updated by server actions—not by the browser.

| State | Visual | Data exposed |
| --- | --- | --- |
| Currently visible | Full color | Terrain, roads, discovered sites/settlements |
| Explored earlier | Muted color | Recorded geography and sites; not live remote NPC movements |
| Never explored | Gray relief | Low-resolution water/lowlands/hills/mountains topology only |

The initial view covers **two hex steps** from the character's city. The
Awareness merit upgrades increase the radius to three and four hexes:

- `awareness_1` (2 merit points) — radius 3.
- `awareness_2` (3 more merit points, Awareness I prerequisite) — radius 4.

Purchasing a tier reveals newly visible tiles immediately. Traveling follows
the generated road's **actual hex sequence**; discovery progresses with travel
time and persists after arrival and across save/replay, including when a
large time jump crosses many road tiles. An inactive journey cannot retain
an in-progress route.

The player snapshot contains a **server-filtered** `world_map` object.
The coarse public relief is intentionally missing resource deposits,
precise elevation, roads and locations. Known tile details are sent only for
previously explored indices. No full world-generation JSON is sent in
normal player snapshots.

## Scope and limitations

The first playable world uses existing **city-to-city journeys** and reveals
the land the character crosses. It does not yet implement arbitrary
wilderness hex movement, off-road pathfinding, cartography trading,
resource depletion, historical political borders, or new dynamic prices.

The 80×64 map uses SVG hex graphics in the existing client with a scrollable
viewport and a visible current-position marker. Topology is visible in
grayscale outside explored regions; towns, dungeons and resource positions
are only drawn when discovered.

Security rules are server-side. The frontend is **only a renderer**, not an
authority for visibility, player position, merit points or route time.

## Test expectations

Run the new-world regression suite:

```sh
PYTHONPATH=src python -m unittest discover -s tests -p 'test_playable_atlas.py' -v
```

Test coverage includes generated-city parity, true initial visibility
radius, non-leaking unexplored map projection, merit prerequisites/radius,
progressive road exploration, and checkpoint encoding.

Tests that assert old city names, five-city counts, or fixed ninety-minute
routes need to use the new geography-aware fixtures and dynamic travel times;
they must not drive legacy aliases back into the live runtime.
