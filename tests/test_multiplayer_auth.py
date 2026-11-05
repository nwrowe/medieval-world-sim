"""Authenticated local multi-account server and durable shared-world journal tests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import unittest

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.multiplayer import MultiplayerGame, AuthError
from medieval_world_sim.web.server import GameHTTPServer
from test_web_client import api


PASSWORD = "correct horse battery staple"


@contextmanager
def serve(game):
    server = GameHTTPServer(("127.0.0.1", 0), None, multiplayer=game)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class MultiAccountPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "accounts.sqlite3"
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def register(self, username, name):
        token, csrf = self.game.register_and_login(username, PASSWORD, name)
        identity = self.game.identity(token)
        self.assertIsNotNone(identity)
        return token, csrf, identity.actor_id

    def test_two_accounts_have_independent_actors_and_private_snapshots(self):
        _, _, alice = self.register("alice", "Alice River")
        _, _, bob = self.register("bob", "Bryn Stone")
        self.assertNotEqual(alice, bob)
        a = self.game.snapshot(alice)
        b = self.game.snapshot(bob)
        self.assertTrue(a["multiplayer"])
        self.assertEqual(a["name"], "Alice River")
        self.assertEqual(b["name"], "Bryn Stone")
        self.assertEqual(a["player"]["gold"], 240)
        self.assertEqual(b["player"]["gold"], 240)
        self.assertEqual(len([u for u in a["users"] if u["kind"] == "human"]), 2)
        for person in a["users"]:
            self.assertNotIn("inventory", person)
            self.assertNotIn("gold", person)
            self.assertNotIn("strength", person)
            self.assertNotIn("defense", person)
        self.game.action(alice, "travel",
                         {"destination": "goldmeadow"}, "to-fields")
        self.game.advance(bob, 60, "arrive-fields")
        self.game.action(alice, "gather", {"item": "grain", "quantity": 1}, "gather-a")
        self.assertEqual(self.game.snapshot(alice)["player"]["inventory"].get("grain"), 1)
        self.assertEqual(self.game.snapshot(bob)["player"]["inventory"].get("grain", 0), 0)
        self.assertTrue(all("gathered" not in str(row).lower()
                            for row in self.game.snapshot(bob)["events"]))
        self.assertEqual(self.game.world.total_gold, self.game.world.initial_gold)

    def test_login_passwords_expiry_logout_and_duplicate_account_rejected(self):
        token, csrf, alice = self.register("Alice", "Alice River")
        self.assertEqual(self.game.identity(token).actor_id, alice)
        self.assertEqual(self.game.identity(token).csrf, csrf)
        self.assertIsNone(self.game.identity("garbage"))
        with self.assertRaises(AuthError):
            self.game.login("alice", "incorrect-password")
        with self.assertRaises(ActionError):
            self.game.register("ALICE", PASSWORD, "Someone Else")
        self.game.logout(token)
        self.assertIsNone(self.game.identity(token))
        second, _ = self.game.login("alice", PASSWORD)
        self.assertEqual(self.game.identity(second).actor_id, alice)

    def test_logged_actions_and_trades_survive_restart_with_conserved_assets(self):
        _, _, alice = self.register("alice", "Alice River")
        _, _, bob = self.register("bob", "Bryn Stone")
        self.game.action(alice, "send_chat",
                         {"kind": "direct", "target": bob, "message": "Private offer"}, "dm-a")
        self.assertEqual(len(self.game.snapshot(bob)["chat"]["messages"]), 1)
        offer = self.game.action(alice, "propose_trade", {
            "recipient_id": bob,
            "offer": {"gold": 20, "items": [], "gear_ids": []},
            "request": {"gold": 15, "items": [], "gear_ids": []},
        }, "trade-a")
        self.assertEqual(len(self.game.snapshot(bob)["trades"]), 1)
        accepted = self.game.action(bob, "accept_trade", {
            "trade_id": offer["id"], "terms_hash": offer["terms_hash"]
        }, "trade-b")
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(self.game.action(bob, "accept_trade", {
            "trade_id": offer["id"], "terms_hash": offer["terms_hash"]
        }, "trade-b"), accepted)
        self.assertEqual(self.game.snapshot(alice)["player"]["gold"], 235)
        self.assertEqual(self.game.snapshot(bob)["player"]["gold"], 245)
        before = {player: self.game.snapshot(player) for player in (alice, bob)}
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        for player in (alice, bob):
            self.assertEqual(self.game.snapshot(player), before[player])
        self.game.world.assert_invariants()

    def test_reused_request_id_mismatched_payload_and_cross_account_isolation(self):
        _, _, alice = self.register("alice", "Alice River")
        _, _, bob = self.register("bob", "Bryn Stone")
        self.game.action(alice, "travel", {"destination": "goldmeadow"}, "trip-a")
        self.game.action(bob, "travel", {"destination": "goldmeadow"}, "trip-b")
        self.game.advance(alice, 60, "arrive-both")
        self.game.action(alice, "gather", {"item": "grain", "quantity": 1}, "req-1")
        with self.assertRaises(ActionError):
            self.game.action(alice, "gather", {"item": "grain", "quantity": 2}, "req-1")
        self.game.action(bob, "gather", {"item": "grain", "quantity": 1}, "req-1")
        self.assertEqual(self.game.snapshot(alice)["player"]["inventory"]["grain"], 1)
        self.assertEqual(self.game.snapshot(bob)["player"]["inventory"]["grain"], 1)
        self.game.world.assert_invariants()

    def test_concurrent_trade_accepts_have_one_winner_and_persist(self):
        _, _, alice = self.register("alice", "Alice River")
        _, _, bob = self.register("bob", "Bryn Stone")
        offer = self.game.action(alice, "propose_trade", {
            "recipient_id": bob, "offer": {"gold": 10, "items": [], "gear_ids": []},
            "request": {"gold": 5, "items": [], "gear_ids": []},
        }, "offer")
        def accept(i):
            try:
                return self.game.action(bob, "accept_trade", {
                    "trade_id": offer["id"], "terms_hash": offer["terms_hash"]
                }, "accept-" + str(i))
            except ActionError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(accept, [1, 2]))
        self.assertEqual(sum(x is not None for x in outcomes), 1)
        self.assertEqual(self.game.snapshot(alice)["player"]["gold"], 235)
        self.assertEqual(self.game.snapshot(bob)["player"]["gold"], 245)
        self.game.world.assert_invariants()
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        self.game.world.assert_invariants()


class MultiAccountHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.game = MultiplayerGame(Path(self.temp.name) / "players.db", require_invites=False, dev_fast_forward=True)

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def test_non_loopback_mode_rejected(self):
        with self.assertRaises(ValueError):
            GameHTTPServer(("0.0.0.0", 0), None, multiplayer=self.game)

    def test_http_cookies_csrf_principal_and_logout(self):
        with serve(self.game) as port:
            status, health, _ = api(port, "GET", "/api/health")
            self.assertEqual((status, health["mode"]), (200, "multi-account-local"))
            status, _, _ = api(port, "GET", "/api/state")
            self.assertEqual(status, 401)
            status, registered, headers = api(port, "POST", "/api/auth/register", {
                "username": "alice", "password": PASSWORD, "display_name": "Alice River"})
            self.assertEqual(status, 200)
            self.assertTrue(registered["state"]["multiplayer"])
            self.assertNotIn("token", json.dumps(registered))
            cookie = headers["Set-Cookie"]
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            alice_cookie = cookie.split(";", 1)[0]
            csrf = registered["csrf"]
            status, alice_state, _ = api(port, "GET", "/api/state",
                                         headers={"Cookie": alice_cookie})
            self.assertEqual(status, 200)
            self.assertEqual(alice_state["name"], "Alice River")
            # Cookie alone is not sufficient for a mutation.
            status, _, _ = api(port, "POST", "/api/action", {
                "action": "gather", "params": {"item": "grain", "quantity": 1},
                "id": "guess"}, headers={"Cookie": alice_cookie})
            self.assertEqual(status, 403)
            # A client-provided identity field is forbidden and cannot steal Bob's actor.
            status, forged, _ = api(port, "POST", "/api/action", {
                "action": "gather", "params": {"item": "grain", "quantity": 1},
                "actor_id": "player:forged", "id": "forged"},
                headers={"Cookie": alice_cookie, "X-CSRF-Token": csrf})
            self.assertEqual(status, 400)
            self.assertIn("Invalid action request fields", forged["error"])
            status, _, _ = api(port, "POST", "/api/action", {
                "action": "travel", "params": {"destination": "goldmeadow"},
                "id": "trip-to-fields"
            }, headers={"Cookie": alice_cookie, "X-CSRF-Token": csrf})
            self.assertEqual(status, 200)
            status, _, _ = api(port, "POST", "/api/advance", {
                "minutes": 60, "id": "arrive-fields"
            }, headers={"Cookie": alice_cookie, "X-CSRF-Token": csrf})
            self.assertEqual(status, 200)
            status, result, _ = api(port, "POST", "/api/action", {
                "action": "gather", "params": {"item": "grain", "quantity": 1},
                "id": "gather-1"},
                headers={"Cookie": alice_cookie, "X-CSRF-Token": csrf})
            self.assertEqual(status, 200)
            self.assertEqual(result["state"]["player"]["inventory"]["grain"], 1)
            status, bob_reg, bob_headers = api(port, "POST", "/api/auth/register", {
                "username": "bob", "password": PASSWORD, "display_name": "Bryn Stone"})
            self.assertEqual(status, 200)
            bob_cookie = bob_headers["Set-Cookie"].split(";", 1)[0]
            status, bob_state, _ = api(port, "GET", "/api/state",
                                       headers={"Cookie": bob_cookie})
            self.assertEqual(status, 200)
            self.assertEqual(bob_state["player"]["inventory"].get("grain", 0), 0)
            self.assertEqual(bob_state["name"], "Bryn Stone")
            status, _, _ = api(port, "POST", "/api/auth/logout", {},
                               headers={"Cookie": alice_cookie, "X-CSRF-Token": csrf})
            self.assertEqual(status, 200)
            status, _, _ = api(port, "GET", "/api/state",
                               headers={"Cookie": alice_cookie})
            self.assertEqual(status, 401)
            status, _, _ = api(port, "GET", "/api/state",
                               headers={"Cookie": bob_cookie})
            self.assertEqual(status, 200)

    def test_http_trade_requires_the_correct_recipient_session(self):
        with serve(self.game) as port:
            credentials = []
            for username, name in (("alice", "Alice River"),
                                   ("bob", "Bryn Stone"),
                                   ("mallory", "Mara Vale")):
                status, registered, headers = api(port, "POST", "/api/auth/register", {
                    "username": username, "password": PASSWORD, "display_name": name})
                self.assertEqual(status, 200)
                credentials.append((registered["state"]["actor_id"],
                                    headers["Set-Cookie"].split(";", 1)[0],
                                    registered["csrf"]))
            alice, alice_cookie, alice_csrf = credentials[0]
            bob, bob_cookie, bob_csrf = credentials[1]
            mallory, mal_cookie, mal_csrf = credentials[2]
            offer = {"gold": 20, "items": [], "gear_ids": []}
            request = {"gold": 15, "items": [], "gear_ids": []}
            status, proposal, _ = api(port, "POST", "/api/action", {
                "action": "propose_trade",
                "params": {"recipient_id": bob, "offer": offer, "request": request},
                "id": "trade-maker-1"
            }, headers={"Cookie": alice_cookie, "X-CSRF-Token": alice_csrf})
            self.assertEqual(status, 200)
            trade = proposal["result"]
            status, outsider, _ = api(port, "GET", "/api/state",
                                      headers={"Cookie": mal_cookie})
            self.assertEqual(status, 200)
            self.assertNotIn(trade["id"], [t["id"] for t in outsider["trades"]])
            status, denied, _ = api(port, "POST", "/api/action", {
                "action": "accept_trade",
                "params": {"trade_id": trade["id"], "terms_hash": trade["terms_hash"]},
                "id": "trade-mallory-1"
            }, headers={"Cookie": mal_cookie, "X-CSRF-Token": mal_csrf})
            self.assertEqual(status, 400)
            status, accepted, _ = api(port, "POST", "/api/action", {
                "action": "accept_trade",
                "params": {"trade_id": trade["id"], "terms_hash": trade["terms_hash"]},
                "id": "trade-bob-1"
            }, headers={"Cookie": bob_cookie, "X-CSRF-Token": bob_csrf})
            self.assertEqual(status, 200)
            self.assertEqual(accepted["state"]["player"]["gold"], 245)
            status, alice_now, _ = api(port, "GET", "/api/state",
                                       headers={"Cookie": alice_cookie})
            self.assertEqual(status, 200)
            self.assertEqual(alice_now["player"]["gold"], 235)
            self.assertEqual(self.game.world.total_gold, self.game.world.initial_gold)

    def test_host_and_cross_origin_validation(self):
        with serve(self.game) as port:
            status, _, _ = api(port, "GET", "/api/health",
                                headers={"Host": "attacker.example"})
            self.assertEqual(status, 403)
            status, _, _ = api(port, "POST", "/api/auth/register",
                               {"username": "alice", "password": PASSWORD,
                                "display_name": "Alice River"},
                               headers={"Origin": "https://evil.example"})
            self.assertEqual(status, 403)
            self.assertEqual(self.game.db.execute(
                "SELECT COUNT(*) FROM accounts").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
