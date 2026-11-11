"""Authoritative exploration completion thresholds and map safety."""
import json
import math
import unittest

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.core.exploration import current_hex, map_projection
from medieval_world_sim.errors import ActionError
from medieval_world_sim.worldgen.hexgrid import hex_distance


class CartographyMeritTests(unittest.TestCase):
    def setUp(self):
        self.world = WorldEngine([Actor("hero", "human", city=CAPITAL)])

    def test_percent_is_consistent_with_recorded_hexes(self):
        view = map_projection(self.world, self.world.actors["hero"])
        self.assertEqual(view["total_hexes"], 5120)
        self.assertEqual(view["explored_percent"],
                         round(view["explored_count"] * 100 / 5120, 1))

    def test_four_achievements_claim_once_at_exact_threshold(self):
        world = self.world
        count = len(world.geography.tiles)
        for percentage in (25, 50, 75, 100):
            threshold = math.ceil(count * percentage / 100)
            key = f"explore_{percentage}"
            world.actors["hero"].explored_hexes = set(range(threshold - 1))
            self.assertFalse(world.merit_system.earned("hero", key))
            world.actors["hero"].explored_hexes = set(range(threshold))
            self.assertTrue(world.merit_system.earned("hero", key))
            self.assertEqual(world.claim_merit("hero", key)["awarded"], 1)
            with self.assertRaises(ActionError):
                world.claim_merit("hero", key)
        self.assertEqual(world.state.merit_balance["hero"], 4)

    def test_far_unexplored_landmark_is_not_in_private_quotes(self):
        world = self.world
        actor = world.actors["hero"]
        start = current_hex(world, actor)
        site = next(site for site in world.geography.sites
                    if hex_distance(start, (site.x, site.y)) > 8)
        view = map_projection(world, actor)
        self.assertNotIn(site.name, json.dumps(view))
        self.assertNotIn((site.x, site.y),
                         {(v["x"], v["y"]) for v in view["steps"]})


if __name__ == "__main__":
    unittest.main()
