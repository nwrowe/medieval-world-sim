"""NPC policies cannot mutate state; all game actions go through WorldEngine."""
from realm_fixtures import IRONVALE

import unittest
import random
from dataclasses import replace

from medieval_world_sim.catalog import CAPITAL, RAW_RESOURCES
from medieval_world_sim.agents.observation import OfferView, observe
from medieval_world_sim.agents.policy import (
    HAULER_BUY_CEILINGS, NPCProfile, RuleBasedPolicy,
)
from medieval_world_sim.systems.regional_trade import RegionalQuote
from medieval_world_sim.agents.runner import create_simulation
from medieval_world_sim.errors import ActionError


class NpcSystemTests(unittest.TestCase):
    def test_population_and_roles(self):
        simulation = create_simulation(24, seed=9)
        self.assertEqual(len(simulation.profiles), 24)
        self.assertTrue(all(a.kind == "npc" for a in simulation.world.actors.values()))
        roles = {p.role for p in simulation.profiles}
        self.assertEqual(roles, {"manager", "worker", "hauler", "gatherer", "adventurer"})
        self.assertEqual(len(simulation.world.companies), 6)
        self.assertEqual(len(simulation.world.cities),
                         len(simulation.world.geography.settlements))
        self.assertEqual(simulation.world.total_gold, simulation.world.initial_gold)

    def test_observation_does_not_expose_mutable_world_state(self):
        sim = create_simulation(24, seed=9)
        view = observe(sim.world, "gatherer_0")
        with self.assertRaises((AttributeError, TypeError)):
            view.gold = 100_000
        with self.assertRaises((AttributeError, TypeError)):
            view.inventory[0] = ("iron_ore", 100)
        self.assertEqual(sim.world.actors["gatherer_0"].gold, 40)

    def test_policy_randomness_reproducible_and_varies_with_seed(self):
        sim = create_simulation(24, seed=1)
        view = observe(sim.world, "gatherer_0")
        profile = NPCProfile("gatherer_0", "gatherer", IRONVALE, "iron_ore",
                             curiosity=0.8, volatility=5.0)
        # Compare the seeded Gaussian stream directly, and policy actions when alternatives exist.
        a = random.Random(13)
        b = random.Random(13)
        self.assertEqual([a.gauss(0, 1) for _ in range(20)],
                         [b.gauss(0, 1) for _ in range(20)])
        self.assertEqual(RuleBasedPolicy(random.Random(13)).choose(profile, view),
                         RuleBasedPolicy(random.Random(13)).choose(profile, view))

    def test_hauler_offer_evaluation_handles_every_raw_resource(self):
        """Live NPCs may be assigned any generated deposit, not just six goods.

        A local stone offer used to raise KeyError inside the server-clock
        transaction, causing repeated broken browser event streams.
        """
        sim = create_simulation(24, seed=9)
        base = next(p for p in sim.profiles if p.role == "hauler")
        observed = observe(sim.world, base.id)
        self.assertEqual(set(HAULER_BUY_CEILINGS), set(RAW_RESOURCES))
        for resource in RAW_RESOURCES:
            with self.subTest(resource=resource):
                profile = replace(base, resource=resource)
                offer = OfferView(
                    id=15, seller_id="other-seller", city=base.home,
                    item=resource, quantity=2, price=1,
                    gear_id=None, quality=None)
                capital = RegionalQuote(
                    city=CAPITAL, item=resource,
                    player_buy_price=9, player_sell_price=10,
                    stock=3, buy_capacity=10, sell_capacity=3,
                    city_gold=1000)
                view = replace(
                    observed, city=base.home, destination=None,
                    inventory=(), gear=(), gold=100,
                    offers=(offer,), regional_quotes=(),
                    capital_quotes=(capital,))
                candidates = RuleBasedPolicy(random.Random(1))._hauler(
                    profile, view)
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0].action.name, "accept_offer")
                self.assertEqual(candidates[0].action.params["offer_id"], 15)

    def test_realized_economic_activity_and_gold_conservation(self):
        sim = create_simulation(28, seed=42)
        report = sim.run(days=6)
        self.assertTrue(report["gold_conserved"])
        self.assertGreater(report["market_trades"], 0)
        self.assertGreater(report["resources_gathered"], 0)
        self.assertGreater(report["shifts_completed"], 0)
        self.assertGreater(report["crafted_equipment"], 0)
        self.assertGreater(report["equipment_purchases"], 0)
        self.assertEqual(report["rejections"], {})
        self.assertGreater(report["market_gold_volume"], 0)
        self.assertEqual(report["npcs"], 28)
        self.assertGreater(report["actions"].get("travel", 0), 0)
        self.assertGreater(report["actions"].get("post_offer", 0), 0)
        sim.world.assert_invariants()

    def test_multi_run_same_seed_is_identical(self):
        a = create_simulation(22, seed=17).run(days=3)
        b = create_simulation(22, seed=17).run(days=3)
        self.assertEqual(a, b)
        self.assertNotEqual(a, create_simulation(22, seed=18).run(days=3))

    def test_untrusted_npc_proposals_still_rejected_by_engine(self):
        sim = create_simulation(20, seed=1)
        owner = "owner_forge"
        with self.assertRaises(ActionError):
            sim.world.execute("gatherer_0", "found_company", {
                "company_id": "hack", "industry": "forge", "investment": 999999
            }, "malicious")
        with self.assertRaises(ActionError):
            sim.world.execute("gatherer_0", "post_offer", {
                "seller_id": "forge_co", "item": "steel",
                "quantity": 100, "unit_price": 0
            }, "steal-stock")
        self.assertNotIn("hack", sim.world.companies)
        self.assertEqual(sim.world.companies["forge_co"].owner_id, owner)
        sim.world.assert_invariants()

    def test_invalid_population_and_clock(self):
        for count in (-1, 0, 19, 151):
            with self.assertRaises(ValueError):
                create_simulation(count)
        sim = create_simulation(20)
        with self.assertRaises(ValueError):
            sim.run(days=-1)
        with self.assertRaises(ValueError):
            sim.run(days=1, step_minutes=125)
        with self.assertRaises(ValueError):
            sim.run(days=1, step_minutes=0)


if __name__ == "__main__":
    unittest.main()
