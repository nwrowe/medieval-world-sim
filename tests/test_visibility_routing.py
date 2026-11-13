"""Visibility-aware multi-hex travel and landmark routing tests."""
import unittest

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.core.exploration import current_hex, map_projection
from medieval_world_sim.errors import ActionError
from medieval_world_sim.worldgen.hexgrid import hex_distance


class VisibilityRoutingTests(unittest.TestCase):
    def setUp(self):
        self.world = WorldEngine([Actor("hero", "human", city=CAPITAL)])

    def test_two_hex_range_quotes_exact_crossing_costs(self):
        world = self.world
        actor = world.actors["hero"]
        start = current_hex(world, actor)
        options = [v for v in map_projection(world, actor)["steps"]
                   if hex_distance(start, (v["x"], v["y"])) == 2]
        self.assertTrue(options)
        step = options[0]
        quote, route = world.travel.plan_hex_journey(
            actor, (step["x"], step["y"]))
        self.assertEqual(quote, step["minutes"])
        self.assertEqual(quote, sum(world.travel.hex_minutes(actor, *p)
                                    for p in route[1:]))
        started = world.explore_hex("hero", step["x"], step["y"])
        self.assertEqual(started["minutes"], quote)
        first = world.actors["hero"].travel.route_durations[0]
        world.advance(first - 1)
        self.assertEqual(current_hex(world, world.actors["hero"]), route[0])
        world.advance(1)
        self.assertEqual(current_hex(world, world.actors["hero"]), route[1])
        world.advance(quote - first)
        self.assertEqual(current_hex(world, world.actors["hero"]), route[-1])
        world.assert_invariants()

    def test_discovered_city_and_site_are_reachable_from_far_away(self):
        world = self.world
        actor = world.actors["hero"]
        start = current_hex(world, actor)
        costs, _ = world.travel.terrain_routes(actor)
        towns = [s for s in world.geography.settlements
                 if s.id != CAPITAL and (s.x, s.y) in costs
                 and hex_distance(start, (s.x, s.y)) > 4]
        sites = [s for s in (*world.geography.sites, *world.geography.landmarks)
                 if (s.x, s.y) in costs
                 and hex_distance(start, (s.x, s.y)) > 4]
        self.assertTrue(towns)
        self.assertTrue(sites)
        city = min(towns, key=lambda s: costs[(s.x, s.y)])
        site = min(sites, key=lambda s: costs[(s.x, s.y)])
        with self.assertRaises(ActionError):
            world.explore_hex("hero", site.x, site.y)
        # Atomic failed actions may swap out the authoritative actor aggregate.
        actor = world.actors["hero"]
        for place in (city, site):
            actor.explored_hexes.add(place.y * world.geography.width + place.x)
        quoted = map_projection(world, actor)["steps"]
        self.assertIn(site.name, {step["label"] for step in quoted})
        self.assertIn(city.name, {step["label"] for step in quoted})
        journey = world.explore_hex("hero", site.x, site.y)
        world.advance(journey["minutes"])
        home = world.explore_hex("hero", city.x, city.y)
        world.advance(home["minutes"])
        self.assertEqual(world.actors["hero"].city, city.id)
        self.assertIsNone(world.actors["hero"].wilderness_hex)
        world.assert_invariants()


if __name__ == "__main__":
    unittest.main()
