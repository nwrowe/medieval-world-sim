"""Phase 2 ownership checks for extracted multiplayer account and social code."""
import tempfile
import unittest
from pathlib import Path

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.accounts import AuthError, Identity
from medieval_world_sim.web.multiplayer import MultiplayerGame


class MultiplayerServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "multi.sqlite3"
        self.game = MultiplayerGame(self.db, require_invites=True, dev_fast_forward=True)

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def test_invite_auth_and_session_round_trip_after_extraction(self):
        invite = self.game.issue_invites(1)[0]
        actor_id = self.game.register("alice", "long correct password", "Alice Meadows", invite)
        token, csrf = self.game.login("alice", "long correct password")
        identity = self.game.identity(token)
        self.assertIsInstance(identity, Identity)
        self.assertEqual(identity.actor_id, actor_id)
        self.assertEqual(identity.csrf, csrf)
        with self.assertRaises(ActionError):
            self.game.register("bob", "long correct password", "Bob Aspen", invite)
        with self.assertRaises(AuthError):
            self.game.login("alice", "incorrect password")
        self.game.logout(token)
        self.assertIsNone(self.game.identity(token))

    def test_social_view_scoped_to_requesting_actor_and_presence(self):
        a = self.game.register("alice", "long correct password", "Alice Meadows",
                               self.game.issue_invites(1)[0])
        b = self.game.register("bob", "second correct password", "Bob Aspen",
                               self.game.issue_invites(1)[0])
        self.game.world.actors[b].gold += 0  # no bypass of authoritative accounting
        self.game.presence_ping(a, True)
        self.game.presence_ping(b, False)
        view = self.game.social_snapshot(a)
        self.assertEqual(view["actor_id"], a)
        other = next(person for person in view["users"] if person["id"] == b)
        self.assertEqual(other["presence"], "away")
        self.assertNotIn("gold", other)
        self.assertNotIn("inventory", other)
        self.assertNotIn("work", other)
        self.assertEqual(view["player_status"]["gold"], self.game.world.actors[a].gold)


if __name__ == "__main__":
    unittest.main()
