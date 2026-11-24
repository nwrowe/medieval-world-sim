"""Finite achievement rewards and one-time merit purchases (no combat inflation)."""
from dataclasses import dataclass
from ..errors import ActionError
from .curriculum import SCHOOLS
from ..catalog import RAW_RESOURCES
from ..content.housing import HOMES, FACILITIES, VEHICLES
from ..equipment import suggested_value

WEALTH_MILESTONES = (1_000, 5_000, 10_000, 25_000, 100_000, 500_000, 1_000_000)


def net_worth_estimate(world, actor, resale_prices=None):
    """One valuation shared by the character page and Renown eligibility."""
    housing = actor.housing
    if resale_prices is None:
        resale_prices = {item: world.regional_quote(actor.city, item).player_sell_price
                         for item in RAW_RESOURCES if actor.inventory.get(item, 0)}
    worth = actor.gold + (HOMES[housing.tier].price if housing.tier else 0)
    worth += sum(FACILITIES[k].price for k in housing.facilities)
    worth += sum(VEHICLES[k].price for k in housing.vehicles)
    worth += sum(n * resale_prices.get(item, 0) for item, n in actor.inventory.items())
    for city, goods in actor.storage.items():
        worth += sum(n * world.regional_quote(city, item).player_sell_price
                     for item, n in goods.items() if n and item in RAW_RESOURCES)
    worth += sum(suggested_value(world.gear[gid]) for gid in actor.gear_ids)
    worth += sum(suggested_value(world.gear[gid])
                 for ids in actor.stored_gear.values() for gid in ids)
    return worth

@dataclass(frozen=True)
class Achievement:
    name: str
    description: str
    award: int = 1

ACHIEVEMENTS = {
    "first_steps": Achievement("First Steps", "Create your character"),
    "apprentice": Achievement("Apprentice", "Reach level 2"),
    "roadfarer": Achievement("Roadfarer", "Complete a journey"),
    "spellbound": Achievement("Spellbound", "Unlock your first spell"),
    "challenger": Achievement("Challenger", "Win a turn-based duel"),
    "stablehand": Achievement("Stablehand", "Own a racehorse"),
    "rider": Achievement("Rider", "Complete your first race"),
    "guild_founder": Achievement("Banner Bearer", "Found a guild"),
    "explore_25": Achievement("Cartographer I", "Explore 25% of the world"),
    "explore_50": Achievement("Cartographer II", "Explore 50% of the world"),
    "explore_75": Achievement("Cartographer III", "Explore 75% of the world"),
    "explore_100": Achievement("Master Cartographer", "Explore 100% of the world"),
    **{f"wealth_{threshold}": Achievement(
        f"Fortune {index + 1}", f"Reach an estimated net worth of {threshold:,} gold")
       for index, threshold in enumerate(WEALTH_MILESTONES)},
    **{"school:" + school: Achievement(
        name + " Scholar", "Complete all eight courses in " + name)
       for school, (name, _, _, _) in SCHOOLS.items()},
}
MAX_PERK_LEVEL = 5
PERK_TRACKS = {
    "horsemanship": ("Horsemanship", lambda level: f"+{2 * level} to your horse-race score"),
    "awareness": ("Awareness", lambda level: f"See and explore within {2 + level} hexes"),
    "roadcraft": ("Roadcraft", lambda level: f"{5 * level}% shorter road journeys"),
}
MERIT_UPGRADES = {
    f"{track}_{level}": {
        "name": name, "track": track, "level": level, "cost": level,
        "description": describe(level),
    }
    for track, (name, describe) in PERK_TRACKS.items()
    for level in range(1, MAX_PERK_LEVEL + 1)
}


def perk_level(owned, track):
    """Return the contiguous purchased level, never skipping a prerequisite."""
    level = 0
    while level < MAX_PERK_LEVEL and f"{track}_{level + 1}" in owned:
        level += 1
    return level


