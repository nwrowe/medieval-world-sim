"""Opening an attack screen should not be a committed combat action.

The browser preview has no command; the first physical swing combines
start and turn in a single authorized transaction.
"""
import unittest

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.core.commands import COMMAND_SPECS
from medieval_world_sim.web.projection import world_snapshot


class CombatPreviewTests(unittest.TestCase):
    def setUp(self):
        self.world = WorldEngine([
            Actor("attacker", "human", city=CAPITAL),
            Actor("defender", "human", city=CAPITAL),
        ])

    def test_opening_preview_is_not_a_command(self):
        self.assertIn("engage_duel", COMMAND_SPECS)
        self.assertEqual(COMMAND_SPECS["engage_duel"].fields,
                         ("defender_id", "move"))
        self.assertFalse(self.world.state.duels)
        self.assertFalse(self.world.events)

    def test_first_physical_swing_commits_duel_and_turn_atomically(self):
        before = self.world.actors["attacker"].stamina
        outcome = self.world.execute("attacker", "engage_duel",
                                     {"defender_id": "defender", "move": "fists"},
                                     "first-swing")
        self.assertEqual(outcome["round"], 1)
        self.assertEqual(outcome["outcome"], "ongoing")
        duel = self.world.state.duels["attacker"]
        self.assertTrue(duel.first_attack)
        self.assertEqual(duel.round, 1)
        self.assertLess(self.world.actors["attacker"].stamina, before)
        self.assertIn("duel_started", [e.kind for e in self.world.events])
        self.assertIn("duel_round", [e.kind for e in self.world.events])
        self.assertEqual(self.world.execute(
            "attacker", "engage_duel",
            {"defender_id": "defender", "move": "fists"},
            "first-swing"), outcome)
        self.world.assert_invariants()

    def test_public_duel_report_uses_display_names_not_actor_ids(self):
        self.world.engage_duel("attacker", "defender", "fists")
        self.world._flee_success = True
        self.world.flee_duel("attacker")
        snap = world_snapshot(self.world, "attacker", "Alden River", {},
                              {"attacker": "Alden River", "defender": "Bryn Stone"},
                              {}, True)
        lines = snap["last_duel"]["log"]
        self.assertTrue(any("Alden River" in line for line in lines))
        self.assertFalse(any("attacker" in line or "defender" in line
                             for line in lines))

    def test_single_and_multi_new_duel_commands_replay_after_restart(self):
        import tempfile
        from pathlib import Path
        from medieval_world_sim.web.session import GameSession
        from medieval_world_sim.web.multiplayer import MultiplayerGame
        with tempfile.TemporaryDirectory() as tmp:
            solo = Path(tmp) / "solo.json"
            session = GameSession(solo)
            session.create("Alden River")
            foe = next(u for u in session.snapshot()["users"] if u["can_attack"])
            one = session.action("engage_duel",
                                 {"defender_id": foe["id"], "move": "fists"}, "opening")
            self.assertEqual(one["outcome"], "ongoing")
            self.assertNotIn("ruleset", session.records[-1])
            self.assertEqual(GameSession(solo).snapshot(), session.snapshot())
            db = Path(tmp) / "multi.db"
            world = MultiplayerGame(db, require_invites=False,
                                    npc_enabled=False, dev_fast_forward=True)
            try:
                first = world.register("alden", "correct horse battery staple",
                                       "Alden River")
                second = world.register("bryn", "correct horse battery staple",
                                        "Bryn Stone")
                world.action(first, "engage_duel",
                             {"defender_id": second, "move": "fists"}, "open")
                before = world.snapshot(first)
                columns = {row[1] for row in world.db.execute(
                    "PRAGMA table_info(world_journal)")}
                self.assertNotIn("xp_version", columns)
            finally:
                world.close()
            world = MultiplayerGame(db, require_invites=False,
                                    npc_enabled=False, dev_fast_forward=True)
            try:
                self.assertEqual(world.snapshot(first), before)
            finally:
                world.close()

    def test_invalid_opening_move_and_failed_swing_roll_back_everything(self):
        for move in ("guard", "cast", "flee", ""):
            with self.assertRaises(ActionError):
                self.world.execute("attacker", "engage_duel",
                                   {"defender_id": "defender", "move": move},
                                   "invalid-" + move)
            self.assertFalse(self.world.state.duels)
            self.assertFalse(self.world.events)
        self.world.actors["attacker"].stamina = 0
        with self.assertRaises(ActionError):
            self.world.execute("attacker", "engage_duel",
                               {"defender_id": "defender", "move": "fists"},
                               "no-stamina")
        self.assertFalse(self.world.state.duels)
        self.assertFalse(self.world.events)
        self.assertEqual(self.world.actors["attacker"].stamina, 0)
        self.world.assert_invariants()


if __name__ == "__main__":
    unittest.main()
