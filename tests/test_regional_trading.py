"""Regional arbitrage never bypasses distance, capacity, accounts or stock."""
from realm_fixtures import IRONVALE

import unittest

from medieval_world_sim.catalog import CAPITAL
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.regional_world import TRAVEL_CARGO_LIMIT
from medieval_world_sim.agents.runner import create_simulation


class RegionalTradingTests(unittest.TestCase):
    def world(self):
        return WorldEngine([
            Actor("trader", "human", city=IRONVALE, gold=200),
            Actor("buyer", "human", city=CAPITAL, gold=200),
        ], seed=42)

    def test_origin_to_capital_route_has_profit_and_conserves_gold(self):
        w = self.world()
        source = w.regional_quote(IRONVALE, "iron_ore")
        destination = w.regional_quote(CAPITAL, "iron_ore")
        self.assertEqual(source.player_buy_price, 5)
        self.assertEqual(destination.player_sell_price, 8)
        self.assertGreater(destination.player_sell_price, source.player_buy_price)
        opening = w.total_gold
        gold = w.actors["trader"].gold
        self.assertEqual(w.regional_buy("trader", "iron_ore", 3), 15)
        self.assertEqual(w.actors["trader"].inventory["iron_ore"], 3)
        w.start_travel("trader", CAPITAL)
        with self.assertRaises(ActionError):
            w.regional_sell("trader", "iron_ore", 1)
        w.advance(90)
        self.assertEqual(w.regional_sell("trader", "iron_ore", 3), 24)
        self.assertEqual(w.actors["trader"].gold, gold + 9)
        self.assertEqual(w.actors["trader"].inventory["iron_ore"], 0)
        self.assertEqual(w.cities[IRONVALE].gold, 600 + 15)
        self.assertEqual(w.cities[CAPITAL].gold, 3600 - 24)
        self.assertEqual(w.total_gold, opening)
        self.assertEqual(len([e for e in w.events if e.kind == "regional_bought"]), 1)
        self.assertEqual(len([e for e in w.events if e.kind == "regional_sold"]), 1)
        w.assert_invariants()

    def test_same_city_buy_then_sell_loses_spread_not_money(self):
        w = self.world()
        before = w.total_gold
        wallet = w.actors["trader"].gold
        w.regional_buy("trader", "iron_ore", 1)
        w.regional_sell("trader", "iron_ore", 1)
        self.assertEqual(w.actors["trader"].gold, wallet - 2)
        self.assertEqual(w.total_gold, before)

    def test_travel_cargo_limit_is_stricter_than_local_inventory(self):
        w = self.world()
        self.assertEqual(TRAVEL_CARGO_LIMIT, 12)
        w.regional_buy("trader", "iron_ore", 10)
        w.gather("trader", "iron_ore", 2)
        self.assertEqual(w.start_travel("trader", CAPITAL), 90)
        w.advance(90)
        # Can still trade in a city while at the 12-item travel limit.
        w.assert_invariants()

    def test_cannot_travel_overburdened_but_can_unload_and_depart(self):
        w = WorldEngine([Actor("trader", "human", city=IRONVALE,
                               gold=100, inventory={"iron_ore": 13})])
        with self.assertRaises(ActionError):
            w.execute("trader", "travel", {"destination": CAPITAL}, "heavy")
        self.assertIsNone(w.actors["trader"].destination)
        w.execute("trader", "regional_sell", {"item": "iron_ore", "quantity": 1}, "unload")
        self.assertEqual(w.start_travel("trader", CAPITAL), 90)
        self.assertEqual(w.actors["trader"].inventory["iron_ore"], 12)
        w.assert_invariants()

    def test_gear_counts_toward_travel_weight(self):
        w = self.world()
        a = w.actors["trader"]
        a.inventory["iron_ore"] = 12
        gear = w._mint_gear(a, "sword", 50, "crafted")
        with self.assertRaises(ActionError):
            w.start_travel("trader", CAPITAL)
        # Selling one ore makes room for the sword.
        w.regional_sell("trader", "iron_ore", 1)
        w.equip("trader", gear.id)
        self.assertEqual(w.start_travel("trader", CAPITAL), 90)
        w.assert_invariants()

    def test_merchant_stock_and_budget_cannot_go_negative(self):
        w = self.world()
        initial = w.total_gold
        local = w.cities[IRONVALE]
        available = local.merchant_stock["iron_ore"]
        with self.assertRaises(ActionError):
            w.regional_buy("trader", "iron_ore", available + 1)
        with self.assertRaises(ActionError):
            w.regional_buy("trader", "iron_ore", -1)
        with self.assertRaises(ActionError):
            w.regional_sell("trader", "iron_ore", 1)
        self.assertEqual(local.merchant_stock["iron_ore"], available)
        w.assert_invariants()
        self.assertEqual(w.total_gold, initial)

    def test_daily_quota_and_stock_capacity_prevent_infinite_selling(self):
        w = WorldEngine([Actor("supplier", "human", city=CAPITAL,
                               gold=100, inventory={"iron_ore": 20})])
        self.assertEqual(w.regional_sell("supplier", "iron_ore", 16), 8 * 16)
        with self.assertRaises(ActionError):
            w.regional_sell("supplier", "iron_ore", 1)
        self.assertEqual(w.actors["supplier"].inventory["iron_ore"], 4)
        w.advance(1440)
        self.assertEqual(w.regional_sell("supplier", "iron_ore", 4), 8 * 4)
        self.assertEqual(w.total_gold, w.initial_gold)

    def test_finite_city_budget_stops_trade_and_cannot_mint_gold(self):
        w = self.world()
        w.actors["buyer"].inventory["iron_ore"] = 1
        w.cities[CAPITAL].household_gold = 0
        w.initial_gold = w.total_gold  # Explicitly funded fixture.
        with self.assertRaises(ActionError):
            w.regional_sell("buyer", "iron_ore", 1)
        self.assertEqual(w.actors["buyer"].inventory["iron_ore"], 1)
        self.assertEqual(w.cities[CAPITAL].merchant_stock.get("iron_ore", 0), 0)
        self.assertEqual(w.total_gold, w.initial_gold)

    def test_daily_restocks_take_stock_from_local_deposits(self):
        w = self.world()
        city = w.cities[IRONVALE]
        city.merchant_stock["iron_ore"] = 0
        w.advance(1440)
        self.assertEqual(city.merchant_stock["iron_ore"], 6)
        self.assertLessEqual(city.deposits["iron_ore"], 24)
        self.assertEqual(w.total_gold, w.initial_gold)

    def test_authorized_command_retry_does_not_trade_twice(self):
        w = self.world()
        before = w.total_gold
        params = {"item": "iron_ore", "quantity": 2}
        gold = w.actors["trader"].gold
        first = w.execute("trader", "regional_buy", params, "trade-order-1")
        self.assertEqual(first, 10)
        self.assertEqual(w.execute("trader", "regional_buy", params, "trade-order-1"), first)
        self.assertEqual(w.actors["trader"].gold, gold - first)
        with self.assertRaises(ActionError):
            w.execute("buyer", "regional_buy", params, "trade-order-1")
        with self.assertRaises(ActionError):
            w.execute("trader", "regional_buy", {"item": "coal", "quantity": 2},
                      "trade-order-1")
        self.assertEqual(w.total_gold, before)
        self.assertEqual(len([e for e in w.events if e.kind == "regional_bought"]), 1)

    def test_unsupported_goods_and_remote_trade_are_rejected(self):
        w = self.world()
        with self.assertRaises(ActionError):
            w.regional_quote("notacity", "iron_ore")
        with self.assertRaises(ActionError):
            w.regional_quote(CAPITAL, "sword")
        with self.assertRaises(ActionError):
            w.regional_buy("trader", "steel", 1)
        with self.assertRaises(ActionError):
            w.regional_buy("trader", "iron_ore", True)
        with self.assertRaises(ActionError):
            w.regional_buy("buyer", "iron_ore", 1)  # Capital currently stocks none.
        w.start_travel("trader", CAPITAL)
        with self.assertRaises(ActionError):
            w.regional_buy("trader", "iron_ore", 1)

    def test_npc_haulers_actually_trade_regional_goods(self):
        sim = create_simulation(npcs=28, seed=42)
        report = sim.run(days=6)
        self.assertTrue(report["gold_conserved"])
        self.assertGreater(report["regional_purchases"], 0)
        self.assertGreater(report["regional_sales"], 0)
        self.assertGreater(report["regional_sale_revenue"], 0)
        self.assertGreater(report["hauler_cash_change"], 0)
        self.assertEqual(report["rejections"], {})
        sim.world.assert_invariants()


if __name__ == "__main__":
    unittest.main()
