"""Food, owner-controlled employment, workmanship and finite city purchases."""
import unittest

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor, Wage
from medieval_world_sim.errors import ActionError
from medieval_world_sim.core.quality import company_quality


class CompanyEconomyTests(unittest.TestCase):
    def world(self):
        return WorldEngine([
            Actor("owner", "human", gold=600),
            Actor("worker", "npc", gold=100),
            Actor("customer", "human", gold=100)
        ], seed=42)

    def test_consumables_are_owned_and_restore_without_overhealing(self):
        w = self.world()
        customer = w.actors["customer"]
        customer.hp = 10
        customer.stamina = 70
        customer.vitals.hunger = 2
        customer.inventory.update({"bread": 1, "healing_potion": 1})
        before = w.total_gold
        self.assertEqual(w.consume("customer", "bread"), (1, 10, 1))
        self.assertEqual(w.consume("customer", "healing_potion"), (8, 0, 0))
        self.assertEqual((customer.hp, customer.stamina, customer.vitals.hunger),
                         (19, 80, 1))
        self.assertEqual(customer.inventory["bread"], 0)
        with self.assertRaises(ActionError):
            w.consume("customer", "bread")
        with self.assertRaises(ActionError):
            w.consume("customer", "steel")
        self.assertEqual(w.total_gold, before)
        w.assert_invariants()

    def test_potion_requires_missing_health(self):
        w = self.world()
        person = w.actors["customer"]
        person.stamina = 10
        person.inventory["healing_potion"] = 1
        with self.assertRaises(ActionError):
            w.consume("customer", "healing_potion")
        self.assertEqual(person.inventory["healing_potion"], 1)
        w.assert_invariants()

    def test_food_recipes_and_employment_pay(self):
        w = self.world()
        w.found_company("owner", "bakery_co", "bakery", 120)
        w.hire("owner", "bakery_co", "worker", Wage(gold=3))
        c = w.companies["bakery_co"]
        c.inventory["grain"] = 2
        w.shift("worker", "bakery_co")
        self.assertEqual(c.inventory["bread"], 3)
        self.assertEqual(w.actors["worker"].gold, 103)
        self.assertEqual(w.actors["worker"].work.experience["bakery"], 1)
        self.assertEqual(w.total_gold, w.initial_gold)

    def test_owner_chooses_wages_and_employees_accept_and_leave(self):
        w = self.world()
        w.found_company("owner", "forge_co", "forge", 150)
        with self.assertRaises(ActionError):
            w.execute("owner", "hire", {
                "company_id": "forge_co", "worker_id": "worker",
                "wage": Wage(gold=1)}, "force-hire")
        w.propose_job("owner", "forge_co", "worker", Wage(gold=4))
        self.assertNotIn("worker", w.companies["forge_co"].employees)
        w.accept_job("worker", "forge_co")
        self.assertEqual(w.companies["forge_co"].employees["worker"].gold, 4)
        with self.assertRaises(ActionError):
            w.set_wage("customer", "forge_co", "worker", Wage(gold=99))
        w.set_wage("owner", "forge_co", "worker", Wage(gold=6))
        self.assertEqual(w.companies["forge_co"].employees["worker"].gold, 6)
        w.leave_job("worker", "forge_co")
        self.assertNotIn("worker", w.companies["forge_co"].employees)
        w.assert_invariants()

    def test_multiple_perks_consume_company_inventory(self):
        w = self.world()
        w.found_company("owner", "bakery_co", "bakery", 120)
        w.hire("owner", "bakery_co", "worker", Wage(gold=2))
        w.set_perks("owner", "bakery_co", ("meal", "medical"))
        company = w.companies["bakery_co"]
        company.inventory.update({"grain": 2, "healing_potion": 1})
        w.shift("worker", "bakery_co")
        self.assertEqual(w.actors["worker"].inventory.get("bread"), 1)
        self.assertEqual(w.actors["worker"].inventory.get("healing_potion"), 1)
        self.assertEqual(company.inventory["bread"], 2)
        self.assertEqual(company.inventory["healing_potion"], 0)
        self.assertEqual(w.total_gold, w.initial_gold)
        w.assert_invariants()

    def test_quality_grows_from_real_work_and_paid_facility_upgrades(self):
        w = self.world()
        w.found_company("owner", "forge_co", "forge", 300)
        w.hire("owner", "forge_co", "worker", Wage(gold=2))
        initial = w.company_quality("forge_co").effectiveness
        w.set_perks("owner", "forge_co", ("training",))
        cost = w.upgrade_facility("owner", "forge_co")
        self.assertEqual(cost, 30)
        for _ in range(5):
            w.companies["forge_co"].inventory.update({"steel": 1, "timber": 1})
            w.shift("worker", "forge_co")
            w.advance(60)
        worker = w.actors["worker"]
        self.assertEqual(worker.work.experience["forge"], 10)
        self.assertEqual(worker.work.shifts, 5)
        self.assertEqual(worker.work.manual, 11)
        self.assertGreater(w.company_quality("forge_co").effectiveness, initial)
        self.assertGreaterEqual(w.suggested_wage("worker", "forge_co"), 2)
        self.assertEqual(w.total_gold, w.initial_gold)
        w.assert_invariants()

    def test_daily_sale_requires_stock_and_spends_finite_city_gold(self):
        w = self.world()
        w.found_company("owner", "bakery_co", "bakery", 100)
        c = w.companies["bakery_co"]
        c.inventory["bread"] = 12
        city = w.cities["crownreach"]
        before = (city.gold, c.gold, w.total_gold)
        w.advance(1440)
        self.assertGreater(c.daily_units_sold, 0)
        self.assertLess(c.daily_units_sold, 12)
        self.assertEqual(c.inventory["bread"] + c.daily_units_sold, 12)
        self.assertEqual(c.gold - before[1], c.daily_revenue)
        self.assertEqual(before[0] - city.gold, c.daily_revenue)
        self.assertEqual(w.total_gold, before[2])
        self.assertEqual(len([e for e in w.events if e.kind == "city_sale"]),
                         c.daily_units_sold)
        w.assert_invariants()

    def test_empty_city_wallet_prevents_passive_sales(self):
        w = self.world()
        w.found_company("owner", "bakery_co", "bakery", 100)
        w.companies["bakery_co"].inventory["bread"] = 10
        w.cities["crownreach"].household_gold = 0
        w.initial_gold = w.total_gold  # Fixture that starts with an empty city wallet.
        w.advance(1440)
        self.assertEqual(w.companies["bakery_co"].inventory["bread"], 10)
        self.assertEqual(w.companies["bakery_co"].daily_revenue, 0)
        self.assertEqual(w.total_gold, w.initial_gold)

    def test_background_customers_can_buy_escrowed_unique_gear(self):
        w = self.world()
        w.found_company("owner", "forge_co", "forge", 100)
        c = w.companies["forge_co"]
        c.inventory["steel"] = 1
        ignored = w.post_offer("owner", "forge_co", "steel", 1, 10)
        sword = w._mint_gear(c, "sword", 85, "crafted")
        offer = w.post_equipment_offer("owner", "forge_co", sword.id, 50)
        self.assertNotEqual(offer, sword.id)
        initial = w.total_gold
        w.advance(1440)
        self.assertNotIn(offer, w.offers)
        self.assertNotIn(sword.id, w.gear)
        self.assertIn(ignored, w.offers)
        self.assertEqual(w.total_gold, initial)
        self.assertGreater(c.daily_revenue, 0)
        w.assert_invariants()

    def test_daily_settlement_is_invariant_to_clock_chunking(self):
        a, b = self.world(), self.world()
        for w in (a, b):
            w.found_company("owner", "bakery_co", "bakery", 100)
            w.companies["bakery_co"].inventory["bread"] = 20
        a.advance(2880)
        b.advance(1440)
        b.advance(1440)
        self.assertEqual(a.total_gold, b.total_gold)
        self.assertEqual(a.cities["crownreach"].gold, b.cities["crownreach"].gold)
        self.assertEqual(a.companies["bakery_co"].inventory,
                         b.companies["bakery_co"].inventory)
        self.assertEqual([e.data for e in a.events], [e.data for e in b.events])


if __name__ == "__main__":
    unittest.main()
