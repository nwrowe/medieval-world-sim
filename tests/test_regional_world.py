import unittest

from medieval_world_sim.catalog import CAPITAL, CITIES, EQUIPMENT, RECIPES
from medieval_world_sim.regional_world import (
    ActionError, Actor, CARRY_LIMIT, RegionalWorld, Wage,
)


class RegionalWorldTests(unittest.TestCase):
    def build(self):
        return RegionalWorld([
            Actor("owner", "human", gold=500),
            Actor("miner", "npc", city="ironvale", gold=30),
            Actor("collier", "human", city="emberfall", gold=30),
            Actor("logger", "npc", city="greenhollow", gold=30),
        ])

    def test_exactly_four_producing_cities_plus_capital(self):
        self.assertEqual(len(CITIES), 5)
        self.assertEqual(len([c for c in CITIES if c != CAPITAL]), 4)
        self.assertIn("sword", EQUIPMENT)
        self.assertEqual(RECIPES["steelworks"].inputs, {"iron_ore": 2, "coal": 1})

    def test_travel_timing_and_no_teleporting_trade(self):
        w = self.build()
        w.gather("miner", "iron_ore", 2)
        self.assertEqual(w.travel_minutes("ironvale", "emberfall"), 160)
        self.assertEqual(w.start_travel("miner", CAPITAL), 90)
        with self.assertRaises(ActionError):
            w.gather("miner", "iron_ore")
        w.advance(89)
        self.assertEqual(w.actors["miner"].destination, CAPITAL)
        w.advance(1)
        self.assertIsNone(w.actors["miner"].destination)
        self.assertEqual(w.actors["miner"].city, CAPITAL)

    def test_stock_regeneration_and_worker_cooldown(self):
        w = self.build()
        self.assertEqual(w.deposits["ironvale"]["iron_ore"], 8)
        w.gather("miner", "iron_ore", 2)
        self.assertEqual(w.deposits["ironvale"]["iron_ore"], 6)
        with self.assertRaises(ActionError):
            w.gather("miner", "iron_ore", 1)
        w.advance(60)
        self.assertEqual(w.deposits["ironvale"]["iron_ore"], 9)
        w.gather("miner", "iron_ore", 1)

    def test_escrow_blocks_overselling_and_remote_acceptance(self):
        w = self.build()
        w.gather("miner", "iron_ore", 2)
        offer = w.post_offer("miner", "miner", "iron_ore", 2, 8)
        self.assertEqual(w.actors["miner"].inventory["iron_ore"], 0)
        gold_before = w.total_gold
        with self.assertRaises(ActionError):
            w.accept_offer("owner", "owner", offer, 1)
        self.assertEqual(w.offers[offer].quantity, 2)
        # Seller can depart, but the listing remains escrowed in Ironvale.
        w.start_travel("miner", CAPITAL)
        w.start_travel("owner", "ironvale")
        w.advance(90)
        w.accept_offer("owner", "owner", offer, 1)
        self.assertEqual(w.actors["owner"].inventory["iron_ore"], 1)
        self.assertEqual(w.offers[offer].quantity, 1)
        self.assertEqual(w.total_gold, gold_before)
        with self.assertRaises(ActionError):
            w.cancel_offer("miner", offer)  # cannot teleport escrow home
        w.start_travel("miner", "ironvale")
        w.advance(90)
        w.cancel_offer("miner", offer)
        self.assertEqual(w.actors["miner"].inventory["iron_ore"], 1)

    def test_account_authorization_and_invalid_actions_are_atomic(self):
        w = self.build()
        w.found_company("owner", "steelco", "steelworks", 200)
        w.gather("miner", "iron_ore", 2)
        offer = w.post_offer("miner", "miner", "iron_ore", 2, 3)
        before = w.total_gold, w.offers[offer].quantity
        with self.assertRaises(ActionError):
            w.accept_offer("miner", "steelco", offer, 1)
        with self.assertRaises(ActionError):
            w.post_offer("miner", "steelco", "steel", 1, 50)
        self.assertEqual((w.total_gold, w.offers[offer].quantity), before)
        with self.assertRaises(ActionError):
            w.found_company("owner", "invalid", "forge", 1_000)
        self.assertNotIn("invalid", w.companies)

    def test_full_regional_supply_chain_and_item_payroll(self):
        w = self.build()
        starting_gold = w.total_gold
        w.found_company("owner", "steelco", "steelworks", 180)
        w.found_company("owner", "forgeco", "forge", 180)

        # In-world workers produce materials where deposits actually exist.
        w.gather("miner", "iron_ore", 2)
        w.gather("collier", "coal", 1)
        w.gather("logger", "timber", 1)
        w.start_travel("miner", CAPITAL)
        w.start_travel("collier", CAPITAL)
        w.start_travel("logger", CAPITAL)
        w.advance(90)

        # Regional markets escrow goods. Companies buy and own the inputs.
        for seller, resource, quantity, price in (
            ("miner", "iron_ore", 2, 4),
            ("collier", "coal", 1, 3),
            ("logger", "timber", 1, 4),
        ):
            offer = w.post_offer(seller, seller, resource, quantity, price)
            buyer_company = "forgeco" if resource == "timber" else "steelco"
            w.accept_offer("owner", buyer_company, offer, quantity)

        # The employee receives gold from the company, not minted wages.
        w.hire("owner", "steelco", "collier", Wage(gold=5))
        gold_before_shift = w.companies["steelco"].gold
        w.shift("collier", "steelco")
        self.assertEqual(w.companies["steelco"].inventory["steel"], 1)
        self.assertEqual(w.companies["steelco"].gold, gold_before_shift - 5)
        with self.assertRaises(ActionError):
            w.shift("collier", "steelco")  # same-hour double shift

        steel = w.post_offer("owner", "steelco", "steel", 1, 20)
        w.accept_offer("owner", "forgeco", steel, 1)

        # Finished sword is a valid wages-in-kind alternative.
        w.hire("owner", "forgeco", "logger", Wage(item="sword", quantity=1))
        w.shift("logger", "forgeco")
        self.assertEqual(len(w.actors["logger"].gear_ids), 1)
        gear_id = w.actors["logger"].gear_ids[0]
        self.assertEqual(w.gear[gear_id].kind, "sword")
        self.assertGreaterEqual(w.gear[gear_id].quality, 20)
        self.assertEqual(w.companies["forgeco"].gear_ids, [])
        self.assertEqual(w.total_gold, starting_gold)
        self.assertTrue(any(e.kind == "shift_completed" for e in w.events))
        w.assert_invariants()

    def test_unbounded_city_inventory_but_road_cargo_and_failed_trade_keep_gold(self):
        w = self.build()
        w.actors["owner"].inventory["stone"] = CARRY_LIMIT
        w.gather("miner", "iron_ore", 1)
        w.start_travel("miner", CAPITAL)
        w.advance(90)
        offer = w.post_offer("miner", "miner", "iron_ore", 1, 9)
        before = w.total_gold
        with self.assertRaises(ActionError):
            w.accept_offer("owner", "owner", offer, 2)  # Invalid quantity
        self.assertEqual(w.total_gold, before)
        self.assertEqual(w.offers[offer].quantity, 1)
        # Local inventory no longer has an artificial twenty-unit ceiling.
        w.accept_offer("owner", "owner", offer, 1)
        self.assertEqual(w.actors["owner"].inventory["iron_ore"], 1)
        self.assertEqual(w.total_gold, before)
        # Leaving the capital still requires staying within road cargo limits.
        with self.assertRaises(ActionError):
            w.start_travel("owner", "ironvale")
        w.assert_invariants()

    def test_invalid_gather_and_wages(self):
        w = self.build()
        with self.assertRaises(ActionError):
            w.gather("owner", "iron_ore")
        with self.assertRaises(ActionError):
            w.gather("miner", "iron_ore", -1)
        w.found_company("owner", "forgeco", "forge", 50)
        with self.assertRaises(ActionError):
            w.hire("owner", "forgeco", "miner", Wage())
        with self.assertRaises(ActionError):
            w.hire("miner", "forgeco", "miner", Wage(gold=3))
        w.hire("owner", "forgeco", "miner", Wage(gold=1))
        with self.assertRaises(ActionError):
            w.shift("miner", "forgeco")  # at ironvale, no materials


if __name__ == "__main__":
    unittest.main()
