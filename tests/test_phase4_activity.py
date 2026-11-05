"""Phase 4: lightweight private activity views and field-delta SSE contracts."""
import http.client
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web.social import activity_projection
from medieval_world_sim.web.server import activity_delta
from test_multiplayer_auth import serve
from test_live_activity import next_sse_activity


class ActivityProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = MultiplayerGame(Path(self.tmp.name) / "activity.sqlite3",
                                    require_invites=False, dev_fast_forward=True)
        self.alice = self.game.register("alice", "long secure password", "Alice Meadows")
        self.bob = self.game.register("bobby", "long secure password", "Bob Forest")

    def tearDown(self):
        self.game.close()
        self.tmp.cleanup()

    def assert_shared_projection(self, actor_id):
        full = self.game.snapshot(actor_id)
        with patch("medieval_world_sim.web.projection.world_snapshot",
                   side_effect=AssertionError("Full projection used for SSE")):
            live = self.game.social_snapshot(actor_id)
        for name in ("users", "events", "duel", "last_duel"):
            self.assertEqual(live[name], full[name], name)
        for name in ("health_next_sim_seconds", "stamina_next_sim_seconds",
                     "mana_next_sim_seconds"):
            self.assertEqual(live["player_status"][name], full["player"][name])
        self.assertEqual(live["player_status"]["gold"], full["player"]["gold"])
        for person in live["users"]:
            if person["id"] != actor_id:
                for secret in ("gold", "inventory", "work", "strength", "defense"):
                    self.assertNotIn(secret, person)

    def test_live_payload_equivalent_before_and_after_gameplay(self):
        self.assert_shared_projection(self.alice)
        self.assert_shared_projection(self.bob)
        self.game.action(self.alice, "send_chat",
                         {"kind": "direct", "target": self.bob, "message": "Hello"},
                         "msg")
        self.game.action(self.alice, "propose_trade", {
            "recipient_id": self.bob,
            "offer": {"gold": 9, "items": [], "gear_ids": []},
            "request": {"gold": 0, "items": [], "gear_ids": []},
        }, "offer")
        self.assert_shared_projection(self.alice)
        self.assert_shared_projection(self.bob)
        self.game.action(self.alice, "start_duel", {"defender_id": self.bob}, "duel")
        self.assert_shared_projection(self.alice)
        self.assert_shared_projection(self.bob)

    def test_delta_includes_only_changes_but_preserves_explicit_empty_values(self):
        original = self.game.social_snapshot(self.alice)
        self.assertEqual(activity_delta(None, original), original)
        same = {**original, "revision": original["revision"] + 1}
        only_revision = activity_delta(original, same)
        self.assertEqual(set(only_revision), {"actor_id", "revision"})
        updated = {**same, "chat": {"messages": [], "channels": []},
                   "duel": None, "trades": []}
        change = activity_delta(original, updated)
        self.assertNotIn("users", change)
        self.assertNotIn("events", change)
        self.assertEqual(change["chat"], updated["chat"])
        self.assertEqual(change["revision"], updated["revision"])

    def test_presence_changes_send_sparse_patch_not_full_roster(self):
        prior = self.game.social_snapshot(self.alice)
        self.game.presence_ping(self.bob, True)
        after = self.game.social_snapshot(self.alice)
        update = activity_delta(prior, after)
        self.assertNotIn("users", update)
        self.assertEqual(update["presence_updates"],
                         [{"id": self.bob, "presence": "active"}])
        self.assertNotIn("chat", update)
        # If a character travels, a full authorized roster is required,
        # because city and attack eligibility changed as well.
        self.game.action(self.bob, "travel",
                         {"destination": "goldmeadow"}, "bob-travels")
        moving = activity_delta(after, self.game.social_snapshot(self.alice))
        self.assertIn("users", moving)
        self.assertNotIn("presence_updates", moving)

    def test_presence_only_revisions_use_cached_projection_and_copy_overlay(self):
        first = self.game.social_snapshot(self.alice)
        cached = self.game._live_activity_cache[self.alice][1]
        self.assertNotIn("presence", cached["users"][0])
        with patch("medieval_world_sim.web.social.activity_projection",
                   side_effect=AssertionError("Expensive activity projection rerun")):
            self.game.presence_ping(self.bob, True)
            second = self.game.social_snapshot(self.alice)
        self.assertNotEqual(first["revision"], second["revision"])
        self.assertEqual(second["events"], first["events"])
        self.assertEqual(
            next(u["presence"] for u in second["users"] if u["id"] == self.bob),
            "active")
        self.assertNotIn("presence", cached["users"][0])
        # A committed command invalidates all previously cached world views.
        self.game.action(self.bob, "send_chat", {
            "kind": "global", "target": "", "message": "fresh"}, "fresh")
        with patch("medieval_world_sim.web.social.activity_projection",
                   wraps=activity_projection) as project:
            self.game.social_snapshot(self.alice)
            self.assertEqual(project.call_count, 1)

    def test_real_sse_presence_frame_is_sparse_and_authorized(self):
        token, _ = self.game.login("alice", "long secure password")
        with serve(self.game) as port:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
            connection.request(
                "GET", "/api/events",
                headers={"Cookie": "oathmere_session=" + token})
            response = connection.getresponse()
            try:
                self.assertEqual(response.status, 200)
                initial = next_sse_activity(response)
                self.assertIn("users", initial)
                self.game.presence_ping(self.bob, True)
                patch = next_sse_activity(response)
                self.assertEqual(patch["actor_id"], self.alice)
                self.assertNotIn("users", patch)
                self.assertEqual(patch["presence_updates"],
                                 [{"id": self.bob, "presence": "active"}])
                self.assertLess(len(json.dumps(patch).encode("utf-8")), 256)
                self.assertNotIn("chat", patch)
                self.assertNotIn("trades", patch)
            finally:
                response.close()
                connection.close()

    def test_presence_changes_do_not_expose_other_accounts(self):
        self.game.presence_ping(self.bob, True)
        self.assert_shared_projection(self.alice)
        bob = next(x for x in self.game.social_snapshot(self.alice)["users"]
                   if x["id"] == self.bob)
        self.assertEqual(bob["presence"], "active")
