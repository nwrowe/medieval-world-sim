"""Playtest regressions: cargo safety, Tavern, and multi-product employment."""
import tempfile
import unittest
from pathlib import Path

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.content.industry import INDUSTRY_PRODUCTS, RECIPES, GOODS
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor, Wage
from medieval_world_sim.errors import ActionError
from medieval_world_sim.systems.tavern import ROOM_DURATION, mead_day
from medieval_world_sim.web.checkpoint import _decode, _encode
from medieval_world_sim.web.session import GameSession
from medieval_world_sim.web.multiplayer import MultiplayerGame
from test_wilderness_phase1 import suitable_site, stage_site


class CargoSafetyTests(unittest.TestCase):
    def test_gather_rejects_overflow_without_spending_stamina_or_stock(self):
        w = WorldEngine([Actor("walker", "human", city=CAPITAL)])
        site = suitable_site(w)
        stage_site(w, "walker", site)
        a = w.actors["walker"]
        item = max(w.geography.tile(site.x, site.y).resources,
                   key=w.geography.tile(site.x, site.y).resources.get)
        a.inventory[item] = 12
        old_stamina, old_stock = a.stamina, dict(w.state.wilderness_stock)
        with self.assertRaisesRegex(ActionError, "Carrying capacity"):
            w.execute("walker", "wilderness_gather",
                      {"item": item, "quantity": 1}, "overflow")
        a = w.actors["walker"]  # Failed atomic commands restore a state snapshot.
        self.assertEqual(a.stamina, old_stamina)
        self.assertEqual(w.state.wilderness_stock, old_stock)
        self.assertEqual(w.wilderness.view("walker")["cargo"], 12)
        self.assertEqual(w.wilderness.view("walker")["cargo_limit"], 12)
        w.execute("walker", "discard_goods",
                  {"item": item, "quantity": 1}, "discard-to-move")
        self.assertEqual(a.inventory[item], 11)
        self.assertEqual(w.wilderness.gather("walker", item, 1)["quantity"], 1)
        self.assertEqual(a.inventory[item], 12)
        w.assert_invariants()

    def test_stranded_character_can_discard_multiple_goods_or_gear(self):
        w = WorldEngine([Actor("walker", "human", city=CAPITAL)])
        site = suitable_site(w)
        stage_site(w, "walker", site)
        a = w.actors["walker"]
        a.inventory["herbs"] = 14
        with self.assertRaisesRegex(ActionError, "Travel cargo limit"):
            w.explore_hex("walker", site.x, site.y + 1)
        with self.assertRaises(ActionError):
            w.discard_goods("walker", "herbs", 100)
        a = w.actors["walker"]
        w.execute("walker", "discard_goods",
                  {"item": "herbs", "quantity": 3}, "drop-3")
        self.assertEqual(a.inventory["herbs"], 11)
        gear = w._mint_gear(a, "sword", 60, "crafted")
        a.equipped["weapon"] = gear.id  # Already equipped before leaving town.
        w.discard_gear("walker", gear.id)
        self.assertNotIn("weapon", a.equipped)
        self.assertNotIn(gear.id, w.gear)
        self.assertNotIn(gear.id, a.gear_ids)
        w.assert_invariants()

    def test_site_rewards_do_not_overfill_backpack(self):
        w = WorldEngine([Actor("walker", "human", city=CAPITAL)])
        site = suitable_site(w)
        stage_site(w, "walker", site)
        a = w.actors["walker"]
        a.inventory["herbs"] = 12
        with self.assertRaisesRegex(ActionError, "Carrying capacity"):
            w.execute("walker", "investigate_site",
                      {"site_id": site.id, "approach": "delve"}, "no-overfill")
        a = w.actors["walker"]
        self.assertEqual(sum(a.inventory.values()) + len(a.gear_ids), 12)
        w.assert_invariants()


