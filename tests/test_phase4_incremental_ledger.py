"""Phase 4 asset ledger: immutable holdings never incur useless SQL writes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from medieval_world_sim.web import ledger
from medieval_world_sim.web.multiplayer import MultiplayerGame


class IncrementalLedgerTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "incremental.sqlite3"
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)
        self.alice = self.game.register("alice", "secure test password", "Alice River")
        self.bob = self.game.register("bobby", "secure test password", "Bryn Stone")
        self.game.db.executescript("""
            CREATE TABLE asset_audit(op TEXT NOT NULL);
            CREATE TRIGGER track_insert AFTER INSERT ON asset_ledger BEGIN
                INSERT INTO asset_audit VALUES('insert');
            END;
            CREATE TRIGGER track_update AFTER UPDATE ON asset_ledger BEGIN
                INSERT INTO asset_audit VALUES('update');
            END;
            CREATE TRIGGER track_delete AFTER DELETE ON asset_ledger BEGIN
                INSERT INTO asset_audit VALUES('delete');
            END;
        """)

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def ops(self):
        result = self.game.db.execute(
            "SELECT op, COUNT(*) FROM asset_audit GROUP BY op").fetchall()
        return dict(result)

    def test_non_asset_actions_have_zero_asset_row_mutations(self):
        before = ledger.current_rows(self.game.world)
        self.game.action(self.alice, "send_chat", {
            "kind": "global", "target": "", "message": "No gold changes"},
            "message")
        self.assertEqual(self.ops(), {})
        self.assertEqual(ledger.current_rows(self.game.world), before)
        ledger.verify(self.game)

    def test_trade_modifies_only_escrow_and_participant_balances(self):
        empty = {"gold": 0, "items": [], "gear_ids": []}
        offer = {"gold": 23, "items": [], "gear_ids": []}
        trade = self.game.action(self.alice, "propose_trade", {
            "recipient_id": self.bob, "offer": offer,
            "request": empty}, "offer")
        # Alice's gold changes and a new trade escrow is inserted. The
        # other player's balance and every city/merchant row remain intact.
        self.assertEqual(self.ops(), {"insert": 1, "update": 1})
        self.game.action(self.bob, "accept_trade", {
            "trade_id": trade["id"], "terms_hash": trade["terms_hash"]}, "accept")
        self.assertEqual(self.ops(), {"delete": 1, "insert": 1, "update": 2})
        ledger.verify(self.game)

    def test_rollback_after_partial_asset_changes_is_atomic(self):
        before = self.game.db.execute(
            "SELECT * FROM asset_ledger ORDER BY 1,2,3,4,5").fetchall()
        original = ledger.persist

        def failed_after_persist(game):
            original(game)
            raise OSError("write interrupted")

        with patch("medieval_world_sim.web.multiplayer.ledger.persist",
                   side_effect=failed_after_persist):
            with self.assertRaisesRegex(OSError, "write interrupted"):
                self.game.action(self.alice, "propose_trade", {
                    "recipient_id": self.bob,
                    "offer": {"gold": 19, "items": [], "gear_ids": []},
                    "request": {"gold": 0, "items": [], "gear_ids": []}
                }, "interrupted")
        self.assertEqual(self.ops(), {})
        self.assertEqual(self.game.db.execute(
            "SELECT * FROM asset_ledger ORDER BY 1,2,3,4,5").fetchall(), before)
        self.assertEqual(len(self.game.world.state.trades), 0)
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)
        ledger.verify(self.game)
