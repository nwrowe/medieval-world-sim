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
        self.assertEqual(a.version, 8)

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
        self.assertIn('C',first.split('<g id="river-network"')[1].split('</g>')[0])
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
        self.assertEqual(w.to_dict()["version"], 8)


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
        self.assertEqual(html.count('<polygon data-index="'), world.width * world.height)
        self.assertIn('id="atlas-inspector-hit"', html)
        self.assertIn('id="atlas-data"', html)
        self.assertIn('id="lake-shores"', html)
        self.assertIn('id="strategic-landmarks"', html)
        self.assertIn("Watercraft suitability", html)
        self.assertIn("resources", html)
        self.assertIn("waterways", str(world.to_dict()))
        self.assertIn("landmarks", str(world.to_dict()))
        # The embedded SVG remains valid after inserting 2816 hit targets.
        embedded = html.split('<svg xmlns=', 1)[1].split('</svg>', 1)[0]
        ElementTree.fromstring('<svg xmlns=' + embedded + '</svg>')


class CoastAccessibilityAndAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = generate_world(seed=7, width=64, height=44, cities=9, sites=25)

    def test_all_ocean_hexes_are_at_sea_level_and_land_is_above(self):
        world = self.world
        sea = [t for t in world.tiles if t.waterbody == "sea"]
        dry = [t for t in world.tiles if t.waterbody not in ("sea", "lake")]
        self.assertTrue(sea)
        self.assertTrue(dry)
        self.assertTrue(all(t.elevation_m == 0 and t.seabed_depth_m >= 1
                            and t.biome == "ocean" for t in sea))
        self.assertTrue(all(t.elevation_m >= 1 and t.seabed_depth_m == 0
                            for t in dry))
        self.assertTrue(all(t.elevation_m > 0 for t in world.tiles
                            if t.waterbody == "lake"))

    def test_road_difficulty_reduces_walking_minutes_without_flattening_geography(self):
        from medieval_world_sim.worldgen.access import path_minutes, minutes_per_hex
        world = self.world
        nonroads = []
        roads = []
        for t in world.tiles:
            if t.waterbody in ("sea", "lake"):
                self.assertIsNone(t.natural_difficulty)
                self.assertIsNone(t.travel_difficulty)
                self.assertIsNone(t.road_surface)
                continue
            self.assertTrue(1 <= t.natural_difficulty <= 100)
            self.assertTrue(1 <= t.travel_difficulty <= 100)
            self.assertLessEqual(t.travel_difficulty, t.natural_difficulty)
            if t.road_surface is not None:
                roads.append(t)
                self.assertIn(t.road_surface, ("dirt", "cobblestone"))
                self.assertLess(t.travel_difficulty, t.natural_difficulty)
            else:
                nonroads.append(t)
                self.assertEqual(t.natural_difficulty, t.travel_difficulty)
        self.assertTrue(roads)
        self.assertTrue(nonroads)
        self.assertGreater(minutes_per_hex(95, 3), minutes_per_hex(10, 3))
        for road in world.roads:
            self.assertEqual(road.travel_minutes,
                             path_minutes(world.tiles, world.width, road.path,
                                          world.cell_km))
        with self.assertRaises(ValueError):
            minutes_per_hex(0)

    def test_site_and_landmark_template_round_trips_with_stable_ids(self):
        from medieval_world_sim.worldgen.content import export_content_template
        from medieval_world_sim.worldgen.inspect import render_inspector_html
        world = self.world
        template = export_content_template(world)
        self.assertEqual(template["generator_version"], 8)
        self.assertEqual(template["seed"], 7)
        self.assertIn("crownreach", template["settlements"])
        self.assertEqual(len(template["sites"]), len(world.sites))
        self.assertEqual(len(template["landmarks"]), len(world.landmarks))
        duplicate = generate_world(seed=7, width=64, height=44, cities=9, sites=25,
                                   content=template)
        self.assertEqual(world.to_dict(), duplicate.to_dict())
        self.assertIn('Natural land difficulty', render_inspector_html(world))

    def test_custom_relocatable_sites_and_scheduled_event_location(self):
        from medieval_world_sim.worldgen.content import export_content_template
        from medieval_world_sim.worldgen.inspect import render_inspector_html
        from medieval_world_sim.worldgen.render import render_svg
        world = self.world
        edited = export_content_template(world)
        edited["settlements"]["crownreach"]["name"] = "Bay of Crownreach"
        old = world.sites[0]
        where = world.sites[1]
        edited["sites"][old.id].update({
            "name": "The Elder Vault", "x": where.x, "y": where.y})
        edited["landmarks"][world.landmarks[0].id]["name"] = "The Old Crossing"
        edited["additional_sites"].append({
            "id": "custom-winter-crypt", "name": "Winter Crypt",
            "kind": "crypt", "x": where.x, "y": where.y,
            "danger": 6, "clue": "A weathered entrance in the hillside"
        })
        capital = world.settlements[0]
        edited["event_locations"].append({
            "id": "event-winter-market", "name": "Winter Market",
            "kind": "festival", "x": capital.x, "y": capital.y,
            "description": "A seasonal merchant caravan",
            "starts_at": "2026-12-01T00:00:00Z",
            "ends_at": "2026-12-08T00:00:00Z",
        })
        revised = generate_world(seed=7, width=64, height=44, cities=9, sites=25,
                                 content=edited)
        self.assertEqual(revised.settlements[0].name, "Bay of Crownreach")
        self.assertEqual(revised.sites[0].name, "The Elder Vault")
        self.assertEqual((revised.sites[0].x, revised.sites[0].y),
                         (where.x, where.y))
        self.assertEqual(revised.landmarks[0].name, "The Old Crossing")
        self.assertIn("custom-winter-crypt", {s.id for s in revised.sites})
        self.assertEqual(len(revised.event_locations), 1)
        self.assertIn("Winter Market", render_svg(revised))
        self.assertIn("Scheduled event:", render_inspector_html(revised))
        # Content overrides never alter the generated terrain or authoritative roads.
        self.assertEqual(world.tiles, revised.tiles)
        self.assertEqual(world.roads, revised.roads)

    def test_reject_invalid_coordinates_duplicate_ids_bad_dates_and_wrong_seed(self):
        from medieval_world_sim.worldgen.content import export_content_template
        world = self.world
        def validate(patch):
            content = export_content_template(world)
            patch(content)
            return generate_world(seed=7, width=64, height=44, cities=9, sites=25,
                                  content=content)

        with self.assertRaises(ValueError):
            validate(lambda c: c.update(seed=99))
        with self.assertRaises(ValueError):
            validate(lambda c: c["settlements"]["crownreach"].update(name=""))
        water = next(t for t in world.tiles if t.waterbody == "sea")
        with self.assertRaises(ValueError):
            validate(lambda c: c["sites"][world.sites[0].id].update(x=water.x, y=water.y))
        with self.assertRaises(ValueError):
            validate(lambda c: c["sites"].update({"non-existent-site": {"name": "Fake"}}))
        event = {
            "id": "event-test", "name": "Holiday", "kind": "fair",
            "x": world.settlements[0].x, "y": world.settlements[0].y,
            "description": "A short-lived event", "starts_at": "2026-12-10T00:00:00Z",
            "ends_at": "2026-12-01T00:00:00Z",
        }
        with self.assertRaises(ValueError):
            validate(lambda c: c["event_locations"].append(event))

    def test_json_loader_rejects_repeated_keys(self):
        from medieval_world_sim.worldgen.content import load_content
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "world-content.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Repeated JSON key"):
                load_content(path)


class HistoricalDevelopmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = generate_world(seed=7, width=64, height=44, cities=9, sites=25)

    def test_historical_eras_are_reproducible_ordered_and_geographically_grounded(self):
        w = self.world
        chron = w.history
        self.assertIsNotNone(chron)
        self.assertEqual(len(chron.eras), 6)
        self.assertEqual([x.year for x in chron.eras],
                         sorted(x.year for x in chron.eras))
        self.assertEqual(chron.present_year, chron.eras[-1].year)
        self.assertEqual(len(chron.eras[-1].towns), len(w.settlements))
        self.assertTrue(len(chron.eras[0].towns) < len(w.settlements))
        all_ids = {s.id for s in w.settlements}
        known = set()
        for era in chron.eras:
            self.assertEqual(len({s.id for s in era.towns}), len(era.towns))
            for town in era.towns:
                known.add(town.id)
                self.assertIn(town.id, all_ids)
                self.assertGreater(town.population, 0)
                self.assertTrue(0 <= town.food_security <= 100)
                self.assertIn(town.status, ("hamlet", "village", "town", "city"))
                self.assertGreaterEqual(era.year, town.founded_year)
                self.assertEqual((town.x, town.y),
                                 (next(s.x for s in w.settlements if s.id == town.id),
                                  next(s.y for s in w.settlements if s.id == town.id)))
            self.assertEqual({t.id for t in era.towns}, known)
        again = generate_world(seed=7, width=64, height=44, cities=9, sites=25)
        self.assertEqual(w.history, again.history)
        self.assertEqual(w.to_dict(), again.to_dict())

    def test_historic_routes_activate_after_founding_and_track_trade(self):
        w = self.world
        modern = {tuple(sorted((r.a, r.b))): r for r in w.roads}
        prior_routes = set()
        for era in w.history.eras:
            present = {t.id for t in era.towns}
            current = set()
            for road in era.roads:
                key = tuple(sorted((road.a, road.b)))
                self.assertIn(key, modern)
                self.assertIn(road.a, present)
                self.assertIn(road.b, present)
                self.assertGreater(road.travel_minutes, 0)
                self.assertGreater(road.trade_volume, 0)
                self.assertIn(road.surface, ("trail", "dirt", "cobblestone"))
                current.add(key)
            self.assertTrue(prior_routes.issubset(current))
            prior_routes = current

    def test_political_membership_and_provenance_are_consistent(self):
        w = self.world
        self.assertTrue(any(e.kind == "founding" for era in w.history.eras
                            for e in era.events))
        self.assertTrue(any(e.kind == "road" for era in w.history.eras
                            for e in era.events))
        for era in w.history.eras:
            members = {member for p in era.polities for member in p.member_ids}
            self.assertEqual(members, {t.id for t in era.towns})
            self.assertEqual(len(members),
                             sum(len(p.member_ids) for p in era.polities))
            for polity in era.polities:
                self.assertIn(polity.seat_id, members)
                self.assertGreater(polity.influence, 0)
            assignment = {t.id: t.polity_id for t in era.towns}
            for polity in era.polities:
                for sid in polity.member_ids:
                    self.assertEqual(assignment[sid], polity.id)
            for e in era.events:
                self.assertEqual(e.year, era.year)
                self.assertTrue(e.title)
                self.assertTrue(e.account)

    def test_ruins_are_dry_sited_and_abandonment_is_recorded(self):
        w = self.world
        self.assertTrue(w.history.ruins)
        sites = {s.id: s for s in w.sites}
        abandonments = {e.site_id for era in w.history.eras
                        for e in era.events if e.kind == "abandonment"}
        self.assertGreaterEqual(len(abandonments), len(w.history.ruins))
        for ruin in w.history.ruins:
            self.assertIn(ruin.id, abandonments)
            self.assertLess(ruin.founded_year, ruin.abandoned_year)
            self.assertLessEqual(ruin.abandoned_year, w.history.present_year)
            self.assertGreater(w.tile(ruin.x, ruin.y).elevation_m, 0)
            self.assertNotIn(w.tile(ruin.x, ruin.y).waterbody, ("sea", "lake"))
            self.assertTrue(ruin.cause)
            if ruin.linked_site_id is not None:
                site = sites[ruin.linked_site_id]
                self.assertEqual((ruin.x, ruin.y), (site.x, site.y))

    def test_historical_atlas_has_valid_svg_and_shows_eras(self):
        from xml.etree import ElementTree
        from medieval_world_sim.worldgen.history_view import render_history_html
        from medieval_world_sim.worldgen.render import render_svg
        w = self.world
        before = w.to_dict()
        html = render_history_html(w)
        self.assertEqual(html, render_history_html(w))
        self.assertEqual(before, w.to_dict())
        self.assertIn('id="historical-overlays"', html)
        self.assertIn('id="era"', html)
        self.assertIn("The Chronicle of Oathmere", html)
        self.assertIn(w.history.eras[-1].name, html)
        self.assertIn("historical-event", html)
        self.assertIn("atlas.html", html)
        svg = html.split('<svg xmlns=', 1)[1].split('</svg>', 1)[0]
        ElementTree.fromstring('<svg xmlns=' + svg + '</svg>')
        plain = render_svg(w)
        self.assertIn('id="river-network"', plain)

    def test_markdown_chronicle_tracks_the_same_event_ids_and_ruins(self):
        from medieval_world_sim.worldgen.history_text import render_chronicle
        w = self.world
        before = w.to_dict()
        narrative = render_chronicle(w)
        self.assertEqual(narrative, render_chronicle(w))
        self.assertIn("The Chronicle of Oathmere", narrative)
        for era in w.history.eras:
            self.assertIn(era.name, narrative)
            for event in era.events:
                self.assertIn(event.title, narrative)
        for ruin in w.history.ruins:
            self.assertIn(ruin.name, narrative)
            self.assertIn(ruin.cause, narrative)
        self.assertEqual(w.to_dict(), before)

    def test_authored_city_names_propagate_into_its_history(self):
        from medieval_world_sim.worldgen.content import export_content_template
        original = self.world
        manifest = export_content_template(original)
        manifest["settlements"]["crownreach"]["name"] = "Bayhaven"
        updated = generate_world(seed=7, width=64, height=44, cities=9,
                                 sites=25, content=manifest)
        self.assertTrue(any(t.name == "Bayhaven" for era in updated.history.eras
                            for t in era.towns))
        self.assertEqual(original.tiles, updated.tiles)
        self.assertEqual(original.roads, updated.roads)
        self.assertNotEqual(original.history, updated.history)


class GeographicTownResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = generate_world(seed=7, width=64, height=44, cities=9, sites=25)

    def test_every_raw_resource_is_classified_with_real_local_evidence(self):
        from medieval_world_sim.content.catalog import RAW_RESOURCES
        from medieval_world_sim.worldgen.society import _nearby
        w = self.world
        self.assertEqual(len(w.resource_profiles), len(w.settlements))
        self.assertEqual([p.settlement_id for p in w.resource_profiles],
                         [s.id for s in w.settlements])
        distinct_production = set()
        for town, profile in zip(w.settlements, w.resource_profiles):
            self.assertEqual(profile.settlement_name, town.name)
            catchment = list(_nearby(w.tiles, w.width, w.height, town.x, town.y, 5))
            records = profile.primary + profile.secondary + profile.lacking
            self.assertEqual({r.resource for r in records}, set(RAW_RESOURCES))
            self.assertEqual(len(records), len(RAW_RESOURCES))
            self.assertLessEqual(len(profile.primary), 2)
            distinct_production.add(tuple(sorted(town.production.items())))
            for record in records:
                expected = sum(t.resources.get(record.resource, 0)
                               for t in catchment) / len(catchment)
                supporters = sum(t.resources.get(record.resource, 0) > 0
                                 for t in catchment)
                self.assertAlmostEqual(record.potential, expected, delta=.006)
                self.assertEqual(record.supporting_hexes, supporters)
                self.assertEqual(record.surveyed_hexes, len(catchment))
                self.assertEqual(record.estimated_units_per_hour,
                                 town.production.get(record.resource, 0))
                self.assertIn(str(supporters), record.explanation)
                if record.tier == "lacking":
                    self.assertEqual(record.estimated_units_per_hour, 0)
                else:
                    self.assertGreater(record.estimated_units_per_hour, 0)
            self.assertEqual(set(town.production),
                             {r.resource for r in profile.primary + profile.secondary})
        self.assertGreater(len(distinct_production), 1)

    def test_recipe_dependencies_include_existing_processed_upstream_inputs(self):
        from medieval_world_sim.content.catalog import RECIPES
        from medieval_world_sim.worldgen.resources import _raw_requirements
        self.assertEqual(_raw_requirements("steelworks"), {"coal": 1, "iron_ore": 2})
        self.assertEqual(_raw_requirements("forge"),
                         {"coal": 1, "iron_ore": 2, "timber": 1})
        self.assertEqual(_raw_requirements("armorer"),
                         {"coal": 3, "hides": 2, "iron_ore": 6})
        self.assertEqual(_raw_requirements("tavern"),
                         {"grain": 2, "meat": 1, "vegetables": 1})
        for profile in self.world.resource_profiles:
            self.assertEqual({r.recipe for r in profile.industries}, set(RECIPES))
            produced = {r.resource for r in profile.primary + profile.secondary}
            for industry in profile.industries:
                inputs = set(industry.raw_inputs_per_craft)
                self.assertEqual(set(industry.available_locally), inputs & produced)
                self.assertEqual(set(industry.imports_needed), inputs - produced)
                self.assertEqual(industry.classification,
                                 "local_inputs" if not industry.imports_needed else
                                 "import_dependent" if industry.available_locally else
                                 "no_local_inputs")

    def test_supplier_candidates_have_real_production_and_connected_road_time(self):
        from medieval_world_sim.worldgen.resources import _road_distances
        w = self.world
        towns = {s.id: s for s in w.settlements}
        for profile in w.resource_profiles:
            lacking = {r.resource for r in profile.lacking}
            distances = _road_distances(w, profile.settlement_id)
            for lead in profile.supplier_candidates:
                self.assertIn(lead.resource, lacking)
                self.assertNotEqual(lead.source_id, profile.settlement_id)
                supplier = towns[lead.source_id]
                self.assertEqual(lead.source_name, supplier.name)
                self.assertEqual(lead.estimated_source_units_per_hour,
                                 supplier.production[lead.resource])
                self.assertEqual(lead.route_minutes, distances[supplier.id])
                self.assertGreater(lead.route_minutes, 0)
            self.assertEqual(len({r.resource for r in profile.supplier_candidates}),
                             len(profile.supplier_candidates))

    def test_report_and_inspector_explain_resources_not_real_export_stock(self):
        import json
        from medieval_world_sim.worldgen.resource_report import (
            render_resource_json, render_resource_markdown)
        from medieval_world_sim.worldgen.inspect import render_inspector_html
        w = self.world
        before = w.to_dict()
        data = json.loads(render_resource_json(w))
        self.assertEqual(data["generator_version"], 8)
        self.assertEqual(data["world_seed"], w.seed)
        self.assertEqual(len(data["towns"]), len(w.settlements))
        report = render_resource_markdown(w)
        html = render_inspector_html(w)
        self.assertIn("Primary natural resources", html)
        self.assertIn("Lacking locally", html)
        self.assertIn('id="town-list"', html)
        self.assertIn("Town resource economy", html)
        self.assertIn("No local production", report)
        for town in w.settlements:
            self.assertIn(town.name, report)
        self.assertEqual(w.to_dict(), before)

    def test_name_overrides_only_change_display_names_not_geologic_supply(self):
        from medieval_world_sim.worldgen.content import export_content_template
        w = self.world
        edited = export_content_template(w)
        edited["settlements"]["crownreach"]["name"] = "Bayhaven"
        modified = generate_world(seed=7, width=64, height=44, cities=9, sites=25,
                                  content=edited)
        original = {p.settlement_id: p for p in w.resource_profiles}
        revised = {p.settlement_id: p for p in modified.resource_profiles}
        self.assertEqual(revised["crownreach"].settlement_name, "Bayhaven")
        self.assertEqual(original["crownreach"].primary, revised["crownreach"].primary)
        self.assertEqual(original["crownreach"].secondary, revised["crownreach"].secondary)
        self.assertEqual(original["crownreach"].lacking, revised["crownreach"].lacking)
        self.assertEqual(w.tiles, modified.tiles)
        self.assertEqual(w.roads, modified.roads)
