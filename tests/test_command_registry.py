"""The authoritative command registry owns method signatures and web exposure."""
import unittest
from dataclasses import FrozenInstanceError

from medieval_world_sim.core.commands import (
    COMMAND_SPECS, MULTIPLAYER_ACTIONS, SINGLE_PLAYER_ACTIONS,
)
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.multiplayer import MULTI_ACTIONS
from medieval_world_sim.web.session import UI_ACTIONS


class CommandRegistryTests(unittest.TestCase):
    def test_all_registry_targets_exist_and_fields_are_unambiguous(self):
        self.assertEqual(len(COMMAND_SPECS), 55)
        for name, spec in COMMAND_SPECS.items():
            with self.subTest(command=name):
                self.assertTrue(callable(getattr(WorldEngine, spec.method, None)))
                self.assertEqual(len(spec.fields), len(set(spec.fields)))
                self.assertTrue(spec.web_modes <= {"single", "multi"})

    def test_web_policies_are_derived_from_registry(self):
        self.assertEqual(UI_ACTIONS, SINGLE_PLAYER_ACTIONS)
        self.assertEqual(MULTI_ACTIONS, MULTIPLAYER_ACTIONS)
        self.assertIn("enroll_course", SINGLE_PLAYER_ACTIONS)  # historic replay
        self.assertNotIn("enroll_course", MULTIPLAYER_ACTIONS)
        for name in ("propose_trade", "accept_trade", "close_trade", "pvp_strike"):
            self.assertIn(name, MULTIPLAYER_ACTIONS)
            self.assertNotIn(name, SINGLE_PLAYER_ACTIONS)
        for name in ("found_company", "attack", "hire"):
            self.assertNotIn(name, SINGLE_PLAYER_ACTIONS)
            self.assertNotIn(name, MULTIPLAYER_ACTIONS)

    def test_registry_is_immutable(self):
        with self.assertRaises(TypeError):
            COMMAND_SPECS["new_action"] = COMMAND_SPECS["travel"]
        with self.assertRaises(FrozenInstanceError):
            COMMAND_SPECS["travel"].method = "gather"

    def test_execute_preserves_validation_and_deduplication(self):
        world = WorldEngine([Actor("hero", "human", city="goldmeadow")])
        with self.assertRaisesRegex(ActionError, "parameter mismatch"):
            world.execute("hero", "gather", {"item": "grain"}, "bad")
        with self.assertRaisesRegex(ActionError, "Unknown or forbidden"):
            world.execute("hero", "arbitrary_method", {}, "invalid")
        first = world.execute("hero", "gather", {"item": "grain", "quantity": 1}, "once")
        second = world.execute("hero", "gather", {"item": "grain", "quantity": 1}, "once")
        self.assertEqual(first, second)
        self.assertEqual(world.actors["hero"].inventory["grain"], 1)


if __name__ == "__main__":
    unittest.main()
