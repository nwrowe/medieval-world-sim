# Stamina, life and level progression (prototype)

All values are provisional; this is a simulation prototype rather than balanced live-game PvP.

- **Life (HP):** Characters start with 24/24 life. Equipped armor and shields reduce incoming damage. Defeated characters reach 0 HP and recover after 60 simulated minutes, at their current maximum HP.
- **Stamina:** Characters start with 100/100 stamina. Every initiated attack costs 20 stamina instead of imposing a 5-minute attack timer. Each completed five-minute world-clock interval regenerates 1 stamina, capped at 100. An unarmed defender's counterstrike does not consume stamina, because the defender did not initiate an attack.
- **Fists:** Everyone can initiate attacks or defend unarmed with a weak base attack. Weapons increase damage but are no longer a strict combat requirement.
- **Open PvP:** Any player or NPC may attack anyone else in the same city, without mutual consent. Defeated opponents cannot be attacked again until recovery. No attack may occur while traveling. This is an intentional *open-world combat* rule; anti-harassment, newbie protection, and safe-zone rules remain future design decisions.
- **Experience:** An attack awards `1 + floor(damage/4)` XP. Defeating an opponent awards an additional 5 XP. XP accumulates in both total combat XP and XP toward the next character level. XP required for level N→N+1 is `10*N*N`.
- **Leveling:** Every new level gives +1 strength, +1 defense, and +4 maximum life. Current life receives +4 unless the player is already defeated; leveling does not resurrect defeated players. Starting level is 1; starting strength and defense are 1 each.
- **Gold:** On defeat, the winner still receives at most 10 gold actually transferred from the defeated character's gold. Gold is conserved in the model.
- **Gear demand:** Equipped weapons, armor, and shields still suffer durability loss in combat. Unarmed fighters do not consume gear.
- **Rules authority:** Player and NPC actors share the same validation and stat growth; no special combat stats or privileged NPC rewards.

## Open questions before a public game

1. Distinguish *character experience* from skill training, and limit XP farming via repeatedly defeating alternate accounts or NPCs.
2. Whether NPCs should initiate attacks, and how a player can escape or avoid unwanted combat.
3. Safe areas, guard response, outlaw reputation, consequences for attacking low-level or defenseless characters, and the impact of defeat on trade activity.
4. Passive life regeneration, healing consumables and hospitals/infirmaries.
5. Whether stamina is shared by gathering, working and travel or reserved for combat.
6. Combat balancing against weapon quality, armor, player level disparity, and NPC respawns.

## Try it

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m medieval_world_sim.combat_demo
```
