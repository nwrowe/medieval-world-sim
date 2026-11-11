"""Regression coverage for architecture boundaries, safe transactions and commands."""
from realm_fixtures import IRONVALE

import unittest
from unittest.mock import patch

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.catalog import CITIES
from medieval_world_sim.systems.travel import DEPOSIT_CAP
from medieval_world_sim.core.entities import Actor, Vitals, Progression, TravelState, Wage
from medieval_world_sim.core.transactions import transfer_gold
from medieval_world_sim.errors import ActionError
from medieval_world_sim.simulation import World as LegacyWorld


class ArchitecturalTests(unittest.TestCase):
    def world(self):
        return WorldEngine([Actor("alice", "human", gold=150), Actor("bob", "npc", gold=80)])

    def test_actor_has_explicit_composed_state_and_legacy_accessors(self):
        w = self.world()
        alice = w.actors["alice"]
        self.assertIsInstance(alice.vitals, Vitals)
        self.assertIsInstance(alice.progression, Progression)
        self.assertIsInstance(alice.travel, TravelState)
        alice.vitals.stamina = 45
        self.assertEqual(alice.stamina, 45)
        alice.level = 2
        self.assertEqual(alice.progression.level, 2)
        alice.destination = IRONVALE
        self.assertEqual(alice.travel.destination, IRONVALE)

    def test_cities_hold_mutable_state_and_keep_catalog_separate(self):
        w = self.world()
        city = w.cities[IRONVALE]
        self.assertEqual(city.name, CITIES[IRONVALE].name)
        self.assertIn("iron_ore", CITIES[IRONVALE].deposits)
        old = city.deposits["iron_ore"]
        w.advance(60)
        expected = min(DEPOSIT_CAP, old + CITIES[IRONVALE].deposits["iron_ore"])
        self.assertEqual(w.cities[IRONVALE].deposits["iron_ore"], expected)
        self.assertEqual(w.deposits[IRONVALE]["iron_ore"], expected)

    def test_services_are_composed_not_inherited(self):
        w = self.world()
        self.assertNotIn("CombatMixin", [base.__name__ for base in type(w).__mro__])
        self.assertIs(w.combat.world, w)
        self.assertIs(w.travel.world, w)
        self.assertIs(w.resources.world, w)
        self.assertIs(w.market.world, w)
        self.assertIs(w.companies_system.world, w)

    def test_transaction_rolls_back_partial_purchase_if_later_check_fails(self):
        w = self.world()
        before = (w.actors["alice"].gold, w.crown_gold, len(w.gear), len(w.events))
        original_check = w.assert_invariants
        with patch.object(w, "assert_invariants", side_effect=RuntimeError("test failure")):
            with self.assertRaises(RuntimeError):
                w.buy_starter_gear("alice", "sword")
        self.assertEqual(before, (w.actors["alice"].gold, w.crown_gold, len(w.gear), len(w.events)))
        original_check()
        sword_id = w.buy_starter_gear("alice", "sword")
        self.assertEqual(sword_id, 1)  # Failed purchase did not consume an item ID.

    def test_client_command_is_idempotent(self):
        w = self.world()
        first = w.execute("alice", "buy_starter_gear", {"kind": "sword"}, "buy-001")
        before = (w.total_gold, w.actors["alice"].gold, len(w.gear), len(w.events))
        same = w.execute("alice", "buy_starter_gear", {"kind": "sword"}, "buy-001")
        self.assertEqual(first, same)
        self.assertEqual(before, (w.total_gold, w.actors["alice"].gold, len(w.gear), len(w.events)))
        self.assertTrue(any(e.action_id == "buy-001" for e in w.events))
        self.assertEqual(w.events[-1].data["buyer_id"], "alice")
        self.assertEqual(w.events[-1].schema_version, 1)
        self.assertEqual(list(range(1, len(w.events) + 1)), [e.event_id for e in w.events])
        with self.assertRaises(ActionError):
            w.execute("alice", "buy_starter_gear", {"kind": "shield"}, "buy-001")
        with self.assertRaises(ActionError):
            w.execute("bob", "buy_starter_gear", {"kind": "sword"}, "buy-001")

    def test_owner_validation_is_shared_by_direct_and_command_routes(self):
        w = self.world()
        w.found_company("alice", "forge", "forge", 50)
        before = w.total_gold
        with self.assertRaises(ActionError):
            w.execute("bob", "post_offer",
                      {"seller_id": "forge", "item": "timber", "quantity": 1, "unit_price": 1},
                      "spoofed")
        self.assertEqual(w.total_gold, before)
        self.assertEqual(w.offers, {})
        with self.assertRaises(ActionError):
            w.execute("alice", "__dict__", {}, "bad")
        with self.assertRaises(ActionError):
            w.execute("alice", "attack", {"defender_id": "bob", "extra": 1}, "extra")

    def test_concurrent_retries_make_one_purchase(self):
        from concurrent.futures import ThreadPoolExecutor
        w = self.world()
        command = lambda _: w.execute("alice", "buy_starter_gear", {"kind": "sword"}, "same-key")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(command, range(20)))
        self.assertEqual(set(results), {1})
        self.assertEqual(len(w.gear), 1)
        self.assertEqual(w.actors["alice"].gold, 134)
        self.assertEqual(w.total_gold, w.initial_gold)

    def test_company_gold_uses_transaction_path(self):
        w = self.world()
        w.found_company("alice", "forge", "forge", 40)
        self.assertEqual(w.actors["alice"].gold, 110)
        self.assertEqual(w.companies["forge"].gold, 40)
        with self.assertRaises(ActionError):
            transfer_gold(w, w.companies["forge"], w.actors["bob"], 41)
        self.assertEqual(w.companies["forge"].gold, 40)
        self.assertEqual(w.total_gold, w.initial_gold)

    def test_legacy_baseline_is_available_independently(self):
        old = LegacyWorld.create(5, seed=1)
        self.assertEqual(old.summary()["citizens"], 5)
        self.assertEqual(len(self.world().cities), len(CITIES))


if __name__ == "__main__":
    unittest.main()
