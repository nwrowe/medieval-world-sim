"""Regression tests for real-time clock, healing and disconnect polish."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web.server import GameHandler
from medieval_world_sim.web.session import GameSession


class HealthRecoveryTests(unittest.TestCase):
    def test_ten_percent_of_max_health_every_three_minutes(self):
        world = WorldEngine([Actor("hero", "human")])
        hero = world.actors["hero"]
        hero.hp = 1
        world.advance(2)
        self.assertEqual(hero.hp, 1)
        world.advance(1)
        self.assertEqual(hero.hp, 4)  # ceil(24 / 10) = 3
        world.advance(6)
        self.assertEqual(hero.hp, 10)
        world.advance(30)
        self.assertEqual(hero.hp, hero.max_hp)

    def test_legacy_health_journal_rule_and_hospitalization(self):
        world = WorldEngine([Actor("hero", "human")])
        hero = world.actors["hero"]
        hero.hp = 2
        world._health_regen_version = 1
        world.advance(10)
        self.assertEqual(hero.hp, 3)  # historic +1 / 10 minutes
        world._health_regen_version = 2
        hero.hp = 0
        hero.defeated_until = world.minute + 7
        world.advance(3)
        self.assertEqual(hero.hp, 0)
        world.advance(4)
        self.assertEqual(hero.hp, hero.max_hp)

    def test_single_player_records_new_recovery_ruleset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.json"
            game = GameSession(path)
            game.create("Local Hero")
            game.advance(3)
            self.assertEqual(game.records[-1]["ruleset"], 12)
            self.assertEqual(GameSession(path).snapshot(), game.snapshot())

    def test_multiplayer_journal_versions_new_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "multi.sqlite3"
            game = MultiplayerGame(path, require_invites=False, dev_fast_forward=True)
            actor = game.register("alice", "correct horse battery staple", "Alice River")
            game.advance(actor, 3, "three-minutes")
            self.assertEqual(game.db.execute(
                "SELECT regen_version FROM world_journal WHERE request_id=?",
                ("three-minutes",)).fetchone()[0], 2)
            game.close()
            game = MultiplayerGame(path, require_invites=False, dev_fast_forward=True)
            self.assertEqual(game.snapshot(actor)["minute"], 3)
            game.close()

    def test_multiplayer_reports_subminute_clock_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clock.sqlite3"
            start = 1_700_000_000
            with patch("medieval_world_sim.web.multiplayer.time.time", return_value=start):
                game = MultiplayerGame(path, require_invites=False)
                actor = game.register("alice", "correct horse battery staple", "Alice River")
            with patch("medieval_world_sim.web.multiplayer.time.time", return_value=start + 75):
                snapshot = game.snapshot(actor)
                self.assertEqual(snapshot["minute"], 1)
                self.assertEqual(snapshot["next_world_tick_seconds"], 45)
                social = game.social_snapshot(actor)
                self.assertEqual(social["next_world_tick_seconds"], 45)
            game.close()


class ClientDisconnectTests(unittest.TestCase):
    def test_aborted_write_does_not_attempt_error_response(self):
        # An aborted browser request can occur after its action committed.
        # Writing a second 500 response to that socket is never meaningful.
        handler = object.__new__(GameHandler)
        handler.server = SimpleNamespace(colab_preview=False)
        handler.close_connection = False
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = SimpleNamespace(
            write=Mock(side_effect=ConnectionAbortedError("browser closed")))
        handler._json(200, {"ok": True})
        self.assertTrue(handler.close_connection)
        self.assertEqual(handler.send_response.call_count, 1)
        self.assertEqual(handler.wfile.write.call_count, 1)


if __name__ == "__main__":
    unittest.main()
