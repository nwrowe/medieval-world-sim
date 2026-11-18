# Oathmere gameplay readiness audit — 18 November 2026

This audit evaluates **what an authenticated player can do from the current
browser**, not merely which Python systems or catalog items exist. It follows
[Gameplay Development](GAMEPLAY_DEVELOPMENT.md). The source reviewed is main
at `c1c2899`, with the current-only replay cleanup tracked separately in
[PR #107](https://github.com/nwrowe/medieval-world-sim/pull/107).
That PR removes two historical browser commands without enabling any feature.
Do not infer browser readiness from deterministic unit tests alone.

## Readiness terminology

- **Browser loop present:** There is a player-facing view, a handled browser
  action, a registry-exposed command, and authoritative game logic. **Not**
  proof of interactive browser playtest or restart safety for every edge case.
- **Partially playable:** Some useful interactions are available, but a
  strategically important loop has not been completed.
- **Engine only:** Implemented internally but not accessible via an authorized
  player action and browser interface.
- **Not implemented:** Only an illustration, placeholder, content outline,
  or proposed system exists.

No feature is certified *playtest-ready* by this source-only audit; that label
requires hands-on browser testing, successful refresh/restart and error paths.

## System inventory

| System | Source-based state | Evidence and remaining gap |
| --- | --- | --- |
| Character creation and progression | Browser loop present | Lineage, level/XP, recovery and merits are server-authoritative; verify a full new-character session |
| Turn-based combat | Browser loop present | `engage_duel`, `duel_turn`, `flee_duel`, equipment and magic in `community-views.mjs`/`app.js`; playtest collisions, hospital/retreat and low-stamina recovery |
| Magic training and use | Browser loop present | Six schools, practice, unlock, attunement, field casting and combat casting; validate tier mastery, mana, UI feedback and all noncombat uses |
| City gathering | Partially playable | `gather` obtains town deposits through the browser; no equivalent wilderness-hex gather/harvest loop |
| Merchant trading | Browser loop present | Local `regional_buy`/`regional_sell` with real stock/treasury; verify empty stock, capped quantities and regional price differences |
| Player market listings | Engine only | `post_offer`, `post_equipment_offer`, `accept_offer`, `cancel_offer` exist in `systems/market.py` but have no browser exposure or complete UI |
| Secure direct trades | Browser loop present (multiplayer only) | `propose_trade`/`accept_trade`/`close_trade`, terms hash and escrow; confirm acceptance, cancellation and reconnect together |
| City contracts | Browser loop present | `complete_city_contract` performs small repeatable civic assignments; it is not a persistent employer/employee relationship or a narrative quest |
| Ongoing employment | Engine only | `propose_job`, `accept_job`, `leave_job`, `shift`, `set_wage`, `set_perks`; the current Job page mainly displays work attributes |
| Player-owned companies/production | Engine only | `found_company` and `upgrade_facility` plus simulated company economy; no complete player ownership, production, employees or quality workflow |
| Equipment and storage | Browser loop present | Buy/equip/unequip gear and store/retrieve local items; crafting and listing quality gear depend on unfinished production/market paths |
| Atlas exploration and travel | Partially playable | City routes, terrain hex navigation, fog of war, discovery and transport operate; unexplored sites lack persistent meaningful interactions and resource loops |
| Housing and transport | Browser loop present | Buy/upgrade home, facilities, vehicles and travel bonuses; verify restart, relocation and interaction at other towns |
| University | Browser loop present | School and course enrollment, tuition, progression, graduation/merits; the old historical enrollment method is being retired |
| Guilds and merits | Partially playable | Guild foundation, roles/invites, membership and merit claims/upgrades have browser actions; guild-war/faction purpose and rewards need a separate player-loop review |
| Racing, church and consumables | Browser loop present | Repeatable racehorse/racing, paid healing and item use; verify cooldowns and on-screen explanations |
| Story quests and onboarding | Not implemented | The City Hall currently displays `Quests are coming soon`; no durable objective, reward or settlement-to-city progression system |

## Highest-value priorities

### 1. Finish the civilian economy as one vertical slice

Connect **companies → employment → production → merchant/player sales** without
bypassing the domain command boundary. Avoid enabling every internal method
in one sweep. Start with a minimal owner/company creation, one paid job,
and one produced item, then connect listings and sale settlement.

Acceptance:
1. Owner can fund/form a legitimate company; worker can accept a displayed
   offer and complete a shift, with wage transfer and cooldown.
2. Items/quality are created through validated recipes and local materials,
   not minted from browser requests.
3. Produced goods can be sold through a local venue; owner, employee, seller
   and buyer balances remain conserved across request retries and restart.
4. Separate authorized projections prevent private terms, items or account
   data from leaking. Test cheating, duplicate requests and simultaneous
   trading before enabling multiplayer writes.

### 2. Give wilderness exploration a purpose

Add a small number of meaningful site interactions (harvest, find, scout,
rest, or encounter) using seeded terrain/content and authoritative commands.
Tie their outcomes into existing inventory, magic, combat and local markets.
Current fog/road behavior can stay intact. Start with one reproducible
interaction and later extend to geography-defined location capabilities.

### 3. Add a durable objective system, then build the tutorial

Once the above systems are playable, add a reusable objective ledger for
both one-off quests and guided introductions. First playable introduction:

`small settlement → receive a task → gather/perform a local action →
meet an NPC → travel a discovered road/hex route → enter nearby city →
trade, equip or study → complete introduction`.

The settlement should have explicit service capabilities; do not give
every village every capital service and do not create a separate tutorial
economy. Progress and rewards must be server-side, idempotent and restart-safe.

## Test strategy for each vertical slice

- Engine, command registry and permission tests: valid, unauthorized, malformed,
  insufficient resources and duplicated commands.
- SQLite receipts/ledger and checkpoint restart; current-only replay means
  **no migration of old development files**, not loss of current-session
  durability.
- Multi-user concurrent access, private visibility, and NPC/player rule parity.
- Real browser E2E smoke for the critical action path, refresh, error/retry,
  and live updates. Existing JavaScript view smoke tests are not equivalent.
- Measure the transactional cost of new company/market actions before scaling
  the number of accounts; don't rewrite the storage engine speculatively.

## Immediate recommendation

Do **not** do another general-purpose refactor. Complete the baseline replay
cleanup and its tests, then implement the smallest company/employment/production
loop as one feature PR. Add wilderness interactions next. Once those systems
have real browser playtests, design the settlement objective chain on top of
the existing actor/world state and location capabilities.
