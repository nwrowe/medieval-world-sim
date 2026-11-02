"""Five-city authoritative experiment independent of the original single-town baseline.

All human/NPC actions share one validation path. Listing goods escrows them at
the market, preventing double sale and remote-teleportation exploits.
No API or persistence layer is exposed yet.
"""
from __future__ import annotations


from ..catalog import CAPITAL, CITIES, GOODS
from ..errors import ActionError
from ..equipment import GEAR, GearItem
from ..combat import MAX_STAMINA
from .entities import Actor, Company, Offer, Wage, WorldEvent
from .cities import CityState
from .state import WorldState

HOUR = 60
CARRY_LIMIT = 20
HARVEST_LIMIT = 2
DEPOSIT_CAP = 24


from ..systems.travel import TravelSystem
from ..systems.resources import ResourceSystem
from ..systems.companies import CompanySystem
from ..systems.market import MarketSystem
from ..systems.combat import CombatSystem, CombatOutcome

class WorldEngine:
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
        self.travel = TravelSystem(self)
        self.resources = ResourceSystem(self)
        self.companies_system = CompanySystem(self)
        self.market = MarketSystem(self)
        self.combat = CombatSystem(self)

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
        return self.travel.travel_minutes(origin, destination)

    def start_travel(self, actor_id: str, destination: str) -> int:
        return self.travel.start_travel(actor_id, destination)

    def advance(self, minutes: int) -> None:
        return self.travel.advance(minutes)

    def gather(self, actor_id: str, item: str, quantity: int = 1) -> None:
        return self.resources.gather(actor_id, item, quantity)

    def found_company(self, owner_id: str, company_id: str, industry: str, investment: int) -> None:
        return self.companies_system.found_company(owner_id, company_id, industry, investment)

    def hire(self, owner_id: str, company_id: str, worker_id: str, wage: Wage) -> None:
        return self.companies_system.hire(owner_id, company_id, worker_id, wage)

    def shift(self, worker_id: str, company_id: str) -> None:
        return self.companies_system.shift(worker_id, company_id)

    def post_offer(self, initiator_id: str, seller_id: str, item: str, quantity: int, unit_price: int) -> int:
        return self.market.post_offer(initiator_id, seller_id, item, quantity, unit_price)

    def post_equipment_offer(self, initiator_id: str, seller_id: str, gear_id: int, unit_price: int) -> int:
        return self.market.post_equipment_offer(initiator_id, seller_id, gear_id, unit_price)

    def accept_offer(self, initiator_id: str, buyer_id: str, offer_id: int, quantity: int) -> None:
        return self.market.accept_offer(initiator_id, buyer_id, offer_id, quantity)

    def cancel_offer(self, initiator_id: str, offer_id: int) -> None:
        return self.market.cancel_offer(initiator_id, offer_id)

    def buy_starter_gear(self, actor_id: str, kind: str) -> int:
        return self.combat.buy_starter_gear(actor_id, kind)

    def equip(self, actor_id: str, gear_id: int) -> None:
        return self.combat.equip(actor_id, gear_id)

    def unequip(self, actor_id: str, slot: str) -> None:
        return self.combat.unequip(actor_id, slot)

    def attack(self, attacker_id: str, defender_id: str) -> CombatOutcome:
        return self.combat.attack(attacker_id, defender_id)

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
