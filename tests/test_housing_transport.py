"""Housing, practical training and travel vehicles; finite payments and road rules."""
from realm_fixtures import IRONVALE

import unittest

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.core.entities import Actor, Wage, HousingState
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.errors import ActionError
from medieval_world_sim.content.housing import HOMES, HOME_ORDER, FACILITIES, VEHICLES


class HousingTests(unittest.TestCase):
    def world(self):
        return WorldEngine([
            Actor("owner", "human", city=CAPITAL, gold=20000),
            Actor("worker", "npc", city=CAPITAL, gold=3000),
            Actor("visitor", "human", city=IRONVALE, gold=1000),
        ], seed=19)

    def test_prices_ascending_and_house_upgrade_pays_difference(self):
        w = self.world()
        self.assertEqual(len(HOMES), 5)
        self.assertEqual(sorted(HOMES, key=lambda name: HOMES[name].price),
                         list(HOME_ORDER))
        before = w.total_gold
        self.assertEqual(w.buy_home("owner", "room"), 90)
        self.assertEqual(w.upgrade_home("owner", "cottage"), 260)
        self.assertEqual(w.upgrade_home("owner", "estate"), 3250)
        view = w.housing_view("owner")
        self.assertEqual((view.city, view.tier, view.training_bonus_pct),
                         (CAPITAL, "estate", 15))
        self.assertEqual(w.actors["owner"].gold, 20000 - 3600)
        self.assertEqual(w.crown_gold, 3600)
        with self.assertRaises(ActionError):
            w.upgrade_home("owner", "cottage")
        with self.assertRaises(ActionError):
            w.buy_home("owner", "manor")
        self.assertEqual(w.total_gold, before)
        w.assert_invariants()

    def test_horse_requires_home_and_stable_not_just_gold(self):
        w = self.world()
        with self.assertRaises(ActionError):
            w.buy_vehicle("owner", "horse")
        w.buy_home("owner", "room")
        with self.assertRaises(ActionError):
            w.build_home_facility("owner", "stable")
        w.upgrade_home("owner", "cottage")
        with self.assertRaises(ActionError):
            w.buy_vehicle("owner", "horse")
        self.assertEqual(w.build_home_facility("owner", "stable"), 180)
        self.assertEqual(w.buy_vehicle("owner", "horse"), 250)
        w.select_vehicle("owner", "horse")
        self.assertEqual(w.housing_view("owner").travel_cargo_limit, 16)
        self.assertEqual(w.estimated_travel_minutes("owner", IRONVALE), 72)
        self.assertEqual(w.start_travel("owner", IRONVALE), 72)
        w.advance(71)
        self.assertEqual(w.actors["owner"].destination, IRONVALE)
        w.advance(1)
        self.assertEqual(w.actors["owner"].city, IRONVALE)
        with self.assertRaises(ActionError):
            w.select_vehicle("owner", None)  # mount must return to home to park
        self.assertEqual(w.start_travel("owner", CAPITAL), 72)
        w.advance(72)
        w.select_vehicle("owner", None)
        self.assertEqual(w.start_travel("owner", IRONVALE), 90)
        w.assert_invariants()

    def test_carriage_reduces_road_duration_and_expands_cargo_not_local_limit(self):
        w = self.world()
        w.buy_home("owner", "estate")
        self.assertEqual(w.build_home_facility("owner", "carriage_house"), 550)
        self.assertEqual(w.buy_vehicle("owner", "carriage"), 950)
        self.assertEqual(w.estimated_travel_minutes("owner", IRONVALE), 90)
        w.select_vehicle("owner", "carriage")
        self.assertEqual(w.estimated_travel_minutes("owner", IRONVALE), 54)
        self.assertEqual(w.housing_view("owner").travel_cargo_limit, 20)
        # 18 units can travel in carriage but not on foot.
        w.actors["owner"].inventory["stone"] = 18
        self.assertEqual(w.start_travel("owner", IRONVALE), 54)
        w.advance(54)
        self.assertEqual(w.actors["owner"].city, IRONVALE)
        with self.assertRaises(ActionError):
            w.buy_home("owner", "room")
        w.assert_invariants()

    def test_transport_limits_enforced_with_equipped_gear_and_rollback(self):
        w = self.world()
        w.buy_home("owner", "cottage")
        w.build_home_facility("owner", "stable")
        w.buy_vehicle("owner", "horse")
        w.select_vehicle("owner", "horse")
        actor = w.actors["owner"]
        actor.inventory["iron_ore"] = 16
        gear = w._mint_gear(actor, "sword", 60, "crafted")
        with self.assertRaises(ActionError):
            w.start_travel("owner", IRONVALE)
        self.assertIsNone(w.actors["owner"].destination)
        # Atomic rollback replaces world state: use the current actor, not a
        # stale reference to the pre-rollback snapshot.
        w.actors["owner"].inventory["iron_ore"] = 15
        w.equip("owner", gear.id)
        self.assertEqual(w.start_travel("owner", IRONVALE), 72)
        w.assert_invariants()

    def test_missing_money_does_not_mint_property_or_vehicle(self):
        w = self.world()
        visitor = w.actors["visitor"]
        before = w.total_gold
        with self.assertRaises(ActionError):
            w.buy_home("visitor", "estate")
        self.assertEqual(visitor.housing, HousingState())
        w.buy_home("visitor", "cottage")
        with self.assertRaises(ActionError):
            w.build_home_facility("visitor", "carriage_house")
        with self.assertRaises(ActionError):
            w.buy_vehicle("visitor", "carriage")
        with self.assertRaises(ActionError):
            w.buy_home("visitor", "unknown")
        self.assertEqual(w.total_gold, before)
        w.assert_invariants()

    def test_owner_bound_action_and_idempotent_property_purchase(self):
        w = self.world()
        before = w.total_gold
        params = {"tier": "cottage"}
        self.assertEqual(w.execute("owner", "buy_home", params, "my-home"), 350)
        self.assertEqual(w.execute("owner", "buy_home", params, "my-home"), 350)
        self.assertEqual(w.actors["owner"].gold, 20000 - 350)
        with self.assertRaises(ActionError):
            w.execute("visitor", "buy_home", params, "my-home")
        with self.assertRaises(ActionError):
            w.execute("owner", "buy_home", {"tier": "manor"}, "my-home")
        self.assertEqual(w.total_gold, before)

    def test_fixed_point_home_bonus_no_rounding_exploit(self):
        w = self.world()
        actor = w.actors["owner"]
        w.buy_home("owner", "cottage")  # 5% local XP.
        total = sum(w.housing_system.training_xp(actor, 1, "work:smith")
                    for _ in range(20))
        self.assertEqual(total, 21)
        self.assertEqual(actor.housing.xp_remainders["work:smith"], 0)
        self.assertEqual(w.housing_system.training_xp(actor, 1, "magic:alchemy"), 1)
        self.assertEqual(actor.housing.xp_remainders["magic:alchemy"], 5)
        # Remote practice gets no benefit; no free XP without real training.
        actor.city = IRONVALE
        actor.discovered_cities.add(IRONVALE)  # Manual relocation mirrors arrival discovery.
        self.assertEqual(w.housing_system.training_xp(actor, 3, "work:smith"), 3)
        self.assertEqual(actor.housing.xp_remainders["work:smith"], 0)
        w.assert_invariants()

    def test_company_shifts_receive_local_home_bonus(self):
        w = self.world()
        w.buy_home("worker", "townhouse")
        w.found_company("owner", "bakery_test", "bakery", 350)
        w.hire("owner", "bakery_test", "worker", Wage(gold=2))
        w.companies["bakery_test"].inventory["grain"] = 20
        for _ in range(10):
            w.shift("worker", "bakery_test")
            w.advance(60)
        self.assertEqual(w.actors["worker"].work.experience["bakery"], 11)
        self.assertEqual(w.actors["worker"].housing.xp_remainders["work:bakery"], 0)
        w.assert_invariants()

    def test_magic_practice_uses_local_housing_experience_residue(self):
        w = self.world()
        w.buy_home("owner", "townhouse")  # 10% XP
        w.unlock_magic("owner", "alchemy.purify_reagents")
        xp = 0
        for _ in range(4):
            result = w.practice_magic("owner", "alchemy.purify_reagents")
            xp += result.xp_gained
            w.advance(120)
        self.assertEqual(xp, w.actors["owner"].magic.school_xp["alchemy"])
        self.assertIn("magic:alchemy", w.actors["owner"].housing.xp_remainders)
        w.assert_invariants()

    def test_default_characters_maintain_original_road_rules(self):
        w = self.world()
        self.assertEqual(w.housing_view("visitor").travel_cargo_limit, 12)
        self.assertEqual(w.estimated_travel_minutes("visitor", CAPITAL), 90)
        self.assertEqual(w.start_travel("visitor", CAPITAL), 90)
        w.advance(90)
        w.assert_invariants()


if __name__ == "__main__":
    unittest.main()
