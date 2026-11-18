"""The authoritative command registry owns method signatures and web exposure."""
from realm_fixtures import GOLDMEADOW

import inspect
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
        self.assertGreaterEqual(len(COMMAND_SPECS), 57)
        self.assertIn("explore_hex", COMMAND_SPECS)
        for name, spec in COMMAND_SPECS.items():
            with self.subTest(command=name):
                self.assertTrue(callable(getattr(WorldEngine, spec.method, None)))
                self.assertEqual(len(spec.fields), len(set(spec.fields)))
                self.assertTrue(spec.web_modes <= {"single", "multi"})

    def test_registered_methods_accept_the_declared_command_fields(self):
        # WorldEngine.execute passes a trusted principal followed by the fields
        # in registry order. Detect drift before a player encounters a TypeError.
        for name, spec in COMMAND_SPECS.items():
            with self.subTest(command=name):
                method = getattr(WorldEngine, spec.method)
                parameters = list(inspect.signature(method).parameters.values())
                self.assertGreaterEqual(len(parameters), 2)
                self.assertEqual(parameters[0].name, "self")
                self.assertEqual(
                    len(parameters) - 2, len(spec.fields),
                    f"{name} must accept one principal plus {len(spec.fields)} fields",
                )
                self.assertTrue(all(
                    p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                               inspect.Parameter.POSITIONAL_OR_KEYWORD)
                    for p in parameters
                ), f"{name} cannot use keyword-only or variadic command arguments")

    def test_web_policies_are_derived_from_registry(self):
        self.assertEqual(UI_ACTIONS, SINGLE_PLAYER_ACTIONS)
        self.assertEqual(MULTI_ACTIONS, MULTIPLAYER_ACTIONS)
        for name in ("enroll_course", "pvp_strike"):
            self.assertNotIn(name, COMMAND_SPECS)
        for name in ("propose_trade", "accept_trade", "close_trade"):
            self.assertIn(name, MULTIPLAYER_ACTIONS)
            self.assertNotIn(name, SINGLE_PLAYER_ACTIONS)
        for name in ("found_company", "offer_job", "shift", "post_offer",
                     "accept_offer", "company_deposit_gold", "company_withdraw_goods"):
            self.assertIn(name, SINGLE_PLAYER_ACTIONS)
            self.assertIn(name, MULTIPLAYER_ACTIONS)
        for name in ("attack", "hire", "propose_job", "set_wage"):
            self.assertNotIn(name, SINGLE_PLAYER_ACTIONS)
            self.assertNotIn(name, MULTIPLAYER_ACTIONS)

    def test_registry_is_immutable(self):
        with self.assertRaises(TypeError):
            COMMAND_SPECS["new_action"] = COMMAND_SPECS["travel"]
        with self.assertRaises(FrozenInstanceError):
            COMMAND_SPECS["travel"].method = "gather"

    def test_execute_preserves_validation_and_deduplication(self):
        world = WorldEngine([Actor("hero", "human", city=GOLDMEADOW)])
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
