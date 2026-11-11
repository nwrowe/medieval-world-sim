# Exploring hexes and fast-travel playtesting

This phase prioritizes **walking the real map** before adding NPC desires and
industrial production (Phase 3). The public resource geography remains fixed.

## Play-test command (Windows PowerShell)

Pull the PR branch when reviewing it, or use `main` after it is merged.
The accelerated mode intentionally needs a **separate database**, so it never
reinterprets the timestamps of journeys recorded in normal mode.

```powershell
python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-quick.sqlite3" --dev-seconds-travel
```

To generate a code, stop the server and run:

```powershell
python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-quick.sqlite3" --dev-seconds-travel --issue-invites 1
```

Then restart with the first command. Existing accounts in a **different**
database are not automatically imported.

**Development-only speed:** this mode treats one simulation minute as one
real second and compresses road travel duration approximately sixtyfold.
Thus, a normal 180-minute journey is about three **real seconds**, while a
long 1800-minute journey takes approximately thirty. This **also accelerates
the simulation's economic and regeneration clock** (and NPC time); use it
only for local testing, not public gameplay. The engine's authentic road
difficulty and saved map remain unchanged. Seconds-mode and normal-mode
journals cannot be mixed.

## Walking, revealing and returning

- On the **World** map, immediately neighboring dry-land hexes are outlined.
  Click one to take **one step** into the wilderness. Your character moves
  there and permanently surveys the terrain within your Awareness radius.
- You can click further adjacent land hexes, including previously unexplored
  ones. Coast/ocean/lake cells are impassable on foot.
- To reenter a settlement, walk back into its hex. While outside, the map
  shows a **Wilderness** notice and city commerce, manufacturing and
  other town-only interactions are blocked.
- City-to-city road journeys remain available **from settlements**, and
  progressively uncover the road hexes the character crosses.
- The browser never determines whether a walk is valid or whether secret
  landmarks, cities or resource data should be visible. The server validates
  one-hex adjacency and filters its own fog-of-war map response.
- Exploration progress is stored with the actor and survives restarts via
  the existing journal/checkpoint mechanism. Awareness I/II still expand
  the radius from two to three/four hexes.

## Limitations

Walking is currently **one neighboring hex per click**, with no stamina or
time charge; the HTTP action rate-limit and authenticated replay receipt
still apply. This keeps initial movement testing responsive. Later we can
add terrain-cost/stamina/time scaling, boat travel, dangerous hexes, resource
collection at a deposit, dungeon interactions and movement controls, after
the basic map behavior has been play-tested.

The step view is deliberately **not** a full pathfinding UI. A distant click
cannot teleport a player across mountains or reveal a ruin they have not
visited.
