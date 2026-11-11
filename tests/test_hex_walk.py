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
        self.assertEqual(current_hex(self.world, self.world.actors["hero"]), (x, y))
        self.assertTrue(known.issubset(self.world.actors["hero"].explored_hexes))
        self.assertEqual(map_projection(self.world, self.world.actors["hero"])["position"],
                         [x, y])
        self.world.assert_invariants()
        self.world.explore_hex("hero", *start)
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
        self.world.explore_hex("hero", x, y)
        if self.world.actors["hero"].wilderness_hex is None:
            self.skipTest("First neighboring hex is another town")
        other = next(c for c in CITIES if c != CAPITAL)
        with self.assertRaises(ActionError):
            self.world.start_travel("hero", other)
        with self.assertRaises(ActionError):
            self.world.regional_buy("hero", "grain", 1)
        self.world.assert_invariants()

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
