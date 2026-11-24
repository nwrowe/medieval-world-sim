"""Five sequential Renown ranks with cumulative effects."""
import unittest
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.core.exploration import sight_radius
from medieval_world_sim.errors import ActionError
from medieval_world_sim.systems.merits import perk_level, roadcraft_minutes


class RenownTracksTest(unittest.TestCase):
    def test_levels_cost_prerequisites_and_effects(self):
        world = WorldEngine([Actor("hero", "human")])
        actor = world.actors["hero"]
        system = world.merit_system
        world.state.merit_balance["hero"] = 45
        for track in ("awareness", "roadcraft", "horsemanship"):
            with self.assertRaises(ActionError):
                system.purchase("hero", f"{track}_2")
            for level in range(1, 6):
                result = system.purchase("hero", f"{track}_{level}")
                self.assertEqual(result["cost"], level)
                owned = world.state.merit_upgrades["hero"]
                self.assertEqual(perk_level(owned, track), level)
                if track == "awareness":
                    self.assertEqual(sight_radius(world, actor), 2 + level)
                if track == "roadcraft":
                    self.assertEqual(roadcraft_minutes(100, owned), 100 - 5 * level)
            with self.assertRaises(ActionError):
                system.purchase("hero", f"{track}_5")
            with self.assertRaises(ActionError):
                system.purchase("hero", f"{track}_6")
        self.assertEqual(world.state.merit_balance["hero"], 0)
        self.assertTrue(all(row["level"] == 5 and row["next_id"] is None
                            for row in system.view("hero")["upgrades"]))
