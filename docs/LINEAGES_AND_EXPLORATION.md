# Lineages, Atmosphere, and the Explored Atlas

## Product intent

Oathmere begins in Crownreach with the rest of the realm unexplored. The
player chooses a **lineage** at character creation. Lineage describes ancestry,
not career: an elf may study smithing and an orc may study restoration.
Professions and party roles remain future orthogonal systems.

Atmosphere is currently deliberately lightweight: local descriptions, better
presentation, an illustrated atlas, and visible personal exploration progress.
These are not quests and do not imply an autonomous live-world event system.

## Playable lineages

| Lineage | Starting work aptitude | Physical combat | Unique level-3 trait |
| --- | --- | --- | --- |
| Human | +1 Manual, +1 Intelligence, +1 Endurance | baseline | Versatility: +1 XP for civic noncombat assignments |
| Elf | +2 Intelligence | +1 Defense | Arcane Insight: +1 XP per spell practice (subject to training ceiling) |
| Dwarf | +2 Manual | +1 Defense | Stoneguard: +1 further physical Defense |
| Orc | +2 Endurance | +1 Attack | Battle Fury: +1 further physical Attack |

Combat bonuses operate inside the authoritative strike formula. All lineages
may use all equipment, learn all schools, and hold any occupation. These are
modest initial balancing numbers, not permanent competitive guarantees.

The server's immutable lineage catalog supplies new-character UI choices.
Lineage can be chosen **once** only. Existing characters created before this
feature begin with no selected lineage; a one-time choice is offered after
login, leaving their original actions and balances unchanged until that choice.
Existing save/journal replay stays deterministic because pre-feature actors
retain their baseline combat behavior.

## Fog of war / exploration

- Crownreach is the starting known city for new characters.
- Each actor owns an individual `discovered_cities` set, independent of UI.
- Reaching an uncharted city's arrival event adds that city to the set.
  Starting a journey alone does not reveal the city.
- The state projection displays undiscovered cities as "Uncharted settlement",
  while retaining real destination IDs for validated travel actions.
- The browser overlays dark fog over the existing illustrated map and cuts
  illuminated circles around discovered cities. Unknown destinations remain
  usable as exploration leads; this is not pathfinding or procedural discovery.
- Discovered places survive single-player replay, multiplayer journal replay,
  and new checkpoints. Old checkpoints gain the player's current location;
  prior historical visits before those checkpoints cannot be reconstructed.
- This intentionally allows travel to unknown road endpoints. Future ruins,
  regions, and dungeons can use a more general discovery registry and explicit
  prerequisites rather than reusing every city rule.

## Security, balancing and future work

Only the server validates chosen lineages and commits exploration. One actor
cannot change another actor's attributes by changing UI payload fields.
The unexplored map is a gameplay presentation feature, **not a secrecy
boundary**: static artwork and city IDs may still be inspected in browser assets.

Balance physical modifiers with NPC and PvP testing; work modifiers currently
affect starting attributes and two earned XP traits, not every possible
future production formula. Avoid runaway combat advantage from stacked traits.

Next coherent vertical slice: discover an exterior point of interest from a
city, assemble an NPC/human party, resolve a short encounter, and record a
persistent discovery. Do not add dozens of regions or lengthy quest writing yet.
