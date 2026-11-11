"""Regression coverage for persistent lineages and discovery-based exploration."""
from realm_fixtures import IRONVALE

import json
import tempfile
import unittest
from pathlib import Path

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.content.lineages import LINEAGES, active_trait, combat_modifiers
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.checkpoint import _encode, _decode
from medieval_world_sim.web.session import GameSession


class LineageExplorationTests(unittest.TestCase):
    def test_one_time_lineage_choice_changes_authoritative_stats(self):
        world = WorldEngine([Actor("hero", "human", city="crownreach")])
        actor = world.actors["hero"]
        self.assertFalse(actor.lineage_selected)
        self.assertEqual(actor.discovered_cities, {"crownreach"})
        world.execute("hero", "choose_lineage", {"lineage": "dwarf"}, "choice-1")
        self.assertTrue(actor.lineage_selected)
        self.assertEqual(actor.lineage, "dwarf")
        self.assertEqual(actor.work.manual, 12)
        self.assertEqual(combat_modifiers(actor), (0, 1))
        with self.assertRaises(ActionError):
            world.execute("hero", "choose_lineage", {"lineage": "elf"}, "choice-2")
        world.assert_invariants()

    def test_trait_unlocks_with_combat_progression(self):
        world = WorldEngine([Actor("hero", "human")])
        world.choose_lineage("hero", "orc")
        actor = world.actors["hero"]
        self.assertFalse(active_trait(actor))
        self.assertEqual(combat_modifiers(actor), (1, 0))
        world.combat._award_xp(actor, 50)  # Level 1 -> 2 -> 3
        self.assertTrue(active_trait(actor))
        self.assertEqual(combat_modifiers(actor), (2, 0))
        world.assert_invariants()

    def test_invalid_lineage_cannot_mutate_assets(self):
        world = WorldEngine([Actor("hero", "human")])
        with self.assertRaises(ActionError):
            world.choose_lineage("hero", "dragon")
        self.assertFalse(world.actors["hero"].lineage_selected)
        self.assertEqual(world.actors["hero"].gold, 100)
        world.assert_invariants()

    def test_exploration_reveals_on_arrival_and_survives_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "world.json"
            game = GameSession(path)
            game.create("Mira Way", "elf")
            initial = game.snapshot()
            self.assertEqual(initial["player"]["city"], "crownreach")
            self.assertEqual(initial["player"]["lineage"], "elf")
            self.assertTrue(initial["player"]["lineage_selected"])
            self.assertEqual([city["id"] for city in initial["cities"] if city["discovered"]],
                             ["crownreach"])
            hidden = next(c for c in initial["cities"] if c["id"] == IRONVALE)
            self.assertEqual(hidden["name"], "Uncharted road exit")
            game.action("travel", {"destination": IRONVALE}, "road-1")
            duration = game.world.actors["hero"].arrival_minute - game.world.minute
            self.assertNotIn(IRONVALE, game.snapshot()["player"]["discovered_cities"])
            while duration:
                step = min(1440, duration)
                game.advance(step)
                duration -= step
            arrived = game.snapshot()
            self.assertIn(IRONVALE, arrived["player"]["discovered_cities"])
            self.assertTrue(next(c for c in arrived["cities"] if c["id"] == IRONVALE)["discovered"])
            restored = GameSession(path).snapshot()
            self.assertEqual(restored["player"]["discovered_cities"],
                             arrived["player"]["discovered_cities"])
            self.assertEqual(restored["player"]["lineage"], "elf")

    def test_existing_save_can_choose_once_without_losing_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.json"
            game = GameSession(path)
            game.create("Eli Stone")
            data = json.loads(path.read_text())
            data.pop("lineage")  # Prior save format
            path.write_text(json.dumps(data))
            legacy = GameSession(path)
            self.assertFalse(legacy.snapshot()["player"]["lineage_selected"])
            legacy.action("choose_lineage", {"lineage": "human"}, "choice")
            again = GameSession(path)
            self.assertTrue(again.snapshot()["player"]["lineage_selected"])
            self.assertEqual(again.world.actors["hero"].work.manual, 11)

    def test_old_checkpoints_accept_only_safe_actor_defaults(self):
        tree = _encode(Actor("hero", "human", city="crownreach"))
        for key in ("lineage", "lineage_selected", "discovered_cities"):
            tree["values"].pop(key)
        # Current fresh-world checkpoints reject missing Actor fields,
        # rather than attempting unrequested five-city save migrations.
        with self.assertRaises(ValueError):
            _decode(tree)

    def test_catalog_has_distinct_real_traits(self):
        self.assertEqual(set(LINEAGES), {"human", "elf", "dwarf", "orc"})
        self.assertEqual(len({spec.trait for spec in LINEAGES.values()}), 4)


if __name__ == "__main__":
    unittest.main()
