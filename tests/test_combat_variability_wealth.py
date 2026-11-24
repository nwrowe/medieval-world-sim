"""Focused combat RNG, narrative and wealth Renown checks."""
import unittest
from unittest.mock import patch

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.systems.merits import net_worth_estimate
from medieval_world_sim.web.projection import _named_duel_log


class CombatVariabilityTests(unittest.TestCase):
    def world(self):
        return WorldEngine([Actor("hero", "human", gold=100),
                            Actor("rival", "human", gold=100)])

    def test_miss_consumes_stamina_and_named_counter_can_crit(self):
        w = self.world()
        w.start_duel("hero", "rival")
        with patch.object(w.combat, "_duel_rolls",
                          side_effect=[(0, 50, 100), (50, 0, 100)]):
            result = w.duel_turn("hero", "fists", "")
        self.assertEqual(result["damage"], 0)
        self.assertEqual(result["stamina_spent"], 2)
        self.assertGreater(result["retaliation"], 0)
        log = _named_duel_log(w.state.duels["hero"].log,
                              {"hero": "Tadersalad", "rival": "Lucille"})[-1]
        self.assertIn("Tadersalad punched but missed Lucille", log)
        self.assertIn("Lucille punched, critically hitting Tadersalad", log)
        self.assertTrue(w.state.duels["hero"].first_attack)

    def test_variance_and_replay_rolls(self):
        w = self.world()
        a, b = w.actors["hero"], w.actors["rival"]
        self.assertEqual(w.combat._duel_rolls(a, b), self.world().combat._duel_rolls(a, b))
        a.strength = 20
        with patch.object(w.combat, "_duel_rolls", return_value=(50, 50, 80)):
            low, _ = w.combat.duel_strike(a, b, "unarmed")
        b.hp = b.max_hp
        with patch.object(w.combat, "_duel_rolls", return_value=(50, 50, 120)):
            high, _ = w.combat.duel_strike(a, b, "unarmed")
        self.assertGreater(high, low)


class WealthRenownTests(unittest.TestCase):
    def test_threshold_and_one_time_claim(self):
        w = WorldEngine([Actor("hero", "human", gold=5000)])
        self.assertEqual(net_worth_estimate(w, w.actors["hero"]), 5000)
        rows = {row["id"]: row for row in w.merit_system.view("hero")["achievements"]}
        self.assertTrue(rows["wealth_1000"]["eligible"])
        self.assertTrue(rows["wealth_5000"]["eligible"])
        self.assertFalse(rows["wealth_10000"]["eligible"])
        w.merit_system.claim("hero", "wealth_5000")
        with self.assertRaises(ActionError):
            w.merit_system.claim("hero", "wealth_5000")
        self.assertEqual(w.state.merit_balance["hero"], 1)
