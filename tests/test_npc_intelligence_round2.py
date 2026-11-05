"""Integrated regressions for mastered magic, city armories and NPC planning."""
from dataclasses import replace
import random
import unittest

from medieval_world_sim.agents.cognition import NPCMemory, TradeRoute
from medieval_world_sim.agents.observation import observe
from medieval_world_sim.agents.planning import deliver_route, recover_route
from medieval_world_sim.agents.policy import NPCAction, RuleBasedPolicy
from medieval_world_sim.agents.runner import create_simulation
from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.checkpoint import _encode, _decode
from medieval_world_sim.web.ledger import current_rows


class NPCIntelligenceRoundTwoTests(unittest.TestCase):
    def test_magic_mastery_is_identical_for_gui_and_npc(self):
        world = WorldEngine([Actor("mage", "human", gold=200)], seed=77)
        node_id = "restoration.soothe_wounds"
        world.unlock_magic("mage", node_id)
        initial = next(n for n in world.magic_tree("mage")
                       if n.node_id == node_id)
        self.assertTrue(initial.can_practice)
        self.assertFalse(initial.mastered)
        self.assertIn(node_id, [name for name, _ in observe(
            world, "mage", include_progression=True).magic_practice])
        actor = world.actors["mage"]
        actor.magic.school_xp["restoration"] = 80
        actor.magic.insight_earned = 1
        actor.magic.insight = 1
        mastered = next(n for n in world.magic_tree("mage")
                        if n.node_id == node_id)
        self.assertTrue(mastered.mastered)
        self.assertFalse(mastered.can_practice)
        self.assertTrue(mastered.active)  # Learned spells remain castable.
        self.assertNotIn(node_id, [name for name, _ in observe(
            world, "mage", include_progression=True).magic_practice])
        before = (actor.magic.mana, actor.magic.attempts)
        with self.assertRaisesRegex(ActionError, "mastered"):
            world.practice_magic("mage", node_id)
        self.assertEqual(before, (world.actors["mage"].magic.mana,
                                  world.actors["mage"].magic.attempts))
        world.assert_invariants()

    def test_city_goods_storage_is_unlimited_for_human_and_npc(self):
        world = WorldEngine([Actor("hero", "human", gold=1000),
                             Actor("trader", "npc", gold=1000)], seed=13)
        for key in ("hero", "trader"):
            actor = world.actors[key]
            actor.inventory["stone"] = 300
            with self.assertRaisesRegex(ActionError, "Travel cargo limit"):
                world.start_travel(key, "ironvale")
            world.store_goods(key, "stone", 290)
            self.assertEqual(world.actors[key].storage[CAPITAL]["stone"], 290)
            self.assertEqual(world.actors[key].inventory["stone"], 10)
            self.assertEqual(world.start_travel(key, "ironvale"), 90)
        world.advance(90)
        for key in ("hero", "trader"):
            self.assertEqual(world.actors[key].city, "ironvale")
            self.assertEqual(world.start_travel(key, CAPITAL), 90)
        world.advance(90)
        for key in ("hero", "trader"):
            world.retrieve_goods(key, "stone", 290)
            self.assertEqual(world.actors[key].inventory["stone"], 300)
            self.assertEqual(world.actors[key].storage[CAPITAL]["stone"], 0)
        world.assert_invariants()

    def test_stored_equipment_cannot_be_stolen_duplicated_or_carried(self):
        world = WorldEngine([Actor("hero", "human", gold=100),
                             Actor("trader", "npc", gold=100)], seed=13)
        hero = world.actors["hero"]
        hero.inventory["grain"] = 12
        sword = world._mint_gear(hero, "sword", 10, "capital_starter_vendor")
        with self.assertRaisesRegex(ActionError, "Travel cargo limit"):
            world.start_travel("hero", "ironvale")
        world.equip("hero", sword.id)
        with self.assertRaisesRegex(ActionError, "Unequip"):
            world.store_gear("hero", sword.id)
        world.unequip("hero", "weapon")
        world.store_gear("hero", sword.id)
        self.assertNotIn(sword.id, world.actors["hero"].gear_ids)
        self.assertIn(sword.id, world.actors["hero"].stored_gear[CAPITAL])
        snapshot = _decode(_encode(world.state))
        self.assertEqual(snapshot.actors["hero"].stored_gear[CAPITAL], [sword.id])
        self.assertIn(("gear_storage", "hero", CAPITAL, "gear",
                       str(sword.id), 1), current_rows(world))
        with self.assertRaises(ActionError):
            world.store_gear("hero", sword.id)
        with self.assertRaises(ActionError):
            world.retrieve_gear("trader", sword.id)
        with self.assertRaises(ActionError):
            world.equip("hero", sword.id)
        world.assert_invariants()
        world.start_travel("hero", "ironvale")
        world.advance(90)
        with self.assertRaises(ActionError):
            world.retrieve_gear("hero", sword.id)
        world.start_travel("hero", CAPITAL)
        world.advance(90)
        world.retrieve_gear("hero", sword.id)
        self.assertIn(sword.id, world.actors["hero"].gear_ids)
        self.assertNotIn(sword.id, world.actors["hero"].stored_gear[CAPITAL])
        world.assert_invariants()

    def test_adventurers_buy_equipment_and_can_prioritize_actual_combat(self):
        sim = create_simulation(20, seed=17, playtesters=True)
        world = sim.world
        actor = world.actors["adventurer_0"]
        profile = next(p for p in sim.profiles if p.id == actor.id)
        first = RuleBasedPolicy(random.Random(13)).choose(
            profile, observe(world, actor.id), sim.memories.setdefault(
                actor.id, NPCMemory()))
        self.assertIn(first.name, {"buy_starter_gear", "accept_offer"})
        world.buy_starter_gear(actor.id, "dagger")
        gid = actor.gear_ids[-1]
        world.equip(actor.id, gid)
        world.actors["worker_forge"].hp = 2
        view = observe(world, actor.id)
        self.assertTrue(all(t.id != "playtest_optimizer"
                            for t in view.combat_targets))
        policy = RuleBasedPolicy(random.Random(2))
        action = policy.choose(profile, view, sim.memories[actor.id])
        self.assertEqual(action.name, "attack")
        self.assertEqual(action.params["defender_id"], "worker_forge")
        outcome = world.execute(actor.id, action.name, action.params, "valid-combat")
        self.assertTrue(outcome.opponent_defeated)
        self.assertGreater(outcome.xp_gained, 0)
        self.assertGreaterEqual(outcome.gold_looted, 0)
        self.assertLessEqual(outcome.gold_looted, 10)
        world.assert_invariants()

    def test_recover_stalled_trade_once_and_store_undeliverable_goods(self):
        sim = create_simulation(20, seed=42, playtesters=True)
        view = observe(sim.world, "playtest_optimizer", include_progression=True)
        route = TradeRoute("ironvale", CAPITAL, "iron_ore", 4, 4, 20, 0)
        exhausted = replace(view, minute=4 * 1440,
                            inventory=(("iron_ore", 4),),
                            regional_quotes=tuple(
                                replace(q, buy_capacity=0) if q.item == "iron_ore" else q
                                for q in view.regional_quotes))
        self.assertIsNone(deliver_route(exhausted, route))
        fallback = recover_route(exhausted, route)
        self.assertEqual(fallback.name, "travel")
        self.assertNotIn(fallback.params["destination"], (CAPITAL, "ironvale"))
        memory = NPCMemory(active_route=route)
        memory.record_trade(exhausted, exhausted,
                            NPCAction("travel", fallback.params))
        self.assertEqual(route.recovery_attempts, 1)
        self.assertEqual(route.destination, fallback.params["destination"])
        expired = replace(exhausted, city=route.destination, minute=8 * 1440)
        recovery = recover_route(expired, route)
        self.assertEqual(recovery.name, "store_goods")
        memory.record_trade(expired, replace(expired, inventory=()),
                            NPCAction(recovery.name, recovery.params))
        self.assertIsNone(memory.active_route)
        self.assertEqual(memory.trade_abandoned, 1)
        self.assertEqual(memory.trade_completed, 0)
        self.assertEqual(memory.pending_cargo[-1]["status"], "stored_unsold")

    def test_multi_seed_engine_maintains_security_and_gold_invariants(self):
        for seed in (17, 42, 47):
            with self.subTest(seed=seed):
                sim = create_simulation(20, seed=seed, playtesters=True)
                report = sim.run(5)
                self.assertTrue(report["gold_conserved"])
                self.assertEqual(report["hauler_losing_trade_cycles"], 0)
                self.assertNotIn("ActionError: This school tier is mastered; "
                                 "practice a higher tier", report["rejections"])
                for key in ("playtest_explorer", "playtest_optimizer"):
                    metrics = report["playtesting"]["agents"][key]["outcomes"]
                    self.assertGreaterEqual(metrics["goal_action_pct"], 0)
                    self.assertLessEqual(metrics["goal_action_pct"], 100)
                    self.assertGreaterEqual(metrics["combat_attacks"], 0)
                self.assertTrue(all(cycle["source"] != cycle["destination"]
                                    for agent in report["playtesting"]["agents"].values()
                                    for cycle in agent["memory"]["trade_cycles"]))
                sim.world.assert_invariants()


if __name__ == "__main__":
    unittest.main()
