"""ASCII username contract, normalization and account collision safety."""
import tempfile
import unittest
from pathlib import Path

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.accounts import validate_registration
from medieval_world_sim.web.multiplayer import MultiplayerGame

PASSWORD = "correct horse battery staple"


class UsernameRules(unittest.TestCase):
    def test_permitted_letters_numbers_underscores_in_any_position(self):
        for name in ("Abc", "_abc", "123", "9player", "__name__", "R2D2", "A" * 24):
            normalized, display = validate_registration(name, PASSWORD, "Alden River")
            self.assertEqual(normalized, name.lower())
            self.assertEqual(display, "Alden River")

    def test_rejects_every_non_ascii_identifier_character(self):
        for bad in ("ab", "x" * 25, "", "a.b", "a-b", "a b",
                    "álpha", "人物X", "a\nb", "a+b", "<script>", "ab💠"):
            with self.subTest(bad=bad), self.assertRaises(ActionError):
                validate_registration(bad, PASSWORD, "Alden River")

    def test_username_case_collision_cannot_register_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            world = MultiplayerGame(Path(folder) / "auth.db",
                                    require_invites=False, npc_enabled=False)
            try:
                world.register("9Player", PASSWORD, "Alden River")
                with self.assertRaises(ActionError):
                    world.register("9PLAYER", PASSWORD, "Bryn Vale")
                token, _ = world.login("9player", PASSWORD)
                self.assertIsNotNone(world.identity(token))
            finally:
                world.close()


if __name__ == "__main__":
    unittest.main()
