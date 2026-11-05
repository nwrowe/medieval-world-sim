"""World integrity checks are owned separately from gameplay mutations."""
import unittest

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.core.invariants import validate_world


class WorldValidationTests(unittest.TestCase):
    def setUp(self):
        self.world = WorldEngine([Actor("hero", "human", city="goldmeadow")])

    def test_validation_entrypoints_are_equivalent(self):
        self.assertIsNone(validate_world(self.world))
        self.assertIsNone(self.world.assert_invariants())

    def test_gold_conservation_still_rejects_minting(self):
        self.world.actors["hero"].gold += 1
        with self.assertRaisesRegex(AssertionError, "Gold was created"):
            self.world.assert_invariants()
        with self.assertRaisesRegex(AssertionError, "Gold was created"):
            validate_world(self.world)

    def test_corrupted_health_and_inventory_are_rejected(self):
        actor = self.world.actors["hero"]
        actor.hp = -1
        with self.assertRaisesRegex(AssertionError, "Invalid combat"):
            self.world.assert_invariants()
        actor.hp = actor.max_hp
        actor.inventory["not-a-real-resource"] = 3
        with self.assertRaisesRegex(AssertionError, "Negative or invalid asset"):
            self.world.assert_invariants()


if __name__ == "__main__":
    unittest.main()
