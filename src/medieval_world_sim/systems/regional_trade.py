"""Fixed regional merchant spreads with finite stock, city liquidity and daily limits.

Player-driven listing markets remain separate. City trade transfers real household
gold and real stocked resources; no vendor can mint money or cargo through trades.
"""
from dataclasses import dataclass

from ..catalog import CAPITAL, CITIES, RAW_RESOURCES
from ..errors import ActionError
from ..core.transactions import transfer_gold

# Local source -> low ask; Crownreach -> guaranteed higher bid while funded.
# Deliberate baseline arbitrage is a gameplay design choice, not infinite demand.
BASE_LOCAL_ASK = {
    "iron_ore": 5, "coal": 5, "stone": 3, "timber": 4, "herbs": 4,
    "grain": 3, "hides": 5, "vegetables": 3, "meat": 4,
}
MERCHANT_STOCK_CAP = 32
MERCHANT_DAILY_LIMIT = 16
DAILY_RESTOCK = 6


@dataclass(frozen=True)
class RegionalQuote:
    city: str
    item: str
    player_buy_price: int  # What player pays to obtain one good.
    player_sell_price: int  # What player receives for selling one good.
    stock: int
    buy_capacity: int  # Maximum units city will buy today; subject to gold.
    sell_capacity: int  # Maximum units city will sell today; subject to stock.
    city_gold: int


class RegionalTradeSystem:
    def __init__(self, world):
        self.world = world

    def quote(self, city_id: str, item: str) -> RegionalQuote:
        if city_id not in CITIES or item not in BASE_LOCAL_ASK:
            raise ActionError("No regional merchant quote for this city or item")
        city = self.world.cities[city_id]
        base = BASE_LOCAL_ASK[item]
        source = item in CITIES[city_id].deposits
        if source:
            sell_to_player, buy_from_player = base, max(1, base - 2)
        elif city_id == CAPITAL:
            sell_to_player, buy_from_player = base + 6, base + 3
        else:
            sell_to_player, buy_from_player = base + 4, base + 1
        stock = city.merchant_stock.get(item, 0)
        # Small, visible scarcity/oversupply adjustment; never reverse spread.
        if stock < 3:
            sell_to_player += 1
        if stock >= 24:
            buy_from_player = max(1, buy_from_player - 1)
        buy_capacity = min(MERCHANT_DAILY_LIMIT - city.merchant_purchases_today,
                           MERCHANT_STOCK_CAP - stock)
        return RegionalQuote(city_id, item, sell_to_player, buy_from_player, stock,
                             buy_capacity,
                             min(MERCHANT_DAILY_LIMIT - city.merchant_sales_today, stock),
                             city.gold)

    def buy(self, actor_id: str, item: str, quantity: int) -> int:
        actor = self.world._actor(actor_id)
        city_id = self.world._at_city(actor)
        self.world._positive(quantity, "quantity")
        quote = self.quote(city_id, item)
        if quantity > quote.sell_capacity:
            raise ActionError("Merchant has insufficient goods or today's sell quota")
        if not self.world._space_for(actor, item, quantity):
            raise ActionError("Insufficient personal carrying capacity")
        payment = quote.player_buy_price * quantity
        if actor.gold < payment:
            raise ActionError("Insufficient gold for merchant purchase")
        city = self.world.cities[city_id]
        transfer_gold(self.world, actor, city, payment)
        city.merchant_stock[item] -= quantity
        city.merchant_sales_today += quantity
        self.world._add(actor, item, quantity)
        self.world._emit("regional_bought", actor_id, city_id, item,
                         quantity, quote.player_buy_price, payment)
        return payment

    def sell(self, actor_id: str, item: str, quantity: int) -> int:
        actor = self.world._actor(actor_id)
        city_id = self.world._at_city(actor)
        self.world._positive(quantity, "quantity")
        quote = self.quote(city_id, item)
        if actor.inventory.get(item, 0) < quantity:
            raise ActionError("Not enough goods owned to sell")
        if quantity > quote.buy_capacity:
            raise ActionError("Merchant has reached its stock or daily buy limit")
        revenue = quote.player_sell_price * quantity
        if self.world.cities[city_id].gold < revenue:
            raise ActionError("City merchant has insufficient household funds")
        city = self.world.cities[city_id]
        transfer_gold(self.world, city, actor, revenue)
        actor.inventory[item] -= quantity
        city.merchant_stock[item] = city.merchant_stock.get(item, 0) + quantity
        city.merchant_purchases_today += quantity
        self.world._emit("regional_sold", actor_id, city_id, item,
                         quantity, quote.player_sell_price, revenue)
        return revenue

    def replenish_daily(self) -> None:
        """Collect finite local source goods from regenerated regional deposits."""
        for city_id in sorted(self.world.cities):
            city = self.world.cities[city_id]
            city.merchant_purchases_today = 0
            city.merchant_sales_today = 0
            for item in sorted(CITIES[city_id].deposits):
                stock = city.merchant_stock.get(item, 0)
                amount = min(DAILY_RESTOCK, city.deposits[item],
                             MERCHANT_STOCK_CAP - stock)
                if amount:
                    city.deposits[item] -= amount
                    city.merchant_stock[item] = stock + amount
