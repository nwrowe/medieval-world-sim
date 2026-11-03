"""Guild and merit foundations: authority, replay, accounting and safe war schema."""
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.systems.guilds import WarRules, WarRecord, reward_proposal
from medieval_world_sim.web.session import GameSession


class GuildMembershipTests(unittest.TestCase):
    def setUp(self):
        self.world = WorldEngine([
            Actor("leader", "human", gold=240),
            Actor("second", "human", gold=200),
            Actor("third", "human", gold=200),
        ])

    def test_found_invite_join_roles_and_leader_guards(self):
        world = self.world
        gold = world.total_gold
        founding = world.found_guild("leader", "The Lantern Watch")
        self.assertEqual(world.actors["leader"].gold, 140)
        self.assertEqual(world.total_gold, gold)
        with self.assertRaises(ActionError):
            world.found_guild("second", "the lantern watch")
        with self.assertRaises(ActionError):
            world.join_guild("second", founding["id"])
        world.invite_guild("leader", "second")
        world.join_guild("second", founding["id"])
        with self.assertRaises(ActionError):
            world.invite_guild("second", "third")
        world.set_guild_role("leader", "second", "officer")
        world.invite_guild("second", "third")
        world.join_guild("third", founding["id"])
        self.assertEqual(len(world.guild_system.membership("third").members), 3)
        with self.assertRaises(ActionError):
            world.leave_guild("leader")
        with self.assertRaises(ActionError):
            world.set_guild_role("second", "leader", "member")
        world.leave_guild("third")
        world.assert_invariants()

    def test_war_schema_is_explicitly_inert_and_rewards_are_proposals(self):
        rules = WarRules()
        self.assertEqual(rules.notice_minutes, 1440)
        self.assertEqual(rules.duration_minutes, 1440)
        self.assertTrue(rules.cumulative_score)
        self.assertTrue(rules.isolate_outside_interference)
        preview = reward_proposal(10, 40, True)
        self.assertEqual(preview, {"participation": 10, "performance": 40, "victory": 20})
        self.assertEqual(self.world.guild_system.view("leader")["war_enabled"], False)
        self.assertEqual(self.world.state.wars, {})
        self.assertTrue(WarRecord("w", "a", "b", 1440, 2880, ("x",), ("y",), 500).target_score > 0)


class MeritReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "world.json"
        self.session = GameSession(self.path)
        self.session.create("Aren Vale")

    def tearDown(self):
        self.tmp.cleanup()

    def command(self, action, params, identity):
        return self.session.action(action, params, identity)

    def test_claim_lifetime_and_permanent_road_upgrade(self):
        self.assertEqual(self.session.snapshot()["merits"]["balance"], 0)
        self.command("claim_merit", {"achievement": "first_steps"}, "first")
        self.assertEqual(self.session.snapshot()["merits"]["balance"], 1)
        with self.assertRaises(ActionError):
            self.command("claim_merit", {"achievement": "first_steps"}, "duplicate")
        with self.assertRaises(ActionError):
            self.command("claim_merit", {"achievement": "spellbound"}, "not-yet")
        self.command("unlock_magic", {"node_id": "restoration.soothe_wounds"}, "learn")
        self.command("claim_merit", {"achievement": "spellbound"}, "spell")
        before = self.session.world.estimated_travel_minutes("hero", "crownreach")
        self.command("buy_merit_upgrade", {"perk": "roadcraft"}, "roadcraft")
        self.assertEqual(self.session.snapshot()["merits"]["balance"], 0)
        self.assertEqual(self.session.snapshot()["merits"]["total_earned"], 2)
        self.assertIn("roadcraft", self.session.world.state.merit_upgrades["hero"])
        after = self.command("travel", {"destination": "crownreach"}, "travel-perk")
        self.assertLess(after, before)
        self.assertEqual(GameSession(self.path).snapshot(), self.session.snapshot())
        self.session.world.assert_invariants()

    def test_guild_founder_merit_replay_and_one_guild_limit(self):
        start = self.session.world.total_gold
        created = self.command("found_guild", {"name": "Ivory Lanterns"}, "found")
        self.assertEqual(created["name"], "Ivory Lanterns")
        self.command("claim_merit", {"achievement": "guild_founder"}, "founder")
        self.assertEqual(self.session.snapshot()["merits"]["balance"], 1)
        self.assertEqual(self.session.snapshot()["guilds"]["my_guild"]["role"], "leader")
        with self.assertRaises(ActionError):
            self.command("found_guild", {"name": "Second Banner"}, "double")
        self.assertEqual(self.session.world.total_gold, start)
        self.assertEqual(GameSession(self.path).snapshot(), self.session.snapshot())
        self.command("leave_guild", {}, "leave")
        self.assertIsNone(self.session.snapshot()["guilds"]["my_guild"])
        self.assertEqual(self.session.snapshot()["merits"]["balance"], 1)
        self.assertEqual(GameSession(self.path).snapshot(), self.session.snapshot())


if __name__ == "__main__":
    unittest.main()
