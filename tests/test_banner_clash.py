"""Integration checks for fresh Banner Clash rules and solo playtesting."""
import unittest

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError


def paired_world():
    world = WorldEngine([
        Actor(f"a{i}", "human", city="crownreach", gold=200)
        for i in range(10)
    ] + [
        Actor(f"b{i}", "human", city="crownreach", gold=200)
        for i in range(10)
    ] + [Actor("outsider", "human", city="crownreach", gold=200)])
    ga = world.found_guild("a0", "Silver Stag")["id"]
    gb = world.found_guild("b0", "Blackthorn")["id"]
    for prefix, leader, guild in [("a", "a0", ga), ("b", "b0", gb)]:
        for i in range(1, 10):
            world.invite_guild(leader, f"{prefix}{i}")
            world.join_guild(f"{prefix}{i}", guild)
    return world, ga, gb


class BannerClashTests(unittest.TestCase):
    def test_weekly_enrollment_and_matching(self):
        world, ga, gb = paired_world()
        with self.assertRaises(ActionError):
            world.enlist_guild_war("a1", True)
        world.invite_guild("a0", "outsider")
        world.enlist_guild_war("a0", True)
        world.enlist_guild_war("b0", True)
        # Matching is invoked at the weekly clock boundary, not by the browser.
        world.war_system.match_week(10080)
        self.assertEqual(len(world.state.wars), 1)
        war = next(iter(world.state.wars.values()))
        self.assertEqual(war.status, "notice")
        self.assertEqual(war.scheduled_minute, 10080 + 1440)
        self.assertEqual(set(war.roster_a), {f"a{i}" for i in range(10)})
        with self.assertRaises(ActionError):
            world.leave_guild("a1")
        with self.assertRaises(ActionError):
            world.join_guild("outsider", ga)
        with self.assertRaises(ActionError):
            world.invite_guild("a0", "outsider")
        self.assertFalse(world.state.guilds[ga].enlisted)
        self.assertFalse(world.state.guilds[gb].enlisted)
        world.assert_invariants()

    def test_weekly_match_fires_from_trusted_world_clock(self):
        world, ga, gb = paired_world()
        world.enlist_guild_war("a0", True)
        world.enlist_guild_war("b0", True)
        world.advance(10080)
        war = next(iter(world.state.wars.values()))
        self.assertEqual(war.scheduled_minute, 11520)
        self.assertEqual(war.status, "notice")
        world.advance(1440)
        self.assertEqual(world.state.wars[war.id].status, "live")
        world.assert_invariants()

    def test_milestones_apply_to_all_routed_members_and_horn_is_single_use(self):
        world, ga, gb = paired_world()
        world.enlist_guild_war("a0", True)
        world.enlist_guild_war("b0", True)
        world.war_system.match_week(10080)
        war = next(iter(world.state.wars.values()))
        world.minute = war.scheduled_minute
        war.status = "live"
        war.present.update((*war.roster_a, *war.roster_b))
        war.advantage = ga
        war.unlocks[ga] = {"field_hospital", "war_horn", "final_rally"}
        for i in range(5):
            war.routed[f"a{i}"] = world.minute + 12
        world.activate_war_milestone("a0", "field_hospital")
        war = world.state.wars[war.id]
        self.assertTrue(all(war.routed[f"a{i}"] == world.minute + 7
                            for i in range(5)))
        world.activate_war_milestone("a0", "war_horn")
        war = world.state.wars[war.id]
        self.assertEqual(war.horn_until, world.minute + 10)
        world.activate_war_milestone("a0", "final_rally")
        war = world.state.wars[war.id]
        self.assertTrue(all(war.routed[f"a{i}"] == world.minute
                            for i in range(5)))
        with self.assertRaises(ActionError):
            world.activate_war_milestone("a0", "final_rally")
        world.assert_invariants()

    def test_permissions_leader_only_then_explicit_delegation(self):
        world, ga, _ = paired_world()
        with self.assertRaises(ActionError):
            world.set_guild_right("a1", "a2", "milestones", True)
        with self.assertRaises(ActionError):
            world.invite_guild("a1", "b9")
        world.set_guild_right("a0", "a1", "milestones", True)
        self.assertIn("milestones", world.guild_system.view("a1")["my_guild"]["my_rights"])
        world.set_guild_right("a0", "a1", "milestones", False)
        self.assertNotIn("milestones", world.guild_system.view("a1")["my_guild"]["my_rights"])
        with self.assertRaises(ActionError):
            world.set_guild_right("a0", "a1", "master", True)
        world.assert_invariants()

    def test_pressure_routing_honor_milestones_and_break(self):
        world, ga, gb = paired_world()
        world.enlist_guild_war("a0", True)
        world.enlist_guild_war("b0", True)
        world.war_system.match_week(10080)
        war = next(iter(world.state.wars.values()))
        world.minute = war.scheduled_minute
        war.status = "live"
        war.present.update((*war.roster_a, *war.roster_b))
        for i in range(10):
            outcome = world.war_system.hit(war.id, f"a{i}", f"b{i}")
            self.assertGreaterEqual(outcome["honor"], 3)
            self.assertTrue(10 <= outcome["routed_until"] - world.minute <= 15)
        self.assertEqual(war.advantage, ga)
        self.assertEqual(war.pressure_a, 0)
        self.assertGreater(war.honor["a0"], 0)
        world.advance(15)
        self.assertGreaterEqual(war.progress_a, 30)
        self.assertIn("field_hospital", war.unlocks[ga])
        with self.assertRaises(ActionError):
            world.activate_war_milestone("a1", "field_hospital")
        world.activate_war_milestone("a0", "field_hospital")
        with self.assertRaises(ActionError):
            world.activate_war_milestone("a0", "field_hospital")
        # A rejected atomic action restores a state snapshot. Refresh references
        # rather than asserting on a stale pre-rollback dataclass.
        war = world.state.wars[war.id]
        for i in range(7):
            world.war_system.hit(war.id, f"b{i}", f"a{i}")
        self.assertIsNone(world.state.wars[war.id].advantage)
        self.assertEqual(war.pressure_a, 0)
        self.assertEqual(war.pressure_b, 0)
        world.assert_invariants()

    def test_healing_and_departure_rules(self):
        world, ga, gb = paired_world()
        war = world.war_system.start_practice("a0")
        record = world.state.wars[war["war_id"]]
        world.join_warfront("a0")
        bot = record.roster_b[0]
        record.routed["a0"] = world.minute + 13
        outcome = world.use_field_dressing("a0")
        self.assertEqual(outcome["remaining"], 5)
        with self.assertRaises(ActionError):
            world.use_field_dressing("a0")
        record = world.state.wars[record.id]
        record.routed["a0"] = world.minute
        result = world.leave_warfront("a0")
        self.assertTrue(result["contested"])
        self.assertEqual(world.state.wars[record.id].hits[record.guild_b], 1)
        world.assert_invariants()

    def test_practice_duels_use_real_combat_without_gold_stealing(self):
        world = WorldEngine([Actor("hero", "human", city="crownreach", gold=200)])
        guild = world.found_guild("hero", "Practice Guard")["id"]
        record_id = world.start_war_practice("hero")["war_id"]
        war = world.state.wars[record_id]
        self.assertEqual(len(war.roster_b), 10)
        world.join_warfront("hero")
        bot = war.roster_b[0]
        self.assertTrue(world.war_system.duel_context("hero", bot))
        world.actors[bot].hp = 1
        gold = world.total_gold
        result = world.engage_duel("hero", bot, "strike")
        if result.get("outcome") == "ongoing":
            for _ in range(10):
                result = world.duel_turn("hero", "strike", "")
                if result.get("outcome") != "ongoing":
                    break
        self.assertEqual(world.total_gold, gold)
        self.assertGreaterEqual(war.honor.get("hero", 0), 0)
        world.advance(3)
        world.assert_invariants()

    def test_group_assists_consume_stamina_and_cannot_double_join(self):
        world, _, _ = paired_world()
        for leader in ("a0", "b0"):
            world.enlist_guild_war(leader, True)
        world.war_system.match_week(10080)
        war = next(iter(world.state.wars.values()))
        world.minute = war.scheduled_minute
        war.status = "live"
        war.present.update((*war.roster_a, *war.roster_b))
        world.start_duel("a0", "b0")
        stamina = world.actors["a1"].stamina
        world.assist_war_attack("a1", "a0")
        self.assertEqual(world.actors["a1"].stamina, stamina - 3)
        with self.assertRaises(ActionError):
            world.assist_war_attack("a1", "a0")
        world.assert_invariants()


if __name__ == "__main__":
    unittest.main()
