# Banner Clash — first integrated playtest

Banner Clash is a **server-authoritative guild war** in the normal Guilds page, not
a separate simulator or an administrative console.

## Playing

1. Found a guild in Crownreach using the Guilds page.
2. **Solo practice:** As guild leader, click **Start solo practice vs Ashen Company**.
   Ten clearly labeled training NPC opponents appear at the Crownreach warfront.
   Practice requires only one player and does not change guild rating, pay gold,
   or claim ranked spoils. Enter the battlefield and click **Attack** on an opponent.
   Fights use the existing ten-round maximum, physical moves, stamina, spells,
   and automatic retaliation. Other guild members can assist an active offensive
   duel for three stamina, up to two assistants.
3. **Real weekly warfare:** Recruit 10–20 members, then a member with the
   *enlist* permission selects **Sign up for weekly war**. At each 10,080-minute
   realm-week boundary, enrolled guilds are paired by neighboring rating;
   unmatched guilds remain enrolled. Matches have a 24-hour preparation window
   and a 12-hour maximum battle after that. The battlefield is in Crownreach.
4. Only a guild leader, or a specific member delegated the *milestones* right,
   can activate one-use milestone powers. Only leaders can grant or revoke
   individual rights. There is no elevated developer UI exposed to players.

## Rules

- **10 qualifying hits** gain advantage. **7 opposing hits** break it.
- A team with advantage makes **one minute of permanent control progress per
  minute** while it has a ready fighter at the warfront; 60 cumulative minutes
  reaches 100% and wins. At timeout the greater progress wins; equal progress
  is a draw.
- Defeated fighters are **Routed for 10–15 minutes**, rather than losing gold
  or being ordinarily hospitalized. A fighter can use up to two dressings
  (eight minutes reduction, 30-minute item cooldown). Restoration magic
  costs five mana, reduces an ally's routing by five minutes, and has a
  15-minute caster cooldown.
- **25% Field Hospital:** Reduce routing for *all* routed teammates by five
  minutes. **50% War Horn:** +50% scoring speed for up to ten minutes while
  advantage is held. **75% Final Rally:** Return *all* routed teammates.
  Powers unlock once for each side and cannot be reused.
- A contested battlefield retreat concedes one opposing team hit but
  generates no fictional personal Honor. An empty defending warfront
  forfeits its advantage, without erasing earned progress.
- Winning an authorized duel awards **Honor**, scaled from opponent strength,
  defense, and level. Assisting guildmates receive a smaller Honor share.
  Honor remains visible at war end as a contribution ledger.
  **No automatic gold or prize distribution has been added.**

## Playtesting without other players

Use **solo practice** on a fresh single-player save, or the local multiplayer
development server. NPC practice actions occur when game time advances;
in single-player, existing time-advance actions can make turns progress
faster. The local multiplayer `--dev-fast-forward` flag also allows accelerated
clock experiments, but must **never** be enabled on a public server.

Practice battles are deliberately shorter (180 realm minutes) and use
ten NPC sparring opponents; they are not a statistically faithful model of
the real 10–20 person wars. They exercise the production combat,
authorization, routing, Honor and milestone rules.

## Limitations

This remains a local-development prototype, not an internet-ready multiplayer
service. War matching uses the **world clock's week boundary**, not a specific
wall-calendar weekday. The initial warfront uses Crownreach as its location;
additional map hex objectives and caravans are future work. Reward pools and
leader-controlled spoil distribution are intentionally deferred; the Honor
ledger is implemented first to support that design.

The new war schema assumes a fresh development save/database. No migration of
the unused previous ranked-war framework has been added.
