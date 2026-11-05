"""SQLite-backed materialized asset ownership and durable command receipts.

The WorldEngine remains authoritative during the running process. Every
journaled change also commits an independently inspectable asset ledger and
receipt table in *the same SQLite transaction*. On restart, rebuilding the
world and comparing against this ledger fails closed on divergence.

This stage intentionally does not replace journal replay or use the ledger
for gameplay mutation; checkpoints and authoritative asset writes follow.
"""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .multiplayer import MultiplayerGame


ASSET_FIELDS = ("holder_type", "holder_id", "location", "asset_type",
                "asset_id", "quantity")


def create_schema(game: MultiplayerGame) -> None:
    """Create auxiliary durable tables without rewriting legacy journal rows."""
    game.db.executescript("""
        CREATE TABLE IF NOT EXISTS asset_ledger(
            holder_type TEXT NOT NULL,
            holder_id TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            asset_type TEXT NOT NULL CHECK(asset_type IN ('gold','item','gear','deposit')),
            asset_id TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            PRIMARY KEY(holder_type, holder_id, location, asset_type, asset_id)
        );
        CREATE TABLE IF NOT EXISTS durable_receipts(
            actor_id TEXT NOT NULL,
            request_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            action TEXT,
            payload TEXT NOT NULL,
            result_json TEXT NOT NULL,
            journal_seq INTEGER NOT NULL UNIQUE
                REFERENCES world_journal(seq),
            PRIMARY KEY(actor_id, request_id)
        );
        CREATE TABLE IF NOT EXISTS ledger_head(
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            journal_seq INTEGER NOT NULL CHECK(journal_seq >= 0)
        );
    """)


def current_rows(world) -> list[tuple[str, str, str, str, str, int]]:
    """Projection of all present assets, including storage and locked escrow.

    This function deliberately captures *actual ownership*, not estimated
    values. It includes every gear instance exactly once and all locations
    holding funds, including city treasuries and accepted trade escrow.
    """
    holdings = Counter()
    gear_locations = []

    def add(kind: str, owner: str, place: str, asset: str,
            asset_id: str | int, count: int) -> None:
        if type(count) is not int or count < 0:
            raise AssertionError("Negative or noninteger durable asset quantity")
        if count:
            key = (kind, str(owner), str(place), asset, str(asset_id))
            holdings[key] += count
            if asset == "gear":
                if count != 1:
                    raise AssertionError("Nonfungible gear cannot have quantity >1")
                gear_locations.append(int(asset_id))

    def bag(kind: str, owner: str, place: str, items: dict) -> None:
        for item, count in items.items():
            add(kind, owner, place, "item", item, count)

    add("crown", "crown", "", "gold", "gold", world.crown_gold)
    for actor in world.actors.values():
        add("actor", actor.id, "", "gold", "gold", actor.gold)
        bag("actor", actor.id, "", actor.inventory)
        for gear_id in actor.gear_ids:
            add("actor", actor.id, "", "gear", gear_id, 1)
        for city, goods in actor.storage.items():
            bag("storage", actor.id, city, goods)
    for company in world.companies.values():
        add("company", company.id, "", "gold", "gold", company.gold)
        bag("company", company.id, "", company.inventory)
        for gear_id in company.gear_ids:
            add("company", company.id, "", "gear", gear_id, 1)
    for city in world.cities.values():
        add("city", city.id, "", "gold", "gold", city.household_gold)
        bag("merchant", city.id, "", city.merchant_stock)
        for resource, count in city.deposits.items():
            add("deposits", city.id, "", "deposit", resource, count)
    for offer in world.offers.values():
        if offer.gear_id is not None:
            add("offer", offer.id, "", "gear", offer.gear_id, 1)
        else:
            add("offer", offer.id, "", "item", offer.item, offer.quantity)
    for trade in world.state.trades.values():
        add("trade", trade.id, "", "gold", "gold", trade.offer.gold)
        for item, count in trade.offer.items:
            add("trade", trade.id, "", "item", item, count)
        for gear_id in trade.offer.gear_ids:
            add("trade", trade.id, "", "gear", gear_id, 1)

    if len(gear_locations) != len(set(gear_locations)):
        raise AssertionError("Durable ledger contains duplicate gear ownership")
    if set(gear_locations) != set(world.gear):
        raise AssertionError("Durable ledger is missing gear ownership")
    result = [(*key, amount) for key, amount in holdings.items()]
    actual_gold = sum(row[-1] for row in result if row[3] == "gold")
    if actual_gold != world.initial_gold:
        raise AssertionError("Durable gold ledger does not conserve issuance")
    return sorted(result)


