"""Finite household demand for real produced inventory.

This is *not* unlimited passive income. Each sale removes a tangible produced
item (including escrow) and moves gold from the city's seeded household ledger.
"""
from hashlib import sha256

from ..catalog import RECIPES
from ..core.quality import company_quality
from ..core.transactions import transfer_gold


RETAIL_PRICES = {
    "bread": 5, "meal": 9, "healing_potion": 18,
    "sword": 58, "axe": 55, "bow": 54, "shield": 49,
    "leather_armor": 51, "plate_armor": 90, "pickaxe": 26,
}


def _roll(seed: int, day: int, company_id: str, item: str) -> int:
    digest = sha256(f"{seed}:{day}:{company_id}:{item}".encode()).digest()
    return digest[0] % 3 - 1


def retail_price(kind: str, stars: int, quality: int | None = None) -> int:
    multiplier = 0.82 + 0.085 * stars
    if quality is not None:
        multiplier *= 0.9 + quality / 200
    return max(1, round(RETAIL_PRICES[kind] * multiplier))


class CityDemandSystem:
    def __init__(self, world):
        self.world = world

    def settle_day(self, day: int) -> None:
        """Sell at most the city's daily purchasing budget, no unpaid promises."""
        for company in self.world.companies.values():
            company.daily_units_sold = 0
            company.daily_revenue = 0
        for city_id in sorted(self.world.cities):
            city = self.world.cities[city_id]
            budget = min(city.household_gold, city.population * 4 // 5)
            for company in sorted(self.world.companies.values(), key=lambda c: c.id):
                if company.city != city_id:
                    continue
                quality = company_quality(self.world, company)
                produced = RECIPES[company.industry].outputs
                for kind in sorted(produced):
                    if kind not in RETAIL_PRICES or budget <= 0:
                        continue  # households do not buy industrial intermediates
                    demand = max(0, city.population // 120 +
                                 (quality.stars - 2) + _roll(self.world.seed, day, company.id, kind))
                    for _ in range(demand):
                        available = self._available(company, kind)
                        if available is None:
                            break
                        source, inventory_id, ask = available
                        gear_id = (self.world.offers[inventory_id].gear_id
                                   if source == "offer" else inventory_id)
                        gear = (self.world.gear[gear_id] if gear_id is not None
                                and kind not in ("bread", "meal", "healing_potion") else None)
                        price = ask if ask is not None else retail_price(
                            kind, quality.stars, gear.quality if gear else None)
                        fair = retail_price(kind, quality.stars, gear.quality if gear else None)
                        if price > round(fair * 1.3) or price > budget or price > city.household_gold:
                            break
                        transfer_gold(self.world, city, company, price)
                        self._consume(company, kind, source, inventory_id)
                        budget -= price
                        company.daily_units_sold += 1
                        company.daily_revenue += price
                        self.world._emit("city_sale", city_id, company.id, kind,
                                         price, quality.stars, day)

    def _available(self, company, kind: str) -> tuple[str, int | None, int | None] | None:
        if kind in ("bread", "meal", "healing_potion"):
            if company.inventory.get(kind, 0) > 0:
                return ("inventory", None, None)
        else:
            for gid in sorted(company.gear_ids):
                if self.world.gear[gid].kind == kind:
                    return ("gear", gid, None)
        for o in sorted(self.world.offers.values(), key=lambda offer: offer.id):
            if o.seller_id == company.id and o.city == company.city and o.item == kind:
                return ("offer", o.id, o.unit_price)
        return None

    def _consume(self, company, kind: str, source: str, identifier: int | None) -> None:
        if source == "inventory":
            company.inventory[kind] -= 1
        elif source == "gear":
            company.gear_ids.remove(identifier)
            del self.world.gear[identifier]
        else:
            offer = self.world.offers[identifier]
            if offer.gear_id is not None:
                del self.world.gear[offer.gear_id]
            offer.quantity -= 1
            if offer.quantity == 0:
                del self.world.offers[identifier]
