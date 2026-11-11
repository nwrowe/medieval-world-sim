"""Independent 24-hour cooldown stack tests and journal compatibility."""
from realm_fixtures import GOLDMEADOW

import json
import tempfile
import unittest
from pathlib import Path

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.session import GameSession


class CooldownTests(unittest.TestCase):
    def test_job_queue_stacks_to_24_hours_then_blocks(self):
        w = WorldEngine([Actor("hero", "human", city=GOLDMEADOW,
                               inventory={"herbs": 26})])
        original_total = w.initial_gold
        for n in range(24):
            w.execute("hero", "complete_city_contract",
                      {"contract_id": "church_supplies"}, f"delivery-{n}")
        actor = w.actors["hero"]
        self.assertEqual(actor.cooldowns.job - w.minute, 1440)
        self.assertEqual(actor.inventory["herbs"], 2)
        self.assertEqual(w.total_gold, original_total)
        previous = (len(w.events), actor.gold)
        with self.assertRaises(ActionError):
            w.complete_city_contract("hero", "church_supplies")
        actor = w.actors["hero"]  # A failed atomic action restores a deep-copied state.
        self.assertEqual(previous, (len(w.events), actor.gold))
        w.advance(60)
        w.complete_city_contract("hero", "church_supplies")
        self.assertEqual(w.actors["hero"].cooldowns.job - w.minute, 1440)
        self.assertEqual(w.total_gold, original_total)
        w.assert_invariants()

    def test_food_and_potion_queues_have_separate_24h_limits(self):
        actor = Actor("hero", "human", inventory={
            "bread": 52, "healing_potion": 15})
        w = WorldEngine([actor])
        for _ in range(48):
            actor.stamina = 0
            w.consume("hero", "bread")
        self.assertEqual(actor.cooldowns.food - w.minute, 1440)
        self.assertEqual(actor.cooldowns.potion, 0)
        actor.stamina = 0
        before = (actor.inventory["bread"], len(w.events))
        with self.assertRaises(ActionError):
            w.consume("hero", "bread")
        actor = w.actors["hero"]
        self.assertEqual(before, (actor.inventory["bread"], len(w.events)))
        for _ in range(12):
            actor.hp = 1
            w.consume("hero", "healing_potion")
        self.assertEqual(actor.cooldowns.potion - w.minute, 1440)
        self.assertEqual(actor.cooldowns.food - w.minute, 1440)
        actor.hp = 1
        with self.assertRaises(ActionError):
            w.consume("hero", "healing_potion")
        actor = w.actors["hero"]
        w.advance(60)
        actor.hp = 1
        with self.assertRaises(ActionError):
            w.consume("hero", "healing_potion")  # Not enough headroom for 120 minutes
        actor = w.actors["hero"]
        w.advance(60)
        actor.hp = 1
        w.consume("hero", "healing_potion")
        self.assertEqual(w.actors["hero"].cooldowns.potion - w.minute, 1440)
        w.assert_invariants()

    def test_legacy_job_replay_retains_old_ready_time_without_new_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            save = Path(folder) / "save.json"
            game = GameSession(save)
            game.create("Old Wanderer")
            document = json.loads(save.read_text(encoding="utf-8"))
            document["records"] = [{
                "kind": "action", "name": "complete_city_contract",
                "params": {"contract_id": "labor_shift"},
                "id": "old-job", "ruleset": 2,
            }]
            save.write_text(json.dumps(document), encoding="utf-8")
            replayed = GameSession(save)
            self.assertEqual(replayed.snapshot()["player"]["ready_minute"], 60)
            self.assertEqual(replayed.snapshot()["player"]["cooldowns"]["job"]["remaining_minutes"], 0)
            # New actions use the distinct job queue and can stack independently.
            replayed.action("complete_city_contract",
                            {"contract_id": "labor_shift"}, "new-job")
            self.assertEqual(replayed.records[-1]["ruleset"], 3)
            self.assertEqual(GameSession(save).snapshot(), replayed.snapshot())


if __name__ == "__main__":
    unittest.main()
