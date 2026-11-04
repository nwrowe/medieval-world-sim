# Oathmere Guilds, Ranked War and Merits — Foundation Architecture

## Intent

Guilds are Oathmere's social and competitive equivalent of factions. Retain organization, coordination, risk and collective identity while avoiding expensive or unbounded wars that reward artificial cooperation more than fair competitive play.

The **first slice is strictly structural**: guild creation, invitations, roles, membership, a war record schema, and a one-time merit achievement ledger. No real player-vs-player ranked war can yet be started. The local browser server still has one human character and explicitly labeled NPC test opponents.

## Guild entity and permissions

- Every guild has a permanent ID, unique display name, one leader, optional officers, members, invitations, a rating and an eventual fortification level.
- Founding costs 100 gold paid to the crown, with a maximum roster size of 25 for this prototype.
- Leader: foundational access to officer appointments. Leader transfer and guild disband authorization are future actions.
- Officer: can invite new characters.
- Member: can depart voluntarily.
- No character may join multiple guilds. The role changes, invitations and membership restrictions are validated in the engine and the same action journal as other web actions.
- A live multiplayer account system is necessary before social recruitment has real human interactions. The UI must never misrepresent NPCs as human players.

## Ranked-war lifecycle (design rules, not active commands)

1. **Enlistment and matchmaking.** Eligible guilds queue. Compare combat-power *distributions*, recent performance (Elo-like), and active roster estimates—not visible rank alone. Matchmaking must remain a trusted service.
2. **Roster lock and notification.** Match announcement 24 hours before combat. Snapshot eligible members and prevent late roster substitution.
3. **24-hour war period.** Each successful *eligible* PvP interaction grants non-negative cumulative War Score to its participating guild. Show both actual scores. Never subtract the opposing score from progress.
4. **Roster-scaled victory target.** First guild reaching its target wins; otherwise higher score when 24 hours expire. Tie-breaking must be explicitly defined later, not inferred. The first prototype value is 500 score units per eligible roster member; balance only after testing.
5. **Surrender.** Guild leader may concede. Surrender should not manufacture participation score or bypass the earned-reward requirements.
6. **War resolution.** Snapshot all contributions and finalize once, with retry safety, then update ratings, victories, and payouts.

**Crucial isolation invariant:** only authorized actions by eligible, roster-locked participants against the opposing roster change *ranked-war* score or the separate ranked-war availability state. A regular open-world PvP hit, an NPC attack, a bounty, self-hospitalization or mercenary attack must never hide a roster member from their ranked opponent. War state is not the ordinary HP/hospital cooldown.

### Strategies, defenses and engagement

Defense should be constructive rather than avoiding play. The planned fortification levels are Barricades, Palisades, Stone Defenses and Fortress Works. These will cost genuine resources and modestly influence eligible combat or objective defense, without generating immunity. Defensive guard assignments, tactical roles, and supply logistics can follow. War participation and engagement should be limited in ways that reward decision-making instead of sleep deprivation.

### Fair rewards

Keep three independent, auditable components: **participation + performance + victory**. Reward meaningful work by the losing side; reward the winner sufficiently more. Avoid a costly net-lead race or an easy loser payout that encourages arranged matches. The present `reward_proposal` is a **pure arithmetic preview**, not a money or cache payout. Before enabling payments, establish anti-farming rules, total budget sources, caps per participant, and exploit tests.

### War record schema

`WarRecord` stores guild IDs, start/end minutes, **roster snapshots**, target, independent scores, per-character contributions, state, and winner. A future authoritative war system must own all record state transitions (notice → live → completed/surrendered). Clients may read results but must never submit score, roster power or payout amounts.

## Merits and achievements

Unlike unlimited XP, merits are finite, one-time rewards associated with stable milestone IDs. They are not awarded for each attack, each race, or repeatable economic loops. Claiming is explicit and idempotent at the command level; duplicate claims fail; spending must never exceed total earned.

Initial achievements (each worth one merit): First Steps, Apprentice (level 2), Roadfarer (one completed trip), Spellbound (one actual spell learned), Challenger (one duel victory), Stablehand (own a horse), Rider (finish a race), Banner Bearer (found a guild).

### First permanent upgrades

| Upgrade | Cost | Benefit |
| --- | ---: | --- |
| Roadcraft | 2 merits | Reduces the duration of future road travel by 5% |
| Horsemanship | 2 merits | +2 to player score in horse races |

These are deliberately modest and once-only to avoid a runaway power gap between new and veteran players. The canonical invariant is **lifetime merits earned − merits spent = available balance**. Keep purchased perks separate from consumables, equipment, guild upgrades and magical practice.

### Later merit directions

- Expand to achievement tiers for travel, crafting, commerce, combat, spell mastery, guild leadership and racing.
- Add costly multi-level improvements with clear ceilings and diminishing returns.
- Preserve respec possibilities, transparent costs and bounded advantage; prevent merit inflation from repeatable or bot-scriptable actions.
- Consider cosmetics, guild banners, titles and character personalization as attractive non-combat rewards.
- Define rules for seasonal accolades separately from permanent lifetime merits.

## Implementation boundaries

All newly enabled guild and merit actions are written through the existing trusted command dispatcher and stored as save-journal **ruleset 6**. Existing rulesets 1–5 and the top-level save version 1 are retained. Unauthorized and invalid actions roll back atomically. This is still an in-memory domain model rebuilt through single-player journal replay; full multiplayer requires durable multi-user transactions, authentication, activity scoring and account migration.
