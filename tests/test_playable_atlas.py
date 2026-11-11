"""Fresh-world integration and server-authoritative exploration regressions."""
from __future__ import annotations

import json
import unittest

from medieval_world_sim.catalog import CITIES, ROADS, GEOGRAPHY, CAPITAL
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.core.exploration import (
    current_hex, map_projection, nearby_indices, public_relief, sight_radius,
)
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web import checkpoint


class PlayableAtlasTests(unittest.TestCase):
    def setUp(self):
        self.world = WorldEngine([Actor("hero", "human", city=CAPITAL)])
        self.actor = self.world.actors["hero"]

    def test_geography_is_the_runtime_catalog(self):
        world = self.world
        self.assertEqual(set(world.cities),
                         {town.id for town in GEOGRAPHY.settlements})
        self.assertEqual(set(CITIES), set(world.cities))
        self.assertEqual(len(world.cities), 12)
        self.assertEqual({tuple(sorted((r.a, r.b))) for r in GEOGRAPHY.roads},
                         set(ROADS))
        self.assertEqual({key: dict(value.deposits) for key, value in CITIES.items()},
                         {town.id: town.production for town in GEOGRAPHY.settlements})
        self.assertEqual(GEOGRAPHY.seed, 7)
        for town in GEOGRAPHY.settlements:
            self.assertEqual(world.cities[town.id].population, town.population)

    def test_new_character_starts_with_only_nearby_hexes(self):
        world, actor = self.world, self.actor
        start = world.geography_settlements[CAPITAL]
        expected = nearby_indices(world.geography, start.x, start.y, 2)
        self.assertEqual(sight_radius(world, actor), 2)
        self.assertEqual(actor.explored_hexes, expected)
        self.assertIn(CAPITAL, actor.discovered_cities)
        public = map_projection(world, actor)
        self.assertEqual(public["explored_count"], len(expected))
        self.assertEqual(len(public["relief"]), world.geography.width * world.geography.height)
        self.assertEqual(set(public["relief"]), set("01234"))
        self.assertEqual({t["i"] for t in public["tiles"]}, expected)
        self.assertTrue(all(t["visible"] for t in public["tiles"]))
        self.assertFalse({"deposits", "sites", "towns", "roads"} & set(public["relief"]))

    def test_inaccessible_information_is_not_in_client_projection(self):
        world, actor = self.world, self.actor
        public = map_projection(world, actor)
        payload = json.dumps(public)
        unseen = [town for town in world.geography.settlements
                  if town.id not in actor.discovered_cities]
        self.assertTrue(unseen)
        self.assertTrue(all(town.name not in payload for town in unseen))
        for town in public["towns"]:
            self.assertIn(town["id"], actor.discovered_cities)
        for tile in public["tiles"]:
            self.assertIn(tile["i"], actor.explored_hexes)
        for edge in public["roads"]:
            self.assertIn(edge[0], actor.explored_hexes)
            self.assertIn(edge[1], actor.explored_hexes)
        self.assertEqual(public_relief(world.geography), public["relief"])
        self.assertNotIn("iron_ore", public["relief"])
        self.assertNotIn("crownreach", public["relief"])

    def test_awareness_merits_are_ordered_and_reveal_more_tiles(self):
        world, actor = self.world, self.actor
        base = actor.explored_hexes.copy()
        with self.assertRaises(ActionError):
            world.buy_merit_upgrade("hero", "awareness_2")
        world.state.merit_balance["hero"] = 5
        world.buy_merit_upgrade("hero", "awareness_1")
        self.assertEqual(sight_radius(world, actor), 3)
        three = actor.explored_hexes.copy()
        self.assertTrue(base < three)
        self.assertEqual(world.state.merit_balance["hero"], 3)
        world.buy_merit_upgrade("hero", "awareness_2")
        self.assertEqual(sight_radius(world, actor), 4)
        self.assertTrue(three < actor.explored_hexes)
        self.assertEqual(world.state.merit_balance["hero"], 0)
        self.assertEqual(map_projection(world, actor)["sight_radius"], 4)
        self.assertTrue(base.issubset(actor.explored_hexes))

    def test_road_journey_reveals_every_crossed_hex_and_ends_at_correct_town(self):
        world, actor = self.world, self.actor
        exits = world.travel.available_destinations(actor)
        self.assertTrue(exits)
        destination = min(exits, key=lambda d: world.travel_minutes(CAPITAL, d))
        total, route = world.travel.travel_route(CAPITAL, destination)
        self.assertEqual(route[0], (world.geography_settlements[CAPITAL].x,
                                    world.geography_settlements[CAPITAL].y))
        self.assertEqual(route[-1], (world.geography_settlements[destination].x,
                                     world.geography_settlements[destination].y))
        self.assertGreater(total, 1)
        before = actor.explored_hexes.copy()
        started = world.start_travel("hero", destination)
        self.assertEqual(started, total)
        self.assertEqual(actor.travel.route_hexes, route)
        world.advance(total // 2)
        halfway = actor.explored_hexes.copy()
        self.assertTrue(before.issubset(halfway))
        self.assertGreaterEqual(len(halfway), len(before))
        self.assertIn(current_hex(world, actor)[0], range(world.geography.width))
        world.advance(started - total // 2)
        self.assertEqual(actor.city, destination)
        self.assertIsNone(actor.destination)
        self.assertFalse(actor.travel.route_hexes)
        self.assertTrue(all(y * world.geography.width + x in actor.explored_hexes
                            for x, y in route))
        self.assertTrue(halfway.issubset(actor.explored_hexes))
        self.assertIn(destination, actor.discovered_cities)
        world.assert_invariants()

    def test_partial_travel_fields_survive_checkpoint_codec(self):
        world, actor = self.world, self.actor
        dest = next(iter(world.travel.available_destinations(actor)))
        length = world.start_travel("hero", dest)
        world.advance(max(1, length // 3))
        encoded = checkpoint._encode(actor)
        decoded = checkpoint._decode(encoded)
        self.assertEqual(decoded.explored_hexes, actor.explored_hexes)
        self.assertEqual(decoded.travel.route_hexes, actor.travel.route_hexes)
        self.assertEqual(decoded.travel.departure_minute, actor.travel.departure_minute)
        self.assertEqual(decoded.travel.route_revealed_index, actor.travel.route_revealed_index)


if __name__ == "__main__":
    unittest.main()