class TavernTests(unittest.TestCase):
    def world(self):
        return WorldEngine([Actor("guest", "human", city=CAPITAL, gold=150)], seed=19)

    def test_room_doubles_three_regens_for_exactly_30_minutes(self):
        a, b = self.world(), self.world()
        guest, control = a.actors["guest"], b.actors["guest"]
        for who in (guest, control):
            who.hp = 1
            who.stamina = 50
            who.magic.mana = 0
        self.assertEqual(a.rent_tavern_room("guest")["boost_until"], ROOM_DURATION)
        self.assertEqual(a.tavern_system.view("guest")["room_cooldown_remaining"], 1440)
        with self.assertRaises(ActionError):
            a.rent_tavern_room("guest")
        guest = a.actors["guest"]
        a.advance(30)
        b.advance(30)
        self.assertEqual(guest.stamina - 50, 2 * (control.stamina - 50))
        self.assertEqual(guest.magic.mana, 2 * control.magic.mana)
        self.assertEqual(guest.hp - 1, 2 * (control.hp - 1))
        self.assertEqual(a.tavern_system.view("guest")["room_boost_remaining"], 0)
        before = (guest.stamina, guest.magic.mana)
        a.advance(10)
        self.assertEqual(guest.stamina - before[0], 2)
        self.assertEqual(guest.magic.mana - before[1], 1)
        a.advance(1400)
        self.assertEqual(a.tavern_system.view("guest")["room_cooldown_remaining"], 0)
        self.assertEqual(a.rent_tavern_room("guest")["gold_spent"], 12)
        a.assert_invariants()

    def test_regeneration_is_chunk_independent(self):
        a, b = self.world(), self.world()
        for w in (a, b):
            v = w.actors["guest"]
            v.hp, v.stamina, v.magic.mana = 1, 45, 0
            w.rent_tavern_room("guest")
        a.advance(38)
        for n in (4, 9, 7, 10, 8):
            b.advance(n)
        self.assertEqual((a.actors["guest"].hp, a.actors["guest"].stamina,
                          a.actors["guest"].magic.mana),
                         (b.actors["guest"].hp, b.actors["guest"].stamina,
                          b.actors["guest"].magic.mana))
        a.assert_invariants()
        b.assert_invariants()

    def test_mead_limits_reset_at_noon_and_preserve_finite_gold(self):
        w = self.world()
        actor = w.actors["guest"]
        actor.stamina = 30
        before = w.total_gold
        self.assertEqual(mead_day(719), -1)
        self.assertEqual(mead_day(720), 0)
        for count in range(6):
            result = w.buy_tavern_mead("guest")
            self.assertEqual(result["remaining"], 5 - count)
            self.assertEqual(result["stamina_gained"], 4)
        self.assertEqual(actor.hp, 12)
        self.assertEqual(actor.stamina, 54)
        self.assertEqual(actor.gold, 150 - 18)
        self.assertFalse(w.tavern_system.view("guest")["mead_available"])
        with self.assertRaisesRegex(ActionError, "cut off"):
            w.buy_tavern_mead("guest")
        w.advance(720)
        actor = w.actors["guest"]
        actor.stamina = 60
        self.assertEqual(w.tavern_system.view("guest")["mead_remaining"], 6)
        self.assertEqual(w.buy_tavern_mead("guest")["remaining"], 5)
        self.assertEqual(w.total_gold, before)
        w.assert_invariants()

    def test_mead_cannot_hospitalize_and_tavern_rejects_wilderness(self):
        w = self.world()
        actor = w.actors["guest"]
        actor.stamina = 0
        actor.hp = 2
        before = (actor.gold, actor.stamina, actor.hp)
        with self.assertRaises(ActionError):
            w.buy_tavern_mead("guest")
        actor = w.actors["guest"]
        self.assertEqual((actor.gold, actor.stamina, actor.hp), before)
        site = suitable_site(w)
        stage_site(w, "guest", site)
        with self.assertRaises(ActionError):
            w.rent_tavern_room("guest")
        with self.assertRaises(ActionError):
            w.buy_tavern_mead("guest")

    def test_checkpoint_rejects_missing_tavern_fields(self):
        w = self.world()
        snap = _encode(w.state)
        for field in ("tavern_last_room", "tavern_room_until", "tavern_mead"):
            snap["values"].pop(field)
        with self.assertRaisesRegex(ValueError, "Checkpoint class schema has changed"):
            _decode(snap)


