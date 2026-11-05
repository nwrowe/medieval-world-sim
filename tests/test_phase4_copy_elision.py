"""Phase 4 rollback ownership: one world snapshot, unchanged atomic guarantees."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.multiplayer import MultiplayerGame


class TransactionCopyElisionTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.game = MultiplayerGame(Path(self.temp.name) / "world.sqlite3",
                                    require_invites=False, dev_fast_forward=True)
        self.player = self.game.register("alice", "secure test password", "Alice River")

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def test_single_copy_for_multiplayer_action_and_world_tick(self):
        from medieval_world_sim.web import multiplayer as service
        from medieval_world_sim.core import transactions as engine_tx
        outer_copy = service.deepcopy
        inner_copy = engine_tx.deepcopy
        with patch.object(service, "deepcopy", wraps=outer_copy) as outer, patch.object(
                engine_tx, "deepcopy", wraps=inner_copy) as inner:
            self.game.action(self.player, "send_chat", {
                "kind": "global", "target": "", "message": "hi"}, "copy-one")
            self.assertEqual(outer.call_count, 1)
            self.assertEqual(inner.call_count, 0)
            self.game.advance(self.player, 3, "copy-tick")
            self.assertEqual(outer.call_count, 2)
            self.assertEqual(inner.call_count, 0)
        self.assertFalse(self.game.world._durable_tx_owns_rollback)

    def test_committed_retry_skips_both_rollback_copies(self):
        self.game.action(self.player, "send_chat", {
            "kind": "global", "target": "", "message": "first"}, "retry-me")
        from medieval_world_sim.web import multiplayer as service
        from medieval_world_sim.core import transactions as engine_tx
        with patch.object(service, "deepcopy", wraps=service.deepcopy) as outer, patch.object(
                engine_tx, "deepcopy", wraps=engine_tx.deepcopy) as inner:
            result = self.game.action(self.player, "send_chat", {
                "kind": "global", "target": "", "message": "first"}, "retry-me")
            self.assertEqual(result["posted"], True)
            self.assertEqual(outer.call_count, 0)
            self.assertEqual(inner.call_count, 0)
            with self.assertRaises(ActionError):
                self.game.action(self.player, "send_chat", {
                    "kind": "global", "target": "", "message": "changed"}, "retry-me")
            self.assertEqual(outer.call_count, 0)

    def test_engine_standalone_still_has_atomic_rollback(self):
        world = WorldEngine([Actor("solo", "human")])
        before = world.actors["solo"].gold
        from medieval_world_sim.core import transactions
        original = transactions.deepcopy
        with patch.object(transactions, "deepcopy", wraps=original) as copied:
            with self.assertRaises(ActionError):
                world.buy_starter_gear("solo", "not-a-real-item")
            self.assertGreaterEqual(copied.call_count, 1)
        self.assertEqual(world.actors["solo"].gold, before)
        world.assert_invariants()

    def test_sql_failure_restores_world_and_disables_elision(self):
        from medieval_world_sim.web import ledger
        original = ledger.persist
        initial = self.game.world.actors[self.player].gold

        def fail_write(game):
            original(game)
            raise OSError("simulated write failure")

        with patch("medieval_world_sim.web.multiplayer.ledger.persist",
                   side_effect=fail_write):
            with self.assertRaisesRegex(OSError, "simulated write"):
                self.game.advance(self.player, 2, "bad-tick")
        self.assertFalse(self.game.world._durable_tx_owns_rollback)
        self.assertEqual(self.game.world.minute, 0)
        self.assertEqual(self.game.world.actors[self.player].gold, initial)
        self.assertIsNone(self.game.db.execute(
            "SELECT 1 FROM durable_receipts WHERE request_id='bad-tick'").fetchone())
        self.game.advance(self.player, 2, "bad-tick")
        self.assertEqual(self.game.world.minute, 2)
        self.game.world.assert_invariants()

    def test_invalid_action_restores_snapshot_and_next_action_works(self):
        with self.assertRaises(ActionError):
            self.game.action(self.player, "buy_starter_gear",
                             {"kind": "nonexistent"}, "invalid")
        self.assertFalse(self.game.world._durable_tx_owns_rollback)
        self.game.action(self.player, "send_chat", {
            "kind": "global", "target": "", "message": "still here"}, "good")
        self.assertEqual(len(self.game.world.state.chat_messages), 1)
