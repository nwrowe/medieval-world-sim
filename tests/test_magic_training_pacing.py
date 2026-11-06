"""Authoritative, paced magic practice and journal-compatible mastery tests."""
from unittest import TestCase

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.content.magic_tree import (
    PRACTICE_COOLDOWN_MINUTES, PRACTICE_XP_CEILING,
)
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.checkpoint import _decode, _encode


NOVICE = "restoration.soothe_wounds"
NEXT = "restoration.field_healing"


class MagicTrainingPacingTests(TestCase):
    def world(self):
        w = WorldEngine([Actor("mage", "human", gold=240)], seed=19)
        w.unlock_magic("mage", NOVICE)
        return w

    def test_training_is_not_click_spammable_and_does_not_charge_on_rejection(self):
        w = self.world()
        result = w.execute("mage", "practice_magic", {"node_id": NOVICE}, "first")
        self.assertEqual(result.xp_gained, 1)
        first_mana = w.actors["mage"].magic.mana
        first_xp = w.actors["mage"].magic.school_xp["restoration"]
        self.assertEqual(w.magic_tree("mage", "restoration")[0].practice_ready_minute,
                         PRACTICE_COOLDOWN_MINUTES)
        self.assertFalse(w.magic_tree("mage", "restoration")[0].can_practice)
        with self.assertRaisesRegex(ActionError, "120 simulated minutes"):
            w.execute("mage", "practice_magic", {"node_id": NOVICE}, "blocked")
        self.assertEqual(w.actors["mage"].magic.mana, first_mana)
        self.assertEqual(w.actors["mage"].magic.school_xp["restoration"], first_xp)
        self.assertEqual(w.actors["mage"].magic.attempts, 1)
        w.advance(119)
        self.assertFalse(w.magic_tree("mage", "restoration")[0].can_practice)
        w.advance(1)
        self.assertTrue(w.magic_tree("mage", "restoration")[0].can_practice)
        next_session = w.execute("mage", "practice_magic",
                                 {"node_id": NOVICE}, "second")
        self.assertEqual(next_session.xp_gained, 1)
        self.assertEqual(w.actors["mage"].magic.school_xp["restoration"], 2)
        w.assert_invariants()

    def test_tier_one_100_means_mastered_and_field_healing_ready(self):
        w = self.world()
        self.assertEqual(PRACTICE_XP_CEILING[1], 80)
        for i in range(80):
            result = w.practice_magic("mage", NOVICE)
            self.assertEqual(result.xp_gained, 1)
            w.advance(PRACTICE_COOLDOWN_MINUTES)
        novice, applied, *_ = w.magic_tree("mage", "restoration")
        self.assertEqual(novice.school_xp, 80)
        self.assertTrue(novice.mastered)
        self.assertFalse(novice.can_practice)
        self.assertTrue(applied.eligible)  # No extra novice practice needed.
        self.assertEqual(w.actors["mage"].magic.insight, 1)
        with self.assertRaisesRegex(ActionError, "mastered"):
            w.practice_magic("mage", NOVICE)
        w.unlock_magic("mage", NEXT)
        self.assertTrue(w.magic_tree("mage", "restoration")[1].can_practice)
        self.assertIn(NEXT, w.actors["mage"].magic.unlocked)
        self.assertEqual(w.actors["mage"].combat_xp, 0)
        w.assert_invariants()

    def test_legacy_training_yield_replays_without_new_cooldown(self):
        w = self.world()
        w._legacy_magic_training_rules = True
        try:
            first = w.practice_magic("mage", NOVICE)
            second = w.practice_magic("mage", NOVICE)
        finally:
            w._legacy_magic_training_rules = False
        self.assertIn(first.xp_gained, (1, 6))
        self.assertIn(second.xp_gained, (1, 6))
        self.assertNotIn("restoration", w.actors["mage"].magic.next_practice_minute)
        w.assert_invariants()

    def test_old_magic_checkpoints_default_the_new_schedule(self):
        w = self.world()
        old = _encode(w.actors["mage"].magic)
        old["values"].pop("next_practice_minute")
        restored = _decode(old)
        self.assertEqual(restored.next_practice_minute, {})
        self.assertEqual(restored.school_xp, w.actors["mage"].magic.school_xp)
