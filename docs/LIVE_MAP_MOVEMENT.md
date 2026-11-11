# Live map movement and zoom play-test

The World page now renders **private, server-authorized, live exploration**.

## Town-to-town travel

Choose a destination from the existing Roads panel. After confirmation,
the World page periodically requests your current private map projection
while the journey is active. The character marker advances along the
generated road and terrain is uncovered along each traversed segment.
Other accounts do not receive your unexplored sites or resources.

This updates while the page is open; there is no longer a need to refresh
the browser to see the revealed road. With `--dev-seconds-travel` the
display updates approximately every real second, and with normal world
timing every few seconds. Travel remains authoritative and keeps working
if the browser disconnects.

## Exploring adjacent hexes

On the map, permitted adjacent **land** hexes have bright outlines.
Click one to open a confirmation popup describing its hex coordinates
and estimated terrain-dependent travel time. **Cancel** returns to the
map, while **Begin journey** starts a timed movement.

A hike costs 3–12 simulated minutes based on the actual destination
hex's travel difficulty. In explicit seconds-testing mode, this means
3–12 real seconds. Reaching the destination reveals permanent fog as
before; stepping into a town hex restores access to city services.

Server rules reject teleportation, water crossing, moves during active
road journeys, moves during duels, and unauthorized replay requests.
Travel is journaled and can resume across a server restart. Older
checkpoints lacking the new optional hex destination load with its
default, without a destructive database migration.

## Zoom

The interactive atlas has **+**, **−**, and **Center** buttons.
Initial zoom is 250%, with 100–400% supported in 50% steps. The player's
marker is automatically centered on initial display, zoom changes, and
as its hex changes. Panning the map is still possible in both directions
with the scroll viewport.

## Development command (PowerShell)

Continue using your existing matching seconds-mode database:

```powershell
python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-quick.sqlite3" --dev-seconds-travel
```

No new invitation is needed for an existing account. After pulling the
updated branch or merged main, restart the local server and hard-refresh
the browser to avoid stale browser assets.

## Validation

The movement tests check authoritative time quotes, mid-trip road fog
progress, queued hex movement, final arrival, checkpoint encoding and
impossible/unauthorized steps. The existing broad test suite still has
legacy five-city assumptions that are not silently exempted.
