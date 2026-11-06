"""Live NPC world and noncombat character progression regressions.

No external model, network server, mock NPC privileges or sleep necessary.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web import ledger
from medieval_world_sim.web.multiplayer import MultiplayerGame, AuthError
from medieval_world_sim.web.npc_runtime import (
    NPC_ACTIONS, MAX_ACTIONS_PER_ADVANCE, _pack_memory, _unpack_memory,
)


class MagicCharacterProgressionTests(TestCase):
    def test_magic_training_earns_level_xp_without_fabricating_combat_xp(self):
        world = WorldEngine([Actor("mage", "human", gold=240)], seed=42)
        node = "restoration.soothe_wounds"
        world.unlock_magic("mage", node)
        current_level = world.actors["mage"].level
        earned = 0
        for idx in range(12):
            result = world.execute(
                "mage", "practice_magic", {"node_id": node}, f"practice-{idx}")
            self.assertEqual(result.level_xp_gained,
                             max(1, result.xp_gained // 2))
            earned += result.level_xp_gained
            world.advance(120)
        actor = world.actors["mage"]
        self.assertGreater(earned, 0)
        self.assertGreater(actor.level, current_level)
        self.assertEqual(actor.combat_xp, 0)
        self.assertEqual(actor.max_hp, 24 + (actor.level - 1) * 4)
        self.assertEqual(actor.strength, actor.level)
        self.assertEqual(actor.defense, actor.level)
        self.assertEqual(world.initial_gold, world.total_gold)
        world.assert_invariants()

    def test_prechange_magic_commands_preserve_old_leveling_rule(self):
        world = WorldEngine([Actor("mage", "human")], seed=42)
        world.unlock_magic("mage", "restoration.soothe_wounds")
        world._legacy_magic_leveling_rules = True
        try:
            old = world.practice_magic("mage", "restoration.soothe_wounds")
        finally:
            world._legacy_magic_leveling_rules = False
        self.assertGreater(old.xp_gained, 0)
        self.assertEqual(old.level_xp_gained, 0)
        self.assertEqual(world.actors["mage"].level_xp, 0)
        world.assert_invariants()


class PersistentNPCAutonomyTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "npc-live.sqlite3"
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True, npc_enabled=True)
        self.player = self.game.register(
            "npcwatcher", "secure test password", "Watcher Reed")

    def tearDown(self):
        if self.game is not None:
            self.game.close()
        self.temp.cleanup()

    def restart(self, npc_enabled=True):
        self.game.close()
        self.game = MultiplayerGame(
            self.path, require_invites=False, dev_fast_forward=True,
            npc_enabled=npc_enabled)

    def _advance(self, minutes: int, name: str) -> None:
        self.assertIsNone(self.game.advance(self.player, minutes, name))

    def test_real_npcs_act_and_journal_replay_reproduces_world(self):
        self._advance(6, "first-clock")
        rows = self.game.db.execute(
            "SELECT journal_seq,payload FROM npc_steps ORDER BY journal_seq"
        ).fetchall()
        self.assertTrue(rows)
        import json
        actions = json.loads(rows[0][1])
        self.assertTrue(1 <= len(actions) <= MAX_ACTIONS_PER_ADVANCE)
        self.assertTrue(all(action["name"] in NPC_ACTIONS for action in actions))
        self.assertTrue(all(action["id"].startswith("npc:") for action in actions))
        self.assertTrue(all(self.game.world.actors[action["id"]].kind == "npc"
                            for action in actions))
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM accounts").fetchone()[0], 1)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM npc_runtime").fetchone()[0], 3)
        self.assertEqual(self.game.world.total_gold, self.game.world.initial_gold)
        ledger.verify(self.game)
        original = ledger.current_rows(self.game.world)
        original_actors = {
            key: (actor.city, actor.gold, actor.level,
                  dict(actor.inventory), tuple(actor.gear_ids))
            for key, actor in self.game.world.actors.items()
            if actor.kind == "npc"}
        due = dict(self.game._npc_due)
        memories = {key: memory.decision_count
                    for key, memory in self.game._npc_memories.items()}
        self.restart()
        self.assertEqual(ledger.current_rows(self.game.world), original)
        self.assertEqual({
            key: (actor.city, actor.gold, actor.level,
                  dict(actor.inventory), tuple(actor.gear_ids))
            for key, actor in self.game.world.actors.items()
            if actor.kind == "npc"}, original_actors)
        self.assertEqual(self.game._npc_due, due)
        self.assertEqual({key: m.decision_count
                          for key, m in self.game._npc_memories.items()},
                         memories)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM accounts").fetchone()[0], 1)
        self.game.create_checkpoint()
        self._advance(6, "second-clock")
        post_checkpoint = ledger.current_rows(self.game.world)
        self.restart()
        self.assertEqual(ledger.current_rows(self.game.world), post_checkpoint)
        self.game.world.assert_invariants()

    def test_paused_controller_preserves_existing_npc_action_history(self):
        self._advance(6, "active")
        expected = ledger.current_rows(self.game.world)
        self.restart(npc_enabled=False)
        self.assertEqual(ledger.current_rows(self.game.world), expected)
        self._advance(1440, "paused")
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM npc_steps").fetchone()[0], 1)
        self.restart(npc_enabled=True)
        self.assertEqual(self.game.world.minute, 1446)
        self._advance(60, "resumed")
        self.assertGreater(self.game.db.execute(
            "SELECT COUNT(*) FROM npc_steps").fetchone()[0], 1)

    def test_failed_commit_rolls_back_npc_gold_memory_and_scheduler(self):
        before = ledger.current_rows(self.game.world)
        due = dict(self.game._npc_due)
        memory = {key: m.decision_count
                  for key, m in self.game._npc_memories.items()}
        with patch("medieval_world_sim.web.multiplayer.ledger.persist",
                   side_effect=OSError("disk error")):
            with self.assertRaisesRegex(OSError, "disk error"):
                self.game.advance(self.player, 6, "failed-clock")
        self.assertEqual(ledger.current_rows(self.game.world), before)
        self.assertEqual(self.game.world.minute, 0)
        self.assertEqual(self.game._npc_due, due)
        self.assertEqual({key: m.decision_count
                          for key, m in self.game._npc_memories.items()},
                         memory)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM npc_steps").fetchone()[0], 0)
        self._advance(6, "failed-clock")
        self.assertTrue(self.game.db.execute(
            "SELECT 1 FROM npc_steps").fetchone())

    def test_player_cannot_issue_npc_commands_or_mutate_npc_account(self):
        target = next(key for key, actor in self.game.world.actors.items()
                      if actor.kind == "npc")
        with self.assertRaises(AuthError):
            self.game.action(target, "travel",
                             {"destination": "ironvale"}, "impersonation")
        with self.assertRaises(ActionError):
            self.game.action(self.player, "attack",
                             {"defender_id": target}, "private-command")
        with self.assertRaises(ActionError):
            self.game.action(self.player, "npc_step",
                             {"actor_id": target}, "private-step")
        with self.assertRaises(ActionError):
            self.game.action(self.player, "regional_sell",
                             {"item": "iron_ore", "quantity": 1,
                              "actor_id": target}, "extraneous-actor")

    def test_multi_seeded_advances_are_bounded_and_keep_human_safe(self):
        for i in range(20):
            self._advance(120, f"tick-{i}")
        batches = self.game.db.execute(
            "SELECT payload FROM npc_steps").fetchall()
        import json
        commands = [row for (payload,) in batches for row in json.loads(payload)]
        self.assertTrue(commands)
        self.assertTrue(all(row["name"] in NPC_ACTIONS for row in commands))
        for row in commands:
            if row["name"] == "attack":
                self.assertEqual(self.game.world.actors[
                    row["params"]["defender_id"]].kind, "npc")
        self.assertEqual(self.game.world.total_gold, self.game.world.initial_gold)
        self.game.world.assert_invariants()
        ledger.verify(self.game)

    def test_trusted_server_clock_advances_npcs_without_a_browser_request(self):
        secure_path = Path(self.temp.name) / "secure-clock.sqlite3"
        game = MultiplayerGame(secure_path, require_invites=False,
                               dev_fast_forward=False, npc_enabled=True)
        try:
            game.register("clocktest", "secure test password", "Clock Keeper")
            anchor = game._clock_anchor
            with patch("medieval_world_sim.web.multiplayer.time.time",
                       return_value=anchor + 120):
                game._tick_world_clock()
            self.assertEqual(game.world.minute, 2)
            self.assertEqual(game.db.execute(
                "SELECT COUNT(*) FROM npc_steps").fetchone()[0], 1)
            self.assertEqual(game.db.execute(
                "SELECT COUNT(*) FROM accounts").fetchone()[0], 1)
            ledger.verify(game)
        finally:
            game.close()

    def test_hired_npc_uses_worker_policy_not_old_profession(self):
        from types import SimpleNamespace
        from medieval_world_sim.core.entities import Company, Wage
        from medieval_world_sim.web.npc_runtime import _assigned_profile
        profile = next(p for p in self.game._npc_profiles
                       if p.role == "hauler")
        company = Company("human-forge", self.player, "forge")
        company.employees[profile.id] = Wage(gold=3)
        game_view = SimpleNamespace(world=SimpleNamespace(
            companies={company.id: company}))
        assigned = _assigned_profile(game_view, profile)
        self.assertEqual(assigned.role, "worker")
        self.assertEqual(assigned.company_id, company.id)
        company.employees.clear()
        self.assertEqual(_assigned_profile(game_view, profile).role, "hauler")

    def test_npc_memory_encoding_is_bounded_and_rejects_corruption(self):
        memory = self.game._npc_memories[next(iter(self.game._npc_memories))]
        self.assertEqual(_unpack_memory(_pack_memory(memory)).decision_count, 0)
        with self.assertRaises(ValueError):
            _unpack_memory('{"version":999}')
        with self.assertRaises(ValueError):
            _unpack_memory("X" * 30000)

    def test_multiplayer_magic_level_xp_is_durable_and_retry_idempotent(self):
        self.game.action(self.player, "unlock_magic", {
            "node_id": "restoration.soothe_wounds"}, "unlock")
        result = self.game.action(self.player, "practice_magic", {
            "node_id": "restoration.soothe_wounds"}, "practice")
        self.assertGreater(result["level_xp_gained"], 0)
        earned = self.game.world.actors[self.player].level_xp
        self.assertEqual(self.game.action(self.player, "practice_magic", {
            "node_id": "restoration.soothe_wounds"}, "practice"), result)
        self.assertEqual(self.game.world.actors[self.player].level_xp, earned)
        self.restart()
        self.assertEqual(self.game.world.actors[self.player].level_xp, earned)
        self.assertEqual(self.game.db.execute(
            "SELECT xp_version FROM world_journal WHERE request_id='practice'"
        ).fetchone()[0], 4)
        ledger.verify(self.game)


if __name__ == "__main__":
    import unittest
    unittest.main()
