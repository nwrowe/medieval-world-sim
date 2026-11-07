"""Focused architecture checks for the magic tree, not economic balancing."""
import unittest
from dataclasses import FrozenInstanceError

from medieval_world_sim.content.magic_tree import (
    NODES, SCHOOLS, ROOT_ID, MAX_ACTIVE_SPECIALIZATIONS,
    MANA_REGEN_MINUTES, school_nodes,
)
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError


def world(seed=42):
    return WorldEngine([Actor("mage", "human"), Actor("other", "npc")], seed=seed)


def grant_school_xp_for_fixture(w, school, xp):
    """Only tests directly seed XP; no public command permits this."""
    magic = w.actors["mage"].magic
    magic.school_xp[school] = xp
    magic.insight_earned = sum(magic.school_xp.values()) // 50
    magic.insight = magic.insight_earned - sum(
        NODES[node_id].insight_cost for node_id in magic.unlocked)


class MagicTreeArchitectureTests(unittest.TestCase):
    def test_six_complete_schools_and_shared_root(self):
        self.assertEqual(len(SCHOOLS), 6)
        self.assertEqual(len(NODES), 37)
        self.assertIn(ROOT_ID, NODES)
        for school in SCHOOLS:
            nodes = school_nodes(school)
            self.assertEqual(len(nodes), 6)
            self.assertEqual([n.tier for n in nodes], [1, 2, 3, 3, 4, 4])
            self.assertEqual(len([n for n in nodes if n.tier == 3]), 2)
            for node in nodes:
                for parent in node.prerequisites:
                    self.assertIn(parent, NODES)
                    self.assertLess(NODES[parent].tier, node.tier)
        with self.assertRaises(TypeError):
            NODES["fake"] = NODES[ROOT_ID]

    def test_casts_require_tier_mastery_and_keep_lower_tiers_available(self):
        w = world()
        w.unlock_magic("mage", "warding.minor_shield")
        initial = w.magic_tree("mage", "warding")[0]
        self.assertTrue(initial.unlocked)   # Open for mana-funded practice.
        self.assertTrue(initial.active)
        self.assertFalse(initial.castable)  # Not learned for casting yet.
        with self.assertRaisesRegex(ActionError, "100/100"):
            w.cast_spell("mage", "warding.minor_shield")
        self.assertEqual(w.actors["mage"].magic.mana, 100)
        grant_school_xp_for_fixture(w, "warding", 50)
        self.assertFalse(w.magic_tree("mage", "warding")[1].eligible)
        with self.assertRaisesRegex(ActionError, "100/100"):
            w.unlock_magic("mage", "warding.ward_goods")
        self.assertFalse(w.magic_tree("mage", "warding")[0].mastered)
        self.assertTrue(w.magic_tree("mage", "warding")[0].can_practice)
        grant_school_xp_for_fixture(w, "warding", 80)
        self.assertTrue(w.magic_tree("mage", "warding")[1].eligible)
        w.unlock_magic("mage", "warding.ward_goods")
        with self.assertRaisesRegex(ActionError, "100/100"):
            w.cast_spell("mage", "warding.ward_goods")
        novice, applied, *_ = w.magic_tree("mage", "warding")
        self.assertTrue(novice.castable)
        self.assertFalse(applied.castable)
        w.cast_spell("mage", "warding.minor_shield")
        self.assertEqual(w.actors["mage"].magic.ward_charge, 5)
        w.actors["mage"].magic.ward_charge = 0
        grant_school_xp_for_fixture(w, "warding", 180)
        self.assertTrue(w.magic_tree("mage", "warding")[1].castable)
        w.cast_spell("mage", "warding.ward_goods")
        self.assertEqual(w.actors["mage"].magic.ward_charge, 7)
        self.assertTrue(w.magic_tree("mage", "warding")[0].castable)
        w.assert_invariants()

    def test_legacy_unlock_policy_preserves_early_tier_journal_actions(self):
        w = world()
        w.unlock_magic("mage", "restoration.soothe_wounds")
        grant_school_xp_for_fixture(w, "restoration", 50)
        with self.assertRaisesRegex(ActionError, "100/100"):
            w.unlock_magic("mage", "restoration.field_healing")
        w._legacy_magic_unlock_rules = True
        try:
            w.unlock_magic("mage", "restoration.field_healing")
        finally:
            w._legacy_magic_unlock_rules = False
        self.assertIn("restoration.field_healing", w.actors["mage"].magic.unlocked)
        self.assertFalse(w.magic_tree("mage", "restoration")[0].mastered)
        w.assert_invariants()

    def test_legacy_cast_policy_remains_replayable(self):
        w = world()
        w.unlock_magic("mage", "warding.minor_shield")
        w._legacy_spell_mastery_rules = True
        try:
            cast = w.cast_spell("mage", "warding.minor_shield")
            self.assertEqual(cast["amount"], 5)
        finally:
            w._legacy_spell_mastery_rules = False
        w.assert_invariants()

    def test_fresh_actor_can_unlock_a_novice_from_each_school(self):
        w = world()
        self.assertEqual(w.actors["mage"].magic.mana, 100)
        self.assertEqual(w.actors["mage"].magic.unlocked, {ROOT_ID})
        for school in SCHOOLS:
            node = school_nodes(school)[0]
            statuses = w.magic_tree("mage", school)
            self.assertTrue(statuses[0].eligible)
            w.execute("mage", "unlock_magic", {"node_id": node.id},
                      f"novice-{school}")
            self.assertIn(node.id, w.actors["mage"].magic.unlocked)
        self.assertEqual(w.actors["mage"].magic.insight, 0)
        self.assertEqual(len(w.actors["mage"].magic.unlocked), 7)
        self.assertEqual(w.total_gold, w.initial_gold)
        w.assert_invariants()

    def test_practice_is_seeded_mana_bounded_and_idempotent(self):
        a, b = world(seed=71), world(seed=71)
        node = "divination.read_omens"
        for w in (a, b):
            w.execute("mage", "unlock_magic", {"node_id": node}, "unlock")
        params = {"node_id": node}
        result = a.execute("mage", "practice_magic", params, "first-cast")
        self.assertEqual(result, b.execute("mage", "practice_magic", params, "first-cast"))
        before = (a.actors["mage"].magic.mana, a.actors["mage"].magic.attempts)
        self.assertEqual(a.execute("mage", "practice_magic", params, "first-cast"), result)
        self.assertEqual(before, (a.actors["mage"].magic.mana,
                                  a.actors["mage"].magic.attempts))
        self.assertEqual(result.mana_spent, 8)
        self.assertEqual(a.actors["mage"].magic.mana, 92)
        self.assertEqual(result.roll in range(1, 101), True)
        with self.assertRaises(ActionError):
            a.execute("mage", "practice_magic", {"node_id": "restoration.soothe_wounds"},
                      "first-cast")
        self.assertEqual(a.total_gold, a.initial_gold)

    def test_mana_regeneration_ignores_clock_chunking(self):
        a, b = world(), world()
        for w in (a, b):
            w.unlock_magic("mage", "alchemy.purify_reagents")
            w.practice_magic("mage", "alchemy.purify_reagents")
        a.advance(27)
        b.advance(7)
        b.advance(20)
        self.assertEqual(a.actors["mage"].magic.mana, b.actors["mage"].magic.mana)
        self.assertEqual(a.actors["mage"].magic.mana, 94)
        self.assertEqual(MANA_REGEN_MINUTES, 10)
        a.assert_invariants()
        b.assert_invariants()

    def test_school_gates_insight_prerequisites_and_no_free_mastery(self):
        w = world()
        self.assertFalse(w.magic_tree("mage", "restoration")[1].eligible)
        with self.assertRaises(ActionError):
            w.unlock_magic("mage", "restoration.field_healing")
        w.unlock_magic("mage", "restoration.soothe_wounds")
        grant_school_xp_for_fixture(w, "restoration", 50)
        with self.assertRaisesRegex(ActionError, "100/100"):
            w.unlock_magic("mage", "restoration.field_healing")
        grant_school_xp_for_fixture(w, "restoration", 80)
        w.unlock_magic("mage", "restoration.field_healing")
        self.assertEqual(w.actors["mage"].magic.insight, 0)
        with self.assertRaises(ActionError):
            w.unlock_magic("mage", "restoration.revival")
        grant_school_xp_for_fixture(w, "restoration", 200)
        w.unlock_magic("mage", "restoration.revival")
        self.assertEqual(w.actors["mage"].magic.insight, 1)
        with self.assertRaises(ActionError):
            w.unlock_magic("mage", "restoration.master_healer")
        grant_school_xp_for_fixture(w, "restoration", 350)
        with self.assertRaisesRegex(ActionError, "100/100"):
            w.unlock_magic("mage", "restoration.master_healer")
        grant_school_xp_for_fixture(w, "restoration", 420)
        w.unlock_magic("mage", "restoration.master_healer")
        self.assertIn("restoration.master_healer", w.actors["mage"].magic.unlocked)
        with self.assertRaises(ActionError):
            w.practice_magic("mage", "restoration.master_healer")  # not attuned
        w.attune_magic("mage", ("restoration.revival",))
        self.assertTrue(next(s for s in w.magic_tree("mage", "restoration")
                             if s.node_id == "restoration.master_healer").active)
        w.assert_invariants()

    def test_two_active_branches_and_attunement_switch_cooldown(self):
        w = world()
        for school, novice, applied, specialist in (
            ("warding", "minor_shield", "ward_goods", "caravan_protector"),
            ("divination", "read_omens", "trade_appraisal", "merchant_foresight"),
            ("alchemy", "purify_reagents", "potion_enhancement", "apothecary_art"),
        ):
            w.unlock_magic("mage", f"{school}.{novice}")
            grant_school_xp_for_fixture(w, school, 350)
            w.unlock_magic("mage", f"{school}.{applied}")
            w.unlock_magic("mage", f"{school}.{specialist}")
        w.attune_magic("mage", ("divination.merchant_foresight",
                               "warding.caravan_protector"))
        self.assertEqual(len(w.actors["mage"].magic.attuned_paths),
                         MAX_ACTIVE_SPECIALIZATIONS)
        with self.assertRaises(ActionError):
            w.attune_magic("mage", ("divination.merchant_foresight",
                                   "warding.caravan_protector", "alchemy.apothecary_art"))
        with self.assertRaises(ActionError):
            w.attune_magic("mage", ("alchemy.apothecary_art",))
        w.advance(360)
        w.attune_magic("mage", ("alchemy.apothecary_art",))
        self.assertEqual(w.actors["mage"].magic.attuned_paths,
                         ("alchemy.apothecary_art",))
        self.assertIn("warding.caravan_protector", w.actors["mage"].magic.unlocked)
        w.assert_invariants()

    def test_cannot_practice_while_traveling_or_defeated(self):
        w = world()
        w.unlock_magic("mage", "elemental.kindle_flame")
        w.start_travel("mage", "ironvale")
        with self.assertRaises(ActionError):
            w.execute("mage", "practice_magic",
                      {"node_id": "elemental.kindle_flame"}, "on-road")
        w.advance(90)
        w.actors["mage"].hp = 0
        with self.assertRaises(ActionError):
            w.practice_magic("mage", "elemental.kindle_flame")
        self.assertEqual(w.actors["mage"].magic.mana, 100)
        w.assert_invariants()

    def test_tree_statuses_are_immutable_and_no_hidden_income(self):
        w = world()
        overview = w.magic_tree("mage")
        self.assertEqual(len(overview), 37)
        with self.assertRaises(FrozenInstanceError):
            overview[0].unlocked = False
        before = w.total_gold
        w.unlock_magic("mage", "enchantment.etch_rune")
        w.practice_magic("mage", "enchantment.etch_rune")
        self.assertEqual(w.total_gold, before)
        self.assertEqual(w.actors["mage"].gold, 100)
        self.assertEqual([e.kind for e in w.events],
                         ["magic_unlocked", "magic_practiced"])
        w.assert_invariants()


if __name__ == "__main__":
    unittest.main()
