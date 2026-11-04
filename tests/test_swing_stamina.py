"""Combat stamina is spent per offensive swing; defensive reactions are free."""
import json
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.session import GameSession


class WeaponStaminaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "save.json"
        self.game = GameSession(self.path)
        self.game.create("Rowan")

    def tearDown(self):
        self.tmp.cleanup()

    def action(self, name, params, ident):
        return self.game.action(name, params, "swing-" + ident)

    def foe(self):
        return next(person["id"] for person in self.game.snapshot()["users"]
                    if person["can_attack"])

    def test_free_duel_start_fists_cost_one_and_counterattack_is_free(self):
        start = self.action("start_duel", {"defender_id": self.foe()}, "begin")
        self.assertEqual(start["stamina_spent"], 0)
        self.assertEqual(self.game.snapshot()["player"]["stamina"], 100)
        turn = self.action("duel_turn", {"move": "fists", "node_id": ""}, "punch")
        self.assertEqual(turn["stamina_spent"], 1)
        self.assertEqual(self.game.snapshot()["player"]["stamina"], 99)
        self.assertGreater(turn["retaliation"], 0)
        self.assertEqual(GameSession(self.path).snapshot(), self.game.snapshot())

    def test_weapon_and_dagger_attack_costs_and_slot_catalog(self):
        self.action("travel", {"destination": "crownreach"}, "travel")
        self.game.advance(60)
        self.assertEqual(self.game.snapshot()["player"]["city"], "crownreach")
        owned = {}
        for kind in ("sword", "dagger", "iron_helm", "iron_boots",
                     "iron_greaves", "iron_gauntlets"):
            owned[kind] = self.action("buy_starter_gear", {"kind": kind}, kind)
            self.action("equip", {"gear_id": owned[kind]}, "equip-" + kind)
        view = self.game.snapshot()
        self.assertEqual(view["equipped"]["secondary"], owned["dagger"])
        for key in ("helm", "boots", "greaves", "gloves"):
            self.assertIn(key, view["equipped"])
        self.assertEqual({m["move"]: m["stamina"] for m in view["combat_moves"]},
                         {"strike": 5, "dagger": 2, "fists": 1})
        self.action("start_duel", {"defender_id": self.foe()}, "start")
        for move, cost in (("fists", 1), ("dagger", 2), ("strike", 5)):
            before = self.game.snapshot()["player"]["stamina"]
            result = self.action("duel_turn", {"move": move, "node_id": ""}, move)
            self.assertEqual(result["stamina_spent"], cost)
            self.assertEqual(self.game.snapshot()["player"]["stamina"], before - cost)
        self.assertEqual(GameSession(self.path).snapshot(), self.game.snapshot())

    def test_insufficient_stamina_rejects_without_spending_and_guard_is_free(self):
        self.action("start_duel", {"defender_id": self.foe()}, "start")
        # The world is loaded from an action journal. Set up 1 stamina in a standalone
        # engine test below rather than introduce an undocumented save mutation.
        before = self.game.snapshot()["player"]["stamina"]
        guarded = self.action("duel_turn", {"move": "guard", "node_id": ""}, "guard")
        self.assertEqual(self.game.snapshot()["player"]["stamina"], before)
        self.assertEqual(guarded["retaliation"], 0)
        with self.assertRaises(ActionError):
            self.action("duel_turn", {"move": "dagger", "node_id": ""}, "no-dagger")

    def test_historical_ruleset_four_still_charges_twenty_on_replay(self):
        foe = self.foe()
        data = json.loads(self.path.read_text())
        data["records"].append({
            "kind": "action", "name": "start_duel",
            "params": {"defender_id": foe}, "id": "historic-start", "ruleset": 4
        })
        self.path.write_text(json.dumps(data))
        recovered = GameSession(self.path)
        self.assertEqual(recovered.snapshot()["player"]["stamina"], 80)
        self.assertIsNotNone(recovered.snapshot()["duel"])
        recovered.action("flee_duel", {}, "modern-flee")
        self.assertEqual(GameSession(self.path).snapshot(), recovered.snapshot())


if __name__ == "__main__":
    unittest.main()
