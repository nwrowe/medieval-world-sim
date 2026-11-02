"""Five-city authoritative experiment independent of the original single-town baseline.

All human/NPC actions share one validation path. Listing goods escrows them at
the market, preventing double sale and remote-teleportation exploits.
No API or persistence layer is exposed yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq

from .catalog import CAPITAL, CITIES, ROADS, GOODS, RECIPES

HOUR = 60
CARRY_LIMIT = 20
HARVEST_LIMIT = 2
DEPOSIT_CAP = 24


class ActionError(ValueError):
    """An invalid or unaffordable action leaves state unchanged."""


@dataclass
class Actor:
    id: str
    kind: str  # "human" or "npc" (does not change authority or capabilities)
    city: str = CAPITAL
    gold: int = 100
    inventory: dict[str, int] = field(default_factory=dict)
    destination: str | None = None
    arrival_minute: int | None = None
    ready_minute: int = 0


@dataclass(frozen=True)
class Wage:
    gold: int = 0
    item: str | None = None
    quantity: int = 0


@dataclass
class Company:
    id: str
    owner_id: str
    industry: str
    city: str = CAPITAL
    gold: int = 0
    inventory: dict[str, int] = field(default_factory=dict)
    employees: dict[str, Wage] = field(default_factory=dict)


@dataclass
class Offer:
    id: int
    seller_id: str
    city: str
    item: str
    quantity: int  # resources held in escrow, not in seller inventory
    unit_price: int


@dataclass(frozen=True)
class WorldEvent:
    minute: int
    kind: str
    details: tuple


class RegionalWorld:
    """In-memory simulation. Domain actions validate then mutate atomically."""

    def __init__(self, actors: list[Actor]):
        if not actors or len({a.id for a in actors}) != len(actors):
            raise ValueError("Actor IDs must be unique and world nonempty")
        for a in actors:
            if a.kind not in ("human", "npc") or a.city not in CITIES:
                raise ValueError("Invalid actor kind/city")
            if a.gold < 0 or any(k not in GOODS or not isinstance(v, int) or v < 0 for k, v in a.inventory.items()):
                raise ValueError("Invalid starting assets")
            if not a.id:
                raise ValueError("Empty actor ID")
            if a.destination is not None or a.arrival_minute is not None:
                raise ValueError("Actors must start stationary")
        self.actors = {a.id: a for a in actors}
        self.companies: dict[str, Company] = {}
        self.offers: dict[int, Offer] = {}
        self.minute = 0
        self.next_offer_id = 1
        self.events: list[WorldEvent] = []
        # Deposits are physical stock, not endlessly generated on demand.
        self.deposits = {
            city: {resource: 8 for resource in spec.deposits}
            for city, spec in CITIES.items()
        }
        self.initial_gold = self.total_gold

    @property
    def total_gold(self) -> int:
        return sum(a.gold for a in self.actors.values()) + sum(c.gold for c in self.companies.values())

    def _emit(self, kind: str, *details: object) -> None:
        self.events.append(WorldEvent(self.minute, kind, tuple(details)))

    def _actor(self, actor_id: str) -> Actor:
        try:
            return self.actors[actor_id]
        except KeyError:
            raise ActionError(f"Unknown actor: {actor_id}") from None

    def _account(self, account_id: str) -> Actor | Company:
        if account_id in self.actors:
            return self.actors[account_id]
        if account_id in self.companies:
            return self.companies[account_id]
        raise ActionError(f"Unknown account: {account_id}")

    def _authorize(self, initiator_id: str, account: Actor | Company) -> None:
        self._actor(initiator_id)
        permitted = account.id if isinstance(account, Actor) else account.owner_id
        if initiator_id != permitted:
            raise ActionError("Not authorized to control that account")

    def _at_city(self, account: Actor | Company) -> str:
        if isinstance(account, Actor) and account.destination is not None:
            raise ActionError("Cannot act while traveling")
        return account.city

    def _space_for(self, actor: Actor | Company, item: str, quantity: int) -> bool:
        return not isinstance(actor, Actor) or sum(actor.inventory.values()) + quantity <= CARRY_LIMIT

    @staticmethod
    def _positive(value: int, name: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ActionError(f"{name} must be a positive integer")

    @staticmethod
    def _nonnegative(value: int, name: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ActionError(f"{name} must be a nonnegative integer")

    @staticmethod
    def _add(account: Actor | Company, item: str, quantity: int) -> None:
        account.inventory[item] = account.inventory.get(item, 0) + quantity

    def travel_minutes(self, origin: str, destination: str) -> int:
        if origin not in CITIES or destination not in CITIES:
            raise ActionError("Unknown city")
        if origin == destination:
            return 0
        edges: dict[str, list[tuple[str, int]]] = {city: [] for city in CITIES}
        for (a, b), time in ROADS.items():
            edges[a].append((b, time))
            edges[b].append((a, time))
        frontier = [(0, origin)]
        best = {origin: 0}
        while frontier:
            time, city = heapq.heappop(frontier)
            if city == destination:
                return time
            if time != best[city]:
                continue
            for neighbor, minutes in edges[city]:
                alt = time + minutes
                if alt < best.get(neighbor, float("inf")):
                    best[neighbor] = alt
                    heapq.heappush(frontier, (alt, neighbor))
        raise ActionError("No road to destination")

    def start_travel(self, actor_id: str, destination: str) -> int:
        actor = self._actor(actor_id)
        city = self._at_city(actor)
        time = self.travel_minutes(city, destination)
        if time == 0:
            raise ActionError("Already in destination")
        actor.destination = destination
        actor.arrival_minute = self.minute + time
        self._emit("travel_started", actor.id, city, destination, actor.arrival_minute)
        return time

    def advance(self, minutes: int) -> None:
        self._nonnegative(minutes, "minutes")
        end = self.minute + minutes
        # Refill each hourly boundary; record arrivals at their actual times.
        arrivals = sorted(
            (a.arrival_minute, a.id)
            for a in self.actors.values() if a.arrival_minute is not None and a.arrival_minute <= end
        )
        boundaries = set(range((self.minute // HOUR + 1) * HOUR, end + 1, HOUR))
        boundaries.update(time for time, _ in arrivals)
        for moment in sorted(boundaries):
            self.minute = moment
            if moment % HOUR == 0:
                for city, spec in CITIES.items():
                    for item, rate in spec.deposits.items():
                        self.deposits[city][item] = min(DEPOSIT_CAP, self.deposits[city][item] + rate)
            for arrival, actor_id in arrivals:
                if arrival == moment:
                    a = self.actors[actor_id]
                    a.city = a.destination  # type: ignore[assignment]
                    a.destination = None
                    a.arrival_minute = None
                    self._emit("arrived", actor_id, a.city)
        self.minute = end
        self.assert_invariants()

    def gather(self, actor_id: str, item: str, quantity: int = 1) -> None:
        actor = self._actor(actor_id)
        city = self._at_city(actor)
        self._positive(quantity, "quantity")
        if quantity > HARVEST_LIMIT or item not in self.deposits[city]:
            raise ActionError("Resource cannot be gathered here at that rate")
        if self.minute < actor.ready_minute:
            raise ActionError("Worker cooldown active")
        if self.deposits[city][item] < quantity or not self._space_for(actor, item, quantity):
            raise ActionError("Insufficient local stock or carrying capacity")
        self.deposits[city][item] -= quantity
        self._add(actor, item, quantity)
        actor.ready_minute = self.minute + HOUR
        self._emit("gathered", actor_id, city, item, quantity)
        self.assert_invariants()

    def found_company(self, owner_id: str, company_id: str, industry: str, investment: int) -> None:
        owner = self._actor(owner_id)
        if self._at_city(owner) != CAPITAL:
            raise ActionError("Founding a company requires being in the capital")
        self._positive(investment, "investment")
        if industry not in RECIPES or not company_id or company_id in self.companies or company_id in self.actors:
            raise ActionError("Invalid company type or ID")
        if owner.gold < investment:
            raise ActionError("Insufficient gold to invest")
        owner.gold -= investment
        self.companies[company_id] = Company(company_id, owner_id, industry, gold=investment)
        self._emit("company_founded", owner_id, company_id, industry, investment)
        self.assert_invariants()

    def hire(self, owner_id: str, company_id: str, worker_id: str, wage: Wage) -> None:
        owner = self._actor(owner_id)
        worker = self._actor(worker_id)
        company = self.companies.get(company_id)
        if not company or company.owner_id != owner.id:
            raise ActionError("Only an owner can hire")
        self._nonnegative(wage.gold, "wage gold")
        self._nonnegative(wage.quantity, "wage item quantity")
        if wage.item is not None and wage.item not in GOODS:
            raise ActionError("Unknown wage item")
        if bool(wage.item) != bool(wage.quantity) or (wage.gold == 0 and wage.quantity == 0):
            raise ActionError("Choose gold, goods, or both as a positive wage")
        company.employees[worker.id] = wage
        self._emit("hired", company_id, worker_id, wage.gold, wage.item, wage.quantity)

    def shift(self, worker_id: str, company_id: str) -> None:
        worker = self._actor(worker_id)
        company = self.companies.get(company_id)
        if company is None or worker_id not in company.employees:
            raise ActionError("Worker not employed at company")
        if self._at_city(worker) != company.city or self.minute < worker.ready_minute:
            raise ActionError("Worker unavailable at company")
        recipe = RECIPES[company.industry]
        wage = company.employees[worker_id]
        for item, amount in recipe.inputs.items():
            if company.inventory.get(item, 0) < amount:
                raise ActionError(f"Company lacks {item}")
        if company.gold < wage.gold:
            raise ActionError("Company cannot pay wages")
        future = dict(company.inventory)
        for item, amount in recipe.inputs.items():
            future[item] -= amount
        for item, amount in recipe.outputs.items():
            future[item] = future.get(item, 0) + amount
        if wage.item and future.get(wage.item, 0) < wage.quantity:
            raise ActionError("Company cannot pay item wages")
        if wage.item and not self._space_for(worker, wage.item, wage.quantity):
            raise ActionError("Worker carrying capacity exceeded")
        company.inventory = future
        if wage.item:
            company.inventory[wage.item] -= wage.quantity
            self._add(worker, wage.item, wage.quantity)
        company.gold -= wage.gold
        worker.gold += wage.gold
        worker.ready_minute = self.minute + HOUR
        self._emit("shift_completed", company_id, worker_id, wage.gold, wage.item, wage.quantity)
        self.assert_invariants()

    def post_offer(self, initiator_id: str, seller_id: str, item: str, quantity: int, unit_price: int) -> int:
        seller = self._account(seller_id)
        self._authorize(initiator_id, seller)
        city = self._at_city(seller)
        self._positive(quantity, "quantity")
        self._nonnegative(unit_price, "unit_price")
        if item not in GOODS or seller.inventory.get(item, 0) < quantity:
            raise ActionError("Seller lacks offered resources")
        seller.inventory[item] -= quantity
        offer_id = self.next_offer_id
        self.next_offer_id += 1
        self.offers[offer_id] = Offer(offer_id, seller_id, city, item, quantity, unit_price)
        self._emit("offer_posted", offer_id, seller_id, city, item, quantity, unit_price)
        self.assert_invariants()
        return offer_id

    def accept_offer(self, initiator_id: str, buyer_id: str, offer_id: int, quantity: int) -> None:
        buyer = self._account(buyer_id)
        self._authorize(initiator_id, buyer)
        offer = self.offers.get(offer_id)
        if offer is None:
            raise ActionError("Unknown or exhausted offer")
        self._positive(quantity, "quantity")
        if buyer_id == offer.seller_id or self._at_city(buyer) != offer.city:
            raise ActionError("Cannot accept your own offer or trade remotely")
        if quantity > offer.quantity or not self._space_for(buyer, offer.item, quantity):
            raise ActionError("Insufficient stock or carrying capacity")
        total = quantity * offer.unit_price
        if buyer.gold < total:
            raise ActionError("Buyer lacks gold")
        seller = self._account(offer.seller_id)
        buyer.gold -= total
        seller.gold += total
        self._add(buyer, offer.item, quantity)
        offer.quantity -= quantity
        if offer.quantity == 0:
            del self.offers[offer_id]
        self._emit("offer_filled", offer_id, buyer_id, quantity, total)
        self.assert_invariants()

    def cancel_offer(self, initiator_id: str, offer_id: int) -> None:
        offer = self.offers.get(offer_id)
        if offer is None:
            raise ActionError("Unknown offer")
        seller = self._account(offer.seller_id)
        self._authorize(initiator_id, seller)
        if self._at_city(seller) != offer.city:
            raise ActionError("Return to listing city to withdraw escrowed goods")
        if not self._space_for(seller, offer.item, offer.quantity):
            raise ActionError("Not enough space to reclaim goods")
        self._add(seller, offer.item, offer.quantity)
        del self.offers[offer_id]
        self._emit("offer_canceled", offer_id)
        self.assert_invariants()

    def assert_invariants(self) -> None:
        if self.total_gold != self.initial_gold:
            raise AssertionError("Gold was created or destroyed")
        ids = list(self.actors) + list(self.companies)
        if len(set(ids)) != len(ids):
            raise AssertionError("Duplicate account IDs")
        for account in list(self.actors.values()) + list(self.companies.values()):
            if account.gold < 0 or any(k not in GOODS or v < 0 for k, v in account.inventory.items()):
                raise AssertionError("Negative or invalid asset")
            if isinstance(account, Actor):
                if sum(account.inventory.values()) > CARRY_LIMIT:
                    raise AssertionError("Carrying limit exceeded")
                if (account.destination is None) != (account.arrival_minute is None):
                    raise AssertionError("Inconsistent travel")
        for city, stock in self.deposits.items():
            if city not in CITIES or any(quantity < 0 or quantity > DEPOSIT_CAP for quantity in stock.values()):
                raise AssertionError("Invalid regional deposits")
        if any(o.quantity <= 0 or o.item not in GOODS for o in self.offers.values()):
            raise AssertionError("Invalid market escrow")
