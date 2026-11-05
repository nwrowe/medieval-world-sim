"""Real-time account-scoped notifications, PvP and University action coverage."""
import http.client
import json
from importlib.resources import files
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.multiplayer import MultiplayerGame
from test_multiplayer_auth import PASSWORD, serve
from test_web_client import api


def next_sse_activity(response):
    event_name = None
    data = None
    for _ in range(40):
        line = response.fp.readline()
        if not line:
            raise AssertionError("SSE stream closed before event")
        line = line.decode("utf-8").rstrip("\r\n")
        if line.startswith("event: "):
            event_name = line[7:]
        elif line.startswith("data: "):
            data = json.loads(line[6:])
        elif not line and event_name in ("activity", "activity-delta") and data is not None:
            if event_name == "activity":
                response._last_activity = data
            else:
                from medieval_world_sim.web.live_delta import apply_activity_delta
                response._last_activity = apply_activity_delta(
                    response._last_activity, data)
            return response._last_activity
    raise AssertionError("Activity event missing")


class PvPSkirmishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        self.alice = self.game.identity(self.game.register_and_login(
            "alice", PASSWORD, "Alice River")[0]).actor_id
        self.bob = self.game.identity(self.game.register_and_login(
            "bob", PASSWORD, "Bryn Stone")[0]).actor_id

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def test_player_attack_uses_replayable_duel_flow(self):
        alice_view = self.game.snapshot(self.alice)
        opponent = next(x for x in alice_view["users"] if x["id"] == self.bob)
        self.assertTrue(opponent["can_attack"])
        before = self.game.world.total_gold
        started = self.game.action(self.alice, "start_duel",
                                   {"defender_id": self.bob}, "pvp-start")
        self.assertEqual(started["stamina_spent"], 0)
        self.assertEqual(self.game.snapshot(self.alice)["duel"]["role"], "attacker")
        self.assertEqual(self.game.snapshot(self.bob)["duel"]["role"], "defender")
        outcome = self.game.action(self.alice, "duel_turn",
                                   {"move": "fists", "node_id": ""}, "pvp-turn")
        self.assertEqual(outcome["stamina_spent"], 2)
        self.assertGreater(outcome["damage"], 0)
        self.assertGreater(outcome["retaliation"], 0)
        self.assertEqual(self.game.snapshot(self.alice)["player"]["stamina"], 98)
        self.assertEqual(self.game.snapshot(self.bob)["player"]["stamina"], 100)
        self.assertLess(self.game.snapshot(self.bob)["player"]["hp"], 24)
        self.assertEqual(self.game.world.total_gold, before)
        self.assertEqual(self.game.action(self.alice, "duel_turn",
                         {"move": "fists", "node_id": ""}, "pvp-turn"), outcome)
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        self.assertEqual(self.game.snapshot(self.alice)["duel"]["round"], 1)
        self.assertEqual(self.game.snapshot(self.bob)["duel"]["round"], 1)
        self.assertEqual(self.game.snapshot(self.alice)["player"]["stamina"], 98)
        self.game.world.assert_invariants()

    def test_cannot_attack_self_or_players_while_traveling(self):
        with self.assertRaises(ActionError):
            self.game.action(self.alice, "start_duel",
                             {"defender_id": self.alice}, "illegal-self")
        with self.assertRaises(ActionError):
            self.game.action(self.alice, "pvp_strike",
                             {"defender_id": self.bob}, "retired-pvp-api")
        self.game.action(self.alice, "travel",
                         {"destination": "goldmeadow"}, "travel-first")
        with self.assertRaises(ActionError):
            self.game.action(self.alice, "start_duel",
                             {"defender_id": self.bob}, "attack-on-the-road")
        self.game.world.assert_invariants()

    def test_university_enrollment_is_atomic_and_visible(self):
        before = self.game.snapshot(self.alice)
        university = before["training_hall"]
        self.assertIsNone(university["active"])
        cost = university["schools"][0]["courses"][2]["tuition"]
        school_id = university["schools"][0]["id"]
        first = self.game.action(self.alice, "enroll_course_choice",
                                 {"school": school_id, "index": 2}, "university-1")
        self.assertEqual(first["tuition"], cost)
        after = self.game.snapshot(self.alice)
        self.assertEqual(after["player"]["gold"], before["player"]["gold"] - cost)
        self.assertEqual(after["training_hall"]["active"]["school"], school_id)
        self.assertGreater(after["training_hall"]["active"]["remaining_minutes"], 0)
        self.assertEqual(self.game.action(self.alice, "enroll_course_choice",
                         {"school": school_id, "index": 2}, "university-1"), first)
        self.assertEqual(self.game.snapshot(self.alice)["player"]["gold"],
                         before["player"]["gold"] - cost)
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        self.assertEqual(self.game.snapshot(self.alice)["training_hall"]["active"],
                         after["training_hall"]["active"])
        self.game.world.assert_invariants()


class LiveEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.game = MultiplayerGame(Path(self.temp.name) / "stream.db", require_invites=False, dev_fast_forward=True)
        self.alice_token, _ = self.game.register_and_login(
            "alice", PASSWORD, "Alice River")
        self.bob_token, _ = self.game.register_and_login(
            "bob", PASSWORD, "Bryn Stone")
        self.mallory_token, _ = self.game.register_and_login(
            "mallory", PASSWORD, "Mara Vale")
        self.alice = self.game.identity(self.alice_token).actor_id
        self.bob = self.game.identity(self.bob_token).actor_id
        self.mallory = self.game.identity(self.mallory_token).actor_id

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    @staticmethod
    def stream(port, token):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
        conn.request("GET", "/api/events",
                     headers={"Cookie": "oathmere_session=" + token})
        response = conn.getresponse()
        return conn, response

    def test_stream_requires_account_and_host_validation(self):
        with serve(self.game) as port:
            status, _, _ = api(port, "GET", "/api/events")
            self.assertEqual(status, 401)
            status, _, _ = api(port, "GET", "/api/events",
                               headers={"Host": "evil.invalid"})
            self.assertEqual(status, 403)

    def test_direct_chat_is_pushed_only_to_authorized_recipient_and_trade_alerts(self):
        with serve(self.game) as port:
            bob_conn, bob_response = self.stream(port, self.bob_token)
            mal_conn, mal_response = self.stream(port, self.mallory_token)
            try:
                self.assertEqual(bob_response.status, 200)
                self.assertIn("text/event-stream",
                              bob_response.getheader("Content-Type"))
                initial = next_sse_activity(bob_response)
                self.assertEqual(initial["actor_id"], self.bob)
                self.assertEqual(initial["chat"]["messages"], [])
                next_sse_activity(mal_response)
                self.game.action(self.alice, "send_chat", {
                    "kind": "direct", "target": self.bob,
                    "message": "Private courier message"}, "dm-one")
                bob_update = next_sse_activity(bob_response)
                mal_update = next_sse_activity(mal_response)
                self.assertEqual([m["body"] for m in bob_update["chat"]["messages"]],
                                 ["Private courier message"])
                self.assertFalse(any(m["body"] == "Private courier message"
                                     for m in mal_update["chat"]["messages"]))
                self.game.action(self.alice, "propose_trade", {
                    "recipient_id": self.bob,
                    "offer": {"gold": 10, "items": [], "gear_ids": []},
                    "request": {"gold": 5, "items": [], "gear_ids": []},
                }, "trade-one")
                traded = next_sse_activity(bob_response)
                self.assertEqual(len(traded["trades"]), 1)
                self.assertEqual(traded["trades"][0]["recipient"], self.bob)
            finally:
                bob_response.close()
                mal_response.close()
                bob_conn.close()
                mal_conn.close()

    def test_browser_script_guards_university_actions_and_unread_count(self):
        source = files("medieval_world_sim.web").joinpath(
            "static", "app.js").read_text(encoding="utf-8")
        self.assertIn("element.dataset.school && !element.dataset.ui", source)
        city_views = files("medieval_world_sim.web").joinpath(
            "static", "city-views.mjs").read_text(encoding="utf-8")
        self.assertIn('data-ui="course-enroll"', city_views)
        self.assertIn('new EventSource("/api/events")', source)
        self.assertIn("function unreadCount()", source)
        self.assertIn("expandedUniversitySchool", source)
        self.assertNotIn('{ id: "trade", icon:', source)


if __name__ == "__main__":
    unittest.main()
