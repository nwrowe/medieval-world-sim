# Local multi-account development mode

Oathmere now has an **opt-in localhost-only, shared-world development mode** for building and testing authenticated player accounts without buying or operating a physical server. It is **not a publicly deployable multiplayer release**.

## Start it

From the project directory (after installing the package in editable mode):

```powershell
python -m medieval_world_sim.web --multiplayer-db "$HOME\.medieval-world-sim\multi-dev.sqlite3"
```

Open the printed `http://127.0.0.1:8765` address. Register a **username**, a separate **character display name**, and a password of at least 12 characters. To test a second player, use a separate browser profile or a private/incognito window, create a second account, and log in independently. The two characters live in the **same simulated world**; actions and assets are persisted in a SQLite database. You can test direct chat, guild/company channel permissions and bilateral trades through the authenticated API.

The ordinary command with no `--multiplayer-db` remains the original single-player game with its original JSON save. **Existing saves are not changed or automatically imported.** You can switch back by restarting the server without the flag.

`--multiplayer-db` is deliberately forbidden when the HTTP host is `0.0.0.0` or other nonloopback addresses. It also cannot be combined with the old shared `--access-token` or the Colab iframe mode. The HTTP endpoint may be used only on the **same computer** at `127.0.0.1` / `localhost`. Do not port-forward it or deploy it on Render.

## Security properties implemented

- Every registered account has an immutable random actor identifier, unique case-insensitive username and character name, and a salted **scrypt password hash**. Passwords are not retained as plaintext. Login failures are bounded with a temporary lockout.
- Successful login issues a fresh random 256-bit session token. Only the **SHA-256 digest** of that token is stored in SQLite; the browser receives it as a 24-hour **HttpOnly, SameSite=Strict, host-only cookie**. Logging out invalidates it.
- The API associates every authenticated request with the actor ID from the session record. The browser never chooses the trusted acting actor. Mutable API routes require an additional per-session CSRF header; same-origin and loopback-only Host checks also apply.
- Gameplay requests use a per-account idempotency key. Commands and account registrations are committed to the **same SQLite database** as an append-only shared-world journal, with a single in-process mutation lock and rollback on database failure. The journal replays to reconstruct the shared world on restart.
- The world validates ownership and asset conservation, including gear and trade escrow. Private player inventory, money, combat stats and Chronicle actions are not placed in other players' public search results; chat and trade read permissions are bound to the current account.

## Development limitations

This is a **single-process local bridge**, not an internet-hardened service. The shared world is reconstructed from a bounded journal on restart; there is no normalized PostgreSQL player/asset ledger, migration/backup management, scale-out, distributed transactions or production monitoring. Chat and incoming trade alerts are now pushed through **authenticated SSE** on localhost with bounded connections. NPC attacks remain turn-based, while player-versus-player attacks are one-swing server-resolved skirmishes (weapon-specific stamina, automatic counterattack and capped gold loot); there is no full player-versus-player turn-based challenge protocol yet. A player-initiated world-time advance currently advances simulated time for everyone, which will need redesign for a live game. Sessions expire after 24 hours and the development backend has a maximum of 100 accounts and 20,000 journal entries. Password reset, MFA, account recovery, moderation and anti-spam controls remain future work.

**Do not put this login mode online as-is.** Before public hosting, require TLS with Secure session cookies, hardened proxy and DNS/Host controls, application-level rate limits across IPs and accounts, password-reset and anti-abuse procedures, backups, a production database with transactional concurrency handling, and a deployment security review.

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
