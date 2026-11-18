"""Chronicle audit, legacy save migration and live public city visibility."""
from realm_fixtures import GOLDMEADOW
from medieval_world_sim.catalog import CAPITAL, CITIES

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web.session import GameSession, SaveError, event_category
from test_multiplayer_auth import serve
from test_live_activity import LiveEventTests, next_sse_activity


PASSWORD = "correct horse battery staple"


def finish_trip(game, principal, actor_id, receipt_prefix):
    remaining = game.world.actors[actor_id].arrival_minute - game.world.minute
    step_number = 0
    while remaining:
        chunk = min(1440, remaining)
        game.advance(principal, chunk, f"{receipt_prefix}-{step_number}")
        remaining -= chunk
        step_number += 1



class ChronicleAuditTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / "multi.sqlite"
        self.game = MultiplayerGame(self.db, require_invites=False, dev_fast_forward=True)
        self.a = self.game.identity(self.game.register_and_login(
            "alice", PASSWORD, "Alice River")[0]).actor_id
        self.b = self.game.identity(self.game.register_and_login(
            "bob", PASSWORD, "Bryn Stone")[0]).actor_id
        self.c = self.game.identity(self.game.register_and_login(
            "carol", PASSWORD, "Carol Vale")[0]).actor_id

    def tearDown(self):
        self.game.close()
        self.folder.cleanup()

    def test_new_players_spawn_crownreach_old_player_spawns_unchanged(self):
        for actor_id in (self.a, self.b, self.c):
            self.assertEqual(self.game.snapshot(actor_id)["player"]["city"],
                             "crownreach")
        self.game.action(self.b, "travel",
                         {"destination": GOLDMEADOW}, "leave")
        finish_trip(self.game, self.a, self.b, "pass-time")
        self.assertEqual(self.game.snapshot(self.b)["player"]["city"], GOLDMEADOW)
        self.game.close()
        self.game = MultiplayerGame(self.db, require_invites=False, dev_fast_forward=True)
        self.assertEqual(self.game.snapshot(self.b)["player"]["city"], GOLDMEADOW)
        self.assertEqual(self.game.snapshot(self.a)["player"]["city"], "crownreach")

    def test_trade_events_visible_to_both_parties_with_exact_terms_and_timestamps(self):
        package = {"gold": 12, "items": [], "gear_ids": []}
        wanted = {"gold": 8, "items": [], "gear_ids": []}
        offer = self.game.action(self.a, "propose_trade", {
            "recipient_id": self.b, "offer": package, "request": wanted
        }, "trade-offer")
        self.game.action(self.b, "accept_trade", {
            "trade_id": offer["id"], "terms_hash": offer["terms_hash"]
        }, "trade-accept")
        for actor_id in (self.a, self.b):
            view = self.game.snapshot(actor_id)
            trade_events = [event for event in view["events"]
                            if event["category"] == "Trade"]
            self.assertEqual({event["kind"] for event in trade_events},
                             {"trade_proposed", "trade_settled"})
            self.assertTrue(any("12g" in event["text"] and "8g" in event["text"]
                                for event in trade_events))
            for event in trade_events:
                self.assertIsNotNone(datetime.fromisoformat(event["recorded_at"]).tzinfo)
                self.assertIsInstance(event["id"], int)
            self.assertTrue(all(event["category"] in {
                "Trade", "Combat", "Travel", "University", "Economy",
                "Equipment", "Magic", "Health", "Racing", "Property",
                "Guild", "Progression", "Other"}
                for event in view["events"]))
        self.assertEqual([e for e in self.game.snapshot(self.c)["events"]
                          if e["category"] == "Trade"], [])
        before = {account: self.game.snapshot(account)["events"] for account in
                  (self.a, self.b, self.c)}
        self.game.close()
        self.game = MultiplayerGame(self.db, require_invites=False, dev_fast_forward=True)
        for account, events in before.items():
            self.assertEqual(self.game.snapshot(account)["events"], events)

    def test_rejected_and_cancelled_trade_visible_to_both(self):
        offer = self.game.action(self.a, "propose_trade", {
            "recipient_id": self.b,
            "offer": {"gold": 20, "items": [], "gear_ids": []},
            "request": {"gold": 0, "items": [], "gear_ids": []}
        }, "gift")
        self.game.action(self.b, "close_trade", {"trade_id": offer["id"]},
                         "reject")
        for actor_id in (self.a, self.b):
            events = self.game.snapshot(actor_id)["events"]
            self.assertTrue(any(e["kind"] == "trade_closed" for e in events))
        self.assertFalse(any(e["category"] == "Trade" for e in
                             self.game.snapshot(self.c)["events"]))

    def test_old_sqlite_journal_migrates_without_fabricating_past_timestamps(self):
        self.game.action(self.a, "claim_merit",
                         {"achievement": "first_steps"}, "old-command")
        # Simulate a pre-timestamp-database entry. Leave the schema in place.
        self.game.db.execute(
            "UPDATE world_journal SET recorded_at=NULL WHERE request_id='old-command'")
        self.game.close()
        self.game = MultiplayerGame(self.db, require_invites=False, dev_fast_forward=True)
        past = [e for e in self.game.snapshot(self.a)["events"]
                if e["kind"] == "merit_claimed"]
        self.assertEqual(len(past), 1)
        self.assertIsNone(past[0]["recorded_at"])
        # Ensure a new event is timestamped without inventing past timestamps.
        self.game.action(self.a, "buy_home", {"tier": "room"}, "new-command")
        current = [e for e in self.game.snapshot(self.a)["events"]
                   if e["kind"] in ("merit_claimed", "home_purchased")]
        self.assertIsNotNone(current[0]["recorded_at"])
        self.assertIsNone(current[1]["recorded_at"])

    def test_presence_stream_reflects_shared_city_and_attack_eligibility(self):
        original = self.game.social_snapshot(self.a)
        alice_bob = next(x for x in original["users"] if x["id"] == self.b)
        self.assertTrue(alice_bob["can_attack"])
        self.game.action(self.b, "travel", {"destination": GOLDMEADOW},
                         "bob-outbound")
        in_transit = self.game.social_snapshot(self.a)
        bob_info = next(x for x in in_transit["users"] if x["id"] == self.b)
        self.assertFalse(bob_info["can_attack"])
        finish_trip(self.game, self.c, self.b, "bob-arrives")
        arrived = self.game.social_snapshot(self.a)
        bob_info = next(x for x in arrived["users"] if x["id"] == self.b)
        self.assertEqual(bob_info["city"], GOLDMEADOW)
        self.assertFalse(bob_info["can_attack"])
        self.game.action(self.a, "travel", {"destination": GOLDMEADOW},
                         "alice-outbound")
        finish_trip(self.game, self.c, self.a, "alice-arrives")
        together = self.game.social_snapshot(self.a)
        bob_info = next(x for x in together["users"] if x["id"] == self.b)
        self.assertTrue(bob_info["can_attack"])
        self.assertNotIn("gold", bob_info)
        self.assertNotIn("strength", bob_info)
        self.assertNotIn("inventory", bob_info)
        self.game.world.assert_invariants()

    def test_authentic_stream_pushes_arrivals_to_other_players(self):
        token, _ = self.game.login("alice", PASSWORD)
        target = min((c for c in CITIES if c != CAPITAL),
                     key=lambda city: self.game.world.travel_minutes(CAPITAL, city))
        with serve(self.game) as port:
            conn, response = LiveEventTests.stream(port, token)
            try:
                self.assertEqual(response.status, 200)
                first = next_sse_activity(response)
                bob = next(user for user in first["users"]
                           if user["id"] == self.b)
                self.assertEqual(bob["city"], "crownreach")
                self.assertTrue(bob["can_attack"])
                self.game.action(self.b, "travel",
                                 {"destination": target}, "outbound")
                moving = next_sse_activity(response)
                self.assertFalse(next(u for u in moving["users"]
                    if u["id"] == self.b)["can_attack"])
                finish_trip(self.game, self.c, self.b, "outbound-arrival")
                elsewhere = next_sse_activity(response)
                bob = next(u for u in elsewhere["users"] if u["id"] == self.b)
                self.assertEqual(bob["city"], target)
                self.assertFalse(bob["can_attack"])
                self.game.action(self.b, "travel",
                                 {"destination": "crownreach"}, "returning")
                next_sse_activity(response)
                finish_trip(self.game, self.c, self.b, "return-arrival")
                returned = next_sse_activity(response)
                bob = next(u for u in returned["users"] if u["id"] == self.b)
                self.assertEqual(bob["city"], "crownreach")
                self.assertTrue(bob["can_attack"])
                self.assertNotIn("gold", bob)
                self.assertNotIn("inventory", bob)
            finally:
                response.close()
                conn.close()

    def test_duel_encounter_projection_groups_by_start_event_not_time(self):
        from medieval_world_sim.core.engine import WorldEngine
        from medieval_world_sim.core.entities import Actor
        from medieval_world_sim.web.projection import activity_projection
        world = WorldEngine([
            Actor("a", "human"), Actor("b", "human"),
            Actor("c", "human"), Actor("d", "human")
        ])
        world._emit("duel_started", "a", "b", 0)
        start_a = world.events[-1].event_id
        world._emit("duel_started", "c", "d", 0)
        world._emit("duel_round", "a", "b", 1, "fists", 2, 1)
        world._emit("duel_flee_attempt", "a", "b", "b", 2, False)
        world._emit("duel_draw", "a", "b", 10)
        events, _, _ = activity_projection(
            world, "a", "Alice", {}, {"a":"Alice", "b":"Bob"},
            {}, True)
        fights = [e for e in events if e["kind"].startswith("duel_")]
        self.assertEqual(len(fights), 4)
        self.assertEqual({e["encounter_id"] for e in fights}, {start_a})
        self.assertTrue(all(e["encounter_outcome"] == "Draw" for e in fights))
        self.assertTrue(all(e["encounter_attacker"] == "Alice" for e in fights))
        self.assertTrue(all(e["encounter_defender"] == "Bob" for e in fights))
        self.assertFalse(any(e.get("encounter_attacker") == "Carol" for e in fights))

    def test_known_event_types_have_stable_categories(self):
        self.assertEqual(event_category("trade_settled"), "Trade")
        self.assertEqual(event_category("pvp_strike"), "Combat")
        self.assertEqual(event_category("arrived"), "Travel")
        self.assertEqual(event_category("course_started"), "University")
        self.assertEqual(event_category("unknown_kind"), "Other")


class LegacyStartTests(unittest.TestCase):
    def test_single_player_uses_current_start_and_rejects_missing_location(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            game = GameSession(path)
            game.create("Aldric Thorn")
            self.assertEqual(game.snapshot()["player"]["city"], CAPITAL)
            self.assertEqual(GameSession(path).snapshot(), game.snapshot())
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored.pop("start_city", None)
            path.write_text(json.dumps(stored), encoding="utf-8")
            with self.assertRaises(SaveError):
                GameSession(path)

if __name__ == "__main__":
    unittest.main()
