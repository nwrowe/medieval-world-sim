# Wilderness Phase 1 (current baseline)

The hex map is the authoritative geography. Wilderness actions **do not**
generate a second resource map. The existing world generator infers biomes,
geology, rivers, elevation and resource **potential** (0–100) from physical
terrain evolution; each tile's potential determines which natural goods may be
collected there.

## Exploration loop

1. From **Map**, travel to a reachable dry-land hex (ordinary map journeys
   already use terrain costs and reveal fog).
2. At a wilderness hex, the **Wilderness** panel shows its physical terrain,
   locally available resources and stamina-based gathering buttons.
3. `wilderness_gather` costs **5 stamina for one unit**. Raw
   goods available on a hex are capped at 1–5 units based on its potential and
   replenish by 1–2 units per simulated day. Exhaustion is shared among players
   and is restored only by elapsed world time.
4. Generated site types (abandoned mines, shrines, watchtowers, caverns,
   crypts, bandit encampments, observatories, temples) appear at their already
   terrain-grounded hex locations. Standing on one presents **Survey** (2
   stamina), **Search for supplies** (4), **Explore the depths** (7), or
   **Go around** (0 stamina).
5. Site outcomes are rolled once per character and are **never rerolled** by
   pressing again, refreshing the browser, or changing the action. Success
   chances depend on site danger, a relevant work stat, and character level;
   bigger risks offer bigger material finds. Failed deep exploration may cause
   a small nonlethal injury. Material rewards are constrained to resources
   naturally present on that tile. Character-specific resolutions persist.

## Travel policy

- **Normal city-to-city journeys ignore optional sites automatically.** They
  continue to destination without pausing for investigation; the Map displays
  this during road-booking confirmation.
- **Manual hex journeys** arrive at the target; players may opt into a site
  investigation or pass by freely. Visiting an unrewarded site does not consume
  its once-only attempt until the player explicitly chooses a paid option.
- Unavoidable ambushes and world events are deliberately **not** part of Phase
  1. Do not impose forced interruptions until route safety, escape, and
  permissions are designed and tested separately.

## Security and persistence

- Only an authenticated character currently standing at the specific dry
  wilderness hex may gather/investigate.
- The server checks stamina, biome resource potential, shared stock, location,
  site IDs, and character's one-time choice before modifying state.
- Site rolls are a secret-keyed, deterministic SHA-256 HMAC in multiplayer and
  seed-derived in single-player. This preserves restart/replay integrity without
  allowing client-authored roll values.
- Stock and site resolutions are stored in authoritative WorldState and
  included in verified checkpoints and replay. Older current-version
  checkpoints can fill the *two empty additive fields* from defaults; no old
  game-rule switch or historical replay branch is restored.
- No new currencies, terrain geometry, worlds, or forced PvE systems.
