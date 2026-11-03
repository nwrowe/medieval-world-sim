"""New player experience and economic integrity for healing, horses and search."""
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.catalog import CITIES, RAW_RESOURCES, EQUIPMENT, CONSUMABLES, PROCESSED_RESOURCES
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.session import GameSession


class GameplayExpansionTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "save.json"
        self.game = GameSession(self.path)
        self.game.create("Aster Reed")

    def tearDown(self):
        self.dir.cleanup()

    def act(self, action, params, ident):
        return self.game.action(action, params, "expansion-" + ident)

    def test_catalog_all_items_and_real_city_quotes(self):
        view = self.game.snapshot()
        catalog = {entry["id"]: entry for entry in view["world_items"]}
        self.assertEqual(set(catalog), set(RAW_RESOURCES) | set(PROCESSED_RESOURCES)
                         | set(CONSUMABLES) | set(EQUIPMENT))
        self.assertEqual(catalog["sword"]["lowest_buy"],
                         {"city": "crownreach", "price": 16})
        self.assertIsNone(catalog["sword"]["highest_sell"])
        self.assertIsNone(catalog["steel"]["lowest_buy"])
        self.assertIsNone(catalog["steel"]["market_value"])
        self.assertEqual(catalog["grain"]["lowest_buy"]["city"], "goldmeadow")
        for item in RAW_RESOURCES:
            for field, is_buy in (("lowest_buy", True), ("highest_sell", False)):
                entry = catalog[item][field]
                if entry is not None:
                    quote = self.game.world.regional_quote(entry["city"], item)
                    self.assertEqual(entry["price"], quote.player_buy_price if is_buy
                                     else quote.player_sell_price)
        armory = {item["kind"]: item for item in view["equipment_catalog"]}
        self.assertEqual(armory["sword"]["quality"], 10)
        self.assertGreater(armory["sword"]["attack"], 0)
        self.assertGreater(armory["plate_armor"]["defense"], 0)

    def test_church_healing_once_a_day_without_cooldown(self):
        self.game.world.actors["hero"].hp = 12
        total = self.game.world.total_gold
        before_cooldowns = self.game.snapshot()["player"]["cooldowns"]
        healed = self.act("church_heal", {}, "heal-one")
        self.assertEqual(healed, 12)
        view = self.game.snapshot()
        self.assertEqual(view["player"]["hp"], 24)
        self.assertEqual(view["player"]["gold"], 220)
        self.assertTrue(view["church"]["used_today"])
        self.assertEqual(view["player"]["cooldowns"], before_cooldowns)
        self.assertEqual(self.game.world.total_gold, total)
        self.assertEqual(GameSession(self.path).snapshot()["church"], view["church"])
        self.game.world.actors["hero"].hp = 18
        with self.assertRaises(ActionError):
            self.act("church_heal", {}, "heal-repeat")
        self.game.advance(1440)
        self.assertFalse(self.game.snapshot()["church"]["used_today"])

    def test_racing_costs_prize_cooldown_and_replay(self):
        self.act("buy_racehorse", {"breed": "moor_pony"}, "buy-horse")
        before = self.game.world.total_gold
        self.assertEqual(self.game.snapshot()["player"]["gold"], 195)
        result = self.act("race_horse", {"breed": "moor_pony"}, "race1")
        self.assertIn(result["placing"], (1, 2, 3))
        self.assertEqual(result["riding_xp"], result["xp"])
        self.assertEqual(self.game.world.total_gold, before)
        self.assertEqual(GameSession(self.path).snapshot(), self.game.snapshot())
        with self.assertRaises(ActionError):
            self.act("race_horse", {"breed": "moor_pony"}, "race-too-soon")
        with self.assertRaises(ActionError):
            self.act("race_horse", {"breed": "royal_courser"}, "not-owned")
        self.game.advance(60)
        second = self.act("race_horse", {"breed": "moor_pony"}, "race2")
        self.assertEqual(self.game.snapshot()["track"]["riding_xp"],
                         result["xp"] + second["xp"])
        self.assertEqual(GameSession(self.path).snapshot(), self.game.snapshot())

    def test_healing_regenerates_on_simulated_boundaries(self):
        world = WorldEngine([Actor("hero", "human", city="goldmeadow")])
        hero = world.actors["hero"]
        hero.hp = 15
        world.advance(9)
        self.assertEqual(hero.hp, 15)
        world.advance(1)
        self.assertEqual(hero.hp, 16)
        world.advance(20)
        self.assertEqual(hero.hp, 18)
        hero.hp = 0
        hero.defeated_until = world.minute + 60
        world.advance(40)
        self.assertEqual(hero.hp, 0)
        world.advance(20)
        self.assertEqual(hero.hp, hero.max_hp)
        world.assert_invariants()

    def test_legacy_advance_does_not_rewrite_prior_health(self):
        world = WorldEngine([Actor("hero", "human", city="goldmeadow")])
        hero = world.actors["hero"]
        hero.hp = 15
        world._legacy_health_regen = True
        world.advance(60)
        world._legacy_health_regen = False
        self.assertEqual(hero.hp, 15)


if __name__ == "__main__":
    unittest.main()
