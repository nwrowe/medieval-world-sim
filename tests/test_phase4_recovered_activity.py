"""Recovered Phase 4 SSE cache and presence protocol safety regressions."""
import http.client
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from medieval_world_sim.web.live_delta import activity_delta, apply_activity_delta
from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web import social
from test_multiplayer_auth import serve


def read_raw_activity(response):
    """Read an unmerged SSE event to check wire bytes, not reconstructed state."""
    event = None
    data = None
    for _ in range(60):
        line = response.fp.readline()
        if not line:
            raise AssertionError("SSE stream terminated")
        line = line.decode("utf-8").rstrip("\r\n")
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data = json.loads(line[6:])
        elif not line and event in ("activity", "activity-delta") and data is not None:
            return event, data
    raise AssertionError("Missing SSE activity event")


class RecoveredActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "recovered.sqlite3"
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)
        self.alice = self.game.register("alice", "long secure password", "Alice Meadows")
        self.bob = self.game.register("bobby", "long secure password", "Bryn Forest")

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def test_presence_revision_reuses_authorized_cache_without_mutating_it(self):
        first = self.game.social_snapshot(self.alice)
        cached = self.game._live_activity_cache[self.alice][1]
        self.assertTrue(cached["users"])
        self.assertTrue(all("presence" not in row for row in cached["users"]))
        with patch.object(social, "activity_projection",
                          side_effect=AssertionError("World activity recalculated")):
            self.game.presence_ping(self.bob, True)
            after = self.game.social_snapshot(self.alice)
        self.assertGreater(after["revision"], first["revision"])
        self.assertEqual(first["events"], after["events"])
        self.assertEqual(next(u["presence"] for u in after["users"]
                              if u["id"] == self.bob), "active")
        self.assertEqual(next(u["presence"] for u in first["users"]
                              if u["id"] == self.bob), "offline")
        self.assertTrue(all("presence" not in row for row in cached["users"]))
        self.assertEqual(self.game._live_activity_cache[self.alice][0],
                         self.game._journal_count)

    def test_world_commit_invalidates_cache_and_retry_does_not(self):
        self.game.social_snapshot(self.alice)
        with patch.object(social, "activity_projection",
                          wraps=social.activity_projection) as rebuild:
            self.game.action(self.bob, "send_chat", {
                "kind": "global", "target": "", "message": "hello"}, "chat-one")
            self.game.social_snapshot(self.alice)
            self.assertEqual(rebuild.call_count, 1)
            self.game.action(self.bob, "send_chat", {
                "kind": "global", "target": "", "message": "hello"}, "chat-one")
            self.game.social_snapshot(self.alice)
            self.assertEqual(rebuild.call_count, 1)

    def test_lru_bound_across_separate_scoped_accounts(self):
        third = self.game.register("carol", "long secure password", "Carol Vale")
        with patch.object(social, "MAX_ACTIVITY_CACHE", 2):
            for actor_id in (self.alice, self.bob, third):
                self.game.social_snapshot(actor_id)
        self.assertEqual(len(self.game._live_activity_cache), 2)
        self.assertNotIn(self.alice, self.game._live_activity_cache)
        self.assertIn(self.bob, self.game._live_activity_cache)
        self.assertIn(third, self.game._live_activity_cache)

    def test_presence_wire_is_small_and_reconstructs_exactly(self):
        prior = self.game.social_snapshot(self.alice)
        self.game.presence_ping(self.bob, True)
        current = self.game.social_snapshot(self.alice)
        delta = activity_delta(prior, current)
        self.assertEqual(delta["presence_updates"],
                         [{"id": self.bob, "presence": "active"}])
        self.assertNotIn("users", delta)
        self.assertNotIn("chat", delta)
        self.assertEqual(apply_activity_delta(prior, delta), current)
        self.assertLess(len(json.dumps(delta).encode("utf-8")), 256)
        # Movement affects city and combat eligibility and requires a new
        # authorized roster, never a misleading presence-only patch.
        self.game.action(self.bob, "travel", {
            "destination": "goldmeadow"}, "bob-travel")
        after_move = self.game.social_snapshot(self.alice)
        movement = activity_delta(current, after_move)
        self.assertIn("users", movement)
        self.assertNotIn("presence_updates", movement)
        self.assertEqual(apply_activity_delta(current, movement), after_move)

    def test_presence_delta_rejects_forged_actor_ids_and_bad_revisions(self):
        prior = self.game.social_snapshot(self.alice)
        self.game.presence_ping(self.bob, True)
        delta = activity_delta(prior, self.game.social_snapshot(self.alice))
        with self.assertRaisesRegex(ValueError, "Invalid presence actor patch"):
            apply_activity_delta(prior, {**delta, "presence_updates": [
                {"id": "unknown", "presence": "active"}]})
        with self.assertRaises(ValueError):
            apply_activity_delta(prior, {**delta, "actor_id": self.bob})
        with self.assertRaises(ValueError):
            apply_activity_delta(prior, {**delta, "revision": prior["revision"]})
        self.assertEqual(next(u["presence"] for u in prior["users"]
                              if u["id"] == self.bob), "offline")

    def test_real_sse_stream_sends_account_scoped_compact_presence(self):
        token, _ = self.game.login("alice", "long secure password")
        with serve(self.game) as port:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
            conn.request("GET", "/api/events",
                         headers={"Cookie": "oathmere_session=" + token})
            response = conn.getresponse()
            try:
                self.assertEqual(response.status, 200)
                event, initial = read_raw_activity(response)
                self.assertEqual(event, "activity")
                self.assertEqual(initial["actor_id"], self.alice)
                self.assertIn("users", initial)
                self.game.presence_ping(self.bob, True)
                event, raw = read_raw_activity(response)
                self.assertEqual(event, "activity-delta")
                self.assertEqual(raw["actor_id"], self.alice)
                self.assertTrue(raw["delta"])
                self.assertEqual(raw["presence_updates"],
                                 [{"id": self.bob, "presence": "active"}])
                self.assertNotIn("users", raw)
                self.assertNotIn("chat", raw)
                self.assertNotIn("trades", raw)
                self.assertLess(len(json.dumps(raw).encode("utf-8")), 256)
                self.assertEqual(apply_activity_delta(initial, raw)["revision"],
                                 raw["revision"])
            finally:
                response.close()
                conn.close()

    def test_browser_applies_presence_and_keeps_omitted_course_state(self):
        from importlib.resources import files
        source = files("medieval_world_sim.web").joinpath(
            "static", "app.js").read_text(encoding="utf-8")
        self.assertIn("update.presence_updates", source)
        self.assertIn('"course_active" in update', source)


if __name__ == "__main__":
    unittest.main()
