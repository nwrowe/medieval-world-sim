# Authenticated bilateral trade: domain foundation

**Status:** trade remains unavailable in the ordinary single-player browser. The opt-in **localhost-only multi-account development mode** (see [setup](MULTIPLAYER_LOCAL_DEVELOPMENT.md)) now authenticates separate players and exposes trade endpoints through session-bound, CSRF-protected requests. This is for local testing only; do **not** use the development server as a public-money or internet-facing trading service. The old shared LAN access code still cannot authenticate individual people.

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

The local multi-account development service uses a **single SQLite transaction** for each replayable action and a shared process lock around world changes; this survives restarts and avoids double settlement in the local mode. Its in-memory world is still **not a normalized shared asset ledger** and cannot provide cross-process ACID behavior or production crash-recovery guarantees without further work. Before enabling publicly hosted player trading, introduce:

- Account registration/login, secure password storage, per-account sessions and a verified session-to-actor mapping.
- A shared database transaction (e.g., PostgreSQL `SERIALIZABLE` or appropriate row locks) for escrow, inventory, trade acceptance, and commit; unique constraints on item/gear ownership.
- Persistent trade status and event audit, expiry/cleanup, trade limits, abuse controls and recovery/reconciliation after process failure.
- Real-time inbox and offer-revision UX, with a second explicit recipient confirmation on changed terms.

Do not claim real multiplayer trading or security until the identity layer, database and end-to-end authentication/authorization tests are complete.
