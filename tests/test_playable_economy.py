"""Full civilian economy: ownership, employment, crafting, escrow and restarts."""
from pathlib import Path
import tempfile
import unittest

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.economy_projection import economy_projection
from medieval_world_sim.web.multiplayer import MultiplayerGame
from medieval_world_sim.web.session import GameSession
from medieval_world_sim.web import ledger


class CivilianEconomyEngineTests(unittest.TestCase):
    def world(self):
        return WorldEngine([
            Actor("owner", "human", city=CAPITAL, gold=500,
                  inventory={"grain": 4, "steel": 2, "timber": 2}),
            Actor("worker", "human", city=CAPITAL, gold=80),
            Actor("buyer", "human", city=CAPITAL, gold=200),
        ], seed=42)

    def run_command(self, world, who, name, params, ident):
        return world.execute(who, name, params, "econ-" + ident)

    def found(self, world, name="river_bakery", industry="bakery"):
        self.run_command(world, "owner", "found_company",
                         {"company_id": name, "industry": industry,
                          "investment": 150}, "found-" + name)
        return world.companies[name]

    def test_complete_employment_production_and_sale_conserves_assets(self):
        w = self.world()
        initial = w.total_gold
        company = self.found(w)
        self.run_command(w, "owner", "company_deposit_goods",
                         {"company_id": company.id, "item": "grain",
                          "quantity": 2}, "grain")
        self.assertEqual(company.inventory["grain"], 2)
        self.run_command(w, "owner", "offer_job",
                         {"company_id": company.id, "worker_id": "worker",
                          "gold": 4, "item": "", "quantity": 0}, "offer")
        self.assertNotIn("worker", company.employees)
        self.run_command(w, "worker", "accept_job",
                         {"company_id": company.id}, "accept")
        self.run_command(w, "worker", "shift",
                         {"company_id": company.id}, "shift")
        self.assertEqual(w.actors["worker"].gold, 84)
        self.assertEqual(company.inventory["bread"], 3)
        self.assertEqual(company.shifts_completed, 1)
        listing_id = self.run_command(w, "owner", "post_offer",
                         {"seller_id": company.id, "item": "bread",
                          "quantity": 2, "unit_price": 6}, "listing")
        self.assertEqual(company.inventory["bread"], 1)
        self.assertEqual(w.offers[listing_id].quantity, 2)
        self.run_command(w, "buyer", "accept_offer",
                         {"buyer_id": "buyer", "offer_id": listing_id,
                          "quantity": 2}, "purchase")
        self.assertNotIn(listing_id, w.offers)
        self.assertEqual(w.actors["buyer"].inventory["bread"], 2)
        self.assertEqual(company.gold, 158)
        self.assertEqual(w.total_gold, initial)
        w.assert_invariants()

    def test_owner_can_fund_stock_and_withdraw_without_minting(self):
        w = self.world()
        c = self.found(w)
        initial = w.total_gold
        self.run_command(w, "owner", "company_deposit_gold",
                         {"company_id": c.id, "amount": 30}, "fund")
        self.run_command(w, "owner", "company_withdraw_gold",
                         {"company_id": c.id, "amount": 20}, "withdraw")
        self.assertEqual(c.gold, 160)
        self.assertEqual(w.actors["owner"].gold, 340)
        self.run_command(w, "owner", "company_deposit_goods",
                         {"company_id": c.id, "item": "grain",
                          "quantity": 2}, "stock")
        self.run_command(w, "owner", "company_withdraw_goods",
                         {"company_id": c.id, "item": "grain",
                          "quantity": 1}, "unstock")
        self.assertEqual(w.actors["owner"].inventory["grain"], 3)
        self.assertEqual(c.inventory["grain"], 1)
        self.assertEqual(w.total_gold, initial)
        w.assert_invariants()

    def test_crafted_quality_gear_escrow_survives_purchase(self):
        w = self.world()
        c = self.found(w, name="forge_shop", industry="forge")
        for item in ("steel", "timber"):
            self.run_command(w, "owner", "company_deposit_goods",
                             {"company_id": c.id, "item": item,
                              "quantity": 1}, "stock-" + item)
        self.run_command(w, "owner", "offer_job",
                         {"company_id": c.id, "worker_id": "worker",
                          "gold": 2, "item": "", "quantity": 0}, "offer-forge")
        self.run_command(w, "worker", "accept_job",
                         {"company_id": c.id}, "accept-forge")
        self.run_command(w, "worker", "shift",
                         {"company_id": c.id}, "forge")
        self.assertEqual(len(c.gear_ids), 1)
        gear_id = c.gear_ids[0]
        quality = w.gear[gear_id].quality
        sale_id = self.run_command(w, "owner", "post_equipment_offer",
                   {"seller_id": c.id, "gear_id": gear_id,
                    "unit_price": 30}, "gear-list")
        self.assertNotIn(gear_id, c.gear_ids)
        self.assertIn(gear_id, w.gear)
        self.run_command(w, "buyer", "accept_offer",
                         {"buyer_id": "buyer", "offer_id": sale_id,
                          "quantity": 1}, "gear-buy")
        self.assertIn(gear_id, w.actors["buyer"].gear_ids)
        self.assertEqual(w.gear[gear_id].quality, quality)
        w.assert_invariants()

    def test_private_company_accounts_and_cross_city_trades_are_blocked(self):
        w = self.world()
        c = self.found(w)
        snapshot = (w.actors["owner"].gold, c.gold, dict(c.inventory))
        attacks = [
            ("buyer", "company_withdraw_gold",
             {"company_id": c.id, "amount": 10}),
            ("worker", "company_deposit_goods",
             {"company_id": c.id, "item": "grain", "quantity": 1}),
            ("worker", "company_withdraw_goods",
             {"company_id": c.id, "item": "grain", "quantity": 1}),
            ("worker", "post_offer",
             {"seller_id": c.id, "item": "grain",
              "quantity": 1, "unit_price": 10}),
            ("owner", "accept_job", {"company_id": c.id}),
            ("buyer", "offer_job", {
                "company_id": c.id, "worker_id": "owner",
                "gold": 10, "item": "", "quantity": 0}),
        ]
        for idx, (who, name, data) in enumerate(attacks):
            with self.subTest(action=name), self.assertRaises(ActionError):
                self.run_command(w, who, name, data, "forgery-" + str(idx))
        self.assertEqual((w.actors["owner"].gold, c.gold, dict(c.inventory)), snapshot)
        w.actors["owner"].city = "goldmeadow"
        with self.assertRaises(ActionError):
            self.run_command(w, "owner", "company_withdraw_gold",
                             {"company_id": c.id, "amount": 1}, "remote")
        w.actors["owner"].city = CAPITAL
        w.assert_invariants()

    def test_malformed_inputs_fail_cleanly_and_limits_hold(self):
        w = self.world()
        c = self.found(w)
        bad = [
            ("company_deposit_gold", {"company_id": c.id, "amount": True}),
            ("company_deposit_goods", {
                "company_id": c.id, "item": [], "quantity": 1}),
            ("offer_job", {
                "company_id": c.id, "worker_id": "worker",
                "gold": 3, "item": [], "quantity": 0}),
            ("post_offer", {
                "seller_id": c.id, "item": {}, "quantity": 1,
                "unit_price": 1}),
            ("post_offer", {
                "seller_id": c.id, "item": "bread", "quantity": 1,
                "unit_price": 0}),
            ("post_offer", {
                "seller_id": [], "item": "bread", "quantity": 1,
                "unit_price": 3}),
            ("cancel_offer", {"offer_id": []}),
            ("set_perks", {"company_id": c.id, "perks": [[]]}),
        ]
        for idx, (name, params) in enumerate(bad):
            with self.subTest(name=name, args=idx), self.assertRaises(ActionError):
                self.run_command(w, "owner", name, params, "bad-" + str(idx))
        with self.assertRaises(ActionError):
            self.found(w, name="second_shop")
        w.assert_invariants()

    def test_projection_never_exposes_other_players_company_assets(self):
        w = self.world()
        c = self.found(w)
        self.run_command(w, "owner", "offer_job",
                         {"company_id": c.id, "worker_id": "worker",
                          "gold": 7, "item": "", "quantity": 0}, "offer")
        names = {"owner": "Owner", "worker": "Worker", "buyer": "Buyer"}
        owner = economy_projection(w, "owner", names)
        worker = economy_projection(w, "worker", names)
        other = economy_projection(w, "buyer", names)
        self.assertEqual(len(owner["owned"]), 1)
        self.assertEqual(owner["owned"][0]["job_offers"][0]["wage"]["gold"], 7)
        self.assertEqual(worker["owned"], [])
        self.assertEqual(worker["job_offers"][0]["wage"]["gold"], 7)
        self.assertEqual(other["owned"], [])
        self.assertEqual(other["job_offers"], [])
        self.assertEqual(other["jobs"], [])
        self.assertNotIn("company", str(other["market_sources"]))


