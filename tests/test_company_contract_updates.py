"""Focused regression checks for timed civic jobs and safe company transfers."""
import unittest

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError


class TimedCivicJobsTests(unittest.TestCase):
    def test_pay_and_xp_only_at_completion_with_independent_daily_cooldown(self):
        w = WorldEngine([Actor("worker", "human", city=CAPITAL, gold=40)])
        before, total = w.actors["worker"].gold, w.total_gold
        started = w.start_city_contract("worker", "warrior_patrol")
        self.assertEqual(started["duration_minutes"], 180)
        self.assertEqual(w.actors["worker"].gold, before)
        self.assertEqual(w.city_contracts.active("worker")["remaining_minutes"], 180)
        self.assertEqual(w.total_gold, total)
        with self.assertRaises(ActionError):
            w.start_city_contract("worker", "labor_shift")
        w.advance(179)
        self.assertEqual(w.actors["worker"].gold, before)
        w.advance(1)
        self.assertEqual(w.actors["worker"].gold, before + 10)
        self.assertIsNone(w.city_contracts.active("worker"))
        self.assertEqual(w.total_gold, total)
        with self.assertRaises(ActionError):
            w.start_city_contract("worker", "warrior_patrol")
        self.assertEqual(w.start_city_contract("worker", "labor_shift")
                         ["duration_minutes"], 180)
        w.assert_invariants()


    def test_herb_delivery_consumes_ten_stamina_and_herbs_at_start(self):
        world = WorldEngine([
            Actor("courier", "human", city=CAPITAL, inventory={"herbs": 1})
        ])
        courier = world.actors["courier"]
        starting_stamina, starting_gold = courier.stamina, courier.gold
        started = world.start_city_contract("courier", "church_supplies")
        self.assertEqual(started["duration_minutes"], 120)
        self.assertEqual(courier.stamina, starting_stamina - 10)
        self.assertEqual(courier.inventory.get("herbs"), 0)
        self.assertEqual(courier.gold, starting_gold,
                         "wages should not be paid until the shift ends")
        world.advance(120)
        self.assertEqual(courier.gold, starting_gold + 11)
        world.assert_invariants()


class CompanyTransfersTests(unittest.TestCase):
    def test_friendly_name_applications_sale_and_asset_return(self):
        w = WorldEngine([
            Actor("seller", "human", gold=500),
            Actor("buyer", "human", gold=500),
            Actor("applicant", "human", gold=100),
        ])
        initial = w.total_gold
        w.found_named_company("seller", "Silver Oak Trading", "bakery", 100)
        ident = "silver_oak_trading"
        self.assertEqual(w.companies[ident].display_name, "Silver Oak Trading")
        with self.assertRaises(ActionError):
            w.found_named_company("seller", "Second Company", "forge", 100)
        with self.assertRaises(ActionError):
            w.company_apply("applicant", ident)
        w.company_set_hiring("seller", ident, True)
        w.company_apply("applicant", ident)
        self.assertIn("applicant", w.companies[ident].applicants)
        w.offer_job("seller", ident, "applicant", 3, "", 0)
        w.accept_job("applicant", ident)
        self.assertNotIn("applicant", w.companies[ident].applicants)
        w.companies[ident].inventory["grain"] = 2
        w.company_list_for_sale("seller", ident, 95)
        with self.assertRaises(ActionError):
            w.company_buy("seller", ident)
        w.company_buy("buyer", ident)
        self.assertEqual(w.companies[ident].owner_id, "buyer")
        self.assertEqual(w.companies[ident].sale_price, 0)
        self.assertIn("applicant", w.companies[ident].employees)
        with self.assertRaises(ActionError):
            w.company_dissolve("seller", ident)
        w.company_dissolve("buyer", ident)
        self.assertNotIn(ident, w.companies)
        self.assertEqual(w.actors["buyer"].inventory["grain"], 2)
        self.assertEqual(w.total_gold, initial)
        w.assert_invariants()


if __name__ == "__main__":
    unittest.main()
