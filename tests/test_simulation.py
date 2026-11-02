import unittest

from medieval_world_sim.simulation import Citizen, World


class WorldTests(unittest.TestCase):
    def test_seeded_reproducibility(self):
        a = World.create(200, 42)
        b = World.create(200, 42)
        self.assertEqual([a.step() for _ in range(20)], [b.step() for _ in range(20)])

    def test_gold_is_conserved_and_no_negative_balances(self):
        world = World.create(200, 14)
        initial = world.total_gold
        for _ in range(100):
            world.step()
            self.assertEqual(world.total_gold, initial)
            self.assertGreaterEqual(world.treasury, 0)

    def test_roles_and_crafts(self):
        world = World.create(200, 42)
        counts = {role: sum(c.role == role for c in world.citizens) for role in ("farmer", "woodcutter", "miner", "blacksmith", "guard")}
        self.assertEqual(counts, {"farmer": 80, "woodcutter": 40, "miner": 40, "blacksmith": 20, "guard": 20})
        for _ in range(3):
            world.step()
        self.assertTrue(any(event.kind == "craft" for event in world.events))
        self.assertTrue(any(event.kind == "trade" for event in world.events))

    def test_no_food_without_producers(self):
        citizen = Citizen(id=1, role="guard", stock={"food": 1, "wood": 0, "iron": 0, "sword": 0})
        world = World([citizen], treasury=0)
        world.step()
        world.step()
        self.assertEqual(citizen.hungry_days, 1)

    def test_small_populations(self):
        for count in (1, 3, 5, 11, 101):
            world = World.create(count=count)
            self.assertEqual(len(world.citizens), count)
            for _ in range(5):
                world.step()

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            World.create(0)
        with self.assertRaises(ValueError):
            World([Citizen(id=1, role="farmer"), Citizen(id=1, role="miner")])
        with self.assertRaises(ValueError):
            World([], treasury=-1)


if __name__ == "__main__":
    unittest.main()
