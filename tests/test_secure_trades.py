"""Adversarial trade tests: forged principals, invalid terms, replay and races."""
from concurrent.futures import ThreadPoolExecutor
import unittest

from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError


def assets(gold=0, items=None, gear=None):
    return {"gold": gold,
            "items": [{"item": k, "quantity": v} for k, v in (items or {}).items()],
            "gear_ids": list(gear or [])}


class SecureBilateralTradeTests(unittest.TestCase):
    def setUp(self):
        self.world = WorldEngine([
            Actor("alice", "human", city="crownreach", gold=200,
                  inventory={"grain": 5}),
            Actor("bob", "human", city="crownreach", gold=150,
                  inventory={"iron_ore": 3}),
            Actor("mallory", "human", city="crownreach", gold=100),
            Actor("guard", "npc", city="crownreach", gold=100),
        ])
        self.gold = self.world.total_gold

    def offer(self, offer=None, request=None, recipient="bob"):
        return self.world.execute("alice", "propose_trade",
                                  {"recipient_id": recipient,
                                   "offer": offer or assets(gold=10),
                                   "request": request or assets(gold=7)},
                                  "test-propose-" + str(self.world.state.next_trade_id))

    def test_gold_resource_equipment_escrow_and_signed_accept(self):
        sword = self.world.buy_starter_gear("alice", "sword")
        self.world.equip("alice", sword)
        proposal = self.offer(assets(gold=20, items={"grain": 2}, gear=[sword]),
                              assets(gold=30, items={"iron_ore": 1}))
        self.assertEqual(self.world.total_gold, self.gold)
        self.assertNotIn(sword, self.world.actors["alice"].gear_ids)
        self.assertNotIn("weapon", self.world.actors["alice"].equipped)
        self.assertEqual(self.world.actors["alice"].gold, 164)
        with self.assertRaises(ActionError):
            self.world.execute("mallory", "accept_trade",
                               {"trade_id": proposal["id"],
                                "terms_hash": proposal["terms_hash"]}, "forged-accept")
        with self.assertRaises(ActionError):
            self.world.execute("bob", "accept_trade",
                               {"trade_id": proposal["id"], "terms_hash": "not-the-hash"},
                               "changed-terms")
        self.assertEqual(self.world.total_gold, self.gold)
        result = self.world.execute("bob", "accept_trade",
                                    {"trade_id": proposal["id"],
                                     "terms_hash": proposal["terms_hash"]}, "real-accept")
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(self.world.execute("bob", "accept_trade",
                          {"trade_id": proposal["id"],
                           "terms_hash": proposal["terms_hash"]}, "real-accept"), result)
        self.assertEqual(self.world.actors["bob"].gold, 140)
        self.assertEqual(self.world.actors["alice"].gold, 194)
        self.assertIn(sword, self.world.actors["bob"].gear_ids)
        self.assertEqual(self.world.actors["bob"].inventory["grain"], 2)
        self.assertEqual(self.world.actors["alice"].inventory["iron_ore"], 1)
        self.assertEqual(self.world.total_gold, self.gold)
        with self.assertRaises(ActionError):
            self.world.execute("bob", "accept_trade",
                               {"trade_id": proposal["id"],
                                "terms_hash": proposal["terms_hash"]}, "accept-again")
        self.world.assert_invariants()

    def test_reject_releases_full_escrow_and_only_participants_can_close(self):
        sword = self.world.buy_starter_gear("alice", "sword")
        proposal = self.offer(assets(gold=12, items={"grain": 3}, gear=[sword]),
                              assets(items={"iron_ore": 1}))
        with self.assertRaises(ActionError):
            self.world.execute("mallory", "close_trade",
                               {"trade_id": proposal["id"]}, "mal-close")
        self.assertNotIn(sword, self.world.actors["alice"].gear_ids)
        self.world.execute("bob", "close_trade", {"trade_id": proposal["id"]}, "reject")
        self.assertIn(sword, self.world.actors["alice"].gear_ids)
        self.assertEqual(self.world.actors["alice"].inventory["grain"], 5)
        self.assertEqual(self.world.actors["alice"].gold, 184)
        self.assertEqual(self.world.total_gold, self.gold)
        self.world.assert_invariants()

    def test_rejected_recipient_insufficient_funds_rolls_back(self):
        proposal = self.offer(assets(gold=5), assets(gold=999999))
        before = self.world.total_gold
        with self.assertRaises(ActionError):
            self.world.accept_trade("bob", proposal["id"], proposal["terms_hash"])
        self.assertIn(proposal["id"], self.world.state.trades)
        self.assertEqual(self.world.total_gold, before)
        self.world.assert_invariants()

    def test_rejects_invalid_assets_and_npc_trades(self):
        for invalid in (assets(gold=-1), assets(gold=True),
                        assets(items={"grain": -1}),
                        {"gold": 1, "items": [{"item": "grain", "quantity": 1},
                                             {"item": "grain", "quantity": 2}], "gear_ids": []},
                        assets(gear=[4, 4])):
            with self.assertRaises(ActionError):
                self.world.propose_trade("alice", "bob", invalid, assets(gold=1))
        with self.assertRaises(ActionError):
            self.offer(recipient="guard")
        with self.assertRaises(ActionError):
            self.world.propose_trade("alice", "alice", assets(gold=1), assets())
        self.assertEqual(self.world.total_gold, self.gold)
        self.world.assert_invariants()

    def test_concurrent_accepts_only_settle_once(self):
        proposal = self.offer(assets(gold=10), assets(gold=7))
        def accept(_):
            try:
                return self.world.accept_trade("bob", proposal["id"], proposal["terms_hash"])
            except ActionError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(accept, range(2)))
        self.assertEqual(sum(x is not None for x in outcomes), 1)
        self.assertEqual(self.world.actors["alice"].gold, 197)
        self.assertEqual(self.world.actors["bob"].gold, 153)
        self.assertEqual(self.world.total_gold, self.gold)
        self.world.assert_invariants()

    def test_existing_single_player_web_actions_cannot_trigger_trades(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from medieval_world_sim.web.session import GameSession
        with TemporaryDirectory() as folder:
            game = GameSession(Path(folder) / "game.json")
            game.create("Hero")
            with self.assertRaises(ActionError):
                game.action("propose_trade", {"recipient_id": "npc:1",
                             "offer": assets(gold=1),
                             "request": assets()}, "malicious-request")


if __name__ == "__main__":
    unittest.main()
