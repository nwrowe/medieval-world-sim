from realm_fixtures import IRONVALE
import unittest

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.equipment import GEAR, STARTER_PRICES, crafted_quality, rarity, suggested_value
from medieval_world_sim.regional_world import Actor, ActionError, RegionalWorld, Wage


class EquipmentCombatTests(unittest.TestCase):
    def world(self):
        return RegionalWorld([
            Actor("hero", "human", gold=600),
            Actor("rival", "human", gold=100),
            Actor("bandit", "npc", gold=35, hostile=True),
            Actor("merchant", "npc", gold=100),
        ], seed=123)

    def test_starter_gear_always_available_and_audited_gold_sink(self):
        w = self.world()
        starting_gold = w.total_gold
        for kind in GEAR:
            item_id = w.buy_starter_gear("hero", kind)
            self.assertEqual(w.gear[item_id].quality, 10)
            self.assertEqual(w.gear[item_id].origin, "capital_starter_vendor")
        self.assertEqual(w.crown_gold, sum(STARTER_PRICES.values()))
        self.assertEqual(w.total_gold, starting_gold)
        w.assert_invariants()

    def test_starter_purchase_restricted_by_location_and_funds(self):
        w = self.world()
        trip = w.start_travel("hero", IRONVALE)
        w.advance(trip)
        before = w.total_gold
        with self.assertRaises(ActionError):
            w.buy_starter_gear("hero", "sword")
        self.assertEqual(w.total_gold, before)
        with self.assertRaises(ActionError):
            w.buy_starter_gear("hero", "healing_potion")
        # Repeated purchases are possible, but not without money.
        trip = w.start_travel("hero", CAPITAL)
        w.advance(trip)
        w.actors["hero"].gold = 0
        w.initial_gold = w.total_gold
        with self.assertRaises(ActionError):
            w.buy_starter_gear("hero", "sword")

    def test_quality_produces_rare_value_and_deterministic_results(self):
        seq = [crafted_quality(33, "smith", "forge", 60, i) for i in range(1000)]
        self.assertEqual(seq, [crafted_quality(33, "smith", "forge", 60, i) for i in range(1000)])
        self.assertTrue(all(20 <= q <= 100 for q in seq))
        self.assertTrue(any(q >= 95 for q in seq))
        self.assertLess(sum(q >= 95 for q in seq), 60)
        self.assertEqual(rarity(10), "rough")
        self.assertEqual(rarity(99), "legendary")
        w = self.world()
        low_id = w.buy_starter_gear("hero", "sword")
        high = w._mint_gear(w.actors["rival"], "sword", 99, "crafted")
        self.assertGreater(suggested_value(high), suggested_value(w.gear[low_id]))

    def test_individual_gear_escrow_and_quality_survive_purchase(self):
        w = self.world()
        original_id = w.buy_starter_gear("hero", "sword")
        w.equip("hero", original_id)
        offer = w.post_equipment_offer("hero", "hero", original_id, 22)
        self.assertNotIn(original_id, w.actors["hero"].gear_ids)
        self.assertNotIn("weapon", w.actors["hero"].equipped)
        before = w.total_gold
        with self.assertRaises(ActionError):
            w.post_equipment_offer("hero", "hero", original_id, 22)
        with self.assertRaises(ActionError):
            w.accept_offer("hero", "hero", offer, 1)
        with self.assertRaises(ActionError):
            w.accept_offer("rival", "rival", offer, 2)
        w.accept_offer("rival", "rival", offer, 1)
        self.assertEqual(w.gear[original_id].quality, 10)
        self.assertIn(original_id, w.actors["rival"].gear_ids)
        self.assertNotIn(offer, w.offers)
        self.assertEqual(w.total_gold, before)
        with self.assertRaises(ActionError):
            w.accept_offer("rival", "rival", offer, 1)
        w.assert_invariants()

    def test_gear_offer_cancellation_returns_exact_item(self):
        w = self.world()
        sword = w.buy_starter_gear("hero", "sword")
        offer = w.post_equipment_offer("hero", "hero", sword, 20)
        w.cancel_offer("hero", offer)
        self.assertIn(sword, w.actors["hero"].gear_ids)
        self.assertNotIn(offer, w.offers)
        w.assert_invariants()

    def test_fists_and_unrestricted_attacks(self):
        w = self.world()
        first = w.attack("hero", "merchant")
        self.assertGreater(first.damage, 0)
        self.assertGreater(first.retaliation, 0)
        w.attack("rival", "hero")
        self.assertEqual(w.actors["hero"].stamina, 80)
        with self.assertRaises(ActionError):
            w.attack("hero", "hero")

    def test_armor_reduces_damage_and_equipping_is_slot_limited(self):
        a, b = self.world(), self.world()
        for w in (a, b):
            sword = w.buy_starter_gear("hero", "sword")
            w.equip("hero", sword)
        leather = b.buy_starter_gear("bandit", "leather_armor")
        b.equip("bandit", leather)
        hit_without_armor = a.attack("hero", "bandit").damage
        hit_with_armor = b.attack("hero", "bandit").damage
        self.assertLess(hit_with_armor, hit_without_armor)
        shield = b.buy_starter_gear("bandit", "shield")
        b.equip("bandit", shield)
        self.assertEqual(b.actors["bandit"].equipped["offhand"], shield)
        with self.assertRaises(ActionError):
            b.equip("hero", shield)

    def test_xp_then_gold_loot_only_once_on_defeat(self):
        w = self.world()
        sword = w.buy_starter_gear("hero", "sword")
        w.equip("hero", sword)
        before = w.total_gold
        rewards = []
        for _ in range(10):
            result = w.attack("hero", "bandit")
            rewards.append(result.gold_looted)
            self.assertGreaterEqual(result.xp_gained, 1)
            if result.opponent_defeated:
                break
            # No cooldown; stamina allows consecutive attacks.
        self.assertTrue(result.opponent_defeated)
        self.assertEqual(sum(rewards), min(10, 35))
        self.assertEqual(w.actors["bandit"].gold, 25)
        self.assertGreater(w.actors["hero"].combat_xp, 0)
        self.assertEqual(w.total_gold, before)
        with self.assertRaises(ActionError):
            w.attack("hero", "bandit")  # can't repeatedly loot defeated body
        w.advance(60)
        self.assertEqual(w.actors["bandit"].hp, 24)
        w.assert_invariants()

    def test_pvp_does_not_require_consent(self):
        w = self.world()
        self.assertFalse(w.actors["rival"].pvp_opt_in)
        self.assertGreater(w.attack("hero", "rival").damage, 0)

    def test_equipment_wear_breaks_and_removes_invalid_equipped_reference(self):
        w = self.world()
        sword = w.buy_starter_gear("hero", "sword")
        w.equip("hero", sword)
        w.gear[sword].durability = 1
        # One durability point now requires twelve strikes. Trigger the
        # wear counter directly so the test isolates breakage from combat.
        for _ in range(12):
            w.combat._wear(w.actors["hero"], sword)
        self.assertNotIn(sword, w.gear)
        self.assertNotIn("weapon", w.actors["hero"].equipped)
        with self.assertRaises(ActionError):
            w.equip("hero", sword)
        w.assert_invariants()

    def test_equipment_wage_from_company_is_unique_and_worth_more_than_starter(self):
        w = self.world()
        w.found_company("hero", "forge", "forge", 100)
        # A company must consume actual inputs to mint one crafted sword.
        w.companies["forge"].inventory.update({"steel": 1, "timber": 1})
        w.hire("hero", "forge", "rival", Wage(item="sword", quantity=1))
        w.shift("rival", "forge")
        self.assertEqual(w.companies["forge"].gear_ids, [])
        self.assertEqual(len(w.actors["rival"].gear_ids), 1)
        item = w.gear[w.actors["rival"].gear_ids[0]]
        self.assertGreaterEqual(item.quality, 20)
        self.assertEqual(item.origin, "crafted")
        w.equip("rival", item.id)
        self.assertEqual(w.actors["rival"].equipped["weapon"], item.id)
        w.assert_invariants()


if __name__ == "__main__":
    unittest.main()