class CivilianEconomyPersistenceTests(unittest.TestCase):
    def test_single_player_owner_operated_company_survives_restart(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "game.json"
            game = GameSession(file)
            game.create("Mira Stone")
            game.action("found_company", {
                "company_id": "mira_bakery", "industry": "bakery",
                "investment": 100}, "found")
            game.action("offer_job", {
                "company_id": "mira_bakery", "worker_id": "hero",
                "gold": 2, "item": "", "quantity": 0}, "offer")
            game.action("accept_job", {
                "company_id": "mira_bakery"}, "accept")
            view = game.snapshot()
            self.assertEqual(view["economy"]["jobs"][0]["company_id"], "mira_bakery")
            self.assertEqual(GameSession(file).snapshot(), view)

    def test_multiplayer_receipts_and_recovery_preserve_company_ownership(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "realm.sqlite3"
            game = MultiplayerGame(db, require_invites=False,
                                   dev_fast_forward=True, npc_enabled=False)
            try:
                alice = game.register("alice", "correct horse battery staple",
                                      "Alice Brook")
                bob = game.register("bob", "correct horse battery staple",
                                    "Bryn Stone")
                game.action(alice, "found_company", {
                    "company_id": "alice_forge", "industry": "forge",
                    "investment": 100}, "company-create")
                game.action(alice, "company_deposit_gold", {
                    "company_id": "alice_forge", "amount": 20}, "fund")
                game.action(alice, "offer_job", {
                    "company_id": "alice_forge", "worker_id": bob,
                    "gold": 3, "item": "", "quantity": 0}, "offer")
                game.action(bob, "accept_job",
                            {"company_id": "alice_forge"}, "accept")
                mine = game.snapshot(alice)
                worker = game.snapshot(bob)
                self.assertEqual(mine["economy"]["owned"][0]["gold"], 120)
                self.assertEqual(worker["economy"]["jobs"][0]["wage"]["gold"], 3)
                self.assertEqual(worker["economy"]["owned"], [])
                with self.assertRaises(ActionError):
                    game.action(bob, "company_withdraw_gold", {
                        "company_id": "alice_forge", "amount": 100}, "steal")
                before = game.db.execute(
                    "SELECT COUNT(*) FROM world_journal").fetchone()[0]
                duplicate = game.action(alice, "company_deposit_gold", {
                    "company_id": "alice_forge", "amount": 20}, "fund")
                self.assertIsNone(duplicate)
                self.assertEqual(game.db.execute(
                    "SELECT COUNT(*) FROM world_journal").fetchone()[0], before)
                ledger.verify(game)
            finally:
                game.close()
            reopened = MultiplayerGame(db, require_invites=False,
                                       dev_fast_forward=True, npc_enabled=False)
            try:
                self.assertEqual(reopened.snapshot(alice)["economy"]["owned"][0]["gold"], 120)
                self.assertEqual(reopened.snapshot(bob)["economy"]["jobs"][0]["wage"]["gold"], 3)
                ledger.verify(reopened)
                reopened.world.assert_invariants()
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
