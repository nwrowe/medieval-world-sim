# Local multi-account development mode

Oathmere now has an **opt-in localhost-only, shared-world development mode** for building and testing authenticated player accounts without buying or operating a physical server. It is **not a publicly deployable multiplayer release**.

## Start it

From the project directory (after installing the package in editable mode):

```powershell
python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-dev.sqlite3"
```

Before registering new characters, stop the server and issue one-time invites using `python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-dev.sqlite3" --issue-invites 2`, then start the server again. Open the printed `http://127.0.0.1:8765` address. Enter a unique invitation code, a **username**, a separate **character display name**, and a password of at least 12 characters. To test a second player, use a separate browser profile or a private/incognito window, create a second account, and log in independently. The two characters live in the **same simulated world**; actions and assets are persisted in a SQLite database. You can test direct chat, guild/company channel permissions and bilateral trades through the authenticated API.

### Live, persistent NPCs

With `--multiplayer-db`, the 15 named world NPCs now act autonomously
alongside authenticated human characters. Each has a stable home, seeded
personality and a small role (gatherer, hauler or adventurer). NPCs gather
and trade resources, buy and equip gear, and fight **other simulated NPCs**;
the automated policy cannot attack human accounts. NPC commands are
never accepted from a browser or assigned a login identity.

The server owns a bounded clock worker (normally ticks from real wall time)
and makes **at most three NPC decisions per committed advance**, with each
individual NPC scheduled no more than once per 180 simulated minutes.
This prevents a large offline catch-up from generating unbounded work, but
also means the world only advances while the local server process is
running. Time accrued while closed is reconciled in capped advances on
restart or the next state request. In explicit `--dev-fast-forward` mode
NPCs instead participate in each manual advance, with no background
fast-forward thread.

NPC actions are saved in the same SQLite transaction as the advance,
world asset ledger, checkpoints and bounded per-NPC decision memory. A
restart replays recorded NPC commands rather than rerunning the AI
policy, so changing a policy doesn't rewrite past transactions. Use
`--no-npcs` if you want to pause new autonomous activity while retaining
all existing NPC assets and historical actions. This is not an
internet-ready MMO scheduler: production scaling, abuse prevention and
cross-process leases remain future work.

**Character progression:** combat continues granting skill and character
level XP as before. Practicing magic now grants character level XP in
addition to school XP (roughly half the actual school XP awarded, minimum
one point when training produces XP). It never adds combat XP and is
not awarded by merely casting a spell. Historical saved magic commands
replay with their original, pre-change level rules. Gold is **not banked**
or protected by this release; city gold deposits can be added separately.

The ordinary command with no `--multiplayer-db` remains the original single-player game with its original JSON save. **Existing saves are not changed or automatically imported.** You can switch back by restarting the server without the flag.

`--multiplayer-db` is deliberately forbidden when the HTTP host is `0.0.0.0` or other nonloopback addresses. It also cannot be combined with the old shared `--access-token` or the Colab iframe mode. The HTTP endpoint may be used only on the **same computer** at `127.0.0.1` / `localhost`. Do not port-forward it or deploy it on Render.

## Security properties implemented

- Every registered account has an immutable random actor identifier, unique case-insensitive username and character name, and a salted **scrypt password hash**. Passwords are not retained as plaintext. Login failures are bounded with a temporary lockout. New registrations also require a one-time, seven-day operator-issued invitation by default, limiting unrestricted starter-gold farming.
- Successful login issues a fresh random 256-bit session token. Only the **SHA-256 digest** of that token is stored in SQLite; the browser receives it as a 24-hour **HttpOnly, SameSite=Strict, host-only cookie**. Logging out invalidates it.
- The API associates every authenticated request with the actor ID from the session record. The browser never chooses the trusted acting actor. Mutable API routes require an additional per-session CSRF header; same-origin and loopback-only Host checks also apply.
- Gameplay requests use a per-account idempotency key. Commands and account registrations are committed to the **same SQLite database** as an append-only shared-world journal, with a single in-process mutation lock and rollback on database failure. The journal replays to reconstruct the shared world on restart.
- The world validates ownership and asset conservation, including gear and trade escrow. Private player inventory, money, combat stats and Chronicle actions are not placed in other players' public search results; chat and trade read permissions are bound to the current account.

## Development limitations

