"""Phase 4 transaction efficiency contracts without reducing safety guarantees."""
import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web import ledger
from medieval_world_sim.web.multiplayer import MultiplayerGame


class TransactionEfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "transactions.sqlite3"
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)
        self.alice = self.game.register("alice", "long secure password", "Alice Meadows")
        self.bob = self.game.register("bobby", "long secure password", "Bob Forest")

    def tearDown(self):
        self.game.close()
        self.tmp.cleanup()

    def test_one_outer_copy_and_no_inner_copy_per_multiplayer_action(self):
        with patch("medieval_world_sim.web.multiplayer.deepcopy",
                   wraps=copy.deepcopy) as outer, patch(
                   "medieval_world_sim.core.transactions.deepcopy",
                   side_effect=AssertionError("Nested whole-world copy")):
            self.game.action(self.alice, "send_chat",
                             {"kind": "global", "target": "", "message": "hello"},
                             "chat-first")
            self.assertEqual(outer.call_count, 1)
            # A trusted clock advance invokes WorldEngine.advance, but it too
            # delegates rollback to the single SQLite owner.
            self.game.advance(self.alice, 1, "advance-first")
            self.assertEqual(outer.call_count, 2)
        self.assertFalse(self.game.world._external_transaction_active)
        ledger.verify(self.game)

    def test_standalone_engine_still_has_independent_atomic_rollback(self):
        standalone = WorldEngine([Actor("solo", "human", city="goldmeadow")])
        with patch("medieval_world_sim.core.transactions.deepcopy",
                   wraps=copy.deepcopy) as copies:
            standalone.gather("solo", "grain", 1)
            self.assertEqual(copies.call_count, 1)
        self.assertEqual(standalone.actors["solo"].inventory["grain"], 1)

    def test_idempotent_retry_avoids_any_world_copy_or_sql_mutation(self):
        payload = {"kind": "global", "target": "", "message": "one only"}
        first = self.game.action(self.alice, "send_chat", payload, "chat-once")
        before = self.game.db.execute(
            "SELECT COUNT(*) FROM world_journal").fetchone()[0]
        with patch("medieval_world_sim.web.multiplayer.deepcopy",
                   side_effect=AssertionError("Duplicate request copied world")):
            self.assertEqual(
                self.game.action(self.alice, "send_chat", payload, "chat-once"),
                first)
            with self.assertRaises(ActionError):
                self.game.action(self.alice, "send_chat",
                                 {**payload, "message": "changed"}, "chat-once")
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM world_journal").fetchone()[0], before)
        self.assertFalse(self.game.world._external_transaction_active)
        ledger.verify(self.game)

    def test_chat_and_presence_do_not_rewrite_whole_asset_table(self):
        sql = []
        self.game.db.set_trace_callback(sql.append)
        try:
            self.game.action(self.alice, "send_chat",
                             {"kind": "global", "target": "", "message": "one"},
                             "chat-1")
            self.game.presence_ping(self.bob, True)
        finally:
            self.game.db.set_trace_callback(None)
        asset_writes = [
            statement for statement in sql
            if statement.lstrip().upper().startswith((
                "DELETE FROM ASSET_LEDGER", "UPDATE ASSET_LEDGER",
                "INSERT INTO ASSET_LEDGER"))
        ]
        self.assertEqual(asset_writes, [])
        ledger.verify(self.game)

    def test_trade_changes_only_asset_rows_then_survives_restart(self):
        empty = {"gold": 0, "items": [], "gear_ids": []}
        sql = []
        self.game.db.set_trace_callback(sql.append)
        try:
            offer = self.game.action(self.alice, "propose_trade", {
                "recipient_id": self.bob,
                "offer": {"gold": 17, "items": [], "gear_ids": []},
                "request": empty}, "offer")
        finally:
            self.game.db.set_trace_callback(None)
        writes = [statement.upper() for statement in sql
                  if "ASSET_LEDGER" in statement.upper()
                  and statement.lstrip().upper().startswith((
                      "DELETE", "UPDATE", "INSERT"))]
        self.assertTrue(any("UPDATE ASSET_LEDGER" in s for s in writes))
        self.assertTrue(any("INSERT INTO ASSET_LEDGER" in s for s in writes))
        self.assertFalse(any(s.startswith("DELETE FROM ASSET_LEDGER") and
                             "WHERE" not in s for s in writes))
        self.game.action(self.bob, "accept_trade", {
            "trade_id": offer["id"], "terms_hash": offer["terms_hash"]}, "accept")
        ledger.verify(self.game)
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)
        self.assertEqual(self.game.world.actors[self.bob].gold, 257)
        ledger.verify(self.game)

    def test_failed_sql_materialization_rolls_back_memory_and_restores_owner(self):
        original = ledger.persist

        def fail_after_insert(game):
            original(game)
            raise OSError("injected fsync failure")

        before = self.game.world.minute
        with patch("medieval_world_sim.web.multiplayer.ledger.persist",
                   side_effect=fail_after_insert):
            with self.assertRaisesRegex(OSError, "fsync"):
                self.game.advance(self.alice, 2, "failed")
        self.assertEqual(self.game.world.minute, before)
        self.assertFalse(self.game.world._external_transaction_active)
        self.assertIsNone(self.game.db.execute(
            "SELECT 1 FROM durable_receipts WHERE request_id='failed'").fetchone())
        ledger.verify(self.game)

    def test_concurrent_duplicates_remain_exactly_once(self):
        payload = {"kind": "global", "target": "", "message": "one result"}
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _: self.game.action(self.alice, "send_chat", payload,
                                           "concurrent"), range(20)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM world_journal "
            "WHERE request_id='concurrent'").fetchone()[0], 1)
        self.assertFalse(self.game.world._external_transaction_active)
        ledger.verify(self.game)