def roadcraft_minutes(minutes, owned):
    return max(1, (minutes * (100 - 5 * perk_level(owned, "roadcraft")) + 99) // 100)


class MeritSystem:
    def __init__(self, world):
        self.world = world

    def earned(self, actor_id: str, key: str, net_worth=None) -> bool:
        actor = self.world._actor(actor_id)
        events = self.world.events
        if key.startswith("wealth_"):
            if net_worth is None:
                net_worth = net_worth_estimate(self.world, actor)
            return net_worth >= int(key.split("_", 1)[1])
        if key.startswith("school:"):
            return len(self.world.curriculum_system.completed_indices(actor_id, key[7:])) == 8
        if key.startswith("explore_"):
            threshold = int(key.split("_", 1)[1])
            observed = len(actor.explored_hexes)
            total = len(self.world.geography.tiles)
            return observed * 100 >= threshold * total
        if key == "first_steps": return True
        if key == "apprentice": return actor.level >= 2
        if key == "roadfarer": return any(e.kind == "arrived" and e.data.get("actor_id") == actor_id for e in events)
        if key == "spellbound": return any(node != "arcane_fundamentals" for node in actor.magic.unlocked)
        if key == "challenger": return any(e.kind == "duel_finished" and e.data.get("winner_id") == actor_id for e in events)
        if key == "stablehand": return bool(self.world.state.horses.get(actor_id))
        if key == "rider": return self.world.state.riding_xp.get(actor_id, 0) > 0
        if key == "guild_founder": return any(e.kind == "guild_founded" and e.data.get("actor_id") == actor_id for e in events)
        return False

    def claim(self, actor_id: str, key: str) -> dict:
        self.world._actor(actor_id)
        if key not in ACHIEVEMENTS:
            raise ActionError("Unknown achievement")
        claimed = self.world.state.merit_claims.setdefault(actor_id, set())
        if key in claimed:
            raise ActionError("Achievement already claimed")
        if not self.earned(actor_id, key):
            raise ActionError("Achievement requirements not yet met")
        claimed.add(key)
        self.world.state.merit_balance[actor_id] = self.world.state.merit_balance.get(actor_id, 0) + ACHIEVEMENTS[key].award
        self.world._emit("merit_claimed", actor_id, key, ACHIEVEMENTS[key].award)
        return {"achievement": key, "awarded": ACHIEVEMENTS[key].award}

    def purchase(self, actor_id: str, perk: str) -> dict:
        self.world._actor(actor_id)
        if perk not in MERIT_UPGRADES:
            raise ActionError("Unknown Renown improvement")
        owned = self.world.state.merit_upgrades.setdefault(actor_id, set())
        if perk in owned:
            raise ActionError("Upgrade already purchased")
        spec = MERIT_UPGRADES[perk]
        if spec["level"] != perk_level(owned, spec["track"]) + 1:
            raise ActionError("Purchase the preceding Renown level first")
        cost = spec["cost"]
        balance = self.world.state.merit_balance.get(actor_id, 0)
        if balance < cost:
            raise ActionError("Insufficient Renown")
        self.world.state.merit_balance[actor_id] = balance - cost
        owned.add(perk)
        if spec["track"] == "awareness":
            from ..core.exploration import current_hex, reveal
            reveal(self.world, self.world._actor(actor_id),
                   current_hex(self.world, self.world._actor(actor_id)))
        self.world._emit("merit_upgrade", actor_id, perk, cost)
        return {"perk": perk, "cost": cost}

    def view(self, actor_id: str, net_worth=None) -> dict:
        if net_worth is None:
            net_worth = net_worth_estimate(self.world, self.world._actor(actor_id))
        claimed = self.world.state.merit_claims.get(actor_id, set())
        upgrades = self.world.state.merit_upgrades.get(actor_id, set())
        return {"balance": self.world.state.merit_balance.get(actor_id, 0),
                "total_earned": sum(ACHIEVEMENTS[k].award for k in claimed),
                "achievements": [{
                    "id": k, "name": spec.name, "description": spec.description,
                    "claimed": k in claimed, "eligible": k in claimed or self.earned(actor_id, k, net_worth),
                    "award": spec.award} for k, spec in ACHIEVEMENTS.items()
                    ],
                "upgrades": [
                    {"id": track, "name": name, "level": level,
                     "max_level": MAX_PERK_LEVEL,
                     "description": describe(level),
                     "next_description": describe(level + 1) if level < MAX_PERK_LEVEL else None,
                     "next_id": f"{track}_{level + 1}" if level < MAX_PERK_LEVEL else None,
                     "cost": level + 1 if level < MAX_PERK_LEVEL else None}
                    for track, (name, describe) in PERK_TRACKS.items()
                    for level in [perk_level(upgrades, track)]]}
