"""Housing ownership, local training and actual road transport.

No artificial rent income, teleporting vehicles or free transportation. The
treasury receives purchases; vehicle speeds only affect road journeys.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..catalog import CITIES
from ..content.housing import HOMES, HOME_ORDER, FACILITIES, VEHICLES
from ..errors import ActionError
from ..core.transactions import transfer_gold

BASE_TRAVEL_CARGO = 12


@dataclass(frozen=True)
class HousingView:
    city: str | None
    tier: str | None
    training_bonus_pct: int
    facilities: tuple[str, ...]
    vehicles: tuple[str, ...]
    active_vehicle: str | None
    travel_cargo_limit: int


class HousingSystem:
    def __init__(self, world):
        self.world = world

    def view(self, actor_id: str) -> HousingView:
        state = self.world._actor(actor_id).housing
        bonus = HOMES[state.tier].training_bonus_pct if state.tier else 0
        cargo = VEHICLES[state.active_vehicle].travel_cargo_limit if state.active_vehicle else BASE_TRAVEL_CARGO
        return HousingView(state.city, state.tier, bonus, tuple(sorted(state.facilities)),
                           tuple(sorted(state.vehicles)), state.active_vehicle, cargo)

    def buy_home(self, actor_id: str, tier: str) -> int:
        actor = self.world._actor(actor_id)
        city = self.world._at_city(actor)
        if tier not in HOMES:
            raise ActionError("Unknown home type")
        if actor.housing.tier is not None:
            raise ActionError("Already own a home: upgrade the existing home")
        price = HOMES[tier].price
        transfer_gold(self.world, actor, None, price)
        actor.housing.city = city
        actor.housing.tier = tier
        self.world._emit("home_purchased", actor_id, city, tier, price)
        return price

    def upgrade_home(self, actor_id: str, tier: str) -> int:
        actor = self.world._actor(actor_id)
        if tier not in HOMES:
            raise ActionError("Unknown home type")
        state = actor.housing
        if state.tier is None or self.world._at_city(actor) != state.city:
            raise ActionError("Must visit your existing home to upgrade")
        if HOME_ORDER.index(tier) <= HOME_ORDER.index(state.tier):
            raise ActionError("Home upgrade must raise tier")
        cost = HOMES[tier].price - HOMES[state.tier].price
        transfer_gold(self.world, actor, None, cost)
        previous = state.tier
        state.tier = tier
        self.world._emit("home_upgraded", actor_id, state.city, previous, tier, cost)
        return cost

    def build_facility(self, actor_id: str, facility: str) -> int:
        actor = self.world._actor(actor_id)
        state = actor.housing
        if facility not in FACILITIES:
            raise ActionError("Unknown housing facility")
        if state.tier is None or self.world._at_city(actor) != state.city:
            raise ActionError("Build facilities at your owned home")
        if facility in state.facilities:
            raise ActionError("Facility already built")
        if HOME_ORDER.index(state.tier) + 1 < FACILITIES[facility].min_home_tier:
            raise ActionError("Home tier cannot support that facility")
        price = FACILITIES[facility].price
        transfer_gold(self.world, actor, None, price)
        state.facilities.add(facility)
        self.world._emit("home_facility_built", actor_id, facility, price)
        return price

    def buy_vehicle(self, actor_id: str, vehicle: str) -> int:
        actor = self.world._actor(actor_id)
        state = actor.housing
        if vehicle not in VEHICLES:
            raise ActionError("Unknown vehicle")
        if state.tier is None or self.world._at_city(actor) != state.city:
            raise ActionError("Purchase and store vehicles at your home")
        if vehicle in state.vehicles:
            raise ActionError("Vehicle already owned")
        if VEHICLES[vehicle].facility not in state.facilities:
            raise ActionError("Required transportation facility not built")
        price = VEHICLES[vehicle].price
        transfer_gold(self.world, actor, None, price)
        state.vehicles.add(vehicle)
        self.world._emit("vehicle_purchased", actor_id, vehicle, price)
        return price

    def select_vehicle(self, actor_id: str, vehicle: str | None) -> None:
        actor = self.world._actor(actor_id)
        state = actor.housing
        if state.tier is None or self.world._at_city(actor) != state.city:
            raise ActionError("Vehicles must be taken from or parked at home")
        if vehicle is not None and vehicle not in state.vehicles:
            raise ActionError("Vehicle not owned")
        if state.active_vehicle == vehicle:
            return
        state.active_vehicle = vehicle
        self.world._emit("vehicle_selected", actor_id, vehicle)

    def travel_cargo_limit(self, actor) -> int:
        return (VEHICLES[actor.housing.active_vehicle].travel_cargo_limit
                if actor.housing.active_vehicle else BASE_TRAVEL_CARGO)

    def road_minutes(self, actor, base_minutes: int) -> int:
        """Use integer ceiling, preserving at least one minute for every road trip."""
        vehicle = actor.housing.active_vehicle
        percent = VEHICLES[vehicle].road_time_percent if vehicle else 100
        return max(1, (base_minutes * percent + 99) // 100)

    def training_xp(self, actor, base: int, domain: str) -> int:
        """Carry fractional bonuses so +5% really means 1 extra XP per 20 XP.

        Activated only while learning in the city where the actor's home stands.
        Skills share the same bonus formula, with separate residual ledgers.
        """
        if type(base) is not int or base < 0 or not isinstance(domain, str) or not domain:
            raise ValueError("Invalid training XP award")
        housing = actor.housing
        if not housing.tier or actor.city != housing.city or actor.destination is not None or base == 0:
            return base
        bonus = HOMES[housing.tier].training_bonus_pct
        remainder = housing.xp_remainders.get(domain, 0) + base * bonus
        extra, housing.xp_remainders[domain] = divmod(remainder, 100)
        return base + extra

    @staticmethod
    def assert_valid(actor) -> None:
        h = actor.housing
        if (h.tier is None) != (h.city is None):
            raise AssertionError("Housing tier without city or vice versa")
        if h.city is not None and h.city not in CITIES:
            raise AssertionError("Unknown housing city")
        if h.tier is not None and h.tier not in HOMES:
            raise AssertionError("Unknown housing tier")
        if (not isinstance(h.facilities, set) or
                any(facility not in FACILITIES for facility in h.facilities) or
                not isinstance(h.vehicles, set) or
                any(vehicle not in VEHICLES for vehicle in h.vehicles)):
            raise AssertionError("Unknown housing facility or vehicle")
        if h.tier is None and (h.facilities or h.vehicles or h.active_vehicle):
            raise AssertionError("Unowned housing assets")
        for facility in h.facilities:
            if HOME_ORDER.index(h.tier) + 1 < FACILITIES[facility].min_home_tier:
                raise AssertionError("Facility incompatible with home")
        for vehicle in h.vehicles:
            if VEHICLES[vehicle].facility not in h.facilities:
                raise AssertionError("Vehicle missing its home facility")
        if h.active_vehicle is not None and h.active_vehicle not in h.vehicles:
            raise AssertionError("Active vehicle not owned")
        if any(not isinstance(k, str) or not k or type(v) is not int or not 0 <= v < 100
               for k, v in h.xp_remainders.items()):
            raise AssertionError("Corrupt fractional training XP")
