"""Industry-specific career slots for Oathmere companies.

Shifts completed establish a business independently of its owner's wealth.
A vacancy is a particular slot, not an unlimited generic employment offer.
All requirements are work attributes (manual, endurance, intelligence).
"""
from __future__ import annotations

# Title, main attribute, supporting attribute. Each trade has a career ladder:
# three entry roles and two specialist/supervisory roles unlocked with growth.
CAREERS = {
    "steelworks": (("Furnace hand", "manual", "endurance"), ("Ore hauler", "endurance", "manual"), ("Smelter", "manual", "intelligence"), ("Metallurgist", "intelligence", "manual"), ("Furnace master", "manual", "intelligence")),
    "tannery": (("Hide scraper", "manual", "endurance"), ("Curing hand", "endurance", "manual"), ("Leather dresser", "manual", "intelligence"), ("Dye specialist", "intelligence", "manual"), ("Master tanner", "manual", "intelligence")),
    "sawmill": (("Log carrier", "endurance", "manual"), ("Sawyer", "manual", "endurance"), ("Timber grader", "intelligence", "manual"), ("Millwright", "manual", "intelligence"), ("Mill foreman", "endurance", "intelligence")),
    "forge": (("Forge striker", "manual", "endurance"), ("Bellows keeper", "endurance", "manual"), ("Blade grinder", "manual", "intelligence"), ("Weaponsmith", "manual", "intelligence"), ("Master smith", "manual", "intelligence")),
    "weaponsmith": (("Hammer hand", "manual", "endurance"), ("Hilt fitter", "manual", "intelligence"), ("Edge polisher", "manual", "endurance"), ("Blade maker", "manual", "intelligence"), ("Master bladesmith", "manual", "intelligence")),
    "shieldmaker": (("Board cutter", "manual", "endurance"), ("Rim fitter", "manual", "intelligence"), ("Shield painter", "intelligence", "manual"), ("Shield assembler", "manual", "intelligence"), ("Master shieldwright", "manual", "intelligence")),
    "armorer": (("Plate hammerer", "manual", "endurance"), ("Rivet setter", "manual", "intelligence"), ("Armor fitter", "manual", "intelligence"), ("Tempering specialist", "intelligence", "manual"), ("Master armorer", "manual", "intelligence")),
    "leatherworker": (("Hide cutter", "manual", "endurance"), ("Stitcher", "manual", "intelligence"), ("Armor fitter", "manual", "endurance"), ("Pattern maker", "intelligence", "manual"), ("Master leatherworker", "manual", "intelligence")),
    "bowyer": (("Wood shaper", "manual", "endurance"), ("String maker", "manual", "intelligence"), ("Fletcher", "manual", "intelligence"), ("Draw tester", "endurance", "manual"), ("Master bowyer", "manual", "intelligence")),
    "toolmaker": (("Forge hand", "manual", "endurance"), ("Handle maker", "manual", "intelligence"), ("Tool grinder", "manual", "endurance"), ("Mechanist", "intelligence", "manual"), ("Master toolwright", "manual", "intelligence")),
    "apothecary": (("Herb sorter", "intelligence", "manual"), ("Mortar hand", "manual", "intelligence"), ("Potion brewer", "intelligence", "manual"), ("Remedy researcher", "intelligence", "endurance"), ("Master apothecary", "intelligence", "manual")),
    "bakery": (("Dough kneader", "manual", "endurance"), ("Oven tender", "endurance", "manual"), ("Pastry maker", "manual", "intelligence"), ("Recipe keeper", "intelligence", "manual"), ("Master baker", "manual", "intelligence")),
    "tavern": (("Kitchen hand", "endurance", "manual"), ("Server", "endurance", "intelligence"), ("Cook", "manual", "intelligence"), ("Cellar keeper", "intelligence", "endurance"), ("Inn steward", "intelligence", "endurance")),
    "charcoal_kiln": (("Wood stacker", "endurance", "manual"), ("Kiln tender", "manual", "endurance"), ("Fuel sorter", "manual", "intelligence"), ("Fire watcher", "intelligence", "endurance"), ("Kiln master", "manual", "intelligence")),
    "brewery": (("Grain miller", "manual", "endurance"), ("Vat tender", "endurance", "manual"), ("Brewer", "intelligence", "manual"), ("Taster", "intelligence", "endurance"), ("Brewmaster", "intelligence", "manual")),
    "stoneworks": (("Stone carrier", "endurance", "manual"), ("Block cutter", "manual", "endurance"), ("Mason", "manual", "intelligence"), ("Surveyor", "intelligence", "manual"), ("Master stonecutter", "manual", "intelligence")),
    "provisioner": (("Stock handler", "endurance", "manual"), ("Food packer", "manual", "endurance"), ("Market clerk", "intelligence", "manual"), ("Supply buyer", "intelligence", "endurance"), ("Provision master", "intelligence", "endurance")),
}
LARGE_TRADES = frozenset({"steelworks", "sawmill", "forge", "armorer", "stoneworks", "tannery"})
GROWTH_SHIFTS = (0, 12, 36, 84, 168)
SMALL_CAPS = (3, 6, 9, 12, 15)
LARGE_CAPS = (3, 6, 10, 14, 18)
OFFER_MINUTES = 48 * 60


