"""Training Hall, graduated merits, wear interval and stamina economy regressions."""
from pathlib import Path
import json
import tempfile
import unittest

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.systems.curriculum import DAYS, SCHOOLS
from medieval_world_sim.web.session import GameSession


class CurriculumWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "world.json"
        self.session = GameSession(self.path)
        self.session.create("Elric")

    def tearDown(self):
        self.temp.cleanup()

    def action(self, name, params, suffix):
        return self.session.action(name, params, "training-" + suffix)

    def test_ten_schools_eight_courses_duration_and_replay(self):
        view = self.session.snapshot()["training_hall"]
        self.assertEqual(len(view["schools"]), 10)
        self.assertEqual(sum(len(s["courses"]) for s in view["schools"]), 80)
        self.assertEqual(DAYS, (4, 6, 8, 10, 13, 17, 22, 30))
        self.assertEqual(sum(DAYS), 110)
        start = self.action("enroll_course", {"school": "rhetoric"}, "enroll-1")
        self.assertEqual(start["ends_at"], 4 * 1440)
        with self.assertRaises(ActionError):
            self.action("enroll_course", {"school": "latin"}, "duplicate")
        before_intel = self.session.snapshot()["player"]["work"]["intelligence"]
        for _ in range(3):
            self.session.advance(1440)
        self.session.advance(1439)
        self.assertEqual(self.session.snapshot()["player"]["work"]["intelligence"], before_intel)
        self.session.advance(1)
        self.assertEqual(self.session.snapshot()["player"]["work"]["intelligence"], before_intel + 1)
        self.assertEqual(self.session.snapshot()["training_hall"]["schools"][0]["completed"], 1)
        self.assertEqual(GameSession(self.path).snapshot(), self.session.snapshot())

    def test_graduation_auto_awards_merit_once_and_capstone(self):
        # Use the domain engine directly for 110 days of simulated coursework:
        # the web adapter intentionally limits each advance to one day.
        world = WorldEngine([Actor("scholar", "human", city="crownreach")])
        before_manual = world.actors["scholar"].work.manual
        before_intelligence = world.actors["scholar"].work.intelligence
        for days in DAYS:
            world.enroll_course("scholar", "commerce")
            world.advance(days * 1440)
        view = world.curriculum_system.view("scholar")
        self.assertEqual(next(s for s in view["schools"] if s["id"] == "commerce")["completed"], 8)
        self.assertEqual(world.state.merit_balance["scholar"], 1)
        self.assertIn("school:commerce", world.state.merit_claims["scholar"])
        self.assertEqual(world.actors["scholar"].work.manual,
                         before_manual + sum((1, 1, 1, 2, 2, 2, 3, 4)))
        self.assertEqual(world.actors["scholar"].work.intelligence, before_intelligence + 2)
        with self.assertRaises(ActionError):
            world.enroll_course("scholar", "commerce")
        with self.assertRaises(ActionError):
            world.claim_merit("scholar", "school:commerce")
        world.assert_invariants()


    def test_any_course_can_be_selected_and_tuition_moves_to_crown(self):
        before = self.session.snapshot()
        self.assertEqual({s["id"] for s in before["training_hall"]["schools"]},
                         {"rhetoric", "logic", "arithmetic", "astronomy", "music",
                          "latin", "commerce", "writing", "physical", "weapons"})
        gold = before["player"]["gold"]
        crown = self.session.world.crown_gold
        first = self.action("enroll_course_choice",
                            {"school": "weapons", "index": 7}, "advanced-weapons")
        self.assertEqual(first["index"], 7)
        self.assertEqual(first["tuition"], 50)
        self.assertEqual(self.session.snapshot()["player"]["gold"], gold - 50)
        self.assertEqual(self.session.world.crown_gold, crown + 50)
        self.assertEqual(self.action("enroll_course_choice",
                         {"school": "weapons", "index": 7}, "advanced-weapons"), first)
        with self.assertRaises(ActionError):
            self.action("enroll_course_choice",
                        {"school": "rhetoric", "index": 0}, "double-book")
        self.assertEqual(GameSession(self.path).snapshot(), self.session.snapshot())

    def test_retired_grammar_replays_old_journal_but_rejects_new_enrollment(self):
        document = json.loads(self.path.read_text())
        document["records"].append({
            "kind": "action", "name": "enroll_course",
            "params": {"school": "grammar"}, "id": "historic-grammar",
            "ruleset": 8,
        })
        self.path.write_text(json.dumps(document))
        restored = GameSession(self.path)
        self.assertEqual(restored.snapshot()["training_hall"]["active"]["school"], "grammar")
        self.assertNotIn("grammar", {s["id"] for s in
                         restored.snapshot()["training_hall"]["schools"]})
        restored.advance(1440)
        self.assertEqual(GameSession(self.path).snapshot(), restored.snapshot())
        world = WorldEngine([Actor("modern", "human", city="crownreach")])
        with self.assertRaises(ActionError):
            world.enroll_course("modern", "grammar")
        with self.assertRaises(ActionError):
            restored.action("enroll_course", {"school": "rhetoric"}, "new-free-class")

    def test_tuition_rejected_atomically_when_not_affordable(self):
        world = WorldEngine([Actor("scholar", "human", city="crownreach", gold=5)])
        crown = world.crown_gold
        with self.assertRaises(ActionError):
            world.enroll_course_choice("scholar", "weapons", 7)
        self.assertEqual(world.actors["scholar"].gold, 5)
        self.assertEqual(world.crown_gold, crown)
        self.assertFalse(world.state.active_courses)

    def test_out_of_order_graduation_merit_is_exactly_once(self):
        world = WorldEngine([Actor("scholar", "human", city="crownreach", gold=250)])
        starting_gold = world.actors["scholar"].gold
        for index in (7, 0, 6, 2, 5, 1, 4, 3):
            result = world.enroll_course_choice("scholar", "physical", index)
            self.assertEqual(result["index"], index)
            world.advance(DAYS[index] * 1440)
        self.assertEqual(world.actors["scholar"].gold, starting_gold - 201)
        self.assertEqual(world.state.merit_balance["scholar"], 1)
        self.assertEqual(len(world.curriculum_system.completed_indices("scholar", "physical")), 8)
        self.assertIn("school:physical", world.state.merit_claims["scholar"])
        self.assertEqual(world.actors["scholar"].max_hp, 29)
        with self.assertRaises(ActionError):
            world.enroll_course_choice("scholar", "physical", 5)
        world.assert_invariants()



