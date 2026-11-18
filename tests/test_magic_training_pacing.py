"""Authoritative, paced magic practice and strict checkpoint schema tests."""
from unittest import TestCase

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.content.magic_tree import PRACTICE_XP_CEILING
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.checkpoint import _decode, _encode


NOVICE = "restoration.soothe_wounds"
NEXT = "restoration.field_healing"


class MagicTrainingPacingTests(TestCase):
    def world(self):
        w = WorldEngine([Actor("mage", "human", gold=240)], seed=19)
        w.unlock_magic("mage", NOVICE)
        return w

    def test_mana_alone_limits_repeat_practice_and_rejection_is_free(self):
        w = self.world()
        for i in range(12):
            result = w.execute("mage", "practice_magic",
                               {"node_id": NOVICE}, f"mana-session-{i}")
            self.assertEqual(result.xp_gained, 1)
            self.assertTrue(w.magic_tree("mage", "restoration")[0].can_practice)
            self.assertEqual(w.magic_tree("mage", "restoration")[0].practice_ready_minute, 0)
        self.assertEqual(w.actors["mage"].magic.mana, 4)
        self.assertEqual(w.actors["mage"].magic.school_xp["restoration"], 12)
        with self.assertRaisesRegex(ActionError, "Insufficient mana"):
            w.execute("mage", "practice_magic",
                      {"node_id": NOVICE}, "out-of-mana")
        self.assertEqual(w.actors["mage"].magic.mana, 4)
        self.assertEqual(w.actors["mage"].magic.school_xp["restoration"], 12)
        self.assertEqual(w.actors["mage"].magic.attempts, 12)
        w.advance(40)  # Existing mana regeneration, not a training timer.
        w.practice_magic("mage", NOVICE)
        self.assertEqual(w.actors["mage"].magic.school_xp["restoration"], 13)
        w.assert_invariants()

    def test_tier_one_100_means_mastered_and_field_healing_ready(self):
        w = self.world()
        self.assertEqual(PRACTICE_XP_CEILING[1], 80)
        for i in range(80):
            if w.actors["mage"].magic.mana < 8:
                w.advance(80)  # Regenerate enough mana for the next session.
            result = w.practice_magic("mage", NOVICE)
            self.assertEqual(result.xp_gained, 1)
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

    def test_training_yield_and_no_practice_timer(self):
        w = self.world()
        first = w.practice_magic("mage", NOVICE)
        second = w.practice_magic("mage", NOVICE)
        self.assertEqual(first.xp_gained, 1)
        self.assertEqual(second.xp_gained, 1)
        self.assertFalse(hasattr(w.actors["mage"].magic, "next_practice_minute"))
        w.assert_invariants()

    def test_multiple_practices_can_use_mana_without_cooldown(self):
        w = self.world()
        for _ in range(3):
            w.practice_magic("mage", NOVICE)
        self.assertEqual(w.actors["mage"].magic.school_xp["restoration"], 3)
        w.assert_invariants()

    def test_checkpoint_rejects_missing_magic_model_fields(self):
        w = self.world()
        damaged = _encode(w.actors["mage"].magic)
        damaged["values"].pop("school_xp")
        with self.assertRaisesRegex(ValueError, "schema has changed"):
            _decode(damaged)

