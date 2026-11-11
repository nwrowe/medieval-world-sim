"""Interactive wilderness exploration and accelerated development journey tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from medieval_world_sim.catalog import CAPITAL, CITIES
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.core.exploration import current_hex, map_projection
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.worldgen.hexgrid import neighbors


class AdjacentExplorationTests(unittest.TestCase):
    def setUp(self):
        self.world = WorldEngine([Actor("hero", "human", city=CAPITAL)])
        self.player = self.world.actors["hero"]

    def _neighbor(self):
        x, y = current_hex(self.world, self.world.actors["hero"])
        choices = [(nx, ny) for nx, ny in neighbors(
            x, y, self.world.geography.width, self.world.geography.height)
            if self.world.geography.tile(nx, ny).elevation_m > 0
            and self.world.geography.tile(nx, ny).waterbody not in ("sea", "lake")]
        self.assertTrue(choices)
        return choices[0]

    def test_neighbor_moves_and_persistent_fog_without_city_teleport(self):
        start = current_hex(self.world, self.player)
        x, y = self._neighbor()
        known = set(self.player.explored_hexes)
        result = self.world.explore_hex("hero", x, y)
        self.assertEqual((result["x"], result["y"]), (x, y))
        self.assertEqual(current_hex(self.world, self.world.actors["hero"]), start)
        self.assertEqual(self.world.actors["hero"].travel.hex_target, (x, y))
        self.assertGreaterEqual(result["minutes"], 3)
        self.assertLessEqual(result["minutes"], 12)
        self.world.assert_invariants()
        self.world.advance(result["minutes"])
        self.assertEqual(current_hex(self.world, self.world.actors["hero"]), (x, y))
        self.assertTrue(known.issubset(self.world.actors["hero"].explored_hexes))
        self.assertEqual(map_projection(self.world, self.world.actors["hero"])["position"],
                         [x, y])
        self.world.assert_invariants()
        back = self.world.explore_hex("hero", *start)
        self.world.advance(back["minutes"])
        self.assertIsNone(self.world.actors["hero"].wilderness_hex)
        self.assertEqual(current_hex(self.world, self.world.actors["hero"]), start)
        self.assertTrue(known.issubset(self.world.actors["hero"].explored_hexes))

    def test_rejects_teleport_water_and_client_input_tricks(self):
        start = current_hex(self.world, self.player)
        x, y = self._neighbor()
        distant = next((t.x, t.y) for t in self.world.geography.tiles
                       if abs(t.x - start[0]) > 6 and t.elevation_m > 0)
        for candidate in [(True, y), (-1, y), distant, (x + 999, y)]:
            with self.assertRaises(ActionError):
                self.world.explore_hex("hero", *candidate)
        self.assertEqual(current_hex(self.world, self.world.actors["hero"]), start)

    def test_wilderness_cannot_trade_or_start_long_distance_road_journey(self):
        x, y = self._neighbor()
        trip = self.world.explore_hex("hero", x, y)
        self.world.advance(trip["minutes"])
        if self.world.actors["hero"].wilderness_hex is None:
            self.skipTest("First neighboring hex is another town")
        other = next(c for c in CITIES if c != CAPITAL)
        with self.assertRaises(ActionError):
            self.world.start_travel("hero", other)
        with self.assertRaises(ActionError):
            self.world.regional_buy("hero", "grain", 1)
        self.world.assert_invariants()

    def test_quote_is_in_snapshot_and_replayable_hex_trip_arrives_after_time(self):
        from medieval_world_sim.web.checkpoint import _encode, _decode
        actor = self.world.actors["hero"]
        target = self._neighbor()
        candidates = map_projection(self.world, actor)["steps"]
        quote = next(step for step in candidates
                     if (step["x"], step["y"]) == target)
        trip = self.world.explore_hex("hero", *target)
        self.assertEqual(quote["minutes"], trip["minutes"])
        self.assertEqual(self.world.actors["hero"].travel.hex_target, target)
        self.assertEqual(_decode(_encode(self.world.actors["hero"].travel)).hex_target, target)
        with self.assertRaises(ActionError):
            self.world.explore_hex("hero", *target)
        if trip["minutes"] > 1:
            self.world.advance(trip["minutes"] - 1)
            self.assertIsNotNone(self.world.actors["hero"].travel.hex_target)
            self.assertEqual(map_projection(self.world, self.world.actors["hero"])["steps"], [])
            self.world.advance(1)
        else:
            self.world.advance(trip["minutes"])
        self.assertIsNone(self.world.actors["hero"].travel.hex_target)
        self.assertEqual(current_hex(self.world, self.world.actors["hero"]), target)
        self.assertIn(target[1] * self.world.geography.width + target[0],
                      self.world.actors["hero"].explored_hexes)
        self.world.assert_invariants()

    def test_road_fog_progress_is_visible_in_authorized_snapshots(self):
        from medieval_world_sim.catalog import CITIES
        world = WorldEngine([Actor("hero", "human", city=CAPITAL)],
                            dev_travel_seconds=True)
        destination = min((city for city in CITIES if city != CAPITAL),
                          key=lambda city: world.estimated_travel_minutes("hero", city))
        before = map_projection(world, world.actors["hero"])
        duration = world.start_travel("hero", destination)
        self.assertGreater(duration, 1)
        world.advance(max(1, duration // 2))
        during = map_projection(world, world.actors["hero"])
        self.assertGreater(during["explored_count"], before["explored_count"])
        self.assertNotEqual(during["position"], before["position"])
        world.advance(duration - max(1, duration // 2))
        after = map_projection(world, world.actors["hero"])
        self.assertGreaterEqual(after["explored_count"], during["explored_count"])
        self.assertEqual(world.actors["hero"].city, destination)

    def test_dev_speed_trips_are_scaled_but_real_map_is_unchanged(self):
        normal = WorldEngine([Actor("hero", "human", city=CAPITAL)])
        fast = WorldEngine([Actor("hero", "human", city=CAPITAL)],
                           dev_travel_seconds=True)
        destination = next(c for c in CITIES if c != CAPITAL)
        ordinary = normal.estimated_travel_minutes("hero", destination)
        accelerated = fast.estimated_travel_minutes("hero", destination)
        self.assertEqual(accelerated, max(1, (ordinary + 59) // 60))
        self.assertEqual(fast.start_travel("hero", destination), accelerated)
        fast.advance(accelerated)
        self.assertEqual(fast.actors["hero"].city, destination)
        self.assertEqual(normal.geography, fast.geography)
        fast.assert_invariants()

    def test_multiplayer_timing_mode_is_fingerprinted_to_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "fast.sqlite"
            game = MultiplayerGame(db, dev_travel_seconds=True, npc_enabled=False,
                                   require_invites=False)
            game.close()
            with self.assertRaises(ValueError):
                MultiplayerGame(db, dev_travel_seconds=False, npc_enabled=False,
                                require_invites=False)
            game = MultiplayerGame(db, dev_travel_seconds=True, npc_enabled=False,
                                   require_invites=False)
            game.close()


if __name__ == "__main__":
    unittest.main()
