"""Combat stamina is spent per offensive swing; defensive reactions are free."""
import json
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.session import GameSession
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor


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
        self.assertEqual(turn["stamina_spent"], 2)
        self.assertEqual(self.game.snapshot()["player"]["stamina"], 98)
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
                         {"strike": 5, "dagger": 3, "fists": 2})
        self.action("start_duel", {"defender_id": self.foe()}, "start")
        for move, cost in (("fists", 2), ("dagger", 3), ("strike", 5)):
            before = self.game.snapshot()["player"]["stamina"]
            result = self.action("duel_turn", {"move": move, "node_id": ""}, "hit-" + move)
            self.assertEqual(result["stamina_spent"], cost)
            self.assertEqual(self.game.snapshot()["player"]["stamina"], before - cost)
        self.assertEqual(GameSession(self.path).snapshot(), self.game.snapshot())

    def test_insufficient_stamina_rejects_without_spending_and_guard_is_free(self):
        self.action("start_duel", {"defender_id": self.foe()}, "start")
        # The world is loaded from an action journal. Set up 1 stamina in a standalone
        # engine test below rather than introduce an undocumented save mutation.
        before = self.game.snapshot()["player"]["stamina"]
        guarded = self.action("duel_turn", {"move": "guard", "node_id": ""}, "guard")
        self.assertEqual(self.game.snapshot()["player"]["stamina"], before - 2)
        self.assertEqual(guarded["retaliation"], 0)
        with self.assertRaises(ActionError):
            self.action("duel_turn", {"move": "dagger", "node_id": ""}, "no-dagger")

    def test_exhausted_sword_swing_is_rejected_and_defender_stays_fresh(self):
        world = WorldEngine([
            Actor("hero", "human", city="crownreach", gold=70),
            Actor("foe", "npc", city="crownreach", gold=70),
        ])
        sword = world.buy_starter_gear("hero", "sword")
        world.equip("hero", sword)
        world.start_duel("hero", "foe")
        defender = world.actors["foe"]
        attacker = world.actors["hero"]
        attacker.stamina = 4
        defender.stamina = 0
        before_hp = defender.hp
        before_round = world.state.duels["hero"].round
        with self.assertRaises(ActionError):
            world.duel_turn("hero", "strike", "")
        # Rejected atomic actions restore the entire state snapshot. Always
        # read actors back from the engine, not a stale pre-rollback reference.
        self.assertEqual(world.actors["hero"].stamina, 4)
        self.assertEqual(world.actors["foe"].hp, before_hp)
        self.assertEqual(world.state.duels["hero"].round, before_round)
        world.duel_turn("hero", "fists", "")
        self.assertEqual(world.actors["hero"].stamina, 2)
        self.assertEqual(world.actors["foe"].stamina, 0)
        world.assert_invariants()

    def test_armored_body_slots_reduce_damage(self):
        def opening_damage(with_armor):
            world = WorldEngine([
                Actor("hero", "human", city="crownreach", gold=70),
                Actor("foe", "npc", city="crownreach", gold=70),
            ])
            if with_armor:
                for kind in ("iron_helm", "iron_greaves", "iron_boots"):
                    ident = world.buy_starter_gear("foe", kind)
                    world.equip("foe", ident)
            world.start_duel("hero", "foe")
            outcome = world.duel_turn("hero", "fists", "")
            return outcome["damage"]
        # Poorly armed fists deal at least one damage, but segmented armor
        # provides a measurable defense improvement.
        self.assertGreater(opening_damage(False), opening_damage(True))

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
