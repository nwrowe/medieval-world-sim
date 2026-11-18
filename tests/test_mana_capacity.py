"""Small initial mana pool, earned growth and replay of live playtest worlds."""
import json
import tempfile
import unittest
from pathlib import Path

from medieval_world_sim.content.magic_tree import (
    STARTING_MANA, MAX_MANA, MANA_PER_LEVEL, MAGIC_XP_PER_MANA,
)
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.systems.magic import earned_mana_capacity
from medieval_world_sim.web.session import GameSession, PLAYER_ID
from medieval_world_sim.web.multiplayer import MultiplayerGame


class ManaGrowthTests(unittest.TestCase):
    def test_new_character_has_ten_mana(self):
        w = WorldEngine([Actor("mage", "human")])
        actor = w.actors["mage"]
        self.assertEqual((actor.magic.mana, actor.magic.max_mana),
                         (STARTING_MANA, STARTING_MANA))
        self.assertEqual(STARTING_MANA, 10)
        self.assertEqual(MAX_MANA, 100)
        self.assertEqual(MANA_PER_LEVEL, 2)
        self.assertEqual(MAGIC_XP_PER_MANA, 20)
        w.assert_invariants()

    def test_leveling_increases_capacity_without_refilling_everything(self):
        w = WorldEngine([Actor("mage", "human")])
        actor = w.actors["mage"]
        actor.magic.mana = 3
        self.assertEqual(w.combat._award_level_xp(actor, 10), 1)
        self.assertEqual(actor.level, 2)
        self.assertEqual(actor.magic.max_mana, 12)
        self.assertEqual(actor.magic.mana, 5)
        w.assert_invariants()

    def test_magic_training_earns_capacity_and_replays_deterministically(self):
        w = WorldEngine([Actor("mage", "human")])
        w.unlock_magic("mage", "restoration.soothe_wounds")
        actor = w.actors["mage"]
        for i in range(20):
            if actor.magic.mana < 8:
                w.advance(80)
            w.execute("mage", "practice_magic",
                      {"node_id": "restoration.soothe_wounds"}, f"train-{i}")
            self.assertEqual(actor.magic.max_mana, earned_mana_capacity(actor))
        self.assertEqual(actor.magic.school_xp["restoration"], 20)
        self.assertGreater(actor.magic.max_mana, 10)
        self.assertEqual(
            w.execute("mage", "practice_magic",
                      {"node_id": "restoration.soothe_wounds"}, "train-19").school_xp,
            20)
        w.assert_invariants()

    def test_singleplayer_new_and_old_save_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "single.json"
            game = GameSession(path)
            game.create("Mage Scout")
            self.assertEqual(game.world.actors[PLAYER_ID].magic.max_mana, 10)
            self.assertEqual(GameSession(path).world.actors[PLAYER_ID].magic.max_mana, 10)

            # Model a save written before this update: no start_mana key,
            # character and NPCs began with 100. Preserve the old journal.
            game.start_mana = 100
            for actor in game.world.actors.values():
                actor.magic.max_mana = 100
                actor.magic.mana = 100
            game.action("unlock_magic",
                        {"node_id": "restoration.soothe_wounds"}, "unlock-before")
            for i in range(2):
                game.action("practice_magic",
                            {"node_id": "restoration.soothe_wounds"}, f"practice-before-{i}")
            old_snapshot = game.snapshot()
            document = json.loads(path.read_text())
            document.pop("start_mana")
            path.write_text(json.dumps(document))
            restored = GameSession(path)
            self.assertEqual(restored.world.actors[PLAYER_ID].magic.max_mana, 100)
            self.assertEqual(restored.snapshot()["player"]["mana"],
                             old_snapshot["player"]["mana"])
            self.assertEqual(restored.world.actors[PLAYER_ID].magic.school_xp,
                             game.world.actors[PLAYER_ID].magic.school_xp)
            restored.world.assert_invariants()

    def test_multiplayer_new_accounts_recover_at_ten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "multi.sqlite"
            game = MultiplayerGame(path, require_invites=False,
                                   dev_fast_forward=True, npc_enabled=False)
            try:
                actor_id = game.register("freshmage", "correct horse battery staple",
                                         "Fresh Mage")
                self.assertEqual(game.world.actors[actor_id].magic.max_mana, 10)
            finally:
                game.close()
            replay = MultiplayerGame(path, require_invites=False,
                                     dev_fast_forward=True, npc_enabled=False)
            try:
                self.assertEqual(replay.world.actors[actor_id].magic.max_mana, 10)
                replay.world.assert_invariants()
            finally:
                replay.close()

    def test_multiplayer_old_join_payload_replays_at_original_capacity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old-multi.sqlite"
            game = MultiplayerGame(path, require_invites=False,
                                   dev_fast_forward=True, npc_enabled=False)
            try:
                actor_id = game.register("oldmage", "correct horse battery staple",
                                         "Old Mage")
                row = game.db.execute(
                    "SELECT seq,payload FROM world_journal WHERE kind='join'"
                ).fetchone()
                payload = json.loads(row[1])
                payload.pop("start_mana")
                game.db.execute("UPDATE world_journal SET payload=? WHERE seq=?",
                                (json.dumps(payload), row[0]))
                # Emulate the corresponding pre-change live state.
                for actor in game.world.actors.values():
                    actor.magic.max_mana = 100
                    actor.magic.mana = 100
            finally:
                game.close()
            replay = MultiplayerGame(path, require_invites=False,
                                     dev_fast_forward=True, npc_enabled=False)
            try:
                self.assertEqual(replay.world.actors[actor_id].magic.max_mana, 100)
                self.assertTrue(all(
                    a.magic.max_mana == 100
                    for a in replay.world.actors.values() if a.kind == "npc"))
                replay.world.assert_invariants()
            finally:
                replay.close()


if __name__ == "__main__":
    unittest.main()
