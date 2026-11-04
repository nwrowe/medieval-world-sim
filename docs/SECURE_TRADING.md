# Authenticated bilateral trade: domain foundation

**Status:** engine-only. The current Oathmere browser server is **single-player**. Its LAN access code identifies a whole server, not an individual account. Do **not** expose trade endpoints on that API: a client must first have a separately authenticated principal. The trade engine deliberately does not appear in `GameSession.UI_ACTIONS` and cannot be called from the single-player browser.

## Proposed workflow

1. An authenticated player calls `WorldEngine.execute(principal_id, "propose_trade", {"recipient_id", "offer", "request"}, request_id)`. The server must derive `principal_id` from its own verified session, never accept it from a client field.
2. The engine validates both players, their common city, the maker's ownership and bounded positive quantities. The maker's exact gold, goods, and unique gear IDs are removed from their holdings into escrow. Equipped gear is unequipped automatically. The recipient's assets are only *requested*, not removed.
3. The recipient reviews both immutable bundles with the specific `trade_id` and SHA-256 `terms_hash`. Only that exact recipient may accept, and they must echo the terms hash. The engine validates their live holdings and both players' location. It releases maker escrow and transfers recipient assets atomically under the engine lock.
4. Either side can close an outstanding offer, returning escrow entirely to the maker. Attempts to accept closed offers fail. Mutating stale terms is impossible; counteroffers must create a new trade.
5. Repeated command IDs have idempotent receipts; conflicting uses of an ID are rejected. Gold conservation includes all escrow. Equipment must have exactly one owner or escrow slot, never two.

Asset schema:

```json
{"gold": 10, "items": [{"item": "grain", "quantity": 2}], "gear_ids": [15]}
```

Offers and requests are explicit, typed and bounded. A trade may gift assets one way, but cannot be completely empty. Only actual human actors can be trade parties; NPCs are not disguised as players.

## What is *not* yet secure or live

The in-memory engine is transaction-safe **within one process** (`atomic_action` rollbacks under `RLock`). It is not a substitute for database ACID durability across multiple servers or processes. Before enabling player trading on a hosted multiplayer service, introduce:

- Account registration/login, secure password storage, per-account sessions and a verified session-to-actor mapping.
- A shared database transaction (e.g., PostgreSQL `SERIALIZABLE` or appropriate row locks) for escrow, inventory, trade acceptance, and commit; unique constraints on item/gear ownership.
- Persistent trade status and event audit, expiry/cleanup, trade limits, abuse controls and recovery/reconciliation after process failure.
- Real-time inbox and offer-revision UX, with a second explicit recipient confirmation on changed terms.

Do not claim real multiplayer trading or security until the identity layer, database and end-to-end authentication/authorization tests are complete.
