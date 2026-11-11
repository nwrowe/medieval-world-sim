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
        self.assertEqual(a.version, 5)

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
        for s in w.settlements:
            self.assertGreater(w.tile(s.x, s.y).elevation_m, 0)
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


class HexTopologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = generate_world(seed=7, width=64, height=44, cities=9, sites=25)

    def test_interior_hex_has_six_reciprocal_equal_length_neighbors(self):
        from medieval_world_sim.worldgen.hexgrid import center, neighbors, edge_neighbor, hex_distance
        from math import hypot, sqrt
        w=self.world
        for y in range(2,w.height-2):
            for x in range(2,w.width-2):
                adjacent=list(neighbors(x,y,w.width,w.height))
                self.assertEqual(len(adjacent),6)
                self.assertEqual(len(set(adjacent)),6)
                for nx,ny in adjacent:
                    self.assertIn((x,y),list(neighbors(nx,ny,w.width,w.height)))
                    self.assertEqual(hex_distance((x,y),(nx,ny)),1)
                    self.assertAlmostEqual(hypot(center(x,y,10)[0]-center(nx,ny,10)[0],
                                                 center(x,y,10)[1]-center(nx,ny,10)[1]),
                                           sqrt(3)*10,places=7)
                    self.assertTrue(any(edge_neighbor(x,y,e)==(nx,ny) for e in range(6)))

    def test_hex_roads_rivers_and_coastline_follow_actual_edges(self):
        from medieval_world_sim.worldgen.hexgrid import neighbors
        from medieval_world_sim.worldgen.render import _edge_path
        w=self.world
        for tile in w.tiles:
            if tile.drains_to is not None:
                self.assertIn(tile.drains_to, list(neighbors(tile.x,tile.y,w.width,w.height)))
        for road in w.roads:
            for a,b in zip(road.path,road.path[1:]):
                self.assertIn(b,list(neighbors(*a,w.width,w.height)))
        expected=sum(1 for t in w.tiles if t.elevation_m>0
                     for nx,ny in neighbors(t.x,t.y,w.width,w.height)
                     if w.tile(nx,ny).elevation_m<=0)
        path=_edge_path(w,14,coastal=True)
        self.assertEqual(path.count('M'),expected)
        self.assertGreater(expected,30)
        self.assertEqual(_edge_path(w,14,coastal=False).count('M'),
                         sum(1 for t in w.tiles for _ in range(6)
                             if True) - sum(1 for t in w.tiles for nx,ny in neighbors(t.x,t.y,w.width,w.height)
                                          if (nx,ny)<(t.x,t.y)))

    def test_seed_seven_keeps_crownreach_by_coastal_bay(self):
        w=self.world
        cap=w.settlements[0]
        water=sum(w.tile(x,y).elevation_m<=0
                  for y in range(max(0,cap.y-5), min(w.height,cap.y+6))
                  for x in range(max(0,cap.x-5), min(w.width,cap.x+6)))
        self.assertGreater(water,4)

    def test_svg_hex_grid_river_curves_and_reproducibility(self):
        from xml.etree import ElementTree
        from medieval_world_sim.worldgen.render import render_svg
        w=self.world
        first=render_svg(w)
        self.assertEqual(first,render_svg(w))
        self.assertIn('id="hex-grid"',first)
        self.assertIn('stroke-dasharray="2.3 3.7"',first)
        self.assertIn('id="coastline"',first)
        self.assertIn('Q',first.split('<g id="river-network"')[1].split('</g>')[0])
        self.assertEqual(w.to_dict(),generate_world(seed=7,width=64,height=44,cities=9,sites=25).to_dict())
        ElementTree.fromstring(first)


class RoadSitingTests(unittest.TestCase):
    """Small synthetic hex worlds make route-construction choices observable."""

    @staticmethod
    def _plain(width, height, *, elevations=None, rivers=None):
        from medieval_world_sim.worldgen.terrain import Tile
        elevations = elevations or {}
        rivers = rivers or {}
        return tuple(
            Tile(x, y, elevations.get((x, y), 160), 12, 1000,
                 "grassland", "sedimentary", 65,
                 (x, y) in rivers, rivers.get((x, y), 0), {}, None)
            for y in range(height) for x in range(width)
        )

    def test_road_uses_lower_saddle_instead_of_climbing_nearest_peak(self):
        from medieval_world_sim.worldgen.society import _path
        width, height = 11, 9
        heights = {(5, y): (410 if y == 7 else 2300) for y in range(height)}
        terrain = self._plain(width, height, elevations=heights)
        path, travel_cost = _path(terrain, width, height, (1, 4), (9, 4))
        self.assertIn((5, 7), path)
        self.assertNotIn((5, 4), path)
        self.assertGreater(travel_cost, 0)

    def test_road_detours_around_isolated_river_instead_of_building_bridge(self):
        from medieval_world_sim.worldgen.society import _path
        width, height = 9, 7
        terrain = self._plain(width, height, rivers={(4, 3): 1400})
        path, _ = _path(terrain, width, height, (1, 3), (7, 3))
        self.assertNotIn((4, 3), path)
        self.assertLessEqual(len(path) - 1, 9)  # Modest detour, not a long bypass.

    def test_road_selects_shallow_ford_over_nearby_deep_bridge(self):
        from medieval_world_sim.worldgen.society import _path, _crossing_kind
        width, height = 11, 9
        river = {(5, y): (130 if y == 3 else 1450) for y in range(height)}
        terrain = self._plain(width, height, rivers=river)
        path, _ = _path(terrain, width, height, (1, 4), (9, 4))
        entries = [(x, y) for (px, py), (x, y) in zip(path, path[1:])
                   if _crossing_kind(terrain[py * width + px],
                                     terrain[y * width + x]) is not None]
        self.assertEqual(entries, [(5, 3)])
        self.assertEqual(_crossing_kind(terrain[4 * width + 4],
                                         terrain[3 * width + 5]), "ford")

    def test_unavoidable_deep_crossing_builds_bridge_but_not_fake_travel_time(self):
        from medieval_world_sim.worldgen.society import (
            _path, _crossing_kind, _road_build_cost, _road_travel_cost)
        width, height = 9, 7
        river = {(4, y): 1500 for y in range(height)}
        terrain = self._plain(width, height, rivers=river)
        path, travel_cost = _path(terrain, width, height, (1, 3), (7, 3))
        pairs = [(terrain[a[1] * width + a[0]], terrain[b[1] * width + b[0]])
                 for a, b in zip(path, path[1:])]
        self.assertEqual(sum(_crossing_kind(a, b) == "bridge" for a, b in pairs), 1)
        self.assertAlmostEqual(travel_cost, sum(_road_travel_cost(a, b) for a, b in pairs))
        self.assertLess(travel_cost, sum(_road_build_cost(a, b) for a, b in pairs))

    def test_serialized_roads_track_fords_and_bridges_separately(self):
        w = generate_world(seed=7, width=64, height=44, cities=9, sites=25)
        for road in w.roads:
            self.assertEqual(road.crossings, road.bridges + road.fords)
            self.assertGreater(road.travel_minutes, 0)
        self.assertEqual(w.to_dict()["version"], 5)


class SurveyWaterAndLandmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = generate_world(seed=7, width=64, height=44, cities=9, sites=25)

    def test_lakes_and_navigation_retain_geographic_invariants(self):
        from medieval_world_sim.worldgen.hexgrid import neighbors
        world = self.world
        self.assertTrue(any(t.waterbody == "sea" for t in world.tiles))
        self.assertTrue(any(w.kind == "sea" for w in world.waterways))
        for tile in world.tiles:
            self.assertIn(tile.waterbody, ("land", "sea", "lake", "river"))
            if tile.waterbody == "lake":
                self.assertEqual(tile.biome, "lake")
                self.assertGreater(tile.elevation_m, 0)
                self.assertTrue(tile.navigable)
                self.assertEqual(tile.resources, {})
            if tile.waterbody == "sea":
                self.assertLessEqual(tile.elevation_m, 0)
                self.assertTrue(tile.navigable)
        for network in world.waterways:
            self.assertTrue(network.tiles)
            self.assertIn(network.kind, ("sea", "lake", "river"))
            self.assertGreater(network.length_km, 0)
            for x, y in network.tiles:
                self.assertTrue(world.tile(x, y).navigable)
        for road in world.roads:
            for x, y in road.path:
                self.assertNotIn(world.tile(x, y).waterbody, ("sea", "lake"))
            for (x, y), (nx, ny) in zip(road.path, road.path[1:]):
                self.assertIn((nx, ny), list(neighbors(x, y, world.width, world.height)))

    def test_landmarks_correspond_to_real_crossings_passes_and_shores(self):
        from medieval_world_sim.worldgen.hexgrid import neighbors
        from medieval_world_sim.worldgen.society import _crossing_kind
        world = self.world
        road_edges = [(a, b) for r in world.roads for a, b in zip(r.path, r.path[1:])]
        road_tiles = {p for r in world.roads for p in r.path}
        self.assertTrue(world.landmarks)
        for mark in world.landmarks:
            self.assertTrue(1 <= mark.importance <= 10)
            self.assertGreater(world.tile(mark.x, mark.y).elevation_m, 0)
            if mark.kind in ("bridge", "ford"):
                self.assertTrue(any(b == (mark.x, mark.y) and
                         _crossing_kind(world.tile(*a), world.tile(*b)) == mark.kind
                         for a, b in road_edges))
            if mark.kind == "mountain_pass":
                self.assertIn((mark.x, mark.y), road_tiles)
                self.assertTrue(any(world.tile(nx, ny).elevation_m >
                                    world.tile(mark.x, mark.y).elevation_m + 270
                                    for nx, ny in neighbors(mark.x, mark.y, world.width, world.height)))
            if mark.kind in ("harbor", "lake_landing"):
                sea = "sea" if mark.kind == "harbor" else "lake"
                self.assertTrue(any(world.tile(nx, ny).waterbody == sea
                                    for nx, ny in neighbors(mark.x, mark.y,
                                                            world.width, world.height)))

    def test_interactive_atlas_is_reproducible_and_has_clickable_hexes(self):
        from xml.etree import ElementTree
        from medieval_world_sim.worldgen.inspect import render_inspector_html
        world = self.world
        before = world.to_dict()
        svg = render_svg(world)
        html = render_inspector_html(world, svg)
        self.assertEqual(before, world.to_dict())
        self.assertEqual(html, render_inspector_html(world, svg))
        self.assertEqual(html.count('data-index="'), world.width * world.height)
        self.assertIn('id="atlas-inspector-hit"', html)
        self.assertIn('id="atlas-data"', html)
        self.assertIn('id="lake-shores"', html)
        self.assertIn('id="strategic-landmarks"', html)
        self.assertIn("Navigability", html)
        self.assertIn("resources", html)
        self.assertIn("waterways", str(world.to_dict()))
        self.assertIn("landmarks", str(world.to_dict()))
        # The embedded SVG remains valid after inserting 2816 hit targets.
        embedded = html.split('<svg xmlns=', 1)[1].split('</svg>', 1)[0]
        ElementTree.fromstring('<svg xmlns=' + embedded + '</svg>')
