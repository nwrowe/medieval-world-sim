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
from .transactions import atomic_action
from .events import event_payload
from threading import RLock

HOUR = 60
CARRY_LIMIT = 20
HARVEST_LIMIT = 2
DEPOSIT_CAP = 24


from ..systems.travel import TravelSystem
from ..systems.resources import ResourceSystem
from ..systems.companies import CompanySystem
from ..systems.market import MarketSystem
from ..systems.combat import CombatSystem, CombatOutcome
from ..systems.consumables import ConsumableSystem
from ..systems.city_demand import CityDemandSystem
from ..systems.regional_trade import RegionalTradeSystem, RegionalQuote, MERCHANT_STOCK_CAP, MERCHANT_DAILY_LIMIT
from .quality import CompanyQuality

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
        self._current_action_id: str | None = None
        self._action_lock = RLock()
        self.travel = TravelSystem(self)
        self.resources = ResourceSystem(self)
        self.companies_system = CompanySystem(self)
        self.market = MarketSystem(self)
        self.combat = CombatSystem(self)
        self.consumables = ConsumableSystem(self)
        self.city_demand = CityDemandSystem(self)
        self.regional_trade = RegionalTradeSystem(self)

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
        return (self.crown_gold + sum(a.gold for a in self.actors.values())
                + sum(c.gold for c in self.companies.values())
                + sum(city.household_gold for city in self.cities.values()))

    def _emit(self, kind: str, *details: object) -> None:
        self.events.append(WorldEvent(
            self.minute, kind, tuple(details), len(self.events) + 1,
            self._current_action_id, 1, event_payload(kind, tuple(details))
        ))

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

    @atomic_action
    def start_travel(self, actor_id: str, destination: str) -> int:
        return self.travel.start_travel(actor_id, destination)

    @atomic_action
    def advance(self, minutes: int) -> None:
        return self.travel.advance(minutes)

    @atomic_action
    def gather(self, actor_id: str, item: str, quantity: int = 1) -> None:
        return self.resources.gather(actor_id, item, quantity)

    @atomic_action
    def found_company(self, owner_id: str, company_id: str, industry: str, investment: int) -> None:
        return self.companies_system.found_company(owner_id, company_id, industry, investment)

    @atomic_action
    def hire(self, owner_id: str, company_id: str, worker_id: str, wage: Wage) -> None:
        return self.companies_system.hire(owner_id, company_id, worker_id, wage)

    @atomic_action
    def propose_job(self, owner_id: str, company_id: str, worker_id: str, wage: Wage) -> None:
        return self.companies_system.propose_job(owner_id, company_id, worker_id, wage)

    @atomic_action
    def accept_job(self, worker_id: str, company_id: str) -> None:
        return self.companies_system.accept_job(worker_id, company_id)

    @atomic_action
    def set_wage(self, owner_id: str, company_id: str, worker_id: str, wage: Wage) -> None:
        return self.companies_system.set_wage(owner_id, company_id, worker_id, wage)

    @atomic_action
    def leave_job(self, worker_id: str, company_id: str) -> None:
        return self.companies_system.leave_job(worker_id, company_id)

    @atomic_action
    def set_perks(self, owner_id: str, company_id: str, perks: tuple[str, ...]) -> None:
        return self.companies_system.set_perks(owner_id, company_id, perks)

    @atomic_action
    def upgrade_facility(self, owner_id: str, company_id: str) -> int:
        return self.companies_system.upgrade_facility(owner_id, company_id)

    def company_quality(self, company_id: str) -> CompanyQuality:
        return self.companies_system.quality(company_id)

    def suggested_wage(self, worker_id: str, company_id: str) -> int:
        return self.companies_system.suggested_wage(worker_id, company_id)

    @atomic_action
    def shift(self, worker_id: str, company_id: str) -> None:
        return self.companies_system.shift(worker_id, company_id)

    @atomic_action
    def post_offer(self, initiator_id: str, seller_id: str, item: str, quantity: int, unit_price: int) -> int:
        return self.market.post_offer(initiator_id, seller_id, item, quantity, unit_price)

    @atomic_action
    def post_equipment_offer(self, initiator_id: str, seller_id: str, gear_id: int, unit_price: int) -> int:
        return self.market.post_equipment_offer(initiator_id, seller_id, gear_id, unit_price)

    @atomic_action
    def accept_offer(self, initiator_id: str, buyer_id: str, offer_id: int, quantity: int) -> None:
        return self.market.accept_offer(initiator_id, buyer_id, offer_id, quantity)

    @atomic_action
    def cancel_offer(self, initiator_id: str, offer_id: int) -> None:
        return self.market.cancel_offer(initiator_id, offer_id)

    def regional_quote(self, city_id: str, item: str) -> RegionalQuote:
        return self.regional_trade.quote(city_id, item)

    @atomic_action
    def regional_buy(self, actor_id: str, item: str, quantity: int) -> int:
        """Pay a city merchant and receive goods; return gold paid."""
        return self.regional_trade.buy(actor_id, item, quantity)

    @atomic_action
    def regional_sell(self, actor_id: str, item: str, quantity: int) -> int:
        """Sell carried resources to a city; return gold earned."""
        return self.regional_trade.sell(actor_id, item, quantity)

    @atomic_action
    def buy_starter_gear(self, actor_id: str, kind: str) -> int:
        return self.combat.buy_starter_gear(actor_id, kind)

    @atomic_action
    def equip(self, actor_id: str, gear_id: int) -> None:
        return self.combat.equip(actor_id, gear_id)

    @atomic_action
    def unequip(self, actor_id: str, slot: str) -> None:
        return self.combat.unequip(actor_id, slot)

    @atomic_action
    def attack(self, attacker_id: str, defender_id: str) -> CombatOutcome:
        return self.combat.attack(attacker_id, defender_id)

    @atomic_action
    def consume(self, actor_id: str, item: str) -> tuple[int, int, int]:
        return self.consumables.consume(actor_id, item)

    def execute(self, principal_id: str, action: str, params: dict, action_id: str):
        """Trusted-adapter command entrypoint with caller-bound identity and retry safety.

        A production API must derive principal_id from authentication, never from
        an untrusted body field. Command receipts are currently in-memory only.
        """
        with self._action_lock:
            if not isinstance(action_id, str) or not action_id:
                raise ActionError("Nonempty action ID required")
            if not isinstance(params, dict):
                raise ActionError("Command parameters must be a mapping")
            self._actor(principal_id)
            command_specs = {
                "travel": ("start_travel", ("destination",)),
                "gather": ("gather", ("item", "quantity")),
                "regional_buy": ("regional_buy", ("item", "quantity")),
                "regional_sell": ("regional_sell", ("item", "quantity")),
                "found_company": ("found_company", ("company_id", "industry", "investment")),
                "shift": ("shift", ("company_id",)),
                "post_offer": ("post_offer", ("seller_id", "item", "quantity", "unit_price")),
                "post_equipment_offer": ("post_equipment_offer", ("seller_id", "gear_id", "unit_price")),
                "accept_offer": ("accept_offer", ("buyer_id", "offer_id", "quantity")),
                "cancel_offer": ("cancel_offer", ("offer_id",)),
                "buy_starter_gear": ("buy_starter_gear", ("kind",)),
                "equip": ("equip", ("gear_id",)),
                "unequip": ("unequip", ("slot",)),
                "attack": ("attack", ("defender_id",)),
                "consume": ("consume", ("item",)),
                "propose_job": ("propose_job", ("company_id", "worker_id", "wage")),
                "accept_job": ("accept_job", ("company_id",)),
                "leave_job": ("leave_job", ("company_id",)),
                "set_wage": ("set_wage", ("company_id", "worker_id", "wage")),
                "set_perks": ("set_perks", ("company_id", "perks")),
                "upgrade_facility": ("upgrade_facility", ("company_id",)),
            }
            if action not in command_specs:
                raise ActionError("Unknown or forbidden command")
            method_name, fields = command_specs[action]
            if set(params) != set(fields):
                raise ActionError("Command parameter mismatch")
            signature = (principal_id, action, tuple((field, repr(params[field])) for field in fields))
            existing = self.state.command_receipts.get(action_id)
            if existing is not None:
                if existing[0] != signature:
                    raise ActionError("Action ID reused for a different command")
                return existing[1]
            previous_id = self._current_action_id
            self._current_action_id = action_id
            try:
                result = getattr(self, method_name)(principal_id, *(params[field] for field in fields))
                self.state.command_receipts[action_id] = (signature, result)
                return result
            finally:
                self._current_action_id = previous_id

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
                        0 <= account.vitals.hunger <= 3 and
                        account.work.manual >= 0 and account.work.intelligence >= 0 and
                        account.work.endurance >= 0 and account.work.shifts >= 0 and
                        all(isinstance(v, int) and 0 <= v <= 100
                            for v in account.work.experience.values()) and
                        account.max_hp == 24 + 4 * (account.level - 1) and
                        account.max_stamina == MAX_STAMINA and
                        account.strength == account.level and account.defense == account.level and
                        account.level_xp >= 0 and account.combat_xp >= 0):
                    raise AssertionError("Invalid combat state")
                for slot, gear_id in account.equipped.items():
                    if gear_id not in account.gear_ids or GEAR[self.gear[gear_id].kind].slot != slot:
                        raise AssertionError("Equipped item is not owned or is in wrong slot")
        for company in self.companies.values():
            if not 1 <= company.facility_level <= 5 or company.shifts_completed < 0:
                raise AssertionError("Invalid company quality state")
        for city in self.cities.values():
            if city.household_gold < 0 or city.population < 0:
                raise AssertionError("Invalid city household budget")
            if any(item not in GOODS or qty < 0 or qty > MERCHANT_STOCK_CAP
                   or not isinstance(qty, int) for item, qty in city.merchant_stock.items()):
                raise AssertionError("Invalid merchant stock")
            if not (0 <= city.merchant_purchases_today <= MERCHANT_DAILY_LIMIT and
                    0 <= city.merchant_sales_today <= MERCHANT_DAILY_LIMIT):
                raise AssertionError("Invalid daily merchant trading volume")
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
