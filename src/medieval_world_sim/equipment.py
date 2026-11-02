"""Quality-bearing, individually owned gear. Every durable item has its own ID.

Stackable resources and potions remain in the material inventory.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


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

# Every durable gear type is always purchasable as a weak quality-10 version
# in the capital. Gold goes to an explicit sink; gear creation is logged.
STARTER_QUALITY = 10
STARTER_PRICES = {kind: spec.base_value for kind, spec in GEAR.items()}


@dataclass
class GearItem:
    id: int
    kind: str
    quality: int
    durability: int
    max_durability: int
    origin: str

    def __post_init__(self) -> None:
        if self.kind not in GEAR or not 1 <= self.quality <= 100:
            raise ValueError("Unknown gear type or invalid quality")
        if not 0 < self.durability <= self.max_durability:
            raise ValueError("Invalid gear durability")


def rarity(quality: int) -> str:
    if not 1 <= quality <= 100:
        raise ValueError("Quality must be between 1 and 100")
    if quality >= 95:
        return "legendary"
    if quality >= 80:
        return "masterwork"
    if quality >= 60:
        return "superior"
    if quality >= 40:
        return "fine"
    if quality >= 20:
        return "common"
    return "rough"


def crafted_quality(seed: int, worker_id: str, company_id: str, minute: int, serial: int) -> int:
    """Repeatable, quality-skewed roll: 20-100; exceptional items uncommon."""
    key = f"{seed}:{worker_id}:{company_id}:{minute}:{serial}".encode()
    fraction = int.from_bytes(sha256(key).digest()[:8], "big") / (2**64)
    return 20 + int(80 * (1.0 - fraction) ** 3)


def suggested_value(item: GearItem) -> int:
    """Indicative value only. Markets may set any nonnegative asking price."""
    base = GEAR[item.kind].base_value
    quality_multiplier = 1 + (item.quality / 35) ** 2
    condition = item.durability / item.max_durability
    return max(1, round(base * quality_multiplier * condition))


def effective_attack(item: GearItem) -> int:
    return round(GEAR[item.kind].attack * (0.75 + item.quality / 100))


def effective_defense(item: GearItem) -> int:
    return round(GEAR[item.kind].defense * (0.75 + item.quality / 100))
