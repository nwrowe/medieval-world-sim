"""Phase 3 checkpoint recovery: strict JSON, tail replay, escrow and failure atomicity."""
from realm_fixtures import GOLDMEADOW

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.web import checkpoint, ledger
from medieval_world_sim.web.multiplayer import MultiplayerGame


class DurableCheckpointTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "checkpoint.sqlite3"
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)

    def tearDown(self):
        if self.game is not None:
            self.game.close()
        self.temp.cleanup()

    def player(self, name):
        return self.game.register(name.lower(), "secure test password", name)

    def restart(self):
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)

    def test_recovery_uses_checkpoint_not_full_journal_replay(self):
        alice = self.player("Alice")
        self.game.advance(alice, 3, "tick-3")
        self.game.action(alice, "send_chat", {
            "kind": "global", "target": "", "message": "Before checkpoint"},
            "chat-before")
        self.assertEqual(self.game.create_checkpoint(), 3)
        expected = self.game.snapshot(alice)
        self.game.close()
        with patch.object(WorldEngine, "execute",
                          side_effect=AssertionError("Replayed old action")):
            self.game = MultiplayerGame(self.path, require_invites=False,
                                        dev_fast_forward=True)
        actual = self.game.snapshot(alice)
        self.assertEqual(actual["player"]["gold"], expected["player"]["gold"])
        self.assertEqual(actual["minute"], expected["minute"])
        self.assertEqual(actual["chat"], expected["chat"])
        self.assertIsNone(self.game.advance(alice, 3, "tick-3"))
        self.assertEqual(self.game.world.minute, 3)
        ledger.verify(self.game)

    def test_exactly_the_tail_is_replayed(self):
        alice = self.player("Alice")
        self.game.advance(alice, 3, "before")
        self.game.create_checkpoint()
        self.game.advance(alice, 2, "after")
        original_advance = WorldEngine.advance
        calls = []

        def audited_advance(engine, minutes):
            calls.append(minutes)
            return original_advance(engine, minutes)

        self.game.close()
        with patch.object(WorldEngine, "advance", audited_advance):
            self.game = MultiplayerGame(self.path, require_invites=False,
                                        dev_fast_forward=True)
        self.assertEqual(calls, [2])  # Only the two-minute tail gets executed.
        self.assertEqual(self.game.world.minute, 5)
        ledger.verify(self.game)

    def test_escrow_survives_checkpoint_and_can_settle_after_restart(self):
        alice, bob = self.player("Alice"), self.player("Bob")
        empty = {"gold": 0, "items": [], "gear_ids": []}
        offer = {"gold": 37, "items": [], "gear_ids": []}
        proposed = self.game.action(alice, "propose_trade", {
            "recipient_id": bob, "offer": offer, "request": empty}, "propose")
        self.game.create_checkpoint()
        self.restart()
        self.assertIn(proposed["id"], self.game.world.state.trades)
        self.assertEqual(self.game.world.state.trades[proposed["id"]].offer.gold, 37)
        self.game.action(bob, "accept_trade", {
            "trade_id": proposed["id"], "terms_hash": proposed["terms_hash"]
        }, "accept")
        self.assertEqual(self.game.world.actors[bob].gold, 277)
        ledger.verify(self.game)

    def test_complex_character_assets_guilds_and_city_storage_round_trip(self):
        alice = self.player("Alice")
        gear_id = self.game.action(
            alice, "buy_starter_gear", {"kind": "sword"}, "buy-sword")
        self.game.action(alice, "equip", {"gear_id": gear_id}, "equip-sword")
        guild = self.game.action(alice, "found_guild", {"name": "Iron Circle"}, "guild")
        self.game.action(
            alice, "travel", {"destination": GOLDMEADOW}, "travel")
        self.game.advance(alice, 60, "arrival")
        self.game.action(
            alice, "gather", {"item": "grain", "quantity": 1}, "gather")
        self.game.action(
            alice, "store_goods", {"item": "grain", "quantity": 1}, "store")
        before = self.game.world.actors[alice]
        self.assertEqual(before.storage[GOLDMEADOW]["grain"], 1)
        self.assertIn(gear_id, before.gear_ids)
        self.game.create_checkpoint()
        self.restart()
        after = self.game.world.actors[alice]
        self.assertEqual(after.storage[GOLDMEADOW]["grain"], 1)
        self.assertEqual(after.equipped, before.equipped)
        self.assertIn(gear_id, after.gear_ids)
        self.assertEqual(self.game.world.gear[gear_id].kind, "sword")
        self.assertIn(alice, self.game.world.state.guilds[guild["id"]].members)
        self.game.world.assert_invariants()
        ledger.verify(self.game)

    def test_corrupted_checkpoint_fails_closed(self):
        alice = self.player("Alice")
        self.game.advance(alice, 1, "tick")
        self.game.create_checkpoint()
        self.game.db.execute(
            "UPDATE world_checkpoints SET payload=payload||' '")
        self.game.close()
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.game = MultiplayerGame(self.path, require_invites=False,
                                        dev_fast_forward=True)
        # The failing constructor closed its own connection.
        self.game = None

    def test_tampered_old_journal_prefix_fails_recovery(self):
        alice = self.player("Alice")
        self.game.advance(alice, 1, "tick")
        self.game.create_checkpoint()
        self.game.db.execute(
            "UPDATE world_journal SET payload='{}' WHERE kind='join'")
        self.game.close()
        with self.assertRaisesRegex(ValueError, "journal prefix checksum"):
            MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        self.game = None

    def test_failure_after_snapshot_insert_rolls_back_all_records(self):
        alice = self.player("Alice")
        self.game.create_checkpoint()
        original = checkpoint.save
        head_before = self.game.db.execute(
            "SELECT COUNT(*) FROM world_journal").fetchone()[0]
        snapshots_before = self.game.db.execute(
            "SELECT COUNT(*) FROM world_checkpoints").fetchone()[0]

        def fail_after_save(game, **kwargs):
            original(game, force=True)
            raise OSError("checkpoint storage failure")

        with patch("medieval_world_sim.web.multiplayer.checkpoint.save",
                   side_effect=fail_after_save):
            with self.assertRaisesRegex(OSError, "checkpoint storage"):
                self.game.advance(alice, 3, "failed")
        self.assertEqual(self.game.world.minute, 0)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM world_journal").fetchone()[0], head_before)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM world_checkpoints").fetchone()[0],
            snapshots_before)
        self.assertIsNone(self.game.db.execute(
            "SELECT 1 FROM durable_receipts WHERE request_id='failed'").fetchone())
        ledger.verify(self.game)
        self.restart()
        self.assertEqual(self.game.world.minute, 0)
        self.game.advance(alice, 3, "failed")
        self.assertEqual(self.game.world.minute, 3)

    def test_checkpoint_retention_is_bounded_without_pruning_receipts(self):
        alice = self.player("Alice")
        with patch("medieval_world_sim.web.checkpoint.CHECKPOINT_INTERVAL", 2):
            for i in range(6):
                self.game.advance(alice, 1, f"clock-{i}")
        saved = self.game.db.execute(
            "SELECT journal_seq FROM world_checkpoints "
            "ORDER BY journal_seq").fetchall()
        self.assertEqual(saved, [(4,), (6,)])
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM durable_receipts").fetchone()[0], 6)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM world_journal").fetchone()[0], 7)
        self.restart()
        self.assertEqual(self.game.world.minute, 6)
        ledger.verify(self.game)

    def test_automatic_checkpoint_on_interval(self):
        alice = self.player("Alice")
        with patch("medieval_world_sim.web.checkpoint.CHECKPOINT_INTERVAL", 3):
            self.game.advance(alice, 1, "first")  # journal sequence 2
            self.assertEqual(self.game.db.execute(
                "SELECT COUNT(*) FROM world_checkpoints").fetchone()[0], 0)
            self.game.advance(alice, 1, "second")  # sequence 3
        self.assertEqual(self.game.db.execute(
            "SELECT journal_seq FROM world_checkpoints").fetchone()[0], 3)
        self.restart()
        self.assertEqual(self.game.world.minute, 2)
