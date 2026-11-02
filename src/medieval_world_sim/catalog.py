"""Provisional five-city resources, roads, equipment, and production recipes.

These are data definitions, not economic balance claims.
"""
from dataclasses import dataclass


CAPITAL = "crownreach"

@dataclass(frozen=True)
class CitySpec:
    name: str
    deposits: dict[str, int]  # new units per simulated hour


CITIES = {
    "crownreach": CitySpec("Crownreach (capital)", {}),
    "ironvale": CitySpec("Ironvale", {"iron_ore": 3}),
    "emberfall": CitySpec("Emberfall", {"coal": 3, "stone": 2}),
    "greenhollow": CitySpec("Greenhollow", {"timber": 3, "herbs": 2}),
    "goldmeadow": CitySpec("Goldmeadow", {"grain": 3, "hides": 2}),
}

# Roads are undirected; other-city journeys connect through the capital.
ROADS = {
    ("crownreach", "ironvale"): 90,
    ("crownreach", "emberfall"): 70,
    ("crownreach", "greenhollow"): 45,
    ("crownreach", "goldmeadow"): 60,
}

RAW_RESOURCES = (
    "iron_ore", "coal", "stone", "timber", "herbs", "grain", "hides",
)
PROCESSED_RESOURCES = ("steel", "leather", "planks")
EQUIPMENT = (
    "sword", "axe", "shield", "plate_armor", "leather_armor",
    "bow", "pickaxe", "healing_potion",
)
GOODS = frozenset(RAW_RESOURCES + PROCESSED_RESOURCES + EQUIPMENT)


@dataclass(frozen=True)
class Recipe:
    inputs: dict[str, int]
    outputs: dict[str, int]


# One recipe per company type initially; recipe names remain stable IDs.
RECIPES = {
    "steelworks": Recipe({"iron_ore": 2, "coal": 1}, {"steel": 1}),
    "tannery": Recipe({"hides": 2}, {"leather": 1}),
    "sawmill": Recipe({"timber": 2}, {"planks": 2}),
    "forge": Recipe({"steel": 1, "timber": 1}, {"sword": 1}),
    "weaponsmith": Recipe({"steel": 1, "timber": 1}, {"axe": 1}),
    "shieldmaker": Recipe({"planks": 2, "steel": 1}, {"shield": 1}),
    "armorer": Recipe({"steel": 3, "leather": 1}, {"plate_armor": 1}),
    "leatherworker": Recipe({"leather": 2}, {"leather_armor": 1}),
    "bowyer": Recipe({"planks": 2}, {"bow": 1}),
    "toolmaker": Recipe({"steel": 1, "timber": 1}, {"pickaxe": 1}),
    "apothecary": Recipe({"herbs": 2}, {"healing_potion": 1}),
}
