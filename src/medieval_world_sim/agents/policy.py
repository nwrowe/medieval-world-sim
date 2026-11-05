"""No neural network yet: economic utility with seeded Gaussian exploration.

Policies receive detached observations and propose validated commands. They never
set gold, inventory, equipment, or state directly. The simulator executes them
through WorldEngine.execute with a unique action ID.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import random

from ..catalog import CAPITAL, CITIES, RECIPES
from ..equipment import GEAR
from .cognition import NPCMemory, Needs
from ..core.entities import Wage
from .observation import NPCView
from .planning import deliver_route, route_candidates


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
    # Only isolated playtest actors use a persona; ordinary NPCs keep their profession.
    persona: str | None = None


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

    def choose(self, profile: NPCProfile, view: NPCView,
               memory: NPCMemory | None = None) -> NPCAction | None:
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
        # A funded purchase commits the Optimizer to delivering its cargo.
        # While a sale is temporarily blocked by city quota or liquidity, it
        # may work locally but cannot trade away or abandon that cargo.
        committed = (profile.role == "playtester" and
                     profile.persona == "optimizer" and memory is not None
                     and memory.active_route is not None)
        if committed:
            next_leg = deliver_route(view, memory.active_route)
            if next_leg:
                return NPCAction(next_leg.name, next_leg.params)
        method = {
            "gatherer": self._gatherer,
            "hauler": self._hauler,
            "manager": self._manager,
            "worker": self._worker,
            "adventurer": self._adventurer,
            "playtester": self._playtester,
        }.get(profile.role)
        if method is None:
            raise ValueError(f"Unknown NPC role: {profile.role}")
        candidates = method(profile, view)
        if committed:
            candidates = [candidate for candidate in candidates if
                          candidate.action.name not in
                          ("travel", "regional_buy", "regional_sell", "gather")]
        # Neither luck nor curiosity can bypass the engine's validation.
        if not candidates:
            return None
        # Greedy most often, but distinct personalities sometimes explore
        # less-rewarding valid actions. A Gaussian gives bounded-in-practice
        # score noise (rather than uniformly selecting nonsensical actions).
        if len(candidates) > 1 and self.rng.random() < profile.curiosity * 0.20:
            return self.rng.choice(candidates).action
        needs = Needs.from_view(view, profile.curiosity)
        def utility(candidate: Candidate) -> float:
            action = candidate.action
            bonus = memory.utility_modifier(action, view, profile.curiosity) if memory else 0.0
            # Common needs influence proposals without bypassing eligibility.
            if action.name in ("complete_city_contract", "regional_sell"):
                bonus += needs.liquidity * profile.greed
            if action.name == "travel":
                bonus += needs.exploration * 0.4
            return candidate.score + bonus + self.rng.gauss(0, profile.volatility)
        return max(candidates, key=utility).action

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
        """Buy source-city goods when their published capital bid clears costs."""
        if p.resource is None:
            return []
        stock = v.stock(p.resource)
        load = sum(q for _, q in v.inventory) + len(v.gear)
        capital_quote = v.regional_quote(p.resource, capital=True)
        if v.city == CAPITAL:
            if stock:
                if capital_quote is not None:
                    qty = min(stock, capital_quote.buy_capacity,
                              capital_quote.city_gold // capital_quote.player_sell_price)
                    if qty > 0:
                        return [self._action(20, "regional_sell", item=p.resource, quantity=qty)]
                # Household liquidity may have dried up; try a real market sale.
                ask = max(1, round(BASE_PRICES[p.resource] * 1.15 * p.greed))
                if not any(o.seller_id == v.id and o.item == p.resource
                           for o in v.local_offers(p.resource)):
                    return [self._action(12, "post_offer", seller_id=v.id, item=p.resource,
                                         quantity=stock, unit_price=ask)]
                return []
            return [self._action(12, "travel", destination=p.home)]
        if v.city == p.home:
            if stock >= 3 or load >= 12:
                return [self._action(16, "travel", destination=CAPITAL)] if load <= 12 else []
            source_quote = v.regional_quote(p.resource)
            remaining = min(3 - stock, max(0, 12 - load))
            profitable = (source_quote is not None and capital_quote is not None
                          and capital_quote.player_sell_price > source_quote.player_buy_price
                          and capital_quote.buy_capacity > 0
                          and capital_quote.city_gold >= capital_quote.player_sell_price)
            if profitable and remaining > 0:
                qty = min(remaining, source_quote.sell_capacity,
                          v.gold // source_quote.player_buy_price)
                if qty > 0:
                    return [self._action(20, "regional_buy", item=p.resource, quantity=qty)]
            offers = sorted((o for o in v.local_offers(p.resource)
                             if o.seller_id != v.id and
                             o.price <= HAULER_BUY_CEILINGS[p.resource] and
                             o.price <= max(1, v.gold // 3)), key=lambda o: (o.price, o.id))
            if offers and remaining > 0 and capital_quote is not None:
                offer = offers[0]
                if offer.price < capital_quote.player_sell_price:
                    qty = min(remaining, offer.quantity,
                              v.gold // max(1, offer.price))
                    if qty:
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


    def _playtester(self, p: NPCProfile, v: NPCView) -> list[Candidate]:
        """Choose actual server-validated actions for two contrasting critics.

        The agent intentionally tries a few expensive/slow systems. It cannot
        adjust stats or assets and can only request the same typed commands
        that a player can. Personas affect utility, not permissions.
        """
        explorer = p.persona == "explorer"
        if p.persona not in ("explorer", "optimizer"):
            raise ValueError("Playtester requires an explorer or optimizer persona")
        actions: list[Candidate] = []
        load = sum(q for _, q in v.inventory) + len(v.gear)
        equipped = dict(v.equipped)
        for gid, kind, _ in v.gear:
            slot = GEAR[kind].slot
            if slot not in equipped:
                actions.append(self._action(22, "equip", gear_id=gid))
        for name in v.contracts:
            # The optimiser focuses on income, explorer tries variety.
            base = 15 if not explorer else 10
            if name == "labor_shift":
                base += 2 if not explorer else 0
            if name == "mage_copywork" and explorer:
                base += 3
            actions.append(self._action(base, "complete_city_contract", contract_id=name))
        for name in v.magic_eligible:
            if explorer:
                actions.append(self._action(13, "unlock_magic", node_id=name))
        for name, mana_cost in v.magic_practice:
            if explorer and v.mana >= mana_cost:
                actions.append(self._action(10, "practice_magic", node_id=name))
        if not v.studying and v.gold >= 30:
            for school, index, cost in v.courses:
                if v.gold >= cost:
                    actions.append(self._action(
                        (8 if explorer else 4) + (2 if school == "commerce" else 0),
                        "enroll_course_choice", school=school, index=index))
        owned_kinds = {kind for _, kind, _ in v.gear}
        if v.city == CAPITAL and "sword" not in owned_kinds and v.gold >= GEAR["sword"].base_value:
            actions.append(self._action(
                11 if explorer else 18, "buy_starter_gear", kind="sword"))
        if v.city == CAPITAL and explorer and "dagger" not in owned_kinds and (
                v.gold >= GEAR["dagger"].base_value):
            actions.append(self._action(9, "buy_starter_gear", kind="dagger"))
        # Explorer samples local markets; Optimizer trades only as a complete
        # source-to-capital route with actual profit credited on delivery.
        if not explorer:
            actions.extend(Candidate(option.score,
                                     NPCAction(option.name, option.params))
                           for option in route_candidates(v))
        # Finite regional prices, treasury capacity and travel cargo all apply.
        for q in v.regional_quotes:
            stock = v.stock(q.item)
            if explorer and stock and q.buy_capacity and q.city_gold >= q.player_sell_price:
                qty = min(stock, q.buy_capacity, q.city_gold // q.player_sell_price, 6)
                if qty:
                    actions.append(self._action(
                        (15 if explorer else 21), "regional_sell", item=q.item, quantity=qty))
            capital = v.regional_quote(q.item, capital=True)
            if (explorer and v.city != CAPITAL and q.sell_capacity and capital is not None
                    and capital.player_sell_price > q.player_buy_price
                    and capital.buy_capacity and v.gold >= q.player_buy_price):
                qty = min(q.sell_capacity, v.gold // q.player_buy_price, max(0, 12 - load), 4)
                if qty:
                    margin = capital.player_sell_price - q.player_buy_price
                    actions.append(self._action(
                        (8 if explorer else 17) + min(3, margin / 2),
                        "regional_buy", item=q.item, quantity=qty))
        if v.minute >= v.ready_minute and load < 12:
            for item, available in v.deposits:
                qty = min(2, available, 12 - load)
                if qty:
                    actions.append(self._action(
                        12 if explorer else 8, "gather", item=item, quantity=qty))
        # Unknown cities are enticing to an explorer. The optimiser travels
        # for trade opportunities, but is willing to try unfamiliar roads too.
        if load <= 12:
            unknown = [city for city in CITIES if city not in v.discovered_cities]
            for city in unknown:
                if city != v.city:
                    actions.append(self._action(
                        (19 if explorer else 5), "travel", destination=city))
            if v.city != CAPITAL:
                actions.append(self._action(
                    10 if explorer else (20 if sum(q for _, q in v.inventory) else 9),
                    "travel", destination=CAPITAL))
            elif explorer and len(v.discovered_cities) == len(CITIES):
                for city in CITIES:
                    if city != CAPITAL:
                        actions.append(self._action(5, "travel", destination=city))
        if (explorer and v.stamina >= 30 and v.hp >= v.max_hp - 3
                and v.city == CAPITAL and self.rng.random() < p.risk * 0.12):
            # Offline playtest combat targets ONLY baseline NPC adventurers.
            targets = [target for target in v.opponents
                       if target.startswith("adventurer_")]
            if targets:
                actions.append(self._action(
                    7, "attack", defender_id=self.rng.choice(targets)))
        return actions
