# Oathmere: Geography-driven historical development

This is an **offline, versioned world-design simulation**. It does not change the
playable multiplayer city catalog, jobs, player progress, markets, gold, travel,
factions or saved events. The historical chronicle is a reproducible foundation
for a later, explicitly migrated gameplay world.

## Why historical development comes after geography

History should follow physical constraints rather than allocate cultures,
roads, dungeons, kingdoms and abandoned settlements randomly:

1. Water access, agricultural soils, local climate and extractive resources
   determine which places can sustain early hearths.
2. Population increases toward the carrying capacity of nearby farms and
   resources. Low rainfall, floodplain exposure and market access modify
   resilience. Population figures are design estimates, not a demographic
   reconstruction or live player/NPC counts.
3. Terrain-aware road corridors connect already founded settlements. A
   corridor begins as a trail, develops into a dirt road and may eventually
   receive cobblestone paving as its economic significance increases.
4. Trade is driven by **complementary local production**, the population
   available to trade, and the travel time/cost of actual road routes.
   The `trade_volume` index is not a quantity of goods or currency.
5. Market strength and travel time attract neighboring settlements into
   political leagues. Distant mountain or isolated-valley towns retain
   more independence because control is costly through the real road network.
6. Historical ruins arise at old watchtowers, mines, crypts and mountain
   sites and at a small number of abandoned hamlet locations selected for
   agricultural feasibility and unfavorable later access to regional markets.
   Their abandonment accounts state the terrain, trade, flood or isolation
   constraints that contributed to decline.

The historical simulation uses stable geography and authored settlement/site
IDs. All inferences can be inspected in the structured JSON, so we can
revisit the coefficients before making the history canonical.

## Generate the two designer atlases

```bash
PYTHONPATH=src python -m medieval_world_sim.worldgen --seed 7 --output seed7
```

Open:

- **`seed7/atlas.html`** — inspect one hex's elevation, climate, resources,
  terrain difficulty and current roadway surface.
- **`seed7/history.html`** — step through six eras, comparing founded towns,
  estimated populations, changing land routes, political leagues and
  abandoned sites. Clicking a historic town or ruin shows its history.
- **`seed7/atlas.svg`** — static geographical atlas.
- **`seed7/world.json`** — versioned complete world plus the machine-readable
  `history` object, with years, towns, roads, polities, events and ruins.
- **`seed7/world-content.template.json`** — plain JSON to rename cities and
  author/move sites without editing generator code. Content overrides are
  applied **before** historical development so era names follow your changes.

## Fictional calendar

| Year | Era | Major modeled change |
| ---: | --- | --- |
| -600 | First Hearths | Highest-suitability sites become small settlements |
| -400 | River Settlements | Settlements spread along productive valleys and water |
| -200 | Merchant Trails | More corridors support exchange and early local leagues |
| 0 | Rise of the City Leagues | Trade wealth concentrates influence around market centers |
| 200 | The Contested Marches | Political borders and old trade infrastructure create tensions and abandonment |
| 400 | The Present Survey | Surviving towns, matured roads, political centers and ancient ruins |

Years are Oathmere's **fictional calendar**, not Earth dates. The era labels
give the chronology a readable structure; the actual founding order, trade
volumes, affiliations, crises and ruin locations are driven by the given
world's geography.

## Structured history contracts

Each `history.eras[]` entry has:

- `year` and `name`
- `towns[]`: immutable settlement ID, name, position, founded year,
  approximate population and status, food-resilience and trade indices,
  governing polity
- `roads[]`: endpoints of an actual terrain-derived road, era-appropriate
  surface, estimated travel minutes, exchange index
- `polities[]`: stable polity ID, seat/capital settlement, controlled
  settlement IDs and relative influence
- `events[]`: dated turning point with an explicit explanation and relevant
  settlement/site IDs

The separate `history.ruins[]` records have stable IDs, coordinates, former
use, foundation and abandonment years, a terrain/commerce-based cause, and
where appropriate a link to an existing authored exploration site.

All historical structures use immutable dataclasses. Serialization through
`GeneratedWorld.to_dict()` is reproducible for a given seed, parameters,
authored-content file and generator version.

## Historical limitations and planned next steps

This first pass is a **region-level history**, not a full demographic, military
or agent-based civilization simulation.

- Road alignments are drawn from the geography-derived **present-day candidate
  network**. Earlier eras back-cast trails along plausible corridors; we have
  *not* simulated every century's competing bridge, pass and road investments.
- Trade uses a proxy index based on accessibility and complementary resources.
  There are no historical commodity inventories, caravan NPCs, taxes, gold
  flows or international markets yet.
- Polities represent settlement allegiance and influence, not precise
  sovereign land borders; later maps can derive territorial hex claims using
  settlement reach, military logistics and topographic barriers.
- Drought and flooding are climate-risk estimates, not weather datasets or
  real-time game events. The chronicle does not grant in-game rewards.
- Ruins and abandoned hamlets have provenance and locations, but no completed
  generated building interiors, loot tables, quests or NPC archaeological
  discovery system.
- Future historical phases can add migration, language and culture,
  dynasties, warfare and road investment, agriculture and extraction depletion,
  religious sites, generational change, trade by boat, and historical naming.
- Historical production output and politics should become authoritative only
  via a separate **game-world adapter with migration/replay rules**. An atlas
  containing all historical sites cannot be sent to ordinary players when
  discovery and fog-of-war are meant to be server-controlled.

## Validation

```bash
PYTHONPATH=src python -m unittest discover -s tests -p test_worldgen.py -v
```

Regression checks cover deterministic eras and events, founding chronology,
trade-route appearance after towns exist, political membership conservation,
historical ruin provenance, authored-name propagation and validity of the
standalone interactive historical HTML.
