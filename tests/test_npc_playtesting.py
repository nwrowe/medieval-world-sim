"""Behavioral playtest instrumentation must not bypass WorldEngine authority."""
import unittest

from medieval_world_sim.agents.cognition import NPCMemory, Needs
from medieval_world_sim.agents.critics import (
    HeuristicCritic, OpenAIChatCritic, PlaytestObserver, ReflectionRequest,
    validate_model_report, aggregate_issues,
)
from medieval_world_sim.agents.observation import observe
from medieval_world_sim.agents.policy import NPCAction, NPCProfile, RuleBasedPolicy
from medieval_world_sim.agents.runner import create_simulation
from medieval_world_sim.errors import ActionError


class PlaytestAgentTests(unittest.TestCase):
    def test_opt_in_only_and_real_actor_rules(self):
        baseline = create_simulation(20, seed=17)
        self.assertEqual(len(baseline.profiles), 20)
        self.assertEqual(baseline.observers, {})
        self.assertTrue(all(a.kind == "npc" for a in baseline.world.actors.values()))
        demo = create_simulation(20, seed=17, playtesters=True, reflection_every=3)
        self.assertEqual(len(demo.profiles), 22)
        self.assertEqual(set(demo.observers),
                         {"playtest_explorer", "playtest_optimizer"})
        self.assertTrue(all(demo.world.actors[key].kind == "human"
                            for key in demo.observers))
        self.assertEqual(demo.world.actors["playtest_explorer"].lineage, "elf")
        self.assertEqual(demo.world.actors["playtest_optimizer"].lineage, "human")
        self.assertEqual(demo.world.actors["playtest_explorer"].gold, 240)
        self.assertEqual(demo.world.total_gold, demo.world.initial_gold)

    def test_needs_are_detached_and_action_memory_is_bounded(self):
        sim = create_simulation(20, seed=4, playtesters=True)
        view = observe(sim.world, "playtest_explorer", include_progression=True)
        self.assertTrue(view.magic_eligible)
        self.assertTrue(view.courses)
        with self.assertRaises((AttributeError, TypeError)):
            view.gold = 99_999
        needs = Needs.from_view(view, curiosity=.8)
        self.assertTrue(0 <= needs.liquidity <= 1)
        memory = NPCMemory()
        for idx in range(80):
            memory.record(view, view, NPCAction("complete_city_contract",
                          {"contract_id": "labor_shift"}), ())
        self.assertEqual(memory.decision_count, 80)
        self.assertEqual(len(memory.recent), 48)
        self.assertLess(memory.utility_modifier(
            NPCAction("complete_city_contract"), view, .9), 2)
        self.assertEqual(sim.world.actors["playtest_explorer"].gold, 240)

    def test_live_playtest_creates_evidence_and_preserves_gold(self):
        sim = create_simulation(20, seed=29, playtesters=True, reflection_every=3)
        report = sim.run(3)
        self.assertTrue(report["gold_conserved"])
        self.assertEqual(report["npcs"], 22)
        playtest = report["playtesting"]
        self.assertEqual(set(playtest["agents"]),
                         {"playtest_explorer", "playtest_optimizer"})
        for agent in playtest["agents"].values():
            self.assertGreater(agent["memory"]["decisions"], 0)
            self.assertGreaterEqual(len(agent["reports"]), 1)
            self.assertTrue(set(agent["reports"][0]["scores"]) >= {
                "progression", "clarity", "meaningful_decisions",
                "repetition", "social_opportunities"})
            self.assertLessEqual(len(agent["memory"]["recent"]), 30)
        self.assertFalse(report["rejections"].get("ActionError: Nonempty action ID required"))
        sim.world.assert_invariants()

    def test_playtest_same_seed_is_reproducible_without_llm(self):
        a = create_simulation(20, seed=41, playtesters=True,
                              reflection_every=3).run(2)
        b = create_simulation(20, seed=41, playtesters=True,
                              reflection_every=3).run(2)
        self.assertEqual(a, b)

    def test_ai_must_obey_authority_and_no_privileged_assets(self):
        sim = create_simulation(20, seed=2, playtesters=True)
        with self.assertRaises(ActionError):
            sim.world.execute("playtest_explorer", "post_offer", {
                "seller_id": "forge_co", "item": "steel",
                "quantity": 999, "unit_price": 1,
            }, "attempt-to-take-goods")
        with self.assertRaises(ActionError):
            sim.world.execute("playtest_explorer", "regional_buy", {
                "item": "iron_ore", "quantity": 1_000_000,
            }, "attempt-to-mint-goods")
        self.assertEqual(sim.world.actors["playtest_explorer"].gold, 240)
        sim.world.assert_invariants()

    def test_models_cannot_influence_action_selection(self):
        sim = create_simulation(20, seed=5, playtesters=True)
        view = observe(sim.world, "playtest_explorer", include_progression=True)
        profile = next(p for p in sim.profiles if p.id == view.id)
        import random
        policy = RuleBasedPolicy(random.Random(7))
        action = policy.choose(profile, view, sim.memories[profile.id])
        self.assertIsNotNone(action)
        self.assertFalse(hasattr(sim.observers[profile.id].critic, "execute"))
        self.assertTrue(action.name in {
            "equip", "complete_city_contract", "unlock_magic", "practice_magic",
            "enroll_course_choice", "buy_starter_gear", "regional_buy",
            "regional_sell", "gather", "travel", "attack", "consume", "accept_offer"})

    def test_untrusted_critic_contract_is_strict(self):
        report = {"scores": {key: 7 for key in (
            "progression", "clarity", "meaningful_decisions",
            "repetition", "social_opportunities")}, "issues": [{
                "code": "possible_stall", "category": "Balance concern",
                "summary": "Maybe a stall", "evidence": "3 failed requests",
                "confidence": "medium"}], "next_experiment": "Try again"}
        validated = validate_model_report(report)
        self.assertTrue(validated["issues"][0]["unverified_hypothesis"])
        report["scores"]["progression"] = 100
        with self.assertRaises(ValueError):
            validate_model_report(report)
        report["scores"]["progression"] = 7
        report["issues"][0]["category"] = "Superuser"
        with self.assertRaises(ValueError):
            validate_model_report(report)

    def test_reflection_is_periodic_and_cannot_grant_gold(self):
        class FakeCritic:
            def __init__(self):
                self.requests = []
            def assess(self, request):
                self.requests.append(request.compact())
                return HeuristicCritic().assess(request)
        sim = create_simulation(20, seed=8, playtesters=True)
        memory = NPCMemory()
        critic = FakeCritic()
        observer = PlaytestObserver("playtest_explorer", "explorer", memory,
                                    critic=critic, every=4)
        view = observe(sim.world, "playtest_explorer", include_progression=True)
        for _ in range(3):
            memory.record(view, view, NPCAction("practice_magic"), ())
            observer.maybe_reflect(view)
        self.assertEqual(critic.requests, [])
        memory.record(view, view, NPCAction("practice_magic"), ())
        observer.maybe_reflect(view)
        self.assertEqual(len(critic.requests), 1)
        observer.maybe_reflect(view, final=True)
        self.assertEqual(len(critic.requests), 1)
        self.assertEqual(sim.world.actors["playtest_explorer"].gold, 240)
        self.assertEqual(aggregate_issues({"one": observer})["report_counts"],
                         {"one": 1})

    def test_llm_is_off_by_default_and_requires_explicit_credentials(self):
        with self.assertRaises(ValueError):
            OpenAIChatCritic("model", api_key="", timeout_seconds=2) if (
                __import__("os").environ.get("OPENAI_API_KEY") is None) else (
                    OpenAIChatCritic("model", endpoint="http://unsafe"))
        self.assertIsInstance(HeuristicCritic().assess(ReflectionRequest(
            "tester", "explorer", "session_end", 0, "crownreach", 240, 1,
            ("crownreach",), 0, {}, {}, ())), dict)

    def test_invalid_playtest_config_rejected(self):
        with self.assertRaises(ValueError):
            create_simulation(20, playtesters=True, reflection_every=0)
        with self.assertRaises(ValueError):
            create_simulation(20, playtesters="yes")


if __name__ == "__main__":
    unittest.main()
