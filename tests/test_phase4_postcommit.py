"""Post-commit failure cannot roll back already-durable player assets."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from medieval_world_sim.web import ledger
from medieval_world_sim.web.multiplayer import MultiplayerGame


class PostCommitBoundaryTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "durable.sqlite3"
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)
        self.alice = self.game.register(
            "alice", "a secure test password", "Alice Meadows")

    def tearDown(self):
        self.game.close()
        self.temp.cleanup()

    def test_notification_exception_after_commit_cannot_undo_world(self):
        before = self.game.db.execute(
            "SELECT COUNT(*) FROM world_journal").fetchone()[0]
        params = {"kind": "global", "target": "", "message": "committed"}
        # A notification error occurs after the SQL commit. The previous
        # transaction implementation incorrectly entered its rollback branch
        # and restored the Python state despite the durable SQL write.
        with patch.object(self.game._activity_changed, "notify_all",
                          side_effect=RuntimeError("notification failure")):
            with self.assertRaisesRegex(RuntimeError, "notification failure"):
                self.game.action(self.alice, "send_chat", params, "committed-id")
        self.assertFalse(self.game.world._durable_tx_owns_rollback)
        self.assertEqual(self.game.db.execute(
            "SELECT COUNT(*) FROM world_journal").fetchone()[0], before + 1)
        self.assertEqual(len(self.game.world.state.chat_messages), 1)
        self.assertEqual(self.game._journal_count, before + 1)
        ledger.verify(self.game)

        # A retry is a receipt lookup, not a second world mutation.
        prior = self.game.action(self.alice, "send_chat",
                                 params, "committed-id")
        self.assertEqual(prior["posted"], True)
        self.assertEqual(len(self.game.world.state.chat_messages), 1)
        self.game.close()
        self.game = MultiplayerGame(self.path, require_invites=False,
                                    dev_fast_forward=True)
        self.assertEqual(len(self.game.world.state.chat_messages), 1)
        ledger.verify(self.game)
