"""Combat escape rolls, presence and interface regressions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from importlib.resources import files

from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web.session import GameSession
from medieval_world_sim.errors import ActionError
from test_multiplayer_auth import serve
from test_web_client import api

PASSWORD = "correct horse battery staple"


class EscapesAndPresence(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / "players.db"
        self.game = MultiplayerGame(self.db, require_invites=False, dev_fast_forward=True)
        self.alice = self.game.identity(self.game.register_and_login(
            "alice", PASSWORD, "Alice River")[0]).actor_id
        self.bob = self.game.identity(self.game.register_and_login(
            "bob", PASSWORD, "Bryn Stone")[0]).actor_id

    def tearDown(self):
        self.game.close()
        self.folder.cleanup()

    def duel(self, tag):
        return self.game.action(self.alice, "start_duel",
                                {"defender_id": self.bob}, tag)

    def test_escape_failure_consumes_turn_and_can_be_retried(self):
        self.duel("duel1")
        start = self.game.snapshot(self.alice)
        self.assertEqual(self.game.snapshot(self.bob)["duel"]["round"], 0)
        with patch("medieval_world_sim.web.multiplayer.secrets.randbits",
                   return_value=0):
            failed = self.game.action(self.alice, "flee_duel", {}, "flee-1")
        self.assertEqual(failed["outcome"], "ongoing")
        self.assertFalse(failed["escape_success"])
        self.assertEqual(failed["round"], 1)
        self.assertGreater(failed["retaliation"], 0)
        self.assertLess(self.game.snapshot(self.alice)["player"]["hp"],
                        start["player"]["hp"])
        self.assertEqual(self.game.snapshot(self.alice)["duel"]["round"], 1)
        self.assertEqual(self.game.action(self.alice, "flee_duel", {}, "flee-1"), failed)
        self.assertEqual(self.game.snapshot(self.alice)["duel"]["round"], 1)
        self.game.close()
        self.game = MultiplayerGame(self.db, require_invites=False, dev_fast_forward=True)
        self.assertEqual(self.game.snapshot(self.alice)["duel"]["round"], 1)
        self.assertEqual(self.game.snapshot(self.alice)["player"]["hp"],
                         start["player"]["hp"] - failed["retaliation"])
        with patch("medieval_world_sim.web.multiplayer.secrets.randbits",
                   return_value=1):
            success = self.game.action(self.alice, "flee_duel", {}, "flee-2")
        self.assertEqual(success["outcome"], "fled")
        self.assertEqual(success["rounds"], 2)
        self.assertIsNone(self.game.snapshot(self.bob)["duel"])
        self.assertEqual(self.game.snapshot(self.alice)["last_duel"]["gold"], 0)
        self.game.close()
        self.game = MultiplayerGame(self.db, require_invites=False, dev_fast_forward=True)
        self.assertEqual(self.game.snapshot(self.alice)["last_duel"]["rounds"], 2)

    def test_defender_failed_escape_invites_attacker_counter(self):
        self.duel("duel2")
        with patch("medieval_world_sim.web.multiplayer.secrets.randbits",
                   return_value=0):
            result = self.game.action(self.bob, "flee_duel", {}, "defender-fails")
        self.assertEqual(result["outcome"], "ongoing")
        self.assertEqual(result["round"], 1)
        self.assertGreater(result["retaliation"], 0)
        self.assertEqual(self.game.snapshot(self.bob)["duel"]["round"], 1)
        self.assertLess(self.game.snapshot(self.bob)["player"]["hp"], 24)
        self.game.world.assert_invariants()

    def test_presence_reports_active_away_offline_without_leaking_credentials(self):
        before = self.game.social_snapshot(self.alice)
        target = next(x for x in before["users"] if x["id"] == self.bob)
        self.assertEqual(target["presence"], "offline")
        self.game.presence_ping(self.bob, True)
        current = next(x for x in self.game.social_snapshot(self.alice)["users"]
                       if x["id"] == self.bob)
        self.assertEqual(current["presence"], "active")
        self.game.presence_ping(self.bob, False)
        self.assertEqual(next(x for x in self.game.social_snapshot(self.alice)["users"]
                              if x["id"] == self.bob)["presence"], "away")
        with patch("medieval_world_sim.web.multiplayer.time.monotonic",
                   return_value=self.game._presence[self.bob][0] + 91):
            self.assertEqual(next(x for x in self.game.social_snapshot(self.alice)["users"]
                                  if x["id"] == self.bob)["presence"], "offline")
        with self.assertRaises(ActionError):
            self.game.presence_ping(self.bob, "true")
        self.assertNotIn("password", json.dumps(self.game.social_snapshot(self.alice)))

    def test_presence_http_requires_session_csrf_and_valid_visibility(self):
        token, csrf = self.game.login("bob", PASSWORD)
        cookie = {"Cookie": "oathmere_session=" + token}
        with serve(self.game) as port:
            status, _, _ = api(port, "POST", "/api/presence", {"visible": True})
            self.assertEqual(status, 401)
            status, _, _ = api(port, "POST", "/api/presence",
                               {"visible": True}, headers=cookie)
            self.assertEqual(status, 403)
            headers = {**cookie, "X-CSRF-Token": csrf}
            status, _, _ = api(port, "POST", "/api/presence",
                               {"visible": "true"}, headers=headers)
            self.assertEqual(status, 400)
            status, result, _ = api(port, "POST", "/api/presence",
                                    {"visible": True}, headers=headers)
            self.assertEqual(status, 200)
            self.assertTrue(result["ok"])
            status, observed, _ = api(port, "GET", "/api/state",
                                      headers={"Cookie": "oathmere_session=" +
                                          self.game.login("alice", PASSWORD)[0]})
            self.assertEqual(status, 200)
            other = next(x for x in observed["users"] if x["id"] == self.bob)
            self.assertEqual(other["presence"], "active")

    def test_notification_only_after_combat_round_starts(self):
        self.duel("duel3")
        first = self.game.social_snapshot(self.bob)["duel"]
        self.assertEqual(first["round"], 0)
        self.game.action(self.alice, "duel_turn",
                         {"move": "guard", "node_id": ""}, "first-move")
        guarded = self.game.social_snapshot(self.bob)["duel"]
        self.assertEqual(guarded["round"], 1)
        self.assertFalse(guarded["attack_started"])
        self.game.action(self.alice, "duel_turn",
                         {"move": "fists", "node_id": ""}, "first-swing")
        moved = self.game.social_snapshot(self.bob)["duel"]
        self.assertEqual(moved["round"], 2)
        self.assertTrue(moved["attack_started"])

    def test_hospitalization_timer_projected_on_player(self):
        self.duel("duel4")
        for i in range(1, 11):
            result = self.game.action(self.alice, "duel_turn",
                                      {"move": "fists", "node_id": ""}, "hit"+str(i))
            if result["outcome"] != "ongoing":
                break
        self.assertEqual(result["outcome"], "won")
        victim = self.game.snapshot(self.bob)
        self.assertGreater(victim["player"]["defeated_until"], victim["minute"])
        self.assertEqual(victim["player"]["hp"], 0)
        self.assertEqual(self.game.social_snapshot(self.bob)["player_status"]["hp"], 0)


class LegacyFleeReplay(unittest.TestCase):
    def test_solo_coin_flip_is_recorded_and_replayed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "single.json"
            game = GameSession(path)
            game.create("Elda Raven")
            enemy = next(u for u in game.snapshot()["users"] if u["can_attack"])
            game.action("start_duel", {"defender_id": enemy["id"]}, "start")
            with patch("medieval_world_sim.web.session.secrets.randbits",
                       return_value=0):
                failed = game.action("flee_duel", {}, "coin-fail")
            self.assertEqual(failed["outcome"], "ongoing")
            data = json.loads(path.read_text(encoding="utf-8"))
            saved = data["records"][-1]
            self.assertEqual(saved["ruleset"], 11)
            self.assertIs(saved["flee_success"], False)
            replay = GameSession(path)
            self.assertEqual(replay.snapshot(), game.snapshot())
            with patch("medieval_world_sim.web.session.secrets.randbits",
                       return_value=1):
                escaped = game.action("flee_duel", {}, "coin-success")
            self.assertEqual(escaped["outcome"], "fled")
            self.assertEqual(GameSession(path).snapshot(), game.snapshot())

    def test_ui_has_city_filter_and_level_differences(self):
        code = files("medieval_world_sim.web").joinpath(
            "static", "app.js").read_text(encoding="utf-8")
        code += files("medieval_world_sim.web").joinpath(
            "static", "community-views.mjs").read_text(encoding="utf-8")
        self.assertIn("person.city === state.player.city", code)
        self.assertIn("defendant.attack_started", code)
        self.assertIn('data-ui="activity-hospital"', code)
        self.assertIn("function presenceBadge(", code)
        self.assertIn("state.player.max_hp - oldStats.hp", code)
        self.assertIn('button("Continue",', code)
        self.assertNotIn("Achievement unlocked", code)
        self.assertNotIn("Your journey grows.", code)


if __name__ == "__main__":
    unittest.main()
