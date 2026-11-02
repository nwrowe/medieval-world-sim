"""Content-only equipment specifications. No world mutations or combat logic."""
from dataclasses import dataclass

@dataclass(frozen=True)
class GearSpec:
    slot: str
    attack: int
    defense: int
    base_value: int
    max_durability: int


GEAR: dict[str, GearSpec] = {
    "sword": GearSpec("weapon", 7, 0, 16, 35),
    "axe": GearSpec("weapon", 8, 0, 18, 32),
    "bow": GearSpec("weapon", 6, 0, 15, 30),
    "shield": GearSpec("offhand", 0, 5, 14, 50),
    "plate_armor": GearSpec("body", 0, 10, 45, 65),
    "leather_armor": GearSpec("body", 0, 5, 20, 40),
    "pickaxe": GearSpec("tool", 0, 1, 12, 35),
}