def career_stage(company) -> int:
    return sum(company.shifts_completed >= threshold for threshold in GROWTH_SHIFTS) - 1


def capacity(company) -> int:
    caps = LARGE_CAPS if company.industry in LARGE_TRADES else SMALL_CAPS
    return caps[career_stage(company)]


def positions(company) -> list[dict]:
    """Stable slot IDs; promotions never reshuffle workers or live offers."""
    careers = CAREERS.get(company.industry, CAREERS["forge"])  # Legacy imported trades
    caps = LARGE_CAPS if company.industry in LARGE_TRADES else SMALL_CAPS
    result = []
    for slot in range(caps[career_stage(company)]):
        tier = next(i for i, cap in enumerate(caps) if slot < cap)
        title, primary, secondary = careers[slot % len(careers)]
        requirements = {primary: 8 + 4 * tier, secondary: 4 + 2 * tier}
        result.append({
            "id": str(slot), "title": title + (" " + str(slot // len(careers) + 1) if slot >= len(careers) else ""),
            "tier": tier + 1, "requirements": requirements,
            "focus": primary, "support": secondary,
        })
    return result


def qualified(actor, slot: dict) -> bool:
    return all(getattr(actor.work, key) >= minimum
               for key, minimum in slot["requirements"].items())


def active_offer(company, actor_id: str, minute: int) -> bool:
    if actor_id not in company.job_offers:
        return False
    expiry = company.offer_expires.get(actor_id, 0)
    return not expiry or expiry > minute


def occupancy(company, minute: int) -> dict[str, tuple[str, str]]:
    """Existing pre-slot staff and old offers consume distinct positions."""
    slots = [p["id"] for p in positions(company)]
    occupied = {}
    for actor, slot in sorted(company.employee_positions.items()):
        if actor in company.employees and slot in slots and slot not in occupied:
            occupied[slot] = ("employee", actor)
    for actor in sorted(company.employees):
        if actor not in company.employee_positions:
            empty = next((p for p in slots if p not in occupied), None)
            if empty is not None:
                occupied[empty] = ("employee", actor)
    for actor, slot in sorted(company.offer_positions.items()):
        if active_offer(company, actor, minute) and slot in slots and slot not in occupied:
            occupied[slot] = ("offer", actor)
    for actor in sorted(company.job_offers):
        if active_offer(company, actor, minute) and actor not in company.offer_positions:
            empty = next((p for p in slots if p not in occupied), None)
            if empty is not None:
                occupied[empty] = ("offer", actor)
    return occupied


def openings(company, minute: int) -> list[dict]:
    taken = occupancy(company, minute)
    return [p for p in positions(company) if p["id"] not in taken]
