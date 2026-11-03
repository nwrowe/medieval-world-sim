"""Turn-based encounters, spells, loot, hospitalization and save replay."""
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.session import GameSession


class DuelWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "save.json"
        self.game = GameSession(self.path)
        self.game.create("Arlen Vale")

    def tearDown(self):
        self.tmp.cleanup()

    def enemy(self):
        return next(p for p in self.game.snapshot()["users"] if p["can_attack"])

    def do(self, action, params, index):
        return self.game.action(action, params, f"duel-test-{index}")

    def test_npc_search_stamina_per_round_persistence_and_exact_loot(self):
        enemy = self.enemy()
        self.assertEqual(enemy["city"], "goldmeadow")
        starting_gold = self.game.world.actors[enemy["id"]].gold
        total = self.game.world.total_gold
        self.do("start_duel", {"defender_id": enemy["id"]}, "start")
        self.assertEqual(self.game.snapshot()["player"]["stamina"], 80)
        with self.assertRaises(ActionError):
            self.do("travel", {"destination": "crownreach"}, "no-travel")
        with self.assertRaises(ActionError):
            self.game.advance(10)
        first = self.do("duel_turn", {"move": "strike", "node_id": ""}, "first")
        self.assertEqual(first["outcome"], "ongoing")
        self.assertEqual(GameSession(self.path).snapshot(), self.game.snapshot())
        for n in range(2, 12):
            outcome = self.do("duel_turn", {"move": "strike", "node_id": ""}, n)
            if outcome["outcome"] != "ongoing":
                break
        self.assertEqual(outcome["outcome"], "won")
        self.assertEqual(outcome["gold"], starting_gold * 5 // 100)
        self.assertEqual(self.game.world.actors[enemy["id"]].gold,
                         starting_gold - outcome["gold"])
        self.assertIsNone(self.game.snapshot()["duel"])
        self.assertEqual(self.game.snapshot()["last_duel"]["outcome"], "won")
        self.assertGreater(self.game.world.actors[enemy["id"]].defeated_until, 0)
        self.assertEqual(self.game.world.total_gold, total)
        self.assertEqual(GameSession(self.path).snapshot(), self.game.snapshot())
        with self.assertRaises(ActionError):
            self.do("start_duel", {"defender_id": enemy["id"]}, "repeat")
        self.game.advance(60)
        self.assertIsNone(self.game.world.actors[enemy["id"]].defeated_until)
        self.assertEqual(self.game.world.actors[enemy["id"]].hp,
                         self.game.world.actors[enemy["id"]].max_hp)

    def test_magic_in_duel_guard_and_field_healing(self):
        foe = self.enemy()["id"]
        self.do("unlock_magic", {"node_id": "warding.minor_shield"}, "ward-unlock")
        self.do("unlock_magic", {"node_id": "restoration.soothe_wounds"}, "heal-unlock")
        ward = self.do("cast_spell", {"node_id": "warding.minor_shield"}, "ward-cast")
        self.assertEqual(ward["amount"], 5)
        self.do("start_duel", {"defender_id": foe}, "start-warded")
        self.assertEqual(self.game.snapshot()["duel"]["pending_ward"], 5)
        first = self.do("duel_turn", {"move": "strike", "node_id": ""}, "ward-hit")
        self.assertEqual(first["retaliation"], 0)
        self.assertEqual(self.game.snapshot()["player"]["hp"], 24)
        self.do("duel_turn", {"move": "strike", "node_id": ""}, "second")
        healed = self.do("duel_turn", {
            "move": "cast", "node_id": "restoration.soothe_wounds"}, "combat-heal")
        self.assertEqual(healed["outcome"], "ongoing")
        self.do("flee_duel", {}, "flee")
        self.assertEqual(self.game.snapshot()["last_duel"]["outcome"], "fled")
        value = self.do("cast_spell", {"node_id": "restoration.soothe_wounds"}, "field-heal")
        self.assertGreater(value["amount"], 0)
        self.assertEqual(GameSession(self.path).snapshot(), self.game.snapshot())

    def test_invalid_cast_does_not_spend_mana_or_record_and_retry_is_idempotent(self):
        foe = self.enemy()["id"]
        self.do("start_duel", {"defender_id": foe}, "start")
        before = self.game.snapshot()
        records = len(self.game.records)
        with self.assertRaises(ActionError):
            self.do("duel_turn", {"move": "cast", "node_id": "elemental.kindle_flame"}, "wrong")
        self.assertEqual(self.game.snapshot(), before)
        self.assertEqual(len(self.game.records), records)
        one = self.do("duel_turn", {"move": "guard", "node_id": ""}, "guard")
        self.assertEqual(one["retaliation"], 0)
        self.assertEqual(self.do("duel_turn", {"move": "guard", "node_id": ""}, "guard"), one)
        self.assertEqual(len(self.game.records), records + 1)
        with self.assertRaises(ActionError):
            self.do("duel_turn", {"move": "strike", "node_id": ""}, "guard")


class FieldSpellTests(unittest.TestCase):
    def test_alchemy_and_elemental_material_conversion(self):
        actor = Actor("hero", "human", city="greenhollow",
                      inventory={"herbs": 2, "iron_ore": 2, "coal": 1})
        world = WorldEngine([actor])
        world.unlock_magic("hero", "alchemy.purify_reagents")
        world.unlock_magic("hero", "elemental.kindle_flame")
        before_gold = world.total_gold
        world.cast_spell("hero", "alchemy.purify_reagents")
        world.cast_spell("hero", "elemental.kindle_flame")
        self.assertEqual(actor.inventory["healing_potion"], 1)
        self.assertEqual(actor.inventory["steel"], 1)
        self.assertEqual(actor.magic.mana, 84)
        self.assertEqual(world.total_gold, before_gold)
        world.assert_invariants()


if __name__ == "__main__":
    unittest.main()
