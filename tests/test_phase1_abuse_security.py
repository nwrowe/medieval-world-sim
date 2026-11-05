"""Adversarial regressions for Phase 1 local multiplayer safety boundaries."""
import hashlib
import hmac
import json
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web.rate_limit import RateLimiter
from test_multiplayer_auth import serve
from test_web_client import api


PASSWORD = "correct horse battery staple"
REPO_MODE = "medieval_world_sim.web.multiplayer"


class EnrollmentAbuseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / "secure.sqlite3"
        self.game = MultiplayerGame(self.db)

    def tearDown(self):
        self.game.close()
        self.folder.cleanup()

    def test_self_service_minting_forbidden_and_invites_single_use(self):
        initial = self.game.world.initial_gold
        with self.assertRaises(ActionError):
            self.game.register("alice", PASSWORD, "Alice River")
        with self.assertRaises(ActionError):
            self.game.register("alice", PASSWORD, "Alice River", "made-up-code")
        self.assertEqual(self.game.world.initial_gold, initial)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM accounts").fetchone()[0], 0)
        codes = self.game.issue_invites(2)
        self.assertEqual(len(set(codes)), 2)
        actor = self.game.register("alice", PASSWORD, "Alice River", codes[0])
        self.assertEqual(self.game.snapshot(actor)["player"]["gold"], 240)
        self.assertEqual(self.game.world.initial_gold, initial + 240)
        self.assertEqual(self.game.world.total_gold, initial + 240)
        with self.assertRaises(ActionError):
            self.game.register("other", PASSWORD, "Other Player", codes[0])
        with self.assertRaises(ActionError):
            self.game.register("alice", PASSWORD, "Different Player", codes[1])
        second = self.game.register("bryn", PASSWORD, "Bryn Stone", codes[1])
        self.assertEqual(self.game.snapshot(second)["player"]["gold"], 240)
        self.game.close()
        self.game = MultiplayerGame(self.db)
        self.assertEqual(self.game.snapshot(actor)["player"]["gold"], 240)
        self.assertEqual(self.game.world.total_gold, initial + 480)
        with self.assertRaises(ActionError):
            self.game.register("carol", PASSWORD, "Carol Vale", codes[1])

    def test_concurrent_invite_redemption_never_duplicates_starter_gold(self):
        from concurrent.futures import ThreadPoolExecutor
        code = self.game.issue_invites(1)[0]
        baseline = self.game.world.initial_gold
        def attempt(i):
            try:
                return self.game.register(
                    f"player{i}", PASSWORD, f"Player {chr(65 + i)}", code)
            except ActionError:
                return None
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(attempt, range(8)))
        self.assertEqual(sum(x is not None for x in results), 1)
        self.assertEqual(self.game.world.initial_gold, baseline + 240)
        self.assertEqual(self.game.world.total_gold, baseline + 240)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM accounts").fetchone()[0], 1)
        self.game.world.assert_invariants()

    def test_admin_codes_are_not_stored_plaintext(self):
        token = self.game.issue_invites(1)[0]
        db_data = self.db.read_bytes()
        self.assertNotIn(token.encode(), db_data)
        row = self.game.db.execute("SELECT digest FROM registration_invites").fetchone()
        self.assertEqual(row[0], hashlib.sha256(token.encode()).digest())
        with self.assertRaises(ValueError):
            self.game.issue_invites(1000000)

    def test_http_invite_required_and_csrf_protected_registration(self):
        code = self.game.issue_invites(1)[0]
        with serve(self.game) as port:
            status, health, _ = api(port, "GET", "/api/health")
            self.assertEqual(status, 200)
            self.assertTrue(health["invite_required"])
            self.assertFalse(health["dev_fast_forward"])
            payload = {"username": "alice", "password": PASSWORD,
                       "display_name": "Alice River"}
            status, _, _ = api(port, "POST", "/api/auth/register", payload)
            self.assertEqual(status, 400)
            status, outcome, _ = api(port, "POST", "/api/auth/register",
                                     {**payload, "invite": code})
            self.assertEqual(status, 200)
            self.assertEqual(outcome["state"]["player"]["gold"], 240)
            status, _, _ = api(port, "POST", "/api/auth/register",
                               {"username": "bob", "password": PASSWORD,
                                "display_name": "Bob Stone", "invite": code})
            self.assertEqual(status, 400)


