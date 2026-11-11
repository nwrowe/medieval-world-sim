"""Playable civic work, personal city storage, and magic-rules compatibility."""
from realm_fixtures import GOLDMEADOW

import json
import tempfile
import unittest
from pathlib import Path

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.session import GameSession


class CityContractTests(unittest.TestCase):
    def world(self, *, goods=None):
        return WorldEngine([Actor("hero", "human", city=GOLDMEADOW, gold=240,
                                  inventory=dict(goods or {}))])

    def test_four_jobs_use_real_city_funds_and_resource_costs(self):
        w = self.world(goods={"herbs": 1})
        starting_gold = w.initial_gold
        city = w.cities[GOLDMEADOW]
        before = city.gold
        stock_before = city.merchant_stock.get("herbs", 0)
        church = w.execute("hero", "complete_city_contract",
                           {"contract_id": "church_supplies"}, "church-1")
        self.assertEqual(church.reward, 11)
        self.assertEqual(w.actors["hero"].gold, 251)
        self.assertEqual(city.gold, before - 11)
        self.assertEqual(w.actors["hero"].inventory["herbs"], 0)
        self.assertEqual(city.merchant_stock["herbs"], stock_before + 1)
        self.assertEqual(w.total_gold, starting_gold)
        self.assertEqual(w.execute("hero", "complete_city_contract",
            {"contract_id": "church_supplies"}, "church-1"), church)
        with self.assertRaises(ActionError):
            w.complete_city_contract("hero", "church_supplies")  # shift cooldown
        w.advance(60)
        before_int = w.actors["hero"].work.intelligence
        mage = w.complete_city_contract("hero", "mage_copywork")
        self.assertEqual(mage.mana_spent, 12)
        self.assertEqual(w.actors["hero"].work.intelligence, before_int + 1)
        w.advance(60)
        before_combat = w.actors["hero"].combat_xp
        warrior = w.complete_city_contract("hero", "warrior_patrol")
        self.assertEqual(w.actors["hero"].combat_xp, before_combat + warrior.xp_gained)
        w.advance(60)
        before_manual = w.actors["hero"].work.manual
        labor = w.complete_city_contract("hero", "labor_shift")
        self.assertEqual(labor.stamina_spent, 20)
        self.assertEqual(w.actors["hero"].work.manual, before_manual + 1)
        self.assertEqual(w.total_gold, starting_gold)
        w.assert_invariants()

    def test_unpaid_unauthorized_and_insufficient_contracts_do_not_mutate_state(self):
        w = self.world()
        initial = (w.total_gold, w.actors["hero"].gold, len(w.events))
        for contract in ("church_supplies", "nonexistent"):
            with self.assertRaises(ActionError):
                w.complete_city_contract("hero", contract)
        self.assertEqual((w.total_gold, w.actors["hero"].gold, len(w.events)), initial)

        city = w.cities[GOLDMEADOW]
        city_gold = city.gold
        city.gold = 0
        w.crown_gold += city_gold  # move rather than destroy preexisting world gold
        with self.assertRaises(ActionError):
            w.complete_city_contract("hero", "labor_shift")
        self.assertEqual(w.actors["hero"].gold, 240)
        w.assert_invariants()

    def test_city_stash_separates_unbounded_ownership_from_travel_load(self):
        w = self.world(goods={"grain": 40})
        with self.assertRaises(ActionError):
            w.start_travel("hero", "crownreach")
        w.execute("hero", "store_goods", {"item": "grain", "quantity": 30}, "store-1")
        self.assertEqual(w.actors["hero"].inventory["grain"], 10)
        self.assertEqual(w.actors["hero"].storage[GOLDMEADOW]["grain"], 30)
        trip = w.start_travel("hero", "crownreach")
        w.advance(trip)
        with self.assertRaises(ActionError):
            w.retrieve_goods("hero", "grain", 1)
        trip = w.start_travel("hero", GOLDMEADOW)
        w.advance(trip)
        w.retrieve_goods("hero", "grain", 30)
        self.assertEqual(w.actors["hero"].inventory["grain"], 40)
        with self.assertRaises(ActionError):
            w.store_goods("hero", "grain", 41)
        w.assert_invariants()


class SaveCompatibilityTests(unittest.TestCase):
    def test_old_magic_practice_replays_under_old_rule_and_new_actions_use_new_rule(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "save.json"
            game = GameSession(path)
            game.create("Vela Gale")
            document = json.loads(path.read_text(encoding="utf-8"))
            document["records"] = [
                {"kind": "action", "name": "unlock_magic",
                 "params": {"node_id": "divination.read_omens"}, "id": "old-unlock"},
                {"kind": "action", "name": "practice_magic",
                 "params": {"node_id": "divination.read_omens"}, "id": "old-practice"},
            ]
            path.write_text(json.dumps(document), encoding="utf-8")
            old = GameSession(path)
            old_chance = [e.data["chance"] for e in old.world.events
                          if e.kind == "magic_practiced"][-1]
            self.assertLess(old_chance, 90)
            new = old.action("practice_magic",
                {"node_id": "divination.read_omens"}, "new-practice")
            self.assertGreaterEqual(new.chance, 90)
            self.assertEqual(GameSession(path).snapshot(), old.snapshot())

    def test_city_job_and_storage_survive_save_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "save.json"
            game = GameSession(path)
            game.create("Cale Rowan")
            # Exercise storage in a real resource-producing generated town.
            old_document = json.loads(path.read_text(encoding="utf-8"))
            old_document["start_city"] = GOLDMEADOW
            path.write_text(json.dumps(old_document), encoding="utf-8")
            game = GameSession(path)
            game.action("gather", {"item": "grain", "quantity": 2}, "gather")
            game.action("store_goods", {"item": "grain", "quantity": 2}, "store")
            self.assertEqual(game.snapshot()["player"]["stored_here"]["grain"], 2)
            # Gathering has a cooldown; the employment hall respects it.
            game.advance(60)
            game.action("complete_city_contract",
                {"contract_id": "labor_shift"}, "job")
            self.assertEqual(game.snapshot()["player"]["work"]["shifts"], 1)
            view = game.snapshot()
            self.assertEqual(GameSession(path).snapshot(), view)
            record_count = len(game.records)
            result = game.action("complete_city_contract",
                {"contract_id": "labor_shift"}, "job")
            self.assertEqual(result.reward, 9)
            self.assertEqual(len(game.records), record_count)
            # New job cooldowns stack independently up to 24 simulated hours.
            game.action("complete_city_contract",
                {"contract_id": "labor_shift"}, "second-job")
            self.assertEqual(game.snapshot()["player"]["cooldowns"]["job"]["remaining_minutes"], 120)
            self.assertEqual(GameSession(path).snapshot(), game.snapshot())


if __name__ == "__main__":
    unittest.main()