This is a **single-process local bridge**, not an internet-hardened service. The shared world is reconstructed from a bounded journal on restart; there is no normalized PostgreSQL player/asset ledger, migration/backup management, scale-out, distributed transactions or production monitoring. Chat and incoming trade alerts are now pushed through **authenticated SSE** on localhost with bounded connections. NPC and human targets now share **the original turn-based duel UI**: the attacker selects each weapon, dagger, fists, guard or unlocked combat spell with its existing stamina/mana cost; a defending player automatically counterstrikes without consuming stamina. Human defenders see an optional Under Attack activity icon and can watch or flee, without being forced away from the current page. PvP duels end on knockout, retreat or a ten-round draw (which carries no loot or hospitalization). The historical one-swing `pvp_strike` action remains replayable in old journals but is no longer accepted as a new multiplayer API request. In normal multi-account mode, server wall time advances the shared simulation through replayable, bounded journal ticks. Untrusted players cannot fast-forward the world. For local demos that intentionally retain the original world-time buttons and open registration, add `--dev-fast-forward --dev-open-registration` to the command line; never use these flags against untrusted players. Sessions expire after 24 hours and the development backend has a maximum of 100 accounts and 20,000 journal entries. Password reset, MFA, account recovery, moderation and anti-spam controls remain future work.

**Do not put this login mode online as-is.** Before public hosting, require TLS with Secure session cookies, hardened proxy and DNS/Host controls, application-level rate limits across IPs and accounts, password-reset and anti-abuse procedures, backups, a production database with transactional concurrency handling, and a deployment security review.

The server also applies in-process HTTP throttling and SQLite-backed daily action/chat/registration quotas. New multiplayer horse-race and magic rolls use a private persisted HMAC key; historical actions still replay with their original RNG. See [the detailed Phase 1 threat model](SECURITY_PHASE1.md) for limitations, operator commands and numeric limits.

## Suggested security smoke checks

1. Create Alice and Bob with different browser profiles; verify each sees only their own gold and equipment.
2. Chat privately between them, then confirm a third account cannot read those messages.
3. Trade gold/items/equipment and restart the server; balances and trade status should persist.
4. Sign out of Alice, then verify her old session cannot mutate the world.
5. Try using Bob's cookie to send a request with an extra `actor_id` field naming Alice; the API must reject it.
6. Retry an already committed action using the same action ID; it must not spend resources twice.

The test suite includes automated account isolation, CSRF, forged identity, idempotency, rollback, trade concurrency, persistence, direct-message streaming privacy and PvP tests.

## Active activities

The top status area displays only current cooldowns, incoming trade requests, active travel and ongoing University studies. Trade is accessible through character profiles or the incoming-trade indicator instead of an always-visible top menu button. University enrollment now executes correctly from the expanded school panel, and its simulated-time remaining duration is shown in the activity icon tooltip. A compact unread count appears beside Chat when other people send unread messages.

## Chronicle, new characters and live presence

Newly registered multiplayer characters begin in **Crownreach**. Previously registered characters retain their existing cities, and journal replay preserves the historical spawn city for old accounts. The old single-player JSON save remains readable; new single-player characters also start in Crownreach, while legacy saves without a recorded starting city continue replaying from Goldmeadow.

The Chronicle now includes player-to-player trade proposals, settlements and cancellations for **both parties**, with summarized exchanged assets. Events have consistent categories such as Trade, Combat, Travel, University, Economy, Health and Racing. The Chronicle supports category filtering and keyword search over the latest 500 authorized events.

New multiplayer journal commands now store timezone-aware UTC wall-clock timestamps in SQLite, rendered in the browser as Eastern time. Existing historical commands without stored wall-clock timestamps remain marked **timestamp unavailable**; dates are not fabricated or inferred from simulation minutes. SQLite migrations add the timestamp column automatically without deleting accounts or transactions.

The authenticated event stream now sends the requesting account's public character directory (name, city, level, health and ability to attack), alongside its authorized Chronicle and social notifications. When someone arrives in a city, other nearby players immediately see updated location and combat eligibility. Private inventories, funds and combat attributes remain excluded.

The compact refresh icon beside Chat requests a full current game snapshot (market, city, public characters, Chronicle, and inventory) without changing screens. This provides a manual way to re-sync pages beyond the pushed chat and character presence fields.

## Player combat, availability and notifications

Fleeing is now a **server-controlled 50/50 coin flip**. Each attempt uses one duel round. A failed escape permits an automatic zero-stamina counterattack, and a successful escape ends the encounter without defeat loot. The actual outcome is saved in the action journal for exact restart replay. Historical journal entries from before this change retain their original guaranteed-escape behavior; no account or combat history is reset.

A defending player's **Under Attack** notification appears after the first real combat action, not merely when an attacker opens an encounter. A defeated character displays a hospital indicator and simulated remaining recovery time alongside active cooldowns.

The Search character list is scoped to the current city. Active/Away/Offline indicators on human profiles and search results reflect **ephemeral authenticated browser presence**, never hidden combat attributes: **Active** means a recent heartbeat from a visible, non-idle tab; **Away** means a background tab or a visible tab with five minutes of no interaction; **Offline** means no heartbeat within approximately ninety seconds. Heartbeats are delivered only to the localhost development server with session and CSRF validation. Presence is not a promise of immediate response, and it is not written to the world simulation journal.