class ClockAndRandomnessTests(unittest.TestCase):
    def test_trusted_clock_rejects_forged_advance_and_replays(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "clock.sqlite3"
            starting_at = 1_700_000_000
            with patch(REPO_MODE + ".time.time", return_value=starting_at):
                game = MultiplayerGame(db)
                code = game.issue_invites(1)[0]
                actor = game.register("alice", PASSWORD, "Alice River", code)
                self.assertEqual(game.world.minute, 0)
                with self.assertRaises(ActionError):
                    game.advance(actor, 1440, "forged-fast-forward")
                self.assertEqual(game.world.minute, 0)
                with self.assertRaises(ActionError):
                    game.action(actor, "send_chat",
                                {"kind": "global", "target": "", "message": "clock"},
                                "__clock__:1700000000")
            with patch(REPO_MODE + ".time.time", return_value=starting_at + 185):
                view = game.snapshot(actor)
                self.assertEqual(view["minute"], 3)
                self.assertEqual(game.world.minute, 3)
                self.assertEqual(game.db.execute(
                    "SELECT COUNT(*) FROM world_journal WHERE server_clock=1"
                ).fetchone()[0], 1)
                for i in range(4):
                    with self.assertRaises(ActionError):
                        game.advance(actor, 1440, "forged-" + str(i))
                self.assertEqual(game.snapshot(actor)["minute"], 3)
                game.close()
                game = MultiplayerGame(db)
                self.assertEqual(game.snapshot(actor)["minute"], 3)
                self.assertEqual(game.world.total_gold, game.world.initial_gold)
                game.close()

    def test_private_keyed_race_and_magic_outcomes_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "rewards.sqlite3"
            game = MultiplayerGame(db, require_invites=False,
                                   dev_fast_forward=True)
            actor = game.register("alice", PASSWORD, "Alice River")
            self.assertEqual(len(game._rng_key), 32)
            game.action(actor, "buy_racehorse", {"breed": "moor_pony"}, "horse")
            race = game.action(actor, "race_horse",
                               {"breed": "moor_pony"}, "race")
            record = game.db.execute(
                "SELECT secure_roll FROM world_journal WHERE request_id='race'"
            ).fetchone()
            self.assertEqual(record[0], 1)
            seed = f"42:{actor}:moor_pony:0:0".encode()
            expected = [
                int.from_bytes(hmac.digest(
                    game._rng_key, seed + bytes([i]), "sha256")[:4], "big") % 19
                for i in range(3)
            ]
            self.assertEqual(race["rival_scores"], [20 + expected[1],
                                                   23 + expected[2]])
            game.action(actor, "unlock_magic",
                        {"node_id": "enchantment.etch_rune"}, "learn")
            magic = game.action(actor, "practice_magic",
                                {"node_id": "enchantment.etch_rune"}, "practice")
            payload = f"42|{actor}|enchantment.etch_rune|0|0".encode()
            expected_roll = int.from_bytes(
                hmac.digest(game._rng_key, payload, "sha256")[:8], "big") % 100 + 1
            self.assertEqual(magic["roll"], expected_roll)
            self.assertEqual(game.db.execute(
                "SELECT secure_roll FROM world_journal WHERE request_id='practice'"
            ).fetchone()[0], 1)
            self.assertNotIn(game._rng_key.hex(),
                             json.dumps(game.snapshot(actor)))
            game.close()
            game = MultiplayerGame(db, require_invites=False,
                                   dev_fast_forward=True)
            self.assertEqual(game.world.state.race_results[actor]["rival_scores"],
                             race["rival_scores"])
            self.assertEqual(game.world.actors[actor].magic.attempts, 1)
            self.assertEqual(game.action(actor, "practice_magic",
                             {"node_id": "enchantment.etch_rune"}, "practice"),
                             asdict(magic) if not isinstance(magic, dict) else magic)
            game.world.assert_invariants()
            game.close()

    def test_old_unkeyed_action_replays_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "historical.sqlite3"
            game = MultiplayerGame(db, require_invites=False,
                                   dev_fast_forward=True)
            actor = game.register("alice", PASSWORD, "Alice River")
            game.action(actor, "unlock_magic",
                        {"node_id": "enchantment.etch_rune"}, "unlock")
            params = {"node_id": "enchantment.etch_rune"}
            key = "legacy-spell"
            engine_id = game._engine_id(actor, key)
            old = game.world.execute(actor, "practice_magic", params, engine_id)
            legacy_roll = old.roll
            payload = json.dumps(params, sort_keys=True, separators=(",", ":"))
            game.db.execute(
                "INSERT INTO world_journal("
                "kind,actor_id,action,payload,request_id,result_json,recorded_at"
                ") VALUES('action',?,?,?,?,?,NULL)",
                (actor, "practice_magic", payload, key,
                 json.dumps(asdict(old))))
            game.close()
            game = MultiplayerGame(db, require_invites=False,
                                   dev_fast_forward=True)
            self.assertEqual(game.world.actors[actor].magic.attempts, 1)
            record = next(e for e in game.world.events
                          if e.kind == "magic_practiced")
            self.assertEqual(record.data["roll"], legacy_roll)
            self.assertIsNone(game.db.execute(
                "SELECT secure_roll FROM world_journal WHERE request_id=?",
                (key,)).fetchone()[0])
            game.world.assert_invariants()
            game.close()


class RequestAndJournalExhaustionTests(unittest.TestCase):
    def test_limiter_is_thread_safe_and_bounded(self):
        from concurrent.futures import ThreadPoolExecutor
        limiter = RateLimiter(max_keys=8)
        with patch("medieval_world_sim.web.rate_limit.time.monotonic",
                   return_value=100.0):
            with ThreadPoolExecutor(max_workers=16) as pool:
                results = list(pool.map(
                    lambda _: limiter.allow(("player", "alice"), 5, 60), range(40)))
            self.assertEqual(sum(results), 5)
            for i in range(20):
                limiter.allow(("user", str(i)), 1, 60)
            self.assertLessEqual(len(limiter._buckets), 8)
        with patch("medieval_world_sim.web.rate_limit.time.monotonic",
                   return_value=160.0):
            self.assertTrue(limiter.allow(("player", "alice"), 5, 60))

    def test_committed_journal_budget_blocks_new_commands_not_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            game = MultiplayerGame(Path(folder) / "quotas.db",
                                   require_invites=False, dev_fast_forward=True)
            a = game.register("alice", PASSWORD, "Alice River")
            payload = {"kind": "global", "target": "", "message": "hi"}
            first = game.action(a, "send_chat", payload, "first")
            with patch(REPO_MODE + ".MAX_ACCOUNT_COMMANDS_PER_DAY", 1):
                self.assertEqual(game.action(a, "send_chat", payload, "first"), first)
                with self.assertRaises(ActionError):
                    game.action(a, "send_chat", payload, "second")
            self.assertEqual(len(game.snapshot(a)["chat"]["messages"]), 1)
            self.assertEqual(game.db.execute(
                "SELECT COUNT(*) FROM world_journal WHERE kind='action'"
            ).fetchone()[0], 1)
            game.world.assert_invariants()
            game.close()

    def test_account_chat_and_global_daily_budgets(self):
        with tempfile.TemporaryDirectory() as folder:
            game = MultiplayerGame(Path(folder) / "budget.db",
                                   require_invites=False, dev_fast_forward=True)
            alice = game.register("alice", PASSWORD, "Alice River")
            bob = game.register("bobby", PASSWORD, "Bobby Stone")
            params = {"kind": "global", "target": "", "message": "hello"}
            game.action(alice, "send_chat", params, "one")
            with patch(REPO_MODE + ".MAX_CHAT_COMMANDS_PER_DAY", 1):
                with self.assertRaises(ActionError):
                    game.action(alice, "send_chat", params, "two")
                # Another player still has their own chat budget.
                game.action(bob, "send_chat", params, "bob-one")
            with patch(REPO_MODE + ".MAX_GLOBAL_COMMANDS_PER_DAY", 2):
                with self.assertRaises(ActionError):
                    game.action(alice, "send_chat", params, "three")
            self.assertEqual(len(game.snapshot(alice)["chat"]["messages"]), 2)
            game.world.assert_invariants()
            game.close()

    def test_http_login_flood_is_throttled(self):
        with tempfile.TemporaryDirectory() as folder:
            game = MultiplayerGame(Path(folder) / "http.db",
                                   require_invites=False, dev_fast_forward=True)
            with serve(game) as port:
                responses = []
                for _ in range(13):
                    status, _, _ = api(port, "POST", "/api/auth/login",
                                       {"username": "nonexistent",
                                        "password": "bad password"})
                    responses.append(status)
                self.assertIn(429, responses)
                self.assertLessEqual(responses.count(401), 10)
            game.close()


if __name__ == "__main__":
    unittest.main()
