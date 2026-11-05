"""Phase 4: account scoped small SSE packets and exact projection parity."""
import json
import tempfile
import unittest
from pathlib import Path

from medieval_world_sim.web.live_delta import activity_delta, apply_activity_delta
from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web.projection import world_snapshot


class NarrowActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.game = MultiplayerGame(Path(self.temp.name) / "narrow.db",
                                    require_invites=False, dev_fast_forward=True)
        self.alice = self.game.register("alice", "secure test password", "Alice River")
        self.bob = self.game.register("bobby", "secure test password", "Bryn Vale")

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def test_narrow_projection_matches_full_for_private_activity(self):
        self.game.action(self.alice, "send_chat", {
            "kind": "direct", "target": self.bob, "message": "hello Bob"}, "private")
        for actor in (self.alice, self.bob):
            full = world_snapshot(
                self.game.world, actor, self.game.names[actor], self.game.npc_names,
                self.game.names, self.game.event_times, True)
            actual = self.game.social_snapshot(actor)
            self.assertEqual(actual["users"], full["users"])
            self.assertEqual(actual["events"], full["events"])
            self.assertEqual(actual["duel"], full["duel"])
            self.assertEqual(actual["last_duel"], full["last_duel"])
            self.assertEqual(actual["player_status"]["health_next_sim_seconds"],
                             full["player"]["health_next_sim_seconds"])
            self.assertEqual(actual["player_status"]["stamina_next_sim_seconds"],
                             full["player"]["stamina_next_sim_seconds"])
            self.assertEqual(actual["player_status"]["mana_next_sim_seconds"],
                             full["player"]["mana_next_sim_seconds"])
        self.assertFalse(any(
            message["body"] == "hello Bob"
            for message in self.game.social_snapshot(self.alice)["chat"]["messages"]
            if message["sender"] != self.alice))

    def test_delta_sends_only_changed_fields_and_merges_exactly(self):
        first = self.game.social_snapshot(self.alice)
        self.game.action(self.bob, "send_chat", {
            "kind": "direct", "target": self.alice, "message": "private"}, "dm-1")
        next_state = self.game.social_snapshot(self.alice)
        delta = activity_delta(first, next_state)
        self.assertTrue(delta["delta"])
        self.assertEqual(set(delta), {"actor_id", "revision", "delta", "chat"})
        self.assertEqual(apply_activity_delta(first, delta), next_state)
        self.assertLess(len(json.dumps(delta)), len(json.dumps(next_state)))

    def test_identity_and_revision_checks_are_required(self):
        before = self.game.social_snapshot(self.alice)
        other = self.game.social_snapshot(self.bob)
        with self.assertRaises(ValueError):
            activity_delta(before, other)
        with self.assertRaises(ValueError):
            activity_delta(before, before)
        with self.assertRaises(ValueError):
            apply_activity_delta(before, {**before, "actor_id": self.bob,
                                          "revision": before["revision"] + 1})

    def test_duel_and_presence_are_narrow_but_fully_scoped(self):
        a = self.game.social_snapshot(self.alice)
        self.game.presence_ping(self.bob, True)
        b = self.game.social_snapshot(self.alice)
        delta = activity_delta(a, b)
        self.assertEqual(set(delta), {"actor_id", "revision", "delta", "users"})
        self.assertEqual(apply_activity_delta(a, delta), b)
        self.game.action(self.alice, "start_duel", {
            "defender_id": self.bob}, "duel")
        c = self.game.social_snapshot(self.alice)
        self.assertIsNotNone(c["duel"])
        self.assertEqual(apply_activity_delta(b, activity_delta(b, c)), c)


if __name__ == "__main__":
    unittest.main()
