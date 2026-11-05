"""Same turn-based weapons/spells duel for NPC and human defenders.

Human defenders react server-side, without needing an online request or an
offensive turn. This module explicitly checks outcome limits, permissions,
replay, old one-swing journal compatibility, and conserved gold.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.multiplayer import MultiplayerGame

PASSWORD = "correct horse battery staple"


class MultiplayerDuelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "players.sqlite3"
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        self.alice = self.game.identity(self.game.register_and_login(
            "alice", PASSWORD, "Alice River")[0]).actor_id
        self.bob = self.game.identity(self.game.register_and_login(
            "bob", PASSWORD, "Bryn Stone")[0]).actor_id
        self.carol = self.game.identity(self.game.register_and_login(
            "carol", PASSWORD, "Carol Vale")[0]).actor_id

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def command(self, player, action, params, request_id):
        return self.game.action(player, action, params, request_id)

    def begin(self):
        return self.command(self.alice, "start_duel",
                            {"defender_id": self.bob}, "duel-start")

    def test_fists_auto_counter_and_defender_can_retreat_independently(self):
        initial_total = self.game.world.total_gold
        self.assertEqual(self.begin()["stamina_spent"], 0)
        att = self.game.snapshot(self.alice)["duel"]
        deff = self.game.snapshot(self.bob)["duel"]
        self.assertEqual(att["role"], "attacker")
        self.assertEqual(deff["role"], "defender")
        self.assertEqual(deff["opponent_id"], self.alice)
        self.assertEqual(deff["max_rounds"], 10)
        with self.assertRaises(ActionError):
            self.command(self.bob, "duel_turn",
                         {"move": "strike", "node_id": ""}, "forged-defender-turn")
        result = self.command(self.alice, "duel_turn",
                              {"move": "fists", "node_id": ""}, "first-fists")
        self.assertEqual(result["stamina_spent"], 2)
        self.assertGreater(result["retaliation"], 0)
        self.assertEqual(self.game.snapshot(self.alice)["player"]["stamina"], 98)
        self.assertEqual(self.game.snapshot(self.bob)["player"]["stamina"], 100)
        with self.assertRaises(ActionError):
            self.command(self.bob, "start_duel",
                         {"defender_id": self.carol}, "defender-aggressor")
        self.assertEqual(self.game.world.total_gold, initial_total)

        # Defender is not locked into an attacker's online presence.
        with patch("medieval_world_sim.web.multiplayer.secrets.randbits", return_value=1):
            ended = self.command(self.bob, "flee_duel", {}, "defender-retreat")
        self.assertEqual(ended["outcome"], "fled")
        self.assertIsNone(self.game.snapshot(self.alice)["duel"])
        self.assertIsNone(self.game.snapshot(self.bob)["duel"])
        self.assertEqual(self.game.snapshot(self.alice)["last_duel"]["outcome"],
                         "opponent_fled")
        self.assertEqual(self.game.snapshot(self.bob)["last_duel"]["outcome"],
                         "fled")
        self.assertEqual(self.game.world.total_gold, initial_total)
        self.assertEqual(self.game.snapshot(self.alice)["last_duel"]["gold"], 0)
        # A defender may choose to travel as soon as they flee.
        self.command(self.bob, "travel",
                     {"destination": "goldmeadow"}, "defender-road")
        self.assertEqual(self.game.snapshot(self.bob)["player"]["destination"],
                         "goldmeadow")
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        self.assertEqual(self.game.snapshot(self.alice)["last_duel"]["outcome"],
                         "opponent_fled")
        self.game.world.assert_invariants()

    def test_tenth_round_draw_no_gold_hospital_or_infinite_encounter(self):
        before = self.game.world.total_gold
        self.begin()
        for n in range(1, 11):
            answer = self.command(
                self.alice, "duel_turn", {"move": "guard", "node_id": ""},
                f"defensive-round-{n}")
            if n < 10:
                self.assertEqual(answer["outcome"], "ongoing")
                self.assertEqual(answer["round"], n)
            else:
                self.assertEqual(answer["outcome"], "draw")
                self.assertEqual(answer["rounds"], 10)
                self.assertEqual(answer["gold"], 0)
        for player in (self.alice, self.bob):
            snapshot = self.game.snapshot(player)
            self.assertEqual(snapshot["last_duel"]["outcome"], "draw")
            self.assertIsNone(snapshot["duel"])
            self.assertIsNone(snapshot["player"]["defeated_until"])
            self.assertGreater(snapshot["player"]["hp"], 0)
        self.assertEqual(self.game.snapshot(self.alice)["player"]["stamina"], 80)
        self.assertEqual(self.game.snapshot(self.bob)["player"]["stamina"], 100)
        self.assertEqual(self.game.world.total_gold, before)
        self.assertEqual(len([event for event in self.game.world.events
                             if event.kind == "duel_draw"]), 1)
        with self.assertRaises(ActionError):
            self.command(self.alice, "duel_turn",
                         {"move": "guard", "node_id": ""}, "round-eleven")
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        self.assertEqual(self.game.snapshot(self.alice)["last_duel"]["rounds"], 10)
        self.assertEqual(self.game.snapshot(self.bob)["last_duel"]["outcome"], "draw")
        self.game.world.assert_invariants()

    def test_full_duel_can_finish_with_victory_loot_and_hospitalization(self):
        start_gold = self.game.world.total_gold
        self.begin()
        last = None
        for round_number in range(1, 11):
            last = self.command(
                self.alice, "duel_turn", {"move": "fists", "node_id": ""},
                f"victory-fists-{round_number}")
            if last["outcome"] != "ongoing":
                break
        self.assertEqual(last["outcome"], "won")
        self.assertLessEqual(last["rounds"], 10)
        self.assertGreater(last["gold"], 0)
        alice_state = self.game.snapshot(self.alice)
        bob_state = self.game.snapshot(self.bob)
        self.assertEqual(alice_state["last_duel"]["outcome"], "won")
        self.assertEqual(bob_state["last_duel"]["outcome"], "lost")
        self.assertIsNotNone(bob_state["player"]["defeated_until"])
        self.assertEqual(bob_state["player"]["hp"], 0)
        self.assertEqual(self.game.world.total_gold, start_gold)
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        self.assertEqual(self.game.snapshot(self.bob)["last_duel"]["outcome"], "lost")
        self.game.world.assert_invariants()

    def test_primary_weapon_stamina_and_automatic_weapon_retaliation(self):
        alice_sword = self.command(self.alice, "buy_starter_gear",
                                   {"kind": "sword"}, "buy-alice")
        bob_sword = self.command(self.bob, "buy_starter_gear",
                                 {"kind": "sword"}, "buy-bob")
        self.command(self.alice, "equip", {"gear_id": alice_sword}, "equip-alice")
        self.command(self.bob, "equip", {"gear_id": bob_sword}, "equip-bob")
        total = self.game.world.total_gold
        self.begin()
        result = self.command(self.alice, "duel_turn",
                              {"move": "strike", "node_id": ""}, "sword-round")
        self.assertEqual(result["stamina_spent"], 5)
        self.assertGreater(result["damage"], 0)
        self.assertGreater(result["retaliation"], 0)
        self.assertEqual(self.game.snapshot(self.alice)["player"]["stamina"], 95)
        self.assertEqual(self.game.snapshot(self.bob)["player"]["stamina"], 100)
        self.assertEqual(self.game.world.total_gold, total)
        self.game.world.assert_invariants()

    def test_combat_magic_uses_same_stamina_and_mana_rules(self):
        self.command(self.alice, "unlock_magic",
                     {"node_id": "warding.minor_shield"}, "unlock")
        self.begin()
        before = self.game.snapshot(self.alice)
        result = self.command(self.alice, "duel_turn",
                              {"move": "cast", "node_id": "warding.minor_shield"},
                              "ward-first")
        self.assertEqual(result["stamina_spent"], 6)
        self.assertEqual(result["retaliation"], 0)
        self.assertEqual(self.game.snapshot(self.alice)["player"]["stamina"],
                         before["player"]["stamina"] - 6)
        self.assertLess(self.game.snapshot(self.alice)["player"]["mana"],
                        before["player"]["mana"])
        self.assertEqual(self.game.snapshot(self.bob)["player"]["stamina"], 100)
        self.assertTrue(any(e["kind"] == "duel_round" for e in
                            self.game.snapshot(self.bob)["events"]))
        self.game.world.assert_invariants()

    def test_rejects_concurrent_combat_and_obsolete_pvp_mutations(self):
        with self.assertRaises(ActionError):
            self.command(self.alice, "pvp_strike",
                         {"defender_id": self.bob}, "legacy-not-for-live")
        self.begin()
        with self.assertRaises(ActionError):
            self.command(self.carol, "start_duel",
                         {"defender_id": self.bob}, "collision-one")
        with self.assertRaises(ActionError):
            self.command(self.carol, "start_duel",
                         {"defender_id": self.alice}, "collision-two")
        with self.assertRaises(ActionError):
            self.command(self.bob, "start_duel",
                         {"defender_id": self.carol}, "collision-three")
        with patch("medieval_world_sim.web.multiplayer.secrets.randbits", return_value=1):
            escaped = self.command(self.alice, "flee_duel", {}, "alice-flee")
        self.assertEqual(escaped["outcome"], "fled")
        self.assertIsNone(self.game.snapshot(self.bob)["duel"])
        self.game.world.assert_invariants()

    def test_historical_one_swing_pvp_journal_remains_replayable(self):
        # The production endpoint refuses new one-swing commands, but journals
        # committed by older versions must still reconstruct exactly.
        payload = json.dumps({"defender_id": self.bob}, sort_keys=True,
                             separators=(",", ":"))
        self.game.db.execute(
            "INSERT INTO world_journal(kind, actor_id, action, payload, request_id, "
            "result_json, recorded_at) VALUES('action', ?, 'pvp_strike', ?, ?, ?, NULL)",
            (self.alice, payload, "legacy-swing", "{}"))
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False, dev_fast_forward=True)
        self.assertLess(self.game.snapshot(self.bob)["player"]["hp"], 24)
        self.assertIsNone(self.game.snapshot(self.alice)["duel"])
        self.game.world.assert_invariants()

    def test_unattended_player_duel_does_not_freeze_shared_world_time(self):
        self.begin()
        self.assertEqual(self.game.world.minute, 0)
        self.game.advance(self.carol, 20, "independent-clock")
        self.assertEqual(self.game.world.minute, 20)
        self.assertEqual(self.game.snapshot(self.alice)["duel"]["round"], 0)
        self.assertEqual(self.game.snapshot(self.bob)["duel"]["role"], "defender")
        self.command(self.bob, "flee_duel", {}, "defender-can-exit")
        self.game.world.assert_invariants()

    def test_stream_owns_only_participating_character_duels(self):
        self.begin()
        defender = self.game.social_snapshot(self.bob)
        attacker = self.game.social_snapshot(self.alice)
        outsider = self.game.social_snapshot(self.carol)
        self.assertEqual(defender["duel"]["role"], "defender")
        self.assertEqual(attacker["duel"]["role"], "attacker")
        self.assertIsNone(outsider["duel"])
        self.assertTrue(all("duel" not in user for user in outsider["users"]))
        self.game.world.assert_invariants()


if __name__ == "__main__":
    unittest.main()
