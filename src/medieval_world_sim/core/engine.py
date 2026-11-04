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
from .entities import Actor, Company, Offer, Wage, WorldEvent, MagicState, HousingState
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
from ..systems.duels import DuelSystem
from ..systems.spells import SpellSystem
from ..systems.track import TrackSystem
from ..systems.guilds import GuildSystem, ROLES, MAX_GUILD_MEMBERS
from ..systems.merits import MeritSystem, ACHIEVEMENTS, MERIT_UPGRADES
from ..systems.curriculum import CurriculumSystem, SCHOOLS
from ..systems.consumables import ConsumableSystem
from ..systems.city_demand import CityDemandSystem
from ..systems.regional_trade import RegionalTradeSystem, RegionalQuote, MERCHANT_STOCK_CAP, MERCHANT_DAILY_LIMIT
from ..systems.magic import MagicSystem, MagicNodeStatus, MagicPracticeResult
from ..systems.housing import HousingSystem, HousingView
from ..systems.contracts import CityContractSystem, CityContractResult
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
            if a.magic != MagicState():
                raise ValueError("Actors must start with baseline magic attributes")
            if a.housing != HousingState():
                raise ValueError("Housing assets must be purchased through the world")
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
        self.duel_system = DuelSystem(self)
        self.spell_system = SpellSystem(self)
        self.track_system = TrackSystem(self)
        self.guild_system = GuildSystem(self)
        self.merit_system = MeritSystem(self)
        self.curriculum_system = CurriculumSystem(self)
        self.consumables = ConsumableSystem(self)
        self.city_demand = CityDemandSystem(self)
        self.regional_trade = RegionalTradeSystem(self)
        self.magic_system = MagicSystem(self)
        self.housing_system = HousingSystem(self)
        self.city_contracts = CityContractSystem(self)

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
        # City inventories are unbounded; road departures enforce the vehicle
        # cargo limit instead. Preserve the signature for existing callers.
        return True

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
    def store_goods(self, actor_id: str, item: str, quantity: int) -> None:
        actor = self._actor(actor_id)
        city = self._at_city(actor)
        self._positive(quantity, "quantity")
        if item not in GOODS or actor.inventory.get(item, 0) < quantity:
            raise ActionError("Not enough valid goods to store")
        actor.inventory[item] -= quantity
        stash = actor.storage.setdefault(city, {})
        stash[item] = stash.get(item, 0) + quantity
        self._emit("goods_stored", actor_id, city, item, quantity)

    @atomic_action
    def retrieve_goods(self, actor_id: str, item: str, quantity: int) -> None:
        actor = self._actor(actor_id)
        city = self._at_city(actor)
        self._positive(quantity, "quantity")
        stash = actor.storage.get(city, {})
        if item not in GOODS or stash.get(item, 0) < quantity:
            raise ActionError("Not enough goods stored in this city")
        stash[item] -= quantity
        self._add(actor, item, quantity)
        self._emit("goods_retrieved", actor_id, city, item, quantity)

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

    def magic_tree(self, actor_id: str, school: str | None = None) -> tuple[MagicNodeStatus, ...]:
        """UI-friendly, immutable progression tree including lock/attunement flags."""
        return self.magic_system.tree(actor_id, school)

    @atomic_action
    def unlock_magic(self, actor_id: str, node_id: str) -> None:
        return self.magic_system.unlock(actor_id, node_id)

    @atomic_action
    def attune_magic(self, actor_id: str, paths: tuple[str, ...]) -> None:
        return self.magic_system.attune(actor_id, paths)

    @atomic_action
    def practice_magic(self, actor_id: str, node_id: str) -> MagicPracticeResult:
        """Spend mana and learn a node; paid work/spell effects come later."""
        return self.magic_system.practice(actor_id, node_id)

    def housing_view(self, actor_id: str) -> HousingView:
        return self.housing_system.view(actor_id)

    def estimated_travel_minutes(self, actor_id: str, destination: str) -> int:
        actor = self._actor(actor_id)
        self._at_city(actor)
        base = self.travel_minutes(actor.city, destination)
        if not base:
            return 0
        minutes = self.housing_system.road_minutes(actor, base)
        if "roadcraft" in self.state.merit_upgrades.get(actor_id, set()):
            minutes = max(1, (minutes * 95 + 99) // 100)
        if actor.magic.road_charm:
            minutes = max(1, (minutes * (100 - actor.magic.road_charm) + 99) // 100)
        return minutes

    @atomic_action
    def buy_home(self, actor_id: str, tier: str) -> int:
        return self.housing_system.buy_home(actor_id, tier)

    @atomic_action
    def upgrade_home(self, actor_id: str, tier: str) -> int:
        return self.housing_system.upgrade_home(actor_id, tier)

    @atomic_action
    def build_home_facility(self, actor_id: str, facility: str) -> int:
        return self.housing_system.build_facility(actor_id, facility)

    @atomic_action
    def buy_vehicle(self, actor_id: str, vehicle: str) -> int:
        return self.housing_system.buy_vehicle(actor_id, vehicle)

    @atomic_action
    def select_vehicle(self, actor_id: str, vehicle: str | None) -> None:
        return self.housing_system.select_vehicle(actor_id, vehicle)

    @atomic_action
    def complete_city_contract(self, actor_id: str, contract_id: str) -> CityContractResult:
        return self.city_contracts.complete(actor_id, contract_id)

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
    def start_duel(self, attacker_id: str, defender_id: str) -> dict:
        return self.duel_system.start(attacker_id, defender_id)

    @atomic_action
    def duel_turn(self, attacker_id: str, move: str, node_id: str) -> dict:
        return self.duel_system.turn(attacker_id, move, node_id)

    @atomic_action
    def flee_duel(self, attacker_id: str) -> dict:
        return self.duel_system.flee(attacker_id)

    @atomic_action
    def cast_spell(self, actor_id: str, node_id: str) -> dict:
        return self.spell_system.field_cast(actor_id, node_id)

    @atomic_action
    def church_heal(self, actor_id: str) -> int:
        actor = self._actor(actor_id)
        self._at_city(actor)
        if actor.hp >= actor.max_hp:
            raise ActionError("You are already at full health")
        today = self.minute // 1440
        if self.state.church_healed_day.get(actor_id) == today:
            raise ActionError("The church has already treated you today")
        price = 20
        if actor.gold < price:
            raise ActionError("Church healing costs 20 gold")
        from .transactions import transfer_gold
        transfer_gold(self, actor, None, price)
        healed = actor.max_hp - actor.hp
        actor.hp = actor.max_hp
        self.state.church_healed_day[actor_id] = today
        self._emit("church_healed", actor_id, price, healed)
        return healed

    @atomic_action
    def buy_racehorse(self, actor_id: str, breed: str) -> dict:
        return self.track_system.buy(actor_id, breed)

    @atomic_action
    def race_horse(self, actor_id: str, breed: str) -> dict:
        return self.track_system.race(actor_id, breed)

    @atomic_action
    def found_guild(self, actor_id: str, name: str) -> dict:
        return self.guild_system.found(actor_id, name)

    @atomic_action
    def invite_guild(self, actor_id: str, candidate_id: str) -> None:
        return self.guild_system.invite(actor_id, candidate_id)

    @atomic_action
    def join_guild(self, actor_id: str, guild_id: str) -> None:
        return self.guild_system.join(actor_id, guild_id)

    @atomic_action
    def set_guild_role(self, actor_id: str, member_id: str, role: str) -> None:
        return self.guild_system.set_role(actor_id, member_id, role)

    @atomic_action
    def leave_guild(self, actor_id: str) -> None:
        return self.guild_system.leave(actor_id)

    @atomic_action
    def enroll_course(self, actor_id: str, school: str) -> dict:
        return self.curriculum_system.start(actor_id, school)

    @atomic_action
    def claim_merit(self, actor_id: str, achievement: str) -> dict:
        return self.merit_system.claim(actor_id, achievement)

    @atomic_action
    def buy_merit_upgrade(self, actor_id: str, perk: str) -> dict:
        return self.merit_system.purchase(actor_id, perk)

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
                "store_goods": ("store_goods", ("item", "quantity")),
                "retrieve_goods": ("retrieve_goods", ("item", "quantity")),
                "regional_buy": ("regional_buy", ("item", "quantity")),
                "regional_sell": ("regional_sell", ("item", "quantity")),
                "unlock_magic": ("unlock_magic", ("node_id",)),
                "attune_magic": ("attune_magic", ("paths",)),
                "practice_magic": ("practice_magic", ("node_id",)),
                "buy_home": ("buy_home", ("tier",)),
                "upgrade_home": ("upgrade_home", ("tier",)),
                "build_home_facility": ("build_home_facility", ("facility",)),
                "buy_vehicle": ("buy_vehicle", ("vehicle",)),
                "select_vehicle": ("select_vehicle", ("vehicle",)),
                "found_company": ("found_company", ("company_id", "industry", "investment")),
                "shift": ("shift", ("company_id",)),
                "post_offer": ("post_offer", ("seller_id", "item", "quantity", "unit_price")),
                "post_equipment_offer": ("post_equipment_offer", ("seller_id", "gear_id", "unit_price")),
                "accept_offer": ("accept_offer", ("buyer_id", "offer_id", "quantity")),
                "cancel_offer": ("cancel_offer", ("offer_id",)),
                "complete_city_contract": ("complete_city_contract", ("contract_id",)),
                "buy_starter_gear": ("buy_starter_gear", ("kind",)),
                "equip": ("equip", ("gear_id",)),
                "unequip": ("unequip", ("slot",)),
                "attack": ("attack", ("defender_id",)),
                "start_duel": ("start_duel", ("defender_id",)),
                "duel_turn": ("duel_turn", ("move", "node_id")),
                "flee_duel": ("flee_duel", ()),
                "cast_spell": ("cast_spell", ("node_id",)),
                "church_heal": ("church_heal", ()),
                "buy_racehorse": ("buy_racehorse", ("breed",)),
                "race_horse": ("race_horse", ("breed",)),
                "found_guild": ("found_guild", ("name",)),
                "invite_guild": ("invite_guild", ("candidate_id",)),
                "join_guild": ("join_guild", ("guild_id",)),
                "set_guild_role": ("set_guild_role", ("member_id", "role")),
                "leave_guild": ("leave_guild", ()),
                "claim_merit": ("claim_merit", ("achievement",)),
                "enroll_course": ("enroll_course", ("school",)),
                "buy_merit_upgrade": ("buy_merit_upgrade", ("perk",)),
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
            # Duplicate requests must return their receipt even after a duel begins.
            if (principal_id in self.state.duels
                    and action not in ("duel_turn", "flee_duel")):
                raise ActionError("Finish your current duel first")
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
                if any(type(getattr(account.cooldowns, channel)) is not int
                       or getattr(account.cooldowns, channel) < 0
                       or max(0, getattr(account.cooldowns, channel) - self.minute) > 1440
                       for channel in ("job", "food", "potion")):
                    raise AssertionError("Cooldown exceeds 24-hour limit")
                if any(city not in CITIES or not isinstance(goods, dict)
                       or any(item not in GOODS or type(qty) is not int or qty < 0
                              for item, qty in goods.items())
                       for city, goods in account.storage.items()):
                    raise AssertionError("Invalid personal city storage")
                self.magic_system.assert_valid(account, self.minute)
                self.housing_system.assert_valid(account)
                if account.destination is not None:
                    load = sum(account.inventory.values()) + len(account.gear_ids)
                    if load > self.housing_system.travel_cargo_limit(account):
                        raise AssertionError("Traveling actor over cargo limit")
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
        membership = []
        if type(self.state.next_guild_id) is not int or self.state.next_guild_id < 1:
            raise AssertionError("Invalid guild sequence")
        for guild_id, guild in self.state.guilds.items():
            if (guild_id != guild.id or guild.founder_id not in self.actors
                    or not 1 <= len(guild.members) <= MAX_GUILD_MEMBERS
                    or len(guild.name) < 3 or len(guild.name) > 40
                    or sum(role == "leader" for role in guild.members.values()) != 1
                    or any(actor_id not in self.actors or role not in ROLES
                           for actor_id, role in guild.members.items())
                    or any(invitee not in self.actors for invitee in guild.invited)
                    or any(invitee in guild.members for invitee in guild.invited)
                    or guild.rating < 0 or guild.wins < 0 or guild.losses < 0):
                raise AssertionError("Invalid guild state")
            membership.extend(guild.members)
        if len(membership) != len(set(membership)):
            raise AssertionError("Character has multiple guilds")
        for actor_id, claimed in self.state.merit_claims.items():
            if (actor_id not in self.actors or not claimed <= ACHIEVEMENTS.keys()
                    or type(self.state.merit_balance.get(actor_id, 0)) is not int
                    or self.state.merit_balance.get(actor_id, 0) < 0):
                raise AssertionError("Invalid merit claims")
            bought = self.state.merit_upgrades.get(actor_id, set())
            if not bought <= MERIT_UPGRADES.keys():
                raise AssertionError("Unknown merit perk")
            issued = sum(ACHIEVEMENTS[k].award for k in claimed)
            spent = sum(MERIT_UPGRADES[k]["cost"] for k in bought)
            if issued - spent != self.state.merit_balance.get(actor_id, 0):
                raise AssertionError("Merit conservation mismatch")
        for actor_id, courses in self.state.completed_courses.items():
            if actor_id not in self.actors or any(
                    school not in SCHOOLS or type(count) is not int or not 0 <= count <= 8
                    for school, count in courses.items()):
                raise AssertionError("Invalid completed curriculum")
        for actor_id, course in self.state.active_courses.items():
            if (actor_id not in self.actors or course.school not in SCHOOLS
                    or self.state.completed_courses.get(actor_id, {}).get(course.school, 0) != course.index
                    or not 0 <= course.index < 8 or course.ends_at <= self.minute):
                raise AssertionError("Invalid active curriculum")
        if any(gid not in self.gear or type(count) is not int or not 0 <= count < 12
               for gid, count in self.state.gear_wear.items()):
            raise AssertionError("Invalid equipment wear")
        participants = []
        for key, duel in self.state.duels.items():
            if (key != duel.attacker_id or duel.attacker_id == duel.defender_id
                    or duel.attacker_id not in self.actors or duel.defender_id not in self.actors
                    or duel.round < 0 or duel.xp_earned < 0 or duel.pending_ward < 0):
                raise AssertionError('Invalid active duel')
            attacker, defender = self.actors[duel.attacker_id], self.actors[duel.defender_id]
            if (attacker.city != defender.city or attacker.destination or defender.destination
                    or attacker.hp <= 0 or defender.hp <= 0):
                raise AssertionError('Invalid duel participants')
            participants.extend((duel.attacker_id, duel.defender_id))
        if len(participants) != len(set(participants)):
            raise AssertionError('Actor participating in multiple duels')
        from ..systems.track import HORSES
        for actor_id, breeds in self.state.horses.items():
            if (actor_id not in self.actors or not isinstance(breeds, list)
                    or len(breeds) != len(set(breeds))
                    or any(breed not in HORSES for breed in breeds)):
                raise AssertionError("Invalid horse ownership")
        for actor_id, xp in self.state.riding_xp.items():
            if actor_id not in self.actors or type(xp) is not int or xp < 0:
                raise AssertionError("Invalid riding experience")
        for actor_id, minute in self.state.last_race_minute.items():
            if actor_id not in self.actors or type(minute) is not int or not 0 <= minute <= self.minute:
                raise AssertionError("Invalid racing timestamp")
        for actor_id, day in self.state.church_healed_day.items():
            if actor_id not in self.actors or type(day) is not int or not 0 <= day <= self.minute // 1440:
                raise AssertionError("Invalid church healing day")
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
