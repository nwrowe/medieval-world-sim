"""Five-city authoritative experiment independent of the original single-town baseline.

All human/NPC actions share one validation path. Listing goods escrows them at
the market, preventing double sale and remote-teleportation exploits.
Game rules are shared by local single-player and multiplayer adapters.
"""
from __future__ import annotations


from ..catalog import CAPITAL, CITIES, GOODS, GEOGRAPHY
from ..worldgen.hexgrid import hex_distance
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
from ..systems.chat import ChatSystem, MAX_MESSAGES_SAVED, MAX_MESSAGE_LENGTH
from ..systems.trades import TradeSystem, TradeAssets
from ..systems.curriculum import CurriculumSystem, SCHOOLS, CURRENT_SCHOOLS
from ..systems.consumables import ConsumableSystem
from ..systems.city_demand import CityDemandSystem
from ..systems.regional_trade import RegionalTradeSystem, RegionalQuote, MERCHANT_STOCK_CAP, MERCHANT_DAILY_LIMIT
from ..systems.magic import MagicSystem, MagicNodeStatus, MagicPracticeResult
from ..systems.housing import HousingSystem, HousingView
from ..systems.contracts import CityContractSystem, CityContractResult
from .quality import CompanyQuality
from .invariants import validate_world
from .commands import COMMAND_SPECS
from .exploration import reveal, current_hex

from ..content.lineages import LINEAGES, select_lineage


