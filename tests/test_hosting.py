"""Hosting entrypoint must fail closed, never launch a public no-token game."""
import contextlib
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from medieval_world_sim.web import deploy


class HostedEntryPointTests(TestCase):
    def test_missing_token_rejected_without_starting_server(self):
        with patch.dict("os.environ", {"GAME_ACCESS_TOKEN": "", "PORT": "10000"}, clear=True):
            with patch.object(deploy, "main") as starter:
                with self.assertRaises(SystemExit) as ctx:
                    deploy.start()
                self.assertIn("GAME_ACCESS_TOKEN", str(ctx.exception))
                starter.assert_not_called()

    def test_short_token_invalid_port_and_relative_save_refused(self):
        bad_configs = (
            {"GAME_ACCESS_TOKEN": "short", "PORT": "10000", "GAME_SAVE_DIR": "/var/data"},
            {"GAME_ACCESS_TOKEN": "very-long-unique-secret-token", "PORT": "invalid", "GAME_SAVE_DIR": "/var/data"},
            {"GAME_ACCESS_TOKEN": "very-long-unique-secret-token", "PORT": "10000", "GAME_SAVE_DIR": "relative"},
        )
        for values in bad_configs:
            with self.subTest(values=values):
                with patch.dict("os.environ", values, clear=True):
                    with patch.object(deploy, "main") as starter:
                        with self.assertRaises(SystemExit):
                            deploy.start()
                        starter.assert_not_called()

    def test_valid_hosting_config_binds_single_player_with_token_and_save(self):
        with patch.dict("os.environ", {
            "GAME_ACCESS_TOKEN": "some-adequately-long-and-secret-token",
            "PORT": "10000",
            "GAME_SAVE_DIR": "/var/data",
        }, clear=True):
            with patch.object(deploy, "main") as starter:
                deploy.start()
                starter.assert_called_once_with([
                    "--host", "0.0.0.0", "--port", "10000",
                    "--access-token", "some-adequately-long-and-secret-token",
                    "--save", "/var/data/medieval-world-save.json",
                ])