def _journal_head(game: MultiplayerGame) -> int:
    return game.db.execute(
        "SELECT COALESCE(MAX(seq),0) FROM world_journal").fetchone()[0]


def _receipt_rows(game: MultiplayerGame):
    return game.db.execute(
        "SELECT actor_id, request_id, kind, action, payload, result_json, seq "
        "FROM world_journal WHERE request_id IS NOT NULL "
        "AND kind IN ('action','advance') ORDER BY seq").fetchall()


def _stored_receipts(game: MultiplayerGame):
    return game.db.execute(
        "SELECT actor_id, request_id, kind, action, payload, result_json, journal_seq "
        "FROM durable_receipts ORDER BY journal_seq").fetchall()


def persist(game: MultiplayerGame) -> None:
    """Persist a changed world and new receipts inside the caller's open txn."""
    head = _journal_head(game)
    stored = game.db.execute(
        "SELECT journal_seq FROM ledger_head WHERE singleton=1").fetchone()
    if stored is not None and stored[0] == head:
        return  # Idempotent command retries do not manufacture a revision.
    rows = current_rows(game.world)
    # Retain the authoritative full-state reconciliation, but write only
    # changed holdings. A no-asset-change command (chat, presence) should
    # not DELETE and INSERT hundreds of other players' balances or gear.
    saved = {
        row[:5]: row[5] for row in game.db.execute(
            "SELECT " + ",".join(ASSET_FIELDS) + " FROM asset_ledger")
    }
    desired = {row[:5]: row[5] for row in rows}
    removed = sorted(set(saved) - set(desired))
    modified = sorted(
        (*key, amount) for key, amount in desired.items()
        if saved.get(key) != amount
    )
    game.db.executemany(
        "DELETE FROM asset_ledger WHERE holder_type=? AND holder_id=? "
        "AND location=? AND asset_type=? AND asset_id=?",
        removed)
    game.db.executemany(
        "INSERT INTO asset_ledger(" + ",".join(ASSET_FIELDS) +
        ") VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(holder_type,holder_id,location,asset_type,asset_id) "
        "DO UPDATE SET quantity=excluded.quantity",
        modified)
    game.db.execute(
        "INSERT INTO durable_receipts("
        "actor_id,request_id,kind,action,payload,result_json,journal_seq) "
        "SELECT actor_id,request_id,kind,action,payload,result_json,seq "
        "FROM world_journal WHERE request_id IS NOT NULL "
        "AND kind IN ('action','advance') "
        "AND seq>? ORDER BY seq",
        (stored[0] if stored is not None else 0,))
    game.db.execute(
        "INSERT INTO ledger_head(singleton,journal_seq) VALUES(1,?) "
        "ON CONFLICT(singleton) DO UPDATE SET journal_seq=excluded.journal_seq",
        (head,))


def verify(game: MultiplayerGame) -> None:
    head = game.db.execute(
        "SELECT journal_seq FROM ledger_head WHERE singleton=1").fetchone()
    if head is None or head[0] != _journal_head(game):
        raise ValueError("Durable ledger revision differs from command journal")
    saved = game.db.execute(
        "SELECT " + ",".join(ASSET_FIELDS) + " FROM asset_ledger "
        "ORDER BY holder_type,holder_id,location,asset_type,asset_id").fetchall()
    if saved != current_rows(game.world):
        raise ValueError("Durable asset reconciliation failed")
    if _stored_receipts(game) != _receipt_rows(game):
        raise ValueError("Durable command receipts diverge from journal")


def initialize_or_verify(game: MultiplayerGame) -> None:
    """Migrate old journals once; never silently reinitialize a known ledger."""
    marker = game.db.execute(
        "SELECT value FROM world_meta WHERE name='durable_ledger_initialized'").fetchone()
    if marker is not None:
        verify(game)
        return
    # Older game databases had journal commands only. Reconstruct their
    # materialized assets and receipts from the fully validated replay.
    game.db.execute("BEGIN IMMEDIATE")
    try:
        persist(game)
        game.db.execute(
            "INSERT INTO world_meta(name,value) VALUES('durable_ledger_initialized',?)",
            (b'1',))
        verify(game)
        game.db.execute("COMMIT")
    except BaseException:
        game.db.execute("ROLLBACK")
        raise
