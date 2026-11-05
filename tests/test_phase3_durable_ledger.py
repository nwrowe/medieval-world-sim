"""Phase 3 durability tests: receipts, escrow, reconciliation and SQL rollback."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web import ledger
from medieval_world_sim.web.multiplayer import MultiplayerGame


class DurableLedgerTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "durable.sqlite3"
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def create_player(self, name):
        return self.game.register(name.lower(), "secure test password", name)

    def journal_count(self):
        return self.game.db.execute(
            "SELECT COUNT(*) FROM world_journal").fetchone()[0]

    def test_asset_and_receipt_are_committed_together_and_idempotent(self):
        actor = self.create_player("Alice")
        self.assertEqual(self.journal_count(), 1)
        self.assertEqual(self.game.db.execute(
            "SELECT quantity FROM asset_ledger WHERE holder_type='actor' "
            "AND holder_id=? AND asset_type='gold'", (actor,)).fetchone()[0], 240)
        receipt_before = self.game.db.execute(
            "SELECT COUNT(*) FROM durable_receipts").fetchone()[0]
        first = self.game.action(actor, "send_chat", {
            "kind": "global", "target": "", "message": "Hello!"}, "chat-1")
        replay = self.game.action(actor, "send_chat", {
            "kind": "global", "target": "", "message": "Hello!"}, "chat-1")
        self.assertEqual(first, replay)
        self.assertEqual(self.journal_count(), 2)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM durable_receipts").fetchone()[0], receipt_before + 1)
        with self.assertRaises(ActionError):
            self.game.action(actor, "send_chat", {
                "kind": "global", "target": "", "message": "Different"}, "chat-1")
        ledger.verify(self.game)

    def test_escrow_ownership_tracks_trade_lifecycle(self):
        alice = self.create_player("Alice")
        bob = self.create_player("Bob")
        empty = {"gold": 0, "items": [], "gear_ids": []}
        offer = {"gold": 31, "items": [], "gear_ids": []}
        result = self.game.action(alice, "propose_trade", {
            "recipient_id": bob, "offer": offer, "request": empty}, "trade-offer")
        trade_id = result["id"]
        self.assertEqual(self.game.db.execute(
            "SELECT quantity FROM asset_ledger WHERE holder_type='trade' "
            "AND holder_id=? AND asset_type='gold'", (str(trade_id),)).fetchone()[0], 31)
        self.assertEqual(self.game.db.execute(
            "SELECT quantity FROM asset_ledger WHERE holder_type='actor' "
            "AND holder_id=? AND asset_type='gold'", (alice,)).fetchone()[0], 209)
        self.game.action(bob, "accept_trade", {
            "trade_id": trade_id, "terms_hash": result["terms_hash"]}, "trade-accept")
        self.assertIsNone(self.game.db.execute(
            "SELECT 1 FROM asset_ledger WHERE holder_type='trade' "
            "AND holder_id=?", (str(trade_id),)).fetchone())
        self.assertEqual(self.game.db.execute(
            "SELECT quantity FROM asset_ledger WHERE holder_type='actor' "
            "AND holder_id=? AND asset_type='gold'", (bob,)).fetchone()[0], 271)
        ledger.verify(self.game)

    def test_restart_reconciles_and_keeps_durable_receipts(self):
        alice = self.create_player("Alice")
        self.game.advance(alice, 3, "tick-3")
        previous_rows = ledger.current_rows(self.game.world)
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)
        self.assertEqual(ledger.current_rows(self.game.world), previous_rows)
        self.assertIsNone(self.game.advance(alice, 3, "tick-3"))
        self.assertEqual(self.game.world.minute, 3)
        self.assertEqual(self.journal_count(), 2)

    def test_sql_commit_failure_rolls_back_receipt_and_asset_ledger(self):
        alice = self.create_player("Alice")
        initial = ledger.current_rows(self.game.world)
        original = ledger.persist

        def fail_after_writes(game):
            original(game)
            raise OSError("disk error after materialization")

        with patch("medieval_world_sim.web.multiplayer.ledger.persist",
                   side_effect=fail_after_writes):
            with self.assertRaisesRegex(OSError, "disk error"):
                self.game.advance(alice, 3, "failed-advance")
        self.assertEqual(self.game.world.minute, 0)
        self.assertEqual(ledger.current_rows(self.game.world), initial)
        self.assertEqual(self.journal_count(), 1)
        self.assertIsNone(self.game.db.execute(
            "SELECT 1 FROM durable_receipts WHERE request_id='failed-advance'").fetchone())
        ledger.verify(self.game)
        self.game.advance(alice, 3, "failed-advance")
        self.assertEqual(self.game.world.minute, 3)

    def test_reconciliation_fails_closed_on_asset_or_receipt_tamper(self):
        alice = self.create_player("Alice")
        self.game.advance(alice, 3, "tick-3")
        self.game.db.execute(
            "UPDATE asset_ledger SET quantity=quantity+1 WHERE holder_type='actor' "
            "AND holder_id=? AND asset_type='gold'", (alice,))
        with self.assertRaisesRegex(ValueError, "asset reconciliation"):
            ledger.verify(self.game)
        self.game.db.execute(
            "UPDATE asset_ledger SET quantity=quantity-1 WHERE holder_type='actor' "
            "AND holder_id=? AND asset_type='gold'", (alice,))
        self.game.db.execute(
            "DELETE FROM durable_receipts WHERE request_id='tick-3'")
        with self.assertRaisesRegex(ValueError, "receipts diverge"):
            ledger.verify(self.game)

    def test_simultaneous_duplicate_requests_have_one_receipt(self):
        alice = self.create_player("Alice")
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(
                lambda _: self.game.advance(alice, 1, "same-request"), range(8)))
        self.assertEqual(outcomes, [None] * 8)
        self.assertEqual(self.game.world.minute, 1)
        self.assertEqual(self.journal_count(), 2)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM durable_receipts WHERE request_id='same-request'"
        ).fetchone()[0], 1)
        ledger.verify(self.game)

    def test_legacy_database_gets_a_one_time_reconciliation(self):
        alice = self.create_player("Alice")
        self.game.advance(alice, 1, "before-migration")
        # Simulate a DB created by the old journal-only release.
        self.game.db.execute(
            "DELETE FROM world_meta WHERE name='durable_ledger_initialized'")
        self.game.db.execute("DELETE FROM ledger_head")
        self.game.db.execute("DELETE FROM durable_receipts")
        self.game.db.execute("DELETE FROM asset_ledger")
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)
        ledger.verify(self.game)
        self.assertEqual(self.game.world.minute, 1)
        self.assertEqual(self.journal_count(), 2)
