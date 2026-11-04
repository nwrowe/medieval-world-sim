"""Chronicle audit, legacy save migration and live public city visibility."""
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web.session import GameSession, event_category


PASSWORD = "correct horse battery staple"


class ChronicleAuditTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / "multi.sqlite"
        self.game = MultiplayerGame(self.db)
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
                         {"destination": "goldmeadow"}, "leave")
        minutes = self.game.world.actors[self.b].arrival_minute - self.game.world.minute
        self.game.advance(self.a, minutes, "pass-time")
        self.assertEqual(self.game.snapshot(self.b)["player"]["city"], "goldmeadow")
        self.game.close()
        self.game = MultiplayerGame(self.db)
        self.assertEqual(self.game.snapshot(self.b)["player"]["city"], "goldmeadow")
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
                "Equipment", "Magic", "Property", "Guild", "Progression", "Other"}
                for event in view["events"]))
        self.assertEqual([e for e in self.game.snapshot(self.c)["events"]
                          if e["category"] == "Trade"], [])
        before = {account: self.game.snapshot(account)["events"] for account in
                  (self.a, self.b, self.c)}
        self.game.close()
        self.game = MultiplayerGame(self.db)
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
        self.game.action(self.a, "travel",
                         {"destination": "goldmeadow"}, "to-fields")
        self.game.advance(self.b, 60, "arrive-fields")
        self.game.action(self.a, "gather",
                         {"item": "grain", "quantity": 1}, "old-command")
        # Simulate a pre-timestamp-database entry. Leave the schema in place.
        self.game.db.execute(
            "UPDATE world_journal SET recorded_at=NULL WHERE request_id='old-command'")
        self.game.close()
        self.game = MultiplayerGame(self.db)
        past = [e for e in self.game.snapshot(self.a)["events"]
                if e["kind"] == "gathered"]
        self.assertEqual(len(past), 1)
        self.assertIsNone(past[0]["recorded_at"])
        self.game.action(self.a, "gather",
                         {"item": "grain", "quantity": 1}, "new-command")
        current = [e for e in self.game.snapshot(self.a)["events"]
                   if e["kind"] == "gathered"]
        self.assertIsNotNone(current[0]["recorded_at"])
        self.assertIsNone(current[1]["recorded_at"])

    def test_presence_stream_reflects_shared_city_and_attack_eligibility(self):
        original = self.game.social_snapshot(self.a)
        alice_bob = next(x for x in original["users"] if x["id"] == self.b)
        self.assertTrue(alice_bob["can_attack"])
        self.game.action(self.b, "travel", {"destination": "goldmeadow"},
                         "bob-outbound")
        in_transit = self.game.social_snapshot(self.a)
        bob_info = next(x for x in in_transit["users"] if x["id"] == self.b)
        self.assertFalse(bob_info["can_attack"])
        trip = self.game.world.actors[self.b].arrival_minute - self.game.world.minute
        self.game.advance(self.c, trip, "bob-arrives")
        arrived = self.game.social_snapshot(self.a)
        bob_info = next(x for x in arrived["users"] if x["id"] == self.b)
        self.assertEqual(bob_info["city"], "goldmeadow")
        self.assertFalse(bob_info["can_attack"])
        self.game.action(self.a, "travel", {"destination": "goldmeadow"},
                         "alice-outbound")
        trip = self.game.world.actors[self.a].arrival_minute - self.game.world.minute
        self.game.advance(self.c, trip, "alice-arrives")
        together = self.game.social_snapshot(self.a)
        bob_info = next(x for x in together["users"] if x["id"] == self.b)
        self.assertTrue(bob_info["can_attack"])
        self.assertNotIn("gold", bob_info)
        self.assertNotIn("strength", bob_info)
        self.assertNotIn("inventory", bob_info)
        self.game.world.assert_invariants()

    def test_known_event_types_have_stable_categories(self):
        self.assertEqual(event_category("trade_settled"), "Trade")
        self.assertEqual(event_category("pvp_strike"), "Combat")
        self.assertEqual(event_category("arrived"), "Travel")
        self.assertEqual(event_category("course_started"), "University")
        self.assertEqual(event_category("unknown_kind"), "Other")


class LegacyStartTests(unittest.TestCase):
    def test_single_player_new_start_and_old_goldmeadow_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            game = GameSession(path)
            game.create("Aldric Thorn")
            self.assertEqual(game.snapshot()["player"]["city"], "crownreach")
            self.assertEqual(GameSession(path).snapshot()["player"]["city"],
                             "crownreach")
            stored = json.loads(path.read_text(encoding="utf-8"))
            # Pre-change saves have no start_city field and began in Goldmeadow.
            stored.pop("start_city", None)
            path.write_text(json.dumps(stored), encoding="utf-8")
            old = GameSession(path)
            self.assertEqual(old.snapshot()["player"]["city"], "goldmeadow")
            old.action("gather", {"item": "grain", "quantity": 1}, "old-gather")
            self.assertEqual(GameSession(path).snapshot(), old.snapshot())


if __name__ == "__main__":
    unittest.main()
