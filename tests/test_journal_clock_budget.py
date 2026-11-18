"""Automatic server clock rows must never lock out an active play-test realm."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.multiplayer import MultiplayerGame


class ClockJournalBudgetTests(TestCase):
    def test_seconds_travel_clock_survives_full_journal_and_restart(self):
        start = 1_700_000_000
        with TemporaryDirectory() as directory:
            path = Path(directory) / "playtest.sqlite3"
            with patch("medieval_world_sim.web.multiplayer.time.time",
                       return_value=start):
                game = MultiplayerGame(path, require_invites=False,
                                       dev_travel_seconds=True)
                actor = game.register("alice", "correct horse battery staple",
                                      "Alice")
            try:
                # The original lifetime cap would count join + automatic
                # advance, then fail before the browser could load again.
                with patch("medieval_world_sim.web.multiplayer.MAX_JOURNAL", 2), \
                     patch("medieval_world_sim.web.multiplayer.time.time",
                           return_value=start + 3):
                    self.assertEqual(game.snapshot(actor)["minute"], 3)
                    self.assertEqual(game.snapshot(actor)["minute"], 3)
                    self.assertEqual(game.db.execute(
                        "SELECT COUNT(*) FROM world_journal").fetchone()[0], 2)
                    self.assertEqual(game.db.execute(
                        "SELECT COUNT(*) FROM world_journal "
                        "WHERE COALESCE(server_clock,0)=0").fetchone()[0], 1)

                    message = {"kind": "global", "target": "",
                               "message": "Saved after the clock reached quota"}
                    result = game.action(actor, "send_chat", message, "unique-1")
                    self.assertEqual(game.action(actor, "send_chat",
                                                 message, "unique-1"), result)

                    # At the player command limit, reject *new* commands,
                    # while the trusted clock and snapshot still work.
                    with self.assertRaisesRegex(ActionError, "journal is full"):
                        game.action(actor, "send_chat",
                                    {**message, "message": "New command"},
                                    "unique-2")
                    with patch("medieval_world_sim.web.multiplayer.time.time",
                               return_value=start + 5):
                        expected = game.snapshot(actor)
                        self.assertEqual(expected["minute"], 5)
                        self.assertEqual(game.create_checkpoint(), 4)
                game.close()
                game = None

                # The old clock rows and checksum-protected checkpoint remain
                # readable; no history, receipt, or player data was deleted.
                with patch("medieval_world_sim.web.multiplayer.time.time",
                           return_value=start + 5):
                    restarted = MultiplayerGame(path, require_invites=False,
                                                dev_travel_seconds=True)
                    try:
                        actual = restarted.snapshot(actor)
                        self.assertEqual(actual["minute"], 5)
                        self.assertEqual(actual["chat"], expected["chat"])
                        self.assertEqual(restarted.action(
                            actor, "send_chat", message, "unique-1"), result)
                    finally:
                        restarted.close()
            finally:
                if game is not None:
                    game.close()
