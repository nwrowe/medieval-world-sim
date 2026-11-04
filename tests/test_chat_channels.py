"""Chat permissions, message privacy and single-player local preview behavior."""
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor, Company, Wage
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.session import GameSession


class ChatDomainTests(unittest.TestCase):
    def setUp(self):
        self.world = WorldEngine([
            Actor("alice", "human", city="crownreach", gold=300),
            Actor("bob", "human", city="crownreach", gold=200),
            Actor("mallory", "human", city="crownreach", gold=200),
            Actor("npc", "npc", city="crownreach"),
        ])

    def test_direct_messages_are_restricted_to_sender_and_recipient(self):
        result = self.world.send_chat("alice", "direct", "bob", "Secret business")
        self.assertTrue(result["posted"])
        self.assertEqual(len(self.world.chat_system.view("alice")["messages"]), 1)
        self.assertEqual(len(self.world.chat_system.view("bob")["messages"]), 1)
        self.assertEqual(self.world.chat_system.view("mallory")["messages"], [])
        with self.assertRaises(ActionError):
            self.world.send_chat("alice", "direct", "npc", "Hello bot")
        with self.assertRaises(ActionError):
            self.world.send_chat("alice", "direct", "alice", "Hello me")
        self.world.assert_invariants()

    def test_guild_chat_requires_current_membership(self):
        guild = self.world.found_guild("alice", "Lantern Guild")
        self.world.invite_guild("alice", "bob")
        self.world.join_guild("bob", guild["id"])
        self.world.send_chat("bob", "guild", guild["id"], "Guild business")
        self.assertEqual(len(self.world.chat_system.view("alice")["messages"]), 1)
        with self.assertRaises(ActionError):
            self.world.send_chat("mallory", "guild", guild["id"], "Intruder")
        self.assertEqual(self.world.chat_system.view("mallory")["messages"], [])
        self.world.leave_guild("bob")
        self.assertEqual(self.world.chat_system.view("bob")["messages"], [])
        self.world.assert_invariants()

    def test_company_and_custom_room_access_is_membership_scoped(self):
        self.world.companies["forge"] = Company("forge", "alice", "blacksmith")
        self.world.companies["forge"].employees["bob"] = Wage(gold=0)
        self.world.send_chat("alice", "company", "forge", "Forge announcement")
        self.assertEqual(len(self.world.chat_system.view("bob")["messages"]), 1)
        with self.assertRaises(ActionError):
            self.world.send_chat("mallory", "company", "forge", "Not employed")
        room = self.world.create_chat_room("alice", "Trusted Circle", ["bob"])
        self.world.send_chat("bob", "room", room["id"], "Private chamber")
        self.assertEqual(len(self.world.chat_system.view("alice")["messages"]), 2)
        self.assertEqual(len(self.world.chat_system.view("bob")["messages"]), 2)
        self.assertFalse(any(m["body"] == "Private chamber"
                             for m in self.world.chat_system.view("mallory")["messages"]))
        with self.assertRaises(ActionError):
            self.world.send_chat("mallory", "room", room["id"], "No invite")
        self.world.assert_invariants()

    def test_sender_is_authoritative_and_message_ids_are_idempotent(self):
        one = self.world.execute("alice", "send_chat",
                                 {"kind": "global", "target": "",
                                  "message": "<b>hello</b>"}, "message-01")
        self.assertEqual(self.world.execute("alice", "send_chat",
                         {"kind": "global", "target": "",
                          "message": "<b>hello</b>"}, "message-01"), one)
        self.assertEqual(len(self.world.state.chat_messages), 1)
        self.assertEqual(self.world.state.chat_messages[0].author, "alice")
        with self.assertRaises(ActionError):
            self.world.execute("mallory", "send_chat",
                               {"kind": "global", "target": "", "message": "spoof"},
                               "message-01")
        for message in ("", "  ", "x" * 401, "a\x00b"):
            with self.assertRaises(ActionError):
                self.world.send_chat("alice", "global", "", message)
        self.world.assert_invariants()


class ChatWebReplayTests(unittest.TestCase):
    def test_local_preview_posts_and_reloads_without_npc_impersonation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "save.json"
            game = GameSession(path)
            game.create("Explorer")
            before = game.snapshot()
            self.assertFalse(before["multiplayer"])
            self.assertEqual([c["key"] for c in before["chat"]["channels"]], ["global"])
            sent = game.action("send_chat",
                               {"kind": "global", "target": "",
                                "message": "Hello from this local server"}, "chat-one")
            self.assertTrue(sent["posted"])
            view = game.snapshot()
            self.assertEqual(len(view["chat"]["messages"]), 1)
            self.assertEqual(view["chat"]["messages"][0]["sender"], "hero")
            self.assertEqual(GameSession(path).snapshot(), view)
            with self.assertRaises(ActionError):
                game.action("send_chat", {"kind": "direct", "target": "npc:1",
                            "message": "Hello npc"}, "chat-two")
            foe = next(user["id"] for user in view["users"] if user["can_attack"])
            game.action("start_duel", {"defender_id": foe}, "duel-begin")
            game.action("send_chat", {"kind": "global", "target": "",
                        "message": "Still here during combat"}, "chat-during-duel")
            self.assertIsNotNone(game.snapshot()["duel"])
            self.assertEqual(len(game.snapshot()["chat"]["messages"]), 2)
            self.assertEqual(GameSession(path).snapshot(), game.snapshot())


if __name__ == "__main__":
    unittest.main()
