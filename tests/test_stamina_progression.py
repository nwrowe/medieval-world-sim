import unittest

from medieval_world_sim.regional_world import ActionError, Actor, RegionalWorld
from medieval_world_sim.combat import ATTACK_STAMINA_COST, xp_to_next_level


class StaminaProgressionTests(unittest.TestCase):
    def world(self):
        return RegionalWorld([Actor("a", "human"), Actor("b", "human", gold=80)])

    def test_stamina_spent_no_attack_timer_and_regenerates(self):
        w = self.world()
        for _ in range(4):
            w.attack("a", "b")
        self.assertEqual(w.actors["a"].stamina, 100 - 4 * ATTACK_STAMINA_COST)
        with self.assertRaises(ActionError):
            w.attack("a", "b")
        w.advance(15)
        self.assertEqual(w.actors["a"].stamina, 23)

    def test_regeneration_works_across_separate_advances(self):
        w1, w2 = self.world(), self.world()
        w1.attack("a", "b")
        w2.attack("a", "b")
        w1.advance(17)
        w2.advance(7)
        w2.advance(10)
        self.assertEqual(w1.actors["a"].stamina, w2.actors["a"].stamina)

    def test_leveling_increases_health_and_stats(self):
        w = self.world()
        for _ in range(4):
            w.attack("a", "b")
        player = w.actors["a"]
        self.assertGreaterEqual(player.level, 2)
        self.assertEqual(player.max_hp, 24 + 4 * (player.level - 1))
        self.assertEqual(player.strength, player.level)
        self.assertEqual(player.defense, player.level)
        self.assertLess(player.level_xp, xp_to_next_level(player.level))
        self.assertEqual(w.total_gold, w.initial_gold)

    def test_unarmed_defender_counterstrikes(self):
        w = self.world()
        outcome = w.attack("a", "b")
        self.assertGreater(outcome.retaliation, 0)

    def test_empty_stamina_rejects_action_atomically(self):
        w = self.world()
        for _ in range(5):
            w.attack("a", "b")
        before = (w.actors["a"].combat_xp, w.actors["b"].hp, w.total_gold)
        with self.assertRaises(ActionError):
            w.attack("a", "b")
        self.assertEqual(before, (w.actors["a"].combat_xp, w.actors["b"].hp, w.total_gold))


if __name__ == "__main__":
    unittest.main()
