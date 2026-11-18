"""Exact cumulative six-percent passive Life recovery every five game minutes."""
import tempfile
import unittest
from pathlib import Path

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.web.session import GameSession
from medieval_world_sim.web.multiplayer import MultiplayerGame


class LifeRegenTests(unittest.TestCase):
    def test_fractional_recovery_accumulates_without_truncation_drift(self):
        world = WorldEngine([Actor("hero", "human")])
        world.actors["hero"].hp = 1
        world.advance(4)
        self.assertEqual(world.actors["hero"].hp, 1)
        world.advance(1)
        self.assertEqual(world.actors["hero"].hp, 2)
        world.advance(5)
        self.assertEqual(world.actors["hero"].hp, 3)
        world.advance(5)
        self.assertEqual(world.actors["hero"].hp, 5)
        # Splitting advances is equivalent to one contiguous advance.
        alternate = WorldEngine([Actor("hero", "human")])
        alternate.actors["hero"].hp = 1
        alternate.advance(15)
        self.assertEqual(world.actors["hero"].hp, alternate.actors["hero"].hp)

    def test_hospital_recovery_is_independent_of_release_timer(self):
        world = WorldEngine([Actor("hero", "human")])
        actor = world.actors["hero"]
        actor.hp = 0
        actor.defeated_until = world.minute + 60
        world.advance(30)
        self.assertEqual(actor.hp, (6 * actor.max_hp * 6) // 100)
        self.assertIsNotNone(actor.defeated_until)
        world.advance(30)
        self.assertIsNone(actor.defeated_until)
        self.assertLess(actor.hp, actor.max_hp)
        world.advance(100)
        self.assertEqual(actor.hp, actor.max_hp)
        world.assert_invariants()

    def test_legacy_version_three_still_uses_ten_percent_per_three_minutes(self):
        world = WorldEngine([Actor("hero", "human")])
        world.actors["hero"].hp = 3
        world._health_regen_version = 3
        world.advance(3)
        self.assertEqual(world.actors["hero"].hp, 6)

    def test_new_single_player_and_multiplayer_journal_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "solo.json"
            session = GameSession(path)
            session.create("Elda Raven")
            session.advance(5)
            self.assertEqual(session.records[-1]["ruleset"], 19)
            self.assertEqual(GameSession(path).world.minute, session.world.minute)
            db = Path(tmp) / "multi.db"
            game = MultiplayerGame(db, require_invites=False,
                                   dev_fast_forward=True, npc_enabled=False)
            try:
                token, _ = game.register_and_login(
                    "hero", "correct horse battery staple", "Hero River")
                principal = game.identity(token).actor_id
                game.advance(principal, 5, "health-v4")
                version = game.db.execute(
                    "SELECT regen_version FROM world_journal WHERE kind='advance' "
                    "ORDER BY seq DESC LIMIT 1").fetchone()
                self.assertEqual(version[0], 4)
            finally:
                game.close()
            restarted = MultiplayerGame(db, require_invites=False,
                                        dev_fast_forward=True, npc_enabled=False)
            try:
                self.assertEqual(restarted.world.minute, 5)
            finally:
                restarted.close()


if __name__ == "__main__":
    unittest.main()
