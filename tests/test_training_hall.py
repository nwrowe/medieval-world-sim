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
        self.assertEqual(view["schools"][-1]["completed"], 8)
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
