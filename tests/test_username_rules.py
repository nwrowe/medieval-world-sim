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

    def test_email_identifier_normalization_and_validation(self):
        for address in ("Alden.River@example.com", "Scout+mail@oathmere.test"):
            normalized, display = validate_registration(address, PASSWORD, "Alden River")
            self.assertEqual(normalized, address.lower())
            self.assertEqual(display, "Alden River")
        for bad in ("x@", "@example.com", "x@localhost", "x@-example.com",
                    "x@example..com", "x..y@example.com", "x@" + "e" * 64 + ".com"):
            with self.subTest(email=bad), self.assertRaises(ActionError):
                validate_registration(bad, PASSWORD, "Alden River")

    def test_email_address_can_sign_in_case_insensitively(self):
        with tempfile.TemporaryDirectory() as folder:
            world = MultiplayerGame(Path(folder) / "auth.db",
                                    require_invites=False, npc_enabled=False)
            try:
                actor_id = world.register("Alden+Scout@Example.com", PASSWORD, "Alden River")
                with self.assertRaises(ActionError):
                    world.register("alden+scout@example.com", PASSWORD, "Bryn Vale")
                token, _ = world.login("ALDEN+SCOUT@EXAMPLE.COM", PASSWORD)
                self.assertEqual(world.identity(token).actor_id, actor_id)
            finally:
                world.close()

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
