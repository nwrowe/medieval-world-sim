"""Stable resource, equipment and industry definitions shared by game and atlas.

Separate from geography to avoid importing the world generator recursively.
"""
from dataclasses import dataclass

RAW_RESOURCES = (
    "iron_ore", "coal", "stone", "timber", "herbs", "grain", "hides", "vegetables", "meat",
)
PROCESSED_RESOURCES = ("steel", "leather", "planks", "stone_blocks", "mead")
EQUIPMENT = (
    "sword", "axe", "shield", "plate_armor", "leather_armor",
    "bow", "pickaxe",
)
CONSUMABLES = ("bread", "meal", "healing_potion", "mana_tonic")
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
    "charcoal_kiln": Recipe({"timber": 2}, {"coal": 1}),
    "brewery": Recipe({"grain": 2, "herbs": 1}, {"mead": 2}),
    "stoneworks": Recipe({"stone": 2}, {"stone_blocks": 1}),
    "provisioner": Recipe({"meat": 1, "vegetables": 1, "grain": 1}, {"meal": 2}),
}

# Keep the original recipes as industry defaults. Historical company shifts
# replay identically while owners may opt into alternative goods or equipment.
INDUSTRY_PRODUCTS = {
    key: {next(iter(recipe.outputs)): recipe}
    for key, recipe in RECIPES.items()
}
INDUSTRY_PRODUCTS["forge"].update({
    "dagger": Recipe({"steel": 1, "timber": 1}, {"dagger": 1}),
    "axe": Recipe({"steel": 2, "timber": 1}, {"axe": 1}),
})
INDUSTRY_PRODUCTS["weaponsmith"].update({
    "sword": Recipe({"steel": 1, "timber": 1}, {"sword": 1}),
    "dagger": Recipe({"steel": 1}, {"dagger": 1}),
})
INDUSTRY_PRODUCTS["armorer"].update({
    "iron_helm": Recipe({"steel": 1, "leather": 1}, {"iron_helm": 1}),
    "iron_boots": Recipe({"steel": 1, "leather": 1}, {"iron_boots": 1}),
    "iron_greaves": Recipe({"steel": 1, "leather": 1}, {"iron_greaves": 1}),
    "iron_gauntlets": Recipe({"steel": 1, "leather": 1}, {"iron_gauntlets": 1}),
})
INDUSTRY_PRODUCTS["leatherworker"].update({
    "leather_cap": Recipe({"leather": 1}, {"leather_cap": 1}),
    "leather_boots": Recipe({"leather": 1}, {"leather_boots": 1}),
    "leather_greaves": Recipe({"leather": 1}, {"leather_greaves": 1}),
    "leather_gloves": Recipe({"leather": 1}, {"leather_gloves": 1}),
})
INDUSTRY_PRODUCTS["apothecary"]["mana_tonic"] = Recipe(
    {"herbs": 2, "coal": 1}, {"mana_tonic": 1})
INDUSTRY_PRODUCTS["tavern"]["mead"] = Recipe(
    {"grain": 2, "herbs": 1}, {"mead": 2})
INDUSTRY_PRODUCTS["provisioner"]["bread"] = Recipe(
    {"grain": 2}, {"bread": 3})
INDUSTRY_PRODUCTS["bakery"]["meal"] = Recipe(
    {"bread": 1, "meat": 1, "vegetables": 1}, {"meal": 2})


def company_recipe(company):
    """An unselected legacy company continues using its original recipe."""
    return INDUSTRY_PRODUCTS[company.industry].get(
        company.product, RECIPES[company.industry])