class MultipleProductTests(unittest.TestCase):
    def world(self):
        return WorldEngine([
            Actor("owner", "human", city=CAPITAL, gold=500),
            Actor("worker", "human", city=CAPITAL, gold=100),
            Actor("intruder", "human", city=CAPITAL, gold=100),
        ], seed=42)

    def test_all_recipes_use_real_goods_and_valid_equipment(self):
        from medieval_world_sim.equipment import GEAR
        self.assertEqual(len(RECIPES), 17)
        for industry, products in INDUSTRY_PRODUCTS.items():
            self.assertIn(next(iter(RECIPES[industry].outputs)), products)
            for recipe in products.values():
                self.assertTrue(all(x in GOODS for x in recipe.inputs))
                self.assertTrue(all(x in GOODS or x in GEAR for x in recipe.outputs))
                self.assertTrue(all(x > 0 for x in recipe.inputs.values()))
                self.assertTrue(all(x > 0 for x in recipe.outputs.values()))

    def test_owner_switches_armor_products_without_new_company(self):
        w = self.world()
        w.execute("owner", "found_company",
                  {"company_id": "ironworks", "industry": "armorer",
                   "investment": 100}, "found")
        c = w.companies["ironworks"]
        w.hire("owner", c.id, "worker", Wage(gold=2))
        with self.assertRaises(ActionError):
            w.execute("intruder", "company_set_product",
                      {"company_id": c.id, "product": "iron_helm"}, "forge-change")
        with self.assertRaises(ActionError):
            w.execute("owner", "company_set_product",
                      {"company_id": c.id, "product": "healing_potion"}, "invalid")
        c = w.companies["ironworks"]  # Rejections restore deep-copied state.
        self.assertEqual(c.product, "")
        c.inventory.update({"steel": 2, "leather": 2})
        w.execute("owner", "company_set_product",
                  {"company_id": c.id, "product": "iron_helm"}, "helmet")
        w.shift("worker", c.id)
        self.assertEqual(w.gear[c.gear_ids[-1]].kind, "iron_helm")
        w.advance(60)
        w.execute("owner", "company_set_product",
                  {"company_id": c.id, "product": "iron_boots"}, "boots")
        w.shift("worker", c.id)
        self.assertEqual({w.gear[g].kind for g in c.gear_ids},
                         {"iron_helm", "iron_boots"})
        self.assertEqual(c.shifts_completed, 2)
        self.assertEqual(w.total_gold, w.initial_gold)
        w.assert_invariants()

    def test_apothecary_can_make_mana_tonic_and_drink_uses_potion_cooldown(self):
        w = self.world()
        w.found_company("owner", "healers", "apothecary", 100)
        c = w.companies["healers"]
        w.hire("owner", c.id, "worker", Wage(gold=3))
        w.company_set_product("owner", c.id, "mana_tonic")
        c.inventory.update({"herbs": 2, "coal": 1})
        w.shift("worker", c.id)
        self.assertEqual(c.inventory["mana_tonic"], 1)
        actor = w.actors["owner"]
        actor.inventory["mana_tonic"] = 1
        actor.magic.mana = 0
        w.consume("owner", "mana_tonic")
        self.assertEqual(actor.magic.mana, 10)
        self.assertEqual(actor.inventory["mana_tonic"], 0)
        self.assertGreater(actor.cooldowns.potion, w.minute)
        w.assert_invariants()

    def test_company_checkpoint_rejects_missing_product_field(self):
        w = self.world()
        w.found_company("owner", "oldforge", "forge", 100)
        encoded = _encode(w.companies["oldforge"])
        encoded["values"].pop("product")
        with self.assertRaisesRegex(ValueError, "Checkpoint class schema has changed"):
            _decode(encoded)


class RestartTests(unittest.TestCase):
    def test_single_player_room_and_mead_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "world.json"
            game = GameSession(path)
            game.create("Inn Traveler")
            game.action("start_city_contract",
                        {"contract_id": "warrior_patrol"}, "stamina-used")
            game.action("rent_tavern_room", {}, "room")
            game.action("buy_tavern_mead", {}, "drink")
            before = game.snapshot()["tavern"]
            loaded = GameSession(path)
            self.assertEqual(loaded.snapshot()["tavern"], before)
            self.assertEqual(loaded.world.actors["hero"].gold,
                             game.world.actors["hero"].gold)
            loaded.world.assert_invariants()

    def test_multiplayer_tavern_replay_and_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "world.sqlite3"
            game = MultiplayerGame(path, require_invites=False,
                                   dev_fast_forward=True, npc_enabled=False)
            try:
                user = game.register("tavernguest", "correct horse battery staple",
                                     "Tavern Guest")
                game.action(user, "start_city_contract",
                            {"contract_id": "warrior_patrol"}, "work")
                rented = game.action(user, "rent_tavern_room", {}, "room")
                self.assertEqual(game.action(user, "rent_tavern_room", {}, "room"),
                                 rented)
                mead = game.action(user, "buy_tavern_mead", {}, "mead")
                self.assertEqual(game.action(user, "buy_tavern_mead", {}, "mead"), mead)
                before = game.snapshot(user)["tavern"]
            finally:
                game.close()
            reopened = MultiplayerGame(path, require_invites=False,
                                       dev_fast_forward=True, npc_enabled=False)
            try:
                self.assertEqual(reopened.snapshot(user)["tavern"], before)
                reopened.world.assert_invariants()
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
