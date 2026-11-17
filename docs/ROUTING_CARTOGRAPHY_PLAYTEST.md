# Visibility-range travel and cartography progression

This update makes the geographic map a navigation surface rather than a
sequence of single-hex clicks.

## Destinations

Any dry-land hex **within the current Awareness sight radius** can be clicked,
including two hexes away without upgrades, three with Awareness I and four
with Awareness II. The map also keeps **previously discovered settlements,
ruins and landmark markers clickable from anywhere** while they remain on
reachable land. Exploration outside the current radius does **not** reveal
ordinary unexplored coordinates or undiscovered landmarks.

The server selects a minimum-time legal land route using Dijkstra on **directed
hex-edge time costs**, not the fewest hexes or direct-line distance. Crossing
a generated road edge is three times faster than the same bare-ground step
(rounding up to at least one minute); mixed road and off-road routes are
considered together. The journey booking and map quote call the same planner.
The engine also persists each actual weighted step duration so live fog
reveals at the correct time, not at the old bare-ground speed.

The graph has V dry-land hexes and at most 6V directed edges. Its heap
search costs O((V+E)log V), with early termination for nearby goals. Far
multi-destination quotes can reuse a full one-source shortest-path tree;
the LRU holds a maximum of four start-hex trees and is invalidated on
geography replacement. Only the user's discovered destinations are exposed.
Historical journeys use their original algorithm during journal replay.
Every intermediate hex is retained in the saved actor's route and revealed
when crossed. The journey confirmation shows the authoritative total. Water
is impassable without future boat/navigation support. A site on an isolated
island therefore requires a future transport feature; clicking cannot
teleport a character across sea.

Road-destination buttons remain a separate convenience using the existing
regional road network. Clicking a discovered city on the map, by contrast,
creates a land journey from **the current wilderness or town hex**.

The map labels coverage as a percentage of its 5,120 coordinates (including
water). Four claimable, one-time achievements award **one merit each** at
25%, 50%, 75% and 100% explored. As currently designed, mapping distant
ocean tiles fully will require navigation upgrades in a future phase.

## Playtesting

The existing seconds-mode server command is unchanged:

```powershell
python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-quick.sqlite3" --dev-seconds-travel
```

Hex journeys use the sum of their simulated per-tile minutes; with this
developer option each of those minutes advances in **one real second**. The
on-screen confirmation labels the estimate in seconds. Geographic routes
may be much longer than adjacent-hex trips.

## UI and regressions

Life/Stamina/Mana tooltips now read `Life: Full`, `Stamina: Full` and
`Mana: Full`. They keep the same focused/hovered DOM element across
one-second refresh ticks. The World tab's travel polling only redraws its
content panel, avoiding a blinking top bar.

The old offline NPC experiment incorrectly referred to pre-generator cities;
its source locations now come from actual generated resource production.
Historical tests that hard-coded five cities, one-hour arrivals or empty
merchant inventories are being rewritten to use current geography while
retaining replay, asset conservation, web authorization and receipt safety.
