"""No neural network yet: economic utility with seeded Gaussian exploration.

Policies receive detached observations and propose validated commands. They never
set gold, inventory, equipment, or state directly. The simulator executes them
through WorldEngine.execute with a unique action ID.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import random

from ..catalog import CAPITAL, RECIPES
from ..core.entities import Wage
from .observation import NPCView


BASE_PRICES = {
    "iron_ore": 7, "coal": 6, "timber": 5, "hides": 6,
    "grain": 3, "herbs": 5, "stone": 3, "vegetables": 4, "meat": 5,
    "steel": 29, "leather": 20, "planks": 12,
    "bread": 5, "meal": 9, "healing_potion": 18,
    "sword": 58, "axe": 55, "leather_armor": 51, "plate_armor": 90,
    "shield": 49, "bow": 54,
}
INPUT_PRICE_CEILINGS = {item: max(1, int(base * 1.4)) for item, base in BASE_PRICES.items()}
HAULER_BUY_CEILINGS = {item: max(1, int(BASE_PRICES[item] * 0.85))
                       for item in ("iron_ore", "coal", "timber", "hides", "grain", "herbs")}


@dataclass(frozen=True)
class NPCProfile:
    id: str
    role: str
    home: str = CAPITAL
    resource: str | None = None
    company_id: str | None = None
    # Private, fixed personality; market decisions will differ even with same job.
    greed: float = 1.0
    risk: float = 0.3
    curiosity: float = 0.2
    volatility: float = 0.7


@dataclass(frozen=True)
class NPCAction:
    name: str
    params: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Candidate:
    score: float
    action: NPCAction


class RuleBasedPolicy:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def choose(self, profile: NPCProfile, view: NPCView) -> NPCAction | None:
        """Observe, score, select. Gaussian perturbations avoid identical NPCs."""
        if view.hp <= 0 or view.destination is not None:
            return None
        # Urgent survival decisions take precedence over profession.
        if view.hp <= view.max_hp - 8:
            if view.stock("healing_potion"):
                return NPCAction("consume", {"item": "healing_potion"})
            potions = sorted(
                (o for o in view.local_offers("healing_potion")
                 if o.seller_id != view.id and o.price <= view.gold // 3
                 and o.price <= 2 * BASE_PRICES["healing_potion"]),
                key=lambda o: (o.price, o.id))
            if potions:
                return NPCAction("accept_offer", {
                    "buyer_id": view.id, "offer_id": potions[0].id, "quantity": 1})
        if view.hunger >= 2:
            food = next((kind for kind in ("meal", "bread") if view.stock(kind)), None)
            if food is not None:
                return NPCAction("consume", {"item": food})
            affordable = sorted(
                (o for o in view.local_offers() if o.item in ("bread", "meal")
                 and o.seller_id != view.id and o.price <= view.gold // 8
                 and o.price <= BASE_PRICES[o.item] * 2),
                key=lambda x: (x.price, x.id))
            if affordable:
                return NPCAction("accept_offer", {
                    "buyer_id": view.id, "offer_id": affordable[0].id, "quantity": 1})
        method = {
            "gatherer": self._gatherer,
            "hauler": self._hauler,
            "manager": self._manager,
            "worker": self._worker,
            "adventurer": self._adventurer,
        }.get(profile.role)
        if method is None:
            raise ValueError(f"Unknown NPC role: {profile.role}")
        candidates = method(profile, view)
        # Neither luck nor curiosity can bypass the engine's validation.
        if not candidates:
            return None
        # Greedy most often, but distinct personalities sometimes explore
        # less-rewarding valid actions. A Gaussian gives bounded-in-practice
        # score noise (rather than uniformly selecting nonsensical actions).
        if len(candidates) > 1 and self.rng.random() < profile.curiosity * 0.20:
            return self.rng.choice(candidates).action
        return max(candidates, key=lambda c: c.score + self.rng.gauss(
            0, profile.volatility)).action

    @staticmethod
    def _action(score: float, name: str, **kwargs: object) -> Candidate:
        return Candidate(score, NPCAction(name, kwargs))

    def _gatherer(self, p: NPCProfile, v: NPCView) -> list[Candidate]:
        if p.resource is None:
            return []
        carrying = sum(q for _, q in v.inventory) + len(v.gear)
        stock = v.stock(p.resource)
        market_supply = sum(o.quantity for o in v.offers if o.item == p.resource
                            and o.city == CAPITAL)
        if v.city == p.home:
            if stock >= 4:
                ask_home = max(1, round(BASE_PRICES[p.resource] * 0.65 * p.greed))
                results = [self._action(12, "travel", destination=CAPITAL)]
                if stock >= 2 and not any(
                    o.seller_id == v.id and o.city == p.home for o in v.offers
                ):
                    results.append(self._action(
                        11 + p.curiosity, "post_offer", seller_id=v.id,
                        item=p.resource, quantity=stock, unit_price=ask_home))
                return results
            available = dict(v.deposits).get(p.resource, 0)
            quantity = min(2, available, max(0, 20 - carrying))
            if (v.minute >= v.ready_minute and quantity > 0
                    and market_supply < 40):
                return [self._action(12, "gather", item=p.resource, quantity=quantity)]
            return []
        if v.city == CAPITAL:
            if stock:
                price = max(1, round(BASE_PRICES[p.resource] * p.greed))
                return [self._action(16, "post_offer", seller_id=v.id,
                                     item=p.resource, quantity=stock, unit_price=price)]
            return [self._action(12, "travel", destination=p.home)]
        return [self._action(10, "travel", destination=p.home)]

    def _hauler(self, p: NPCProfile, v: NPCView) -> list[Candidate]:
        if p.resource is None:
            return []
        stock = v.stock(p.resource)
        if v.city == CAPITAL:
            if stock:
                ask = max(1, round(BASE_PRICES[p.resource] * 1.15 * p.greed))
                return [self._action(17, "post_offer", seller_id=v.id, item=p.resource,
                                     quantity=stock, unit_price=ask)]
            return [self._action(12, "travel", destination=p.home)]
        if v.city == p.home:
            if stock >= 3:
                return [self._action(16, "travel", destination=CAPITAL)]
            offers = sorted((o for o in v.local_offers(p.resource)
                             if o.seller_id != v.id and
                             o.price <= HAULER_BUY_CEILINGS[p.resource] and
                             o.price <= max(1, v.gold // 3)),
                            key=lambda o: (o.price, o.id))
            if offers:
                offer = offers[0]
                qty = min(3 - stock, offer.quantity, v.gold // max(1, offer.price))
                if qty > 0:
                    return [self._action(15, "accept_offer", buyer_id=v.id,
                                         offer_id=offer.id, quantity=qty)]
            if stock:
                return [self._action(11, "travel", destination=CAPITAL)]
            return []
        return [self._action(12, "travel", destination=p.home)]

    def _manager(self, p: NPCProfile, v: NPCView) -> list[Candidate]:
        company = v.company(p.company_id or "")
        if company is None or company.owner_id != v.id:
            return []
        if v.city != company.city:
            return [self._action(18, "travel", destination=company.city)]
        recipe = RECIPES[company.industry]
        proposed: list[Candidate] = []
        # Owners adjust pay to each employee's earned professional skill.
        for worker_id, actual, recommended in company.employee_pay:
            if actual != recommended and company.gold >= recommended * 3:
                proposed.append(self._action(9, "set_wage", company_id=company.id,
                                             worker_id=worker_id,
                                             wage=Wage(gold=recommended)))
        if company.facility_level < 3 and company.gold >= 280:
            proposed.append(self._action(7, "upgrade_facility", company_id=company.id))
        for item, minimum in recipe.inputs.items():
            if company.stock(item) >= minimum * 2:
                continue
            for offer in v.local_offers(item):
                if offer.seller_id == company.id:
                    continue
                maximum = INPUT_PRICE_CEILINGS.get(item, BASE_PRICES.get(item, 10) * 2)
                if offer.price > maximum:
                    continue
                qty = min(minimum * 2 - company.stock(item), offer.quantity)
                if qty <= 0 or qty * offer.price > company.gold:
                    continue
                urgency = 16 if company.stock(item) < minimum else 9
                proposed.append(self._action(
                    urgency - offer.price / max(1, maximum),
                    "accept_offer", buyer_id=company.id, offer_id=offer.id, quantity=qty))
        listing_ids = {o.gear_id for o in v.offers if o.seller_id == company.id
                       and o.gear_id is not None}
        existing = {(o.item, o.gear_id) for o in v.offers if o.seller_id == company.id}
        for item, qty in company.inventory:
            if item in recipe.outputs and qty > 0 and (item, None) not in existing:
                price = round(BASE_PRICES.get(item, 20) * p.greed)
                proposed.append(self._action(
                    14, "post_offer", seller_id=company.id, item=item,
                    quantity=min(3, qty), unit_price=max(1, price)))
        for gid, kind, quality in company.gear:
            if gid not in listing_ids:
                price = max(1, round(BASE_PRICES.get(kind, 30) * p.greed
                                      * (1 + quality / 140)))
                proposed.append(self._action(
                    14, "post_equipment_offer", seller_id=company.id,
                    gear_id=gid, unit_price=price))
        return proposed

    def _worker(self, p: NPCProfile, v: NPCView) -> list[Candidate]:
        c = v.company(p.company_id or "")
        if c is None or v.id not in c.employees:
            return []
        if v.city != c.city:
            return [self._action(18, "travel", destination=c.city)]
        if v.minute < v.ready_minute:
            return []
        recipe = RECIPES[c.industry]
        if all(c.stock(item) >= qty for item, qty in recipe.inputs.items()) and c.gold >= 2:
            return [self._action(16, "shift", company_id=c.id)]
        return []

    def _adventurer(self, p: NPCProfile, v: NPCView) -> list[Candidate]:
        if v.city != CAPITAL:
            return [self._action(12, "travel", destination=CAPITAL)]
        owned = {kind for _, kind, _ in v.gear}
        equipped = dict(v.equipped)
        choices: list[Candidate] = []
        for gid, kind, quality in v.gear:
            slot = "weapon" if kind in ("sword", "axe", "bow") else (
                "body" if kind in ("leather_armor", "plate_armor") else None)
            if slot and slot not in equipped:
                choices.append(self._action(18, "equip", gear_id=gid))
        if not any(k in owned for k in ("sword", "axe", "bow")):
            for offer in v.local_offers():
                if offer.gear_id is not None and offer.item in ("sword", "axe", "bow") and (
                    offer.price <= v.gold * 0.5):
                    choices.append(self._action(
                        13 - offer.price / 50, "accept_offer", buyer_id=v.id,
                        offer_id=offer.id, quantity=1))
        if not any(k in owned for k in ("leather_armor", "plate_armor")):
            for offer in v.local_offers():
                if offer.gear_id is not None and offer.item in ("leather_armor", "plate_armor") and (
                    offer.price <= v.gold * 0.45):
                    choices.append(self._action(
                        11 - offer.price / 75, "accept_offer", buyer_id=v.id,
                        offer_id=offer.id, quantity=1))
        if (v.stamina >= 20 and v.hp >= 16
                and self.rng.random() < p.risk * 0.07):
            # Combatants fight consenting-to-risk occupations within the
            # policy; the engine itself permits unrestricted attacks.
            eligible = [name for name in v.opponents if name.startswith("adventurer_")]
            if eligible:
                choices.append(self._action(8, "attack", defender_id=self.rng.choice(eligible)))
        return choices
