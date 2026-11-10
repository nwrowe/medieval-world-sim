"""World-generator invariants. No live-world data is changed by generation."""
import unittest

from medieval_world_sim.worldgen import generate_world
from medieval_world_sim.worldgen.render import render_svg
from medieval_world_sim.worldgen.terrain import RESOURCE_KEYS


class WorldGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = generate_world(seed=42, width=64, height=44, cities=9, sites=25)

    def test_deterministic_and_seed_sensitive(self):
        a = self.world
        b = generate_world(seed=42, width=64, height=44, cities=9, sites=25)
        c = generate_world(seed=43, width=64, height=44, cities=9, sites=25)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertNotEqual(a.tiles, c.tiles)
        self.assertEqual(a.version, 2)

    def test_terrain_dimensions_climate_and_river_network(self):
        world = self.world
        self.assertEqual(len(world.tiles), world.width * world.height)
        self.assertTrue(any(t.biome == 'ocean' for t in world.tiles))
        self.assertTrue(any(t.biome == 'mountain' or t.biome == 'alpine' for t in world.tiles))
        self.assertTrue(any(t.river for t in world.tiles))
        self.assertTrue(any(t.rainfall_mm != world.tiles[0].rainfall_mm for t in world.tiles))
        for t in world.tiles:
            self.assertTrue(all(k in RESOURCE_KEYS and 0 <= v <= 100 for k, v in t.resources.items()))
            if t.elevation_m < 0:
                self.assertEqual(t.resources, {})

    def test_city_placement_production_is_local_and_crownreach_selected(self):
        w = self.world
        self.assertEqual(w.settlements[0].id, 'crownreach')
        self.assertEqual(len({(s.x, s.y) for s in w.settlements}), len(w.settlements))
        self.assertEqual(len({s.name for s in w.settlements}), len(w.settlements))
        for s in w.settlements:            self.assertGreater(w.tile(s.x, s.y).elevation_m, 0)
            self.assertGreater(s.population, 0)
            self.assertTrue(s.production)
            for good in s.production:
                self.assertTrue(any(t.resources.get(good, 0) > 0
                                    for t in w.tiles if abs(t.x - s.x) <= 5 and abs(t.y - s.y) <= 5))

    def test_road_network_connected_with_walkable_paths(self):
        w = self.world
        cities = {s.id for s in w.settlements}
        graph = {k: set() for k in cities}
        for road in w.roads:
            graph[road.a].add(road.b)
            graph[road.b].add(road.a)
            self.assertGreater(road.travel_minutes, 0)
            self.assertGreater(road.distance_km, 0)
            for x, y in road.path:
                self.assertGreater(w.tile(x, y).elevation_m, 0)
            for (x, y), (nx, ny) in zip(road.path, road.path[1:]):
                self.assertLessEqual(max(abs(nx - x), abs(ny - y)), 1)
        frontier, seen = ['crownreach'], set()
        while frontier:
            city = frontier.pop()
            if city not in seen:
                seen.add(city)
                frontier.extend(graph[city] - seen)
        self.assertEqual(seen, cities)
        self.assertGreaterEqual(len(w.roads), len(w.settlements) - 1)

    def test_sites_follow_geology_biomes_or_trade_roads(self):
        w = self.world
        self.assertEqual(len(w.sites), 25)
        road_points = {pt for road in w.roads for pt in road.path}
        for site in w.sites:
            tile = w.tile(site.x, site.y)
            self.assertGreater(tile.elevation_m, 0)
            self.assertTrue(1 <= site.danger <= 10)
            self.assertGreaterEqual(min(((site.x-s.x)**2+(site.y-s.y)**2)**.5
                                        for s in w.settlements), 3)
            if site.kind == 'abandoned_mine':
                self.assertIn(tile.geology, ('igneous', 'metamorphic'))
            if site.kind == 'cavern':
                self.assertEqual(tile.geology, 'limestone')
            if site.kind in ('bandit_camp', 'ruined_watch'):
                self.assertTrue(any(abs(site.x - x) <= 2 and abs(site.y - y) <= 2
                                    for x, y in road_points))

    def test_json_and_svg_exports_are_complete(self):
        w = self.world
        snapshot = w.to_dict()
        self.assertEqual(snapshot['seed'], 42)
        self.assertEqual(len(snapshot['tiles']), 64 * 44)
        self.assertEqual(len(snapshot['sites']), 25)
        svg = render_svg(w)
        self.assertIn('<svg', svg)
        self.assertIn('Crownreach', svg)
        self.assertIn('</svg>', svg)

    def test_input_bounds(self):
        with self.assertRaises(ValueError):
            generate_world(width=15)
        with self.assertRaises(ValueError):
            generate_world(cities=0)
        with self.assertRaises(ValueError):
            generate_world(sites=201)
        with self.assertRaises(ValueError):
            generate_world(cell_km=0)


if __name__ == '__main__':
    unittest.main()

class AtlasRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = generate_world(seed=42, width=64, height=44, cities=9, sites=25)

    def test_drainage_segments_follow_actual_priority_flood_graph(self):
        w = self.world
        river_edges = 0
        for tile in w.tiles:
            if tile.drains_to is None:
                continue
            nx, ny = tile.drains_to
            self.assertLessEqual(max(abs(nx - tile.x), abs(ny - tile.y)), 1)
            self.assertNotEqual((nx, ny), (tile.x, tile.y))
            if tile.river:
                river_edges += 1
                parent = w.tile(nx, ny)
                self.assertGreaterEqual(parent.flow, tile.flow)
        self.assertGreater(river_edges, 0)
        self.assertTrue(all(t.drains_to is None for t in w.tiles if t.elevation_m <= 0))

    def test_surfaces_are_environment_derived_and_connected(self):
        w = self.world
        self.assertEqual({r.surface for r in w.roads}, {'dirt', 'cobblestone'})
        for r in w.roads:
            if r.surface == 'cobblestone':
                self.assertIn('crownreach', (r.a, r.b))
                self.assertLessEqual(r.distance_km, 135)
        # Changing road graphics does not change pathfinding or route durations.
        self.assertTrue(all(r.travel_minutes > 0 for r in w.roads))

    def test_detailed_svg_is_valid_reproducible_and_read_only(self):
        import base64
        from xml.etree import ElementTree as ET
        w = self.world
        before = w.to_dict()
        svg = render_svg(w)
        self.assertEqual(before, w.to_dict())
        self.assertEqual(svg, render_svg(w))
        root = ET.fromstring(svg)
        ns = {'s': 'http://www.w3.org/2000/svg'}
        for element_id in ('shaded-relief', 'coastline', 'river-network',
                           'elevation-contours', 'summit-markers', 'road-network',
                           'exploration-sites', 'settlements'):
            self.assertIsNotNone(root.find(f'.//*[@id="{element_id}"]', namespaces=ns))
        self.assertIn('dirt-road', svg)
        self.assertIn('cobbled-road', svg)
        png = root.find('.//s:image', ns).get('href')
        self.assertTrue(base64.b64decode(png.split(',', 1)[1]).startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertIn('30 km', svg)
