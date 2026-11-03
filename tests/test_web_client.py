"""Web-client contract: real authorized engine actions, JSON saves and local HTTP."""
from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from importlib.resources import files

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.session import GameSession, SaveError
from medieval_world_sim.web.server import GameHTTPServer


@contextmanager
def running_server(session, token=None):
    server = GameHTTPServer(("127.0.0.1", 0), session, token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
    headers = dict(headers or {})
    payload = None if body is None else json.dumps(body)
    if payload is not None:
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, payload, headers)
        response = conn.getresponse()
        raw = response.read()
        return response.status, dict(response.getheaders()), raw
    finally:
        conn.close()


def api(port, method, path, body=None, headers=None):
    status, response_headers, raw = request(port, method, path, body, headers)
    return status, json.loads(raw), response_headers


class WebSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.save = Path(self.temp.name) / "world.json"
        self.game = GameSession(self.save)

    def tearDown(self):
        self.temp.cleanup()

    def test_create_and_read_only_snapshot(self):
        self.assertFalse(self.game.snapshot()["started"])
        self.game.create("River Stone")
        view = self.game.snapshot()
        self.assertTrue(view["started"])
        self.assertEqual(view["player"]["gold"], 240)
        self.assertEqual(view["player"]["city"], "goldmeadow")
        self.assertEqual(len(view["cities"]), 5)
        self.assertEqual(len(view["magic_nodes"]), 37)
        self.assertEqual(view["player"]["cargo_limit"], 12)
        self.assertTrue(self.save.exists())
        with self.assertRaises(ActionError):
            self.game.create("Another Hero")

    def test_action_journal_survives_restart_and_remains_authoritative(self):
        self.game.create("Alin Marlow")
        initial_gold = self.game.world.initial_gold
        self.game.action("gather", {"item": "grain", "quantity": 2}, "gather-1")
        self.game.action("regional_sell", {"item": "grain", "quantity": 1}, "sell-1")
        self.game.advance(90)
        self.game.action("travel", {"destination": "crownreach"}, "travel-1")
        self.game.advance(60)
        before = self.game.snapshot()
        second = GameSession(self.save)
        self.assertEqual(second.snapshot(), before)
        self.assertEqual(second.world.total_gold, initial_gold)
        self.assertEqual(second.world.state.command_receipts["gather-1"][0][1], "gather")
        self.assertIsNone(second.snapshot()["player"]["destination"])
        self.assertEqual(second.snapshot()["player"]["city"], "crownreach")
        second.world.assert_invariants()

    def test_saved_command_id_is_not_charged_twice(self):
        self.game.create("Eryn Vale")
        args = {"item": "grain", "quantity": 2}
        self.game.action("regional_buy", args, "one-purchase")
        before = self.game.snapshot()
        count = len(self.game.records)
        first = self.game.action("regional_buy", args, "one-purchase")
        self.assertIsInstance(first, int)
        self.assertEqual(self.game.snapshot(), before)
        self.assertEqual(len(self.game.records), count)
        with self.assertRaises(ActionError):
            self.game.action("regional_buy", {"item": "grain", "quantity": 1}, "one-purchase")

    def test_forbidden_actions_and_invalid_time_do_not_modify_save(self):
        self.game.create("Ash Rowan")
        before = self.save.read_bytes()
        for action in ("attack", "hire", "found_company", "set_wage", "admin"):
            with self.assertRaises(ActionError):
                self.game.action(action, {}, "hack-" + action)
        for amount in (0, -1, 1441, True, 10.5):
            with self.assertRaises(ActionError):
                self.game.advance(amount)
        self.assertEqual(self.save.read_bytes(), before)

    def test_corrupt_save_is_reported_instead_of_overwritten(self):
        self.save.write_text('{"version":99}', encoding="utf-8")
        with self.assertRaises(SaveError):
            GameSession(self.save)
        self.assertEqual(self.save.read_text(), '{"version":99}')

    def test_housing_and_magic_can_be_played_and_reloaded(self):
        self.game.create("Nora Pine")
        self.game.action("buy_home", {"tier": "room"}, "home-1")
        self.game.action("unlock_magic", {"node_id": "divination.read_omens"}, "magic-1")
        result = self.game.action("practice_magic", {"node_id": "divination.read_omens"}, "magic-2")
        self.assertGreater(result.xp_gained, 0)
        after = GameSession(self.save).snapshot()
        self.assertEqual(after["housing"]["tier"], "room")
        self.assertIn("divination.read_omens",
                      [x["node_id"] for x in after["magic_nodes"] if x["unlocked"]])
        self.assertLess(after["player"]["mana"], 100)
        self.assertEqual(after["player"]["gold"], 150)
        self.assertEqual(self.game.world.total_gold, self.game.world.initial_gold)


class WebHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.save = Path(self.temp.name) / "world.json"
        self.game = GameSession(self.save)

    def tearDown(self):
        self.temp.cleanup()

    def test_http_create_gather_travel_market_and_restart(self):
        with running_server(self.game) as port:
            status, data, headers = api(port, "GET", "/api/state")
            self.assertEqual(status, 200)
            self.assertFalse(data["started"])
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            status, data, _ = api(port, "POST", "/api/new", {"name": "Carin Moss"})
            self.assertEqual(status, 200)
            self.assertEqual(data["state"]["name"], "Carin Moss")
            status, data, _ = api(port, "POST", "/api/action",
                                  {"action": "gather", "params": {"item": "grain", "quantity": 2},
                                   "id": "gather-a"})
            self.assertEqual(status, 200)
            self.assertEqual(data["state"]["player"]["inventory"]["grain"], 2)
            status, data, _ = api(port, "POST", "/api/action",
                                  {"action": "regional_sell",
                                   "params": {"item": "grain", "quantity": 1}, "id": "sell-a"})
            self.assertEqual(status, 200)
            self.assertEqual(data["state"]["player"]["inventory"]["grain"], 1)
            status, data, _ = api(port, "POST", "/api/action",
                                  {"action": "travel", "params": {"destination": "crownreach"},
                                   "id": "trip-a"})
            self.assertEqual(status, 200)
            self.assertEqual(data["state"]["player"]["destination"], "crownreach")
            status, data, _ = api(port, "POST", "/api/advance", {"minutes": 60})
            self.assertEqual(status, 200)
            self.assertEqual(data["state"]["player"]["city"], "crownreach")
            self.assertIsNone(data["state"]["player"]["destination"])
            final = data["state"]
        reloaded = GameSession(self.save)
        self.assertEqual(reloaded.snapshot(), final)
        reloaded.world.assert_invariants()

    def test_authentication_origin_and_mutation_boundary(self):
        self.game.create("Willow Fern")
        with running_server(self.game, token="secret-local-code") as port:
            status, data, _ = api(port, "GET", "/api/state")
            self.assertEqual(status, 401)
            status, data, _ = api(port, "GET", "/api/state",
                                  headers={"X-Game-Token": "secret-local-code"})
            self.assertEqual(status, 200)
            headers = {"X-Game-Token": "secret-local-code"}
            status, data, _ = api(port, "POST", "/api/action",
                                  {"action": "found_company", "params": {}, "id": "rogue"},
                                  headers=headers)
            self.assertEqual(status, 400)
            self.assertIn("not available", data["error"])
            status, data, _ = api(port, "POST", "/api/advance", {"minutes": 60},
                                  headers={**headers, "Origin": "https://evil.example"})
            self.assertEqual(status, 403)
            self.assertEqual(self.game.world.minute, 0)

    def test_static_assets_and_no_unknown_file_paths(self):
        self.game.create("Pine Brook")
        with running_server(self.game) as port:
            for path, marker in (
                ("/", b'<meta name="viewport"'),
                ("/app.js", b"Magic progression"),
                ("/styles.css", b"@media (max-width:640px)"),
                ("/favicon.svg", b"<svg"),
            ):
                status, headers, body = request(port, "GET", path)
                self.assertEqual(status, 200, path)
                self.assertIn(marker, body)
                self.assertIn("no-store", headers["Cache-Control"])
            status, data, _ = api(port, "GET", "/web/session.py")
            self.assertEqual(status, 404)
            status, data, _ = api(port, "GET", "/../private.json")
            self.assertEqual(status, 404)

    def test_rejected_actions_do_not_erase_existing_save(self):
        self.game.create("Flint Ford")
        before = self.save.read_bytes()
        with running_server(self.game) as port:
            status, data, _ = api(port, "POST", "/api/action",
                                  {"action": "regional_sell",
                                   "params": {"item": "iron_ore", "quantity": 10},
                                   "id": "invalid-sale"})
            self.assertEqual(status, 400)
            self.assertIn("error", data)
        self.assertEqual(self.save.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
