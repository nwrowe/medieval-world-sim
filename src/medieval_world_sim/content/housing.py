"""Data-only home, facility and vehicle definitions.

Homes affect training *at their home city*. Transport bonuses require real
purchased vehicles supported by suitable facilities, never by a house alone.
"""
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class HomeSpec:
    name: str
    price: int  # Total cumulative cost; upgrades pay the difference.
    training_bonus_pct: int
    min_facility_tier: int


HOME_ORDER = ("room", "cottage", "townhouse", "estate", "manor")
HOMES = MappingProxyType({
    "room": HomeSpec("Rented Room", 90, 0, 1),
    "cottage": HomeSpec("Cottage", 350, 5, 2),
    "townhouse": HomeSpec("Townhouse", 1100, 10, 3),
    "estate": HomeSpec("Estate", 3600, 15, 4),
    "manor": HomeSpec("Manor", 10000, 20, 5),
})


@dataclass(frozen=True)
class FacilitySpec:
    name: str
    price: int
    min_home_tier: int


FACILITIES = MappingProxyType({
    "stable": FacilitySpec("Stable", 180, 2),
    "carriage_house": FacilitySpec("Carriage House", 550, 4),
    # Docks intentionally wait until the map has actual navigable water routes.
})


@dataclass(frozen=True)
class VehicleSpec:
    name: str
    price: int
    facility: str
    road_time_percent: int  # 100 is walking speed.
    travel_cargo_limit: int  # Count-based, including equipped gear.


VEHICLES = MappingProxyType({
    "horse": VehicleSpec("Horse", 250, "stable", 80, 16),
    "carriage": VehicleSpec("Carriage", 950, "carriage_house", 60, 20),
})
