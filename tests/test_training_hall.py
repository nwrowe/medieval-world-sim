"""Training Hall, graduated merits, wear interval and stamina economy regressions."""
from pathlib import Path
import json
import tempfile
import unittest

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.systems.curriculum import DAYS, SCHOOLS
from medieval_world_sim.web.session import GameSession, SaveError


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
        start = self.action("enroll_course_choice", {"school": "rhetoric", "index": 0}, "enroll-1")
        self.assertEqual(start["ends_at"], 4 * 1440)
        with self.assertRaises(ActionError):
            self.action("enroll_course_choice", {"school": "latin", "index": 0}, "duplicate")
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
        world = WorldEngine([Actor("scholar", "human", city="crownreach", gold=1000)])
        before_manual = world.actors["scholar"].work.manual
        before_intelligence = world.actors["scholar"].work.intelligence
        for index, days in enumerate(DAYS):
            world.enroll_course_choice("scholar", "commerce", index)
            world.advance(days * 1440)
        view = world.curriculum_system.view("scholar")
        self.assertEqual(next(s for s in view["schools"] if s["id"] == "commerce")["completed"], 8)
        self.assertEqual(world.state.merit_balance["scholar"], 1)
        self.assertIn("school:commerce", world.state.merit_claims["scholar"])
        self.assertEqual(world.actors["scholar"].work.manual,
                         before_manual + sum((1, 1, 1, 2, 2, 2, 3, 4)))
        self.assertEqual(world.actors["scholar"].work.intelligence, before_intelligence + 2)
        with self.assertRaises(ActionError):
            world.enroll_course_choice("scholar", "commerce", 0)
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
                            {"school": "weapons", "index": 6}, "advanced-weapons")
        self.assertEqual(first["index"], 6)
        self.assertEqual(first["tuition"], 40)
        self.assertEqual(self.session.snapshot()["player"]["gold"], gold - 40)
        self.assertEqual(self.session.world.crown_gold, crown + 40)
        self.assertEqual(self.action("enroll_course_choice",
                         {"school": "weapons", "index": 6}, "advanced-weapons"), first)
        with self.assertRaises(ActionError):
            self.action("enroll_course_choice",
                        {"school": "rhetoric", "index": 0}, "double-book")
        self.assertEqual(GameSession(self.path).snapshot(), self.session.snapshot())

    def test_master_capstones_require_every_other_course_in_all_ten_tracks(self):
        from medieval_world_sim.systems.curriculum import CURRENT_SCHOOLS
        for school in CURRENT_SCHOOLS:
            with self.subTest(school=school):
                world = WorldEngine([Actor("scholar", "human", city="crownreach", gold=500)])
                before_gold = world.actors["scholar"].gold
                view = next(s for s in world.curriculum_system.view("scholar")["schools"]
                            if s["id"] == school)
                self.assertFalse(view["courses"][7]["available"])
                self.assertEqual(len(view["courses"][7]["prerequisites_missing"]), 7)
                with self.assertRaisesRegex(ActionError, "other seven courses"):
                    world.enroll_course_choice("scholar", school, 7)
                self.assertEqual(world.actors["scholar"].gold, before_gold)
                for i in (6, 2, 5, 0, 4, 1, 3):
                    world.enroll_course_choice("scholar", school, i)
                    world.advance(DAYS[i] * 1440)
                view = next(s for s in world.curriculum_system.view("scholar")["schools"]
                            if s["id"] == school)
                self.assertTrue(view["courses"][7]["available"])
                world.enroll_course_choice("scholar", school, 7)
                world.advance(DAYS[7] * 1440)
                self.assertIn("school:" + school, world.state.merit_claims["scholar"])
                self.assertEqual(world.state.merit_balance["scholar"], 1)
                world.assert_invariants()

    def test_old_ruleset_record_is_rejected_instead_of_migrated(self):
        document = json.loads(self.path.read_text())
        document["records"].append({
            "kind": "action", "name": "enroll_course_choice",
            "params": {"school": "physical", "index": 7},
            "id": "obsolete-master", "ruleset": 9,
            "recorded_at": "2026-11-18T12:00:00+00:00",
        })
        self.path.write_text(json.dumps(document))
        with self.assertRaises(SaveError):
            GameSession(self.path)

    def test_removed_school_and_free_enrollment_are_unavailable(self):
        world = WorldEngine([Actor("modern", "human", city="crownreach")])
        with self.assertRaises(ActionError):
            world.enroll_course_choice("modern", "grammar", 0)
        with self.assertRaises(ActionError):
            self.session.action("enroll_course", {"school": "rhetoric"}, "free")
        self.assertNotIn("grammar", SCHOOLS)
        self.assertNotIn("geometry", SCHOOLS)

    def test_tuition_rejected_atomically_when_not_affordable(self):
        world = WorldEngine([Actor("scholar", "human", city="crownreach", gold=5)])
        crown = world.crown_gold
        with self.assertRaises(ActionError):
            world.enroll_course_choice("scholar", "weapons", 6)
        self.assertEqual(world.actors["scholar"].gold, 5)
        self.assertEqual(world.crown_gold, crown)
        self.assertFalse(world.state.active_courses)

    def test_out_of_order_graduation_merit_is_exactly_once(self):
        world = WorldEngine([Actor("scholar", "human", city="crownreach", gold=250)])
        starting_gold = world.actors["scholar"].gold
        for index in (6, 0, 2, 5, 1, 4, 3, 7):
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