class WorldEngine:
    """In-memory simulation. Domain actions validate then mutate atomically."""

    def __init__(self, actors: list[Actor], seed: int = 42, *, dev_travel_seconds: bool = False):
        self.dev_travel_seconds = dev_travel_seconds
        self.geography = GEOGRAPHY
        self.geography_settlements = {s.id: s for s in self.geography.settlements}
        if not actors or len({a.id for a in actors}) != len(actors):
            raise ValueError("Actor IDs must be unique and world nonempty")
        for a in actors:
            if a.kind not in ("human", "npc") or a.city not in CITIES:
                raise ValueError("Invalid actor kind/city")
            if a.gold < 0 or any(k not in GOODS or not isinstance(v, int) or v < 0 for k, v in a.inventory.items()):
                raise ValueError("Invalid starting assets")
            if not a.id:
                raise ValueError("Empty actor ID")
            if (a.lineage not in LINEAGES or type(a.lineage_selected) is not bool
                    or not isinstance(a.discovered_cities, set)
                    or not a.discovered_cities.issubset(CITIES.keys())):
                raise ValueError("Invalid lineage or discovered cities")
            a.discovered_cities.add(a.city)
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
        for actor in self.actors.values():
            if not actor.explored_hexes:
                point = self.geography_settlements[actor.city]
                reveal(self, actor, (point.x, point.y))
        self._current_action_id: str | None = None
        self._action_lock = RLock()
        self.travel = TravelSystem(self)
        self.resources = ResourceSystem(self)
        self.companies_system = CompanySystem(self)
        self.market = MarketSystem(self)
        self.trades_system = TradeSystem(self)
        self.combat = CombatSystem(self)
        self.duel_system = DuelSystem(self)
        self.spell_system = SpellSystem(self)
        self.track_system = TrackSystem(self)
        self.guild_system = GuildSystem(self)
        self.chat_system = ChatSystem(self)
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
                + sum(city.household_gold for city in self.cities.values())
                + sum(t.offer.gold for t in self.state.trades.values()))

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
            if account.wilderness_hex is not None:
                raise ActionError("Return to a settlement to use city services")
            if account.hp <= 0 or account.defeated_until is not None:
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
    def choose_lineage(self, actor_id: str, lineage: str) -> None:
        actor = self._actor(actor_id)
        self._at_city(actor)
        if any(actor_id in (duel.attacker_id, duel.defender_id)
               for duel in self.state.duels.values()):
            raise ActionError("Finish combat before selecting a lineage")
        select_lineage(actor, lineage)
        self._emit("lineage_chosen", actor_id, lineage)

    @atomic_action
    def explore_hex(self, actor_id: str, x: int, y: int) -> dict:
        """Travel by safe land to a visible hex or previously discovered site.

        City commerce and other settlement-only actions are disabled outside
        towns. Server-side ownership and replay rules apply to every step.
        """
        actor = self._actor(actor_id)
        if type(x) is not int or type(y) is not int:
            raise ActionError("Hex coordinates must be integers")
        if not 0 <= x < self.geography.width or not 0 <= y < self.geography.height:
            raise ActionError("Target hex is outside the world")
        if actor.destination is not None:
            raise ActionError("Finish your road journey before exploring")
        if actor.hp <= 0 or actor.defeated_until is not None:
            raise ActionError("Cannot explore while recovering")
        if any(actor_id in (duel.attacker_id, duel.defender_id)
               for duel in self.state.duels.values()):
            raise ActionError("Finish your duel before exploring")
        # Enforce the same carried-item limit as regional road travel.
        load = sum(actor.inventory.values()) + len(actor.gear_ids)
        limit = self.housing_system.travel_cargo_limit(actor)
        if load > limit:
            raise ActionError(f"Travel cargo limit is {limit} units; carrying {load}")
        # The authoritative route can cross several hexes, but each step
        # contributes its own terrain cost. Client input only names an endpoint.
        duration, route = self.travel.plan_hex_journey(actor, (x, y))
        actor.destination = actor.city  # Maintains existing travel invariants.
        actor.arrival_minute = self.minute + duration
        actor.travel.departure_minute = self.minute
        actor.travel.route_hexes = route
        actor.travel.route_revealed_index = 0
        actor.travel.hex_target = (x, y)
        self._emit("hex_journey_started", actor_id, x, y, actor.arrival_minute)
        return {"x": x, "y": y, "minutes": duration, "arrival_minute": actor.arrival_minute}

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
    def store_gear(self, actor_id: str, gear_id: int) -> None:
        """Keep unequipped gear in the current city; ownership never changes."""
        actor = self._actor(actor_id)
        city = self._at_city(actor)
        if type(gear_id) is not int or gear_id not in actor.gear_ids:
            raise ActionError("You do not carry this equipment")
        if gear_id in actor.equipped.values():
            raise ActionError("Unequip this item before storing it")
        actor.gear_ids.remove(gear_id)
        actor.stored_gear.setdefault(city, []).append(gear_id)
        self._emit("gear_stored", actor_id, city, gear_id)

    @atomic_action
    def retrieve_gear(self, actor_id: str, gear_id: int) -> None:
        """Withdraw only this account's locally stored equipment."""
        actor = self._actor(actor_id)
        city = self._at_city(actor)
        if type(gear_id) is not int or gear_id not in actor.stored_gear.get(city, []):
            raise ActionError("Equipment is not stored here")
        actor.stored_gear[city].remove(gear_id)
        actor.gear_ids.append(gear_id)
        self._emit("gear_retrieved", actor_id, city, gear_id)

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

    @atomic_action
    def propose_trade(self, principal_id: str, recipient_id: str,
                      offer: dict, request: dict) -> dict:
        return self.trades_system.propose(principal_id, recipient_id, offer, request)

    @atomic_action
    def accept_trade(self, principal_id: str, trade_id: int, terms_hash: str) -> dict:
        return self.trades_system.accept(principal_id, trade_id, terms_hash)

    @atomic_action
    def close_trade(self, principal_id: str, trade_id: int) -> dict:
        return self.trades_system.close(principal_id, trade_id)

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
        return max(1, (minutes + 59) // 60) if self.dev_travel_seconds else minutes

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
    def pvp_strike(self, attacker_id: str, defender_id: str) -> dict:
        return self.combat.pvp_strike(attacker_id, defender_id)

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
    def send_chat(self, principal_id: str, kind: str, target: str, message: str) -> dict:
        return self.chat_system.send(principal_id, kind, target, message)

    @atomic_action
    def create_chat_room(self, principal_id: str, name: str, members: list[str]) -> dict:
        return self.chat_system.create_room(principal_id, name, members)

    @atomic_action
    def enroll_course_choice(self, actor_id: str, school: str, index: int) -> dict:
        return self.curriculum_system.choose(actor_id, school, index)

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
            spec = COMMAND_SPECS.get(action)
            if spec is None:
                raise ActionError("Unknown or forbidden command")
            method_name, fields = spec.method, spec.fields
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
                    and action not in ("duel_turn", "flee_duel",
                                       "send_chat", "create_chat_room")):
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
        """Verify world integrity after mutating commands."""
        validate_world(self)
