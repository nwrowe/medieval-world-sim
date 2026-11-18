"""Terrain-grounded wilderness gathering, persistent site decisions and replay."""
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.core.exploration import reveal
from medieval_world_sim.errors import ActionError
from medieval_world_sim.systems.wilderness import supply_cap
from medieval_world_sim.web.session import GameSession, PLAYER_ID
from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web.checkpoint import _decode, _encode
from medieval_world_sim.worldgen.hexgrid import hex_distance


def suitable_site(world):
    # A generated site (not a fake combat map) has physically plausible goods.
    candidates = [
        s for s in world.geography.sites
        if world.geography.tile(s.x, s.y).resources
    ]
    capital = world.geography_settlements[CAPITAL]
    return min(candidates, key=lambda s: (
        hex_distance((capital.x, capital.y), (s.x, s.y)), s.id))


def stage_site(world, actor_id, site):
    """A test-only arrival fixture; game API tests use real route commands."""
    actor = world.actors[actor_id]
    actor.wilderness_hex = (site.x, site.y)
    reveal(world, actor, actor.wilderness_hex)
    world.assert_invariants()


def walk_to_site(action, advance, world, actor_id, site):
    """Travel in visible hex segments, with the real engine and game clock."""
    for sequence in range(70):
        actor = world.actors[actor_id]
        if actor.wilderness_hex == (site.x, site.y):
            return
        start = actor.wilderness_hex
        if start is None:
            t = world.geography_settlements[actor.city]
            start = (t.x, t.y)
        costs, prior = world.travel.terrain_routes(actor, {(site.x, site.y)})
        target = (site.x, site.y)
        if target not in costs:
            raise AssertionError("Test site is unreachable from the city")
        path = [target]
        while path[-1] != start:
            path.append(prior[path[-1]])
        path.reverse()
        next_point = path[min(2, len(path) - 1)]
        action("explore_hex", {"x": next_point[0], "y": next_point[1]},
               f"wilderness-walk-{sequence}")
        remain = world.actors[actor_id].arrival_minute - world.minute
        advance(remain, f"wilderness-arrive-{sequence}")
    raise AssertionError("Could not walk to physically generated site")


class WildernessEngineTests(unittest.TestCase):
    def world(self):
        return WorldEngine([
            Actor("scout", "human", city=CAPITAL),
            Actor("rival", "human", city=CAPITAL),
        ], seed=37)

    def test_site_is_generated_from_terrain_and_has_choices(self):
        world = self.world()
        site = suitable_site(world)
        tile = world.geography.tile(site.x, site.y)
        self.assertEqual(tile.biome, site.biome)
        self.assertTrue(tile.resources)
        stage_site(world, "scout", site)
        snap = world.wilderness.view("scout")
        self.assertEqual(snap["biome"], tile.biome)
        self.assertEqual(snap["geology"], tile.geology)
        self.assertEqual(snap["sites"][0]["id"], site.id)
        self.assertEqual(
            {c["id"] for c in snap["sites"][0]["choices"]},
            {"survey", "scavenge", "delve"})
        self.assertEqual(
            {c["stamina"] for c in snap["sites"][0]["choices"]},
            {2, 4, 7})

    def test_harvest_depletes_shared_stock_replenishes_and_costs_stamina(self):
        w = self.world()
        site = suitable_site(w)
        stage_site(w, "scout", site)
        stage_site(w, "rival", site)
        item = max(w.geography.tile(site.x, site.y).resources,
                   key=w.geography.tile(site.x, site.y).resources.get)
        cap = supply_cap(w.geography.tile(site.x, site.y).resources[item])
        self.assertGreaterEqual(cap, 2)
        initial = w.actors["scout"].stamina
        result = w.execute("scout", "wilderness_gather",
                           {"item": item, "quantity": 1}, "gather-1")
        self.assertEqual(result["quantity"], 1)
        self.assertEqual(w.actors["scout"].stamina, initial - 5)
        self.assertEqual(w.wilderness.view("rival")["resources"][
            next(i for i, r in enumerate(w.wilderness.view("rival")["resources"])
                 if r["item"] == item)]["available"], cap - 1)
        for i in range(cap - 1):
            w.execute("rival", "wilderness_gather",
                      {"item": item, "quantity": 1}, f"gather-rival-{i}")
        with self.assertRaisesRegex(ActionError, "exhausted"):
            w.execute("scout", "wilderness_gather",
                      {"item": item, "quantity": 1}, "gather-exhausted")
        w.advance(1440)
        self.assertGreater(w.wilderness._available(
            w.geography.tile(site.x, site.y), item), 0)
        w.assert_invariants()

    def test_site_success_chance_tracks_attributes_and_never_rerolls(self):
        w = self.world()
        site = suitable_site(w)
        stage_site(w, "scout", site)
        actor = w.actors["scout"]
        original = w.wilderness.view("scout")["sites"][0]["choices"][0]["chance"]
        actor.work.intelligence += 20
        improved = w.wilderness.view("scout")["sites"][0]["choices"][0]["chance"]
        self.assertGreaterEqual(improved, original)
        before = actor.stamina
        args = {"site_id": site.id, "approach": "survey"}
        result = w.execute("scout", "investigate_site", args, "site-attempt")
        self.assertEqual(before - actor.stamina, 2)
        self.assertEqual(result["chance"], improved)
        self.assertIn(result["success"], (True, False))
        self.assertTrue(w.wilderness.view("scout")["sites"][0]["resolved"])
        self.assertEqual(w.execute("scout", "investigate_site", args,
                                   "site-attempt"), result)
        with self.assertRaisesRegex(ActionError, "already explored"):
            w.execute("scout", "investigate_site",
                      {"site_id": site.id, "approach": "delve"}, "reroll")
        self.assertEqual(before - actor.stamina, 2)
        w.assert_invariants()

    def test_remote_and_tampered_site_requests_do_not_change_resources(self):
        w = self.world()
        site = suitable_site(w)
        actor = w.actors["scout"]
        before = actor.stamina
        with self.assertRaises(ActionError):
            w.execute("scout", "investigate_site",
                      {"site_id": site.id, "approach": "delve"}, "remote")
        with self.assertRaises(ActionError):
            w.execute("scout", "wilderness_gather",
                      {"item": "steel", "quantity": 1}, "remote-resource")
        stage_site(w, "scout", site)
        bad = [
            ("investigate_site", {"site_id": [], "approach": "survey"}),
            ("investigate_site", {"site_id": site.id, "approach": "loot_everything"}),
            ("wilderness_gather", {"item": "steel", "quantity": 1}),
            ("wilderness_gather", {"item": 123, "quantity": 1}),
            ("wilderness_gather", {"item": "herbs", "quantity": True}),
            ("wilderness_gather", {"item": "herbs", "quantity": 100}),
            ("wilderness_gather", {"item": "herbs", "quantity": 2}),
        ]
        for i, (action, params) in enumerate(bad):
            with self.subTest(i=i), self.assertRaises(ActionError):
                w.execute("scout", action, params, f"invalid-{i}")
        self.assertEqual(actor.stamina, before)
        self.assertEqual(w.state.site_attempts, {})
        self.assertEqual(w.state.wilderness_stock, {})
        w.assert_invariants()

    def test_automatic_road_journeys_do_not_trigger_optional_encounters(self):
        w = self.world()
        other = next(x for x in w.travel.available_destinations(w.actors["scout"])
                     if x != CAPITAL)
        start = w.actors["scout"].stamina
        minutes = w.start_travel("scout", other)
        w.advance(minutes)
        self.assertEqual(w.actors["scout"].city, other)
        self.assertEqual(w.actors["scout"].stamina, start)
        self.assertFalse(w.state.site_attempts)
        self.assertFalse(w.state.wilderness_stock)
        w.assert_invariants()

    def test_checkpoint_encode_decode_preserves_both_wilderness_ledgers(self):
        w = self.world()
        site = suitable_site(w)
        stage_site(w, "scout", site)
        item = next(iter(w.geography.tile(site.x, site.y).resources))
        w.execute("scout", "wilderness_gather", {"item": item, "quantity": 1}, "item")
        w.execute("scout", "investigate_site",
                  {"site_id": site.id, "approach": "survey"}, "site")
        clone = _decode(_encode(w.state))
        self.assertEqual(clone.wilderness_stock, w.state.wilderness_stock)
        self.assertEqual(clone.site_attempts, w.state.site_attempts)


