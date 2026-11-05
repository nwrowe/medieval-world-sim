"""Regressions for route-level NPC planning, telemetry and critic signals."""
from dataclasses import replace
import unittest

from medieval_world_sim.agents.cognition import NPCMemory
from medieval_world_sim.agents.critics import (
    HeuristicCritic, PlaytestObserver, ReflectionRequest,
)
from medieval_world_sim.agents.observation import observe
from medieval_world_sim.agents.planning import deliver_route, route_candidates
from medieval_world_sim.agents.policy import NPCAction, RuleBasedPolicy
from medieval_world_sim.agents.runner import create_simulation
from medieval_world_sim.catalog import CAPITAL


class NPCPlanningTests(unittest.TestCase):
    def test_ironvale_cargo_cannot_be_sold_to_ironvale_merchant(self):
        sim = create_simulation(20, seed=42, playtesters=True)
        world = sim.world
        key = "playtest_optimizer"
        memory = sim.memories[key]
        # Use the real city travel command, then purchase normal merchant stock.
        duration = world.estimated_travel_minutes(key, "ironvale")
        world.execute(key, "travel", {"destination": "ironvale"}, "road")
        world.advance(duration)
        before = observe(world, key, include_progression=True)
        trades = [option for option in route_candidates(before)
                  if option.name == "regional_buy"
                  and option.params["item"] == "iron_ore"]
        self.assertTrue(trades)
        buy = trades[0]
        self.assertGreater(buy.projected_profit, 0)
        world.execute(key, buy.name, buy.params, "ore-bought")
        after = observe(world, key, include_progression=True)
        self.assertEqual(memory.record_trade(
            before, after, NPCAction(buy.name, buy.params)), None)
        self.assertIsNotNone(memory.active_route)
        self.assertEqual(memory.active_route.destination, CAPITAL)
        self.assertEqual(memory.active_route.cost, before.gold - after.gold)

        policy = RuleBasedPolicy(__import__("random").Random(7))
        profile = next(p for p in sim.profiles if p.id == key)
        decision = policy.choose(profile, after, memory)
        self.assertEqual(decision.name, "travel")
        self.assertEqual(decision.params, {"destination": CAPITAL})
        self.assertNotEqual(decision.name, "regional_sell")

        world.execute(key, "travel", {"destination": CAPITAL}, "return")
        world.advance(world.actors[key].arrival_minute - world.minute)
        capital = observe(world, key, include_progression=True)
        sell = policy.choose(profile, capital, memory)
        self.assertEqual(sell.name, "regional_sell")
        self.assertEqual(sell.params["item"], "iron_ore")
        world.execute(key, sell.name, sell.params, "sale")
        sold = observe(world, key, include_progression=True)
        profit = memory.record_trade(capital, sold, sell)
        self.assertIsNotNone(profit)
        self.assertGreater(profit, 0)
        self.assertIsNone(memory.active_route)
        self.assertEqual(memory.trade_completed, 1)
        self.assertEqual(memory.trade_net_profit, profit)
        self.assertEqual(world.actors[key].gold, before.gold + profit)
        world.assert_invariants()

    def test_trade_objective_learning_excludes_raw_cash_movements(self):
        sim = create_simulation(20, seed=21, playtesters=True)
        memory = NPCMemory()
        view = observe(sim.world, "playtest_optimizer", include_progression=True)
        purchase = NPCAction("regional_buy", {"item": "iron_ore", "quantity": 4})
        other = replace(view, gold=view.gold - 20,
                        inventory=(("iron_ore", 4),))
        memory.record(view, other, purchase, ("regional_bought",),
                      defer_trade_credit=True)
        self.assertNotIn("regional_buy", memory.values)
        self.assertEqual(memory.recent[-1].gold_delta, -20)
        self.assertGreater(memory.recent[-1].marked_wealth_delta, -20)

    def test_critic_flags_existing_local_loss_pattern(self):
        base = {
            "city": "ironvale", "target": "iron_ore", "ok": True,
            "level_delta": 0, "discovered": [], "error": "",
            "events": [],
        }
        recent = (
            {**base, "action": "regional_buy", "gold_delta": -20},
            {**base, "action": "regional_sell", "gold_delta": 12},
        )
        request = ReflectionRequest(
            "optimizer", "optimizer", "session_end", 720, "ironvale",
            232, 1, ("crownreach", "ironvale"), 2,
            {"regional_buy": 1, "regional_sell": 1}, {}, recent)
        report = HeuristicCritic().assess(request)
        self.assertIn("same_city_trade_loss",
                      [issue["code"] for issue in report["issues"]])
        self.assertIn("clarity", report["score_caveats"])

    def test_critic_uses_actual_skill_progress_and_route_profit(self):
        request = ReflectionRequest(
            "optimizer", "optimizer", "session_end", 6000, "crownreach",
            300, 1, ("crownreach", "ironvale"), 24,
            {"regional_sell": 1}, {},
            ({"action": "regional_sell", "ok": True, "target": "iron_ore",
              "city": "crownreach", "gold_delta": 24,
              "level_delta": 0, "discovered": [], "error": "", "events": [],
              "work_xp_delta": 0, "trade_profit": -4},),
            trade_cycles=({"source": "ironvale", "destination": "crownreach",
                           "item": "iron_ore", "spent": 28,
                           "revenue": 24, "profit": -4},))
        report = HeuristicCritic().assess(request)
        self.assertEqual(report["metrics"]["route_profit"], -4)
        self.assertEqual(report["metrics"]["completed_routes"], 1)
        self.assertIn("negative_trade_route",
                      [issue["code"] for issue in report["issues"]])

    def test_new_discovery_is_only_reported_once(self):
        sim = create_simulation(20, seed=14, playtesters=True)
        memory = NPCMemory()
        view = observe(sim.world, "playtest_explorer", include_progression=True)
        observer = PlaytestObserver("explorer", "explorer", memory, every=1)
        memory.record_arrival(360, "ironvale")
        memory.record(view, view, NPCAction("practice_magic", {"node_id": "x"}), ())
        observer.maybe_reflect(view)
        self.assertIn("new_discovery", [x["code"] for x in
                      observer.reports[-1]["issues"]])
        memory.record(view, view, NPCAction("practice_magic", {"node_id": "x"}), ())
        observer.maybe_reflect(view)
        self.assertNotIn("new_discovery", [x["code"] for x in
                         observer.reports[-1]["issues"]])

    def test_multiseed_full_engine_preserves_gold_and_never_sells_locally(self):
        for seed in (7, 29, 42):
            with self.subTest(seed=seed):
                sim = create_simulation(20, seed=seed, playtesters=True)
                report = sim.run(4)
                self.assertTrue(report["gold_conserved"])
                self.assertFalse(report["rejections"])
                optimizer = report["playtesting"]["agents"]["playtest_optimizer"]
                memory = optimizer["memory"]
                self.assertEqual(memory["trade_loss_cycles"],
                                 sum(cycle["profit"] <= 0
                                     for cycle in memory["trade_cycles"]))
                self.assertTrue(all(cycle["source"] != cycle["destination"]
                                    for cycle in memory["trade_cycles"]))
                # A failed sale must not silently abandon its purchased cargo.
                if memory["active_trade"]:
                    self.assertEqual(memory["active_trade"]["destination"], CAPITAL)
                sim.world.assert_invariants()


if __name__ == "__main__":
    unittest.main()
