"""Five-city authoritative experiment independent of the original single-town baseline.

All human/NPC actions share one validation path. Listing goods escrows them at
the market, preventing double sale and remote-teleportation exploits.
No API or persistence layer is exposed yet.
"""
from __future__ import annotations

import heapq

from .catalog import CAPITAL, CITIES, ROADS, GOODS, RECIPES
from .errors import ActionError
from .equipment import GEAR, GearItem, crafted_quality
from .combat import CombatMixin, MAX_STAMINA, STAMINA_REGEN_MINUTES
from .core.entities import Actor, Company, Offer, Wage, WorldEvent
from .core.cities import CityState
from .core.state import WorldState

HOUR = 60
CARRY_LIMIT = 20
HARVEST_LIMIT = 2
DEPOSIT_CAP = 24


class RegionalWorld(CombatMixin):
    """In-memory simulation. Domain actions validate then mutate atomically."""

    def __init__(self, actors: list[Actor], seed: int = 42):
        if not actors or len({a.id for a in actors}) != len(actors):
            raise ValueError("Actor IDs must be unique and world nonempty")
        for a in actors:
            if a.kind not in ("human", "npc") or a.city not in CITIES:
                raise ValueError("Invalid actor kind/city")
            if a.gold < 0 or any(k not in GOODS or not isinstance(v, int) or v < 0 for k, v in a.inventory.items()):
                raise ValueError("Invalid starting assets")
            if not a.id:
                raise ValueError("Empty actor ID")
            if a.destination is not None or a.arrival_minute is not None or a.gear_ids or a.equipped:
                raise ValueError("Actors must start stationary without externally minted equipment")
            if (a.hp != 24 or a.max_hp != 24 or a.stamina != MAX_STAMINA or
                a.max_stamina != MAX_STAMINA or a.level != 1 or a.level_xp != 0 or
                a.combat_xp != 0 or a.strength != 1 or a.defense != 1 or
                a.defeated_until is not None):
                raise ValueError("Actors must start with baseline combat attributes")
        self.state = WorldState(
            actors={a.id: a for a in actors},
            cities={city_id: CityState.create(city_id, definition)
                    for city_id, definition in CITIES.items()},
            seed=seed,
        )
        self.state.initial_gold = self.total_gold

    @property
    def actors(self) -> dict[str, Actor]:
        return self.state.actors

    @property
    def companies(self) -> dict[str, Company]:
        return self.state.companies

    @property
    def offers(self) -> dict[int, Offer]:
        return self.state.offers

    @property
    def gear(self) -> dict[int, GearItem]:
        return self.state.gear

    @property
    def cities(self) -> dict[str, CityState]:
        return self.state.cities

    @property
    def events(self) -> list[WorldEvent]:
        return self.state.events

    @property
    def minute(self) -> int:
        return self.state.minute

    @minute.setter
    def minute(self, value: int) -> None:
        self.state.minute = value

    @property
    def seed(self) -> int:
        return self.state.seed

    @property
    def next_offer_id(self) -> int:
        return self.state.next_offer_id

    @next_offer_id.setter
    def next_offer_id(self, value: int) -> None:
        self.state.next_offer_id = value

    @property
    def next_gear_id(self) -> int:
        return self.state.next_gear_id

    @next_gear_id.setter
    def next_gear_id(self, value: int) -> None:
        self.state.next_gear_id = value

    @property
    def crown_gold(self) -> int:
        return self.state.crown_gold

    @crown_gold.setter
    def crown_gold(self, value: int) -> None:
        self.state.crown_gold = value

    @property
    def initial_gold(self) -> int:
        return self.state.initial_gold

    @initial_gold.setter
    def initial_gold(self, value: int) -> None:
        self.state.initial_gold = value

    @property
    def deposits(self) -> dict[str, dict[str, int]]:
        """Compatibility view; authoritative stocks live on CityState."""
        return {city_id: city.deposits for city_id, city in self.cities.items()}

    @property
    def total_gold(self) -> int:
        return self.crown_gold + sum(a.gold for a in self.actors.values()) + sum(c.gold for c in self.companies.values())

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
        if isinstance(account, Actor):
            if account.destination is not None:
                raise ActionError("Cannot act while traveling")
            if account.hp <= 0:
                raise ActionError("Cannot act while recovering from defeat")
        return account.city

    def _space_for(self, actor: Actor | Company, item: str, quantity: int) -> bool:
        return not isinstance(actor, Actor) or (
            sum(actor.inventory.values()) + len(actor.gear_ids) + quantity <= CARRY_LIMIT
        )

    def _mint_gear(self, holder: Actor | Company, kind: str, quality: int, origin: str) -> GearItem:
        """Only called after authorized crafting or a paid capital starter purchase."""
        spec = GEAR[kind]
        maximum = spec.max_durability if origin == "crafted" else max(5, spec.max_durability // 2)
        item = GearItem(self.next_gear_id, kind, quality, maximum, maximum, origin)
        self.next_gear_id += 1
        self.gear[item.id] = item
        holder.gear_ids.append(item.id)
        self._emit("gear_created", holder.id, item.id, kind, quality, origin)
        return item

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
        start_minute = self.minute
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
        # Regeneration is computed from elapsed discrete world-minute boundaries
        # and is independent of whether time is advanced in one or many steps.
        regen_ticks = end // STAMINA_REGEN_MINUTES - start_minute // STAMINA_REGEN_MINUTES
        self.minute = end
        for actor in self.actors.values():
            actor.stamina = min(actor.max_stamina, actor.stamina + regen_ticks)
            if actor.defeated_until is not None and actor.defeated_until <= end:
                actor.hp = actor.max_hp
                actor.defeated_until = None
                self._emit("recovered", actor.id)
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
        if wage.item is not None and wage.item not in GOODS and wage.item not in GEAR:
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

        # Preview the transaction before any state is changed.
        future = dict(company.inventory)
        for item, amount in recipe.inputs.items():
            future[item] -= amount
        produced_gear: list[str] = []
        for item, amount in recipe.outputs.items():
            if item in GEAR:
                produced_gear.extend([item] * amount)
            else:
                future[item] = future.get(item, 0) + amount
        if wage.item in GEAR:
            owned = sum(self.gear[g].kind == wage.item for g in company.gear_ids)
            available = owned + produced_gear.count(wage.item)
            if available < wage.quantity:
                raise ActionError("Company cannot pay equipment wage")
        elif wage.item and future.get(wage.item, 0) < wage.quantity:
            raise ActionError("Company cannot pay material wage")
        if wage.item and not self._space_for(worker, wage.item, wage.quantity):
            raise ActionError("Worker carrying capacity exceeded")

        company.inventory = future
        for kind in produced_gear:
            quality = crafted_quality(self.seed, worker_id, company_id, self.minute, self.next_gear_id)
            self._mint_gear(company, kind, quality, "crafted")
        if wage.item in GEAR:
            # Prefer lower-quality gear to avoid silently taking a masterwork as wages.
            available = sorted((g for g in company.gear_ids if self.gear[g].kind == wage.item),
                               key=lambda g: (self.gear[g].quality, g))
            for gear_id in available[:wage.quantity]:
                company.gear_ids.remove(gear_id)
                worker.gear_ids.append(gear_id)
        elif wage.item:
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

    def post_equipment_offer(self, initiator_id: str, seller_id: str, gear_id: int, unit_price: int) -> int:
        """A specific quality/durability-bearing item is escrowed by unique ID."""
        seller = self._account(seller_id)
        self._authorize(initiator_id, seller)
        city = self._at_city(seller)
        self._nonnegative(unit_price, "unit_price")
        if gear_id not in seller.gear_ids:
            raise ActionError("Seller does not own this equipment")
        seller.gear_ids.remove(gear_id)
        if isinstance(seller, Actor):
            for slot, equipped in list(seller.equipped.items()):
                if equipped == gear_id:
                    del seller.equipped[slot]
        item = self.gear[gear_id]
        offer_id = self.next_offer_id
        self.next_offer_id += 1
        self.offers[offer_id] = Offer(offer_id, seller_id, city, item.kind, 1, unit_price, gear_id)
        self._emit("equipment_offered", offer_id, seller_id, gear_id, item.quality, unit_price)
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
        if (quantity > offer.quantity or (offer.gear_id is not None and quantity != 1)
                or not self._space_for(buyer, offer.item, quantity)):
            raise ActionError("Insufficient stock or carrying capacity")
        total = quantity * offer.unit_price
        if buyer.gold < total:
            raise ActionError("Buyer lacks gold")
        seller = self._account(offer.seller_id)
        buyer.gold -= total
        seller.gold += total
        if offer.gear_id is not None:
            buyer.gear_ids.append(offer.gear_id)
        else:
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
        if offer.gear_id is not None:
            seller.gear_ids.append(offer.gear_id)
        else:
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
                if sum(account.inventory.values()) + len(account.gear_ids) > CARRY_LIMIT:
                    raise AssertionError("Carrying limit exceeded")
                if (account.destination is None) != (account.arrival_minute is None):
                    raise AssertionError("Inconsistent travel")
                if not (0 <= account.hp <= account.max_hp and
                        0 <= account.stamina <= account.max_stamina and
                        account.max_hp == 24 + 4 * (account.level - 1) and
                        account.max_stamina == MAX_STAMINA and
                        account.strength == account.level and account.defense == account.level and
                        account.level_xp >= 0 and account.combat_xp >= 0):
                    raise AssertionError("Invalid combat state")
                for slot, gear_id in account.equipped.items():
                    if gear_id not in account.gear_ids or GEAR[self.gear[gear_id].kind].slot != slot:
                        raise AssertionError("Equipped item is not owned or is in wrong slot")
        for city, stock in self.deposits.items():
            if city not in CITIES or any(quantity < 0 or quantity > DEPOSIT_CAP for quantity in stock.values()):
                raise AssertionError("Invalid regional deposits")
        holdings = [gear_id for a in self.actors.values() for gear_id in a.gear_ids]
        holdings += [gear_id for company in self.companies.values() for gear_id in company.gear_ids]
        for offer in self.offers.values():
            if offer.quantity <= 0:
                raise AssertionError("Invalid market escrow")
            if offer.gear_id is None:
                if offer.item not in GOODS:
                    raise AssertionError("Unknown offered resource")
            else:
                if offer.quantity != 1 or offer.item != self.gear[offer.gear_id].kind:
                    raise AssertionError("Invalid equipment offer")
                holdings.append(offer.gear_id)
        if len(holdings) != len(set(holdings)) or set(holdings) != set(self.gear):
            raise AssertionError("Equipment ownership / escrow mismatch")
        for gear_id, gear in self.gear.items():
            if gear.id != gear_id or not 1 <= gear.quality <= 100 or not 0 < gear.durability <= gear.max_durability:
                raise AssertionError("Corrupted equipment")
