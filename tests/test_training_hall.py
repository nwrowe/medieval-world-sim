"""Training Hall, graduated merits, wear interval and stamina economy regressions."""
from pathlib import Path
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

    def test_nine_schools_eight_courses_duration_and_replay(self):
        view = self.session.snapshot()["training_hall"]
        self.assertEqual(len(view["schools"]), 9)
        self.assertEqual(sum(len(s["courses"]) for s in view["schools"]), 72)
        self.assertEqual(DAYS, (4, 6, 8, 10, 13, 17, 22, 30))
        self.assertEqual(sum(DAYS), 110)
        start = self.action("enroll_course", {"school": "grammar"}, "enroll-1")
        self.assertEqual(start["ends_at"], 4 * 1440)
        with self.assertRaises(ActionError):
            self.action("enroll_course", {"school": "latin"}, "duplicate")
        before_intel = self.session.snapshot()["player"]["work"]["intelligence"]
        self.session.advance(4 * 1440 - 1)
        self.assertEqual(self.session.snapshot()["player"]["work"]["intelligence"], before_intel)
        self.session.advance(1)
        self.assertEqual(self.session.snapshot()["player"]["work"]["intelligence"], before_intel + 1)
        self.assertEqual(self.session.snapshot()["training_hall"]["schools"][0]["completed"], 1)
        self.assertEqual(GameSession(self.path).snapshot(), self.session.snapshot())

    def test_graduation_auto_awards_merit_once_and_capstone(self):
        before = self.session.snapshot()["player"]["work"]
        for index, days in enumerate(DAYS):
            self.action("enroll_course", {"school": "commerce"}, f"start-{index}")
            self.session.advance(days * 1440)
        snapshot = self.session.snapshot()
        self.assertEqual(snapshot["training_hall"]["schools"][-1]["completed"], 8)
        self.assertEqual(snapshot["merits"]["balance"], 1)
        self.assertEqual(snapshot["merits"]["total_earned"], 1)
        self.assertEqual(snapshot["player"]["work"]["manual"],
                         before["manual"] + sum((1, 1, 1, 2, 2, 2, 3, 4)))
        self.assertEqual(snapshot["player"]["work"]["intelligence"], before["intelligence"] + 2)
        with self.assertRaises(ActionError):
            self.action("enroll_course", {"school": "commerce"}, "repeat")
        with self.assertRaises(ActionError):
            self.action("claim_merit", {"achievement": "school:commerce"}, "duplicate-claim")
        self.assertEqual(GameSession(self.path).snapshot(), snapshot)
        self.session.world.assert_invariants()


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
