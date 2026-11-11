"""Stable resource, equipment and industry definitions shared by game and atlas.

Separate from geography to avoid importing the world generator recursively.
"""
from dataclasses import dataclass

RAW_RESOURCES = (
    "iron_ore", "coal", "stone", "timber", "herbs", "grain", "hides", "vegetables", "meat",
)
PROCESSED_RESOURCES = ("steel", "leather", "planks")
EQUIPMENT = (
    "sword", "axe", "shield", "plate_armor", "leather_armor",
    "bow", "pickaxe",
)
CONSUMABLES = ("bread", "meal", "healing_potion")
GOODS = frozenset(RAW_RESOURCES + PROCESSED_RESOURCES + CONSUMABLES)  # Stackable goods only


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
    "bakery": Recipe({"grain": 2}, {"bread": 3}),
    "tavern": Recipe({"bread": 1, "meat": 1, "vegetables": 1}, {"meal": 2}),
}