class WildernessPersistenceTests(unittest.TestCase):
    def test_single_player_hex_walk_and_site_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "single.json"
            game = GameSession(path)
            game.create("Forest Reader")
            site = suitable_site(game.world)
            walk_to_site(
                lambda a, p, req: game.action(a, p, req),
                lambda mins, req: game.advance(mins),
                game.world, PLAYER_ID, site)
            self.assertEqual(game.world.actors[PLAYER_ID].wilderness_hex,
                             (site.x, site.y))
            item = next(iter(game.world.geography.tile(site.x, site.y).resources))
            game.action("wilderness_gather", {"item": item, "quantity": 1}, "gather")
            report = game.action("investigate_site",
                                 {"site_id": site.id, "approach": "survey"}, "site")
            view = game.snapshot()
            self.assertEqual(view["wilderness"]["sites"][0]["resolved"]["success"],
                             report["success"])
            restored = GameSession(path)
            self.assertEqual(restored.world.state.site_attempts,
                             game.world.state.site_attempts)
            self.assertEqual(restored.world.state.wilderness_stock,
                             game.world.state.wilderness_stock)
            self.assertEqual(restored.snapshot()["wilderness"], view["wilderness"])

    def test_multiplayer_protection_and_keyed_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shared.sqlite3"
            game = MultiplayerGame(path, require_invites=False,
                                   dev_fast_forward=True, npc_enabled=False)
            try:
                alice = game.register("wanderer", "correct horse battery staple", "Wanderer")
                bob = game.register("shopkeep", "correct horse battery staple", "Shopkeeper")
                site = suitable_site(game.world)
                walk_to_site(
                    lambda a, p, req: game.action(alice, a, p, req),
                    lambda mins, req: game.advance(alice, mins, req),
                    game.world, alice, site)
                initial = game.snapshot(alice)
                self.assertIsNotNone(initial["wilderness"])
                self.assertIsNone(game.snapshot(bob)["wilderness"])
                with self.assertRaises(ActionError):
                    game.action(bob, "investigate_site",
                                {"site_id": site.id, "approach": "delve"}, "forge-location")
                response = game.action(alice, "investigate_site",
                    {"site_id": site.id, "approach": "scavenge"}, "alice-site")
                same = game.action(alice, "investigate_site",
                    {"site_id": site.id, "approach": "scavenge"}, "alice-site")
                self.assertEqual(response, same)
                self.assertNotIn(site.id, game.world.state.site_attempts.get(bob, {}))
            finally:
                game.close()
            restored = MultiplayerGame(path, require_invites=False,
                                       dev_fast_forward=True, npc_enabled=False)
            try:
                past = restored.snapshot(alice)["wilderness"]["sites"][0]["resolved"]
                self.assertEqual(past["success"], response["success"])
                self.assertEqual(past["approach"], "scavenge")
                restored.world.assert_invariants()
            finally:
                restored.close()


if __name__ == "__main__":
    unittest.main()
