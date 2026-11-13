"""Finite achievement rewards and one-time merit purchases (no combat inflation)."""
from dataclasses import dataclass
from ..errors import ActionError
from .curriculum import SCHOOLS, RETIRED_SCHOOLS

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
    **{"school:" + school: Achievement(
        name + " Scholar", "Complete all eight courses in " + name)
       for school, (name, _, _, _) in SCHOOLS.items()},
}
MERIT_UPGRADES = {
    "roadcraft": {"name": "Roadcraft", "cost": 2, "description": "5% shorter road journeys"},
    "horsemanship": {"name": "Horsemanship", "cost": 2, "description": "+2 to your horse-race score"},
    "awareness_1": {"name": "Awareness I", "cost": 2,
                    "description": "See and permanently explore within 3 hexes instead of 2"},
    "awareness_2": {"name": "Awareness II", "cost": 3,
                    "description": "Increase sight and exploration radius to 4 hexes"},
}

class MeritSystem:
    def __init__(self, world):
        self.world = world

    def earned(self, actor_id: str, key: str) -> bool:
        actor = self.world._actor(actor_id)
        events = self.world.events
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
            raise ActionError("Unknown merit upgrade")
        owned = self.world.state.merit_upgrades.setdefault(actor_id, set())
        if perk in owned:
            raise ActionError("Upgrade already purchased")
        if perk == "awareness_2" and "awareness_1" not in owned:
            raise ActionError("Awareness II requires Awareness I")
        cost = MERIT_UPGRADES[perk]["cost"]
        balance = self.world.state.merit_balance.get(actor_id, 0)
        if balance < cost:
            raise ActionError("Insufficient merit points")
        self.world.state.merit_balance[actor_id] = balance - cost
        owned.add(perk)
        if perk in ("awareness_1", "awareness_2"):
            from ..core.exploration import current_hex, reveal
            reveal(self.world, self.world._actor(actor_id),
                   current_hex(self.world, self.world._actor(actor_id)))
        self.world._emit("merit_upgrade", actor_id, perk, cost)
        return {"perk": perk, "cost": cost}

    def view(self, actor_id: str) -> dict:
        claimed = self.world.state.merit_claims.get(actor_id, set())
        upgrades = self.world.state.merit_upgrades.get(actor_id, set())
        return {"balance": self.world.state.merit_balance.get(actor_id, 0),
                "total_earned": sum(ACHIEVEMENTS[k].award for k in claimed),
                "achievements": [{
                    "id": k, "name": spec.name, "description": spec.description,
                    "claimed": k in claimed, "eligible": self.earned(actor_id, k),
                    "award": spec.award} for k, spec in ACHIEVEMENTS.items()
                    if not (k.startswith("school:") and k[7:] in RETIRED_SCHOOLS)
                    or k in claimed or self.earned(actor_id, k)],
                "upgrades": [{"id": key, **spec, "owned": key in upgrades}
                             for key, spec in MERIT_UPGRADES.items()]}