class SwingAndWearTests(unittest.TestCase):
    def setUp(self):
        self.world = WorldEngine([
            Actor("hero", "human", city="crownreach", gold=150),
            Actor("foe", "npc", city="crownreach", gold=100),
        ])
        self.hero = self.world.actors["hero"]
        self.foe = self.world.actors["foe"]

    def test_twelve_strikes_to_lose_one_weapon_durability(self):
        blade = self.world.buy_starter_gear("hero", "sword")
        self.world.equip("hero", blade)
        initial = self.world.gear[blade].durability
        for _ in range(11):
            self.world.combat._strike(self.hero, self.foe)
            # Reset the target's life; this test isolates durability math.
            self.foe.hp = self.foe.max_hp
        self.assertEqual(self.world.gear[blade].durability, initial)
        self.world.combat._strike(self.hero, self.foe)
        self.assertEqual(self.world.gear[blade].durability, initial - 1)
        self.world.assert_invariants()

    def test_guard_and_fists_cost_two_and_defense_is_free(self):
        self.world.start_duel("hero", "foe")
        self.assertEqual(self.hero.stamina, 100)
        first = self.world.duel_turn("hero", "guard", "")
        self.assertEqual(first["stamina_spent"], 2)
        self.assertEqual(self.world.actors["hero"].stamina, 98)
        before = self.world.actors["foe"].stamina
        second = self.world.duel_turn("hero", "fists", "")
        self.assertEqual(second["stamina_spent"], 2)
        self.assertEqual(self.world.actors["hero"].stamina, 96)
        self.assertEqual(self.world.actors["foe"].stamina, before)
        self.world.assert_invariants()


if __name__ == "__main__":
    unittest.main()
