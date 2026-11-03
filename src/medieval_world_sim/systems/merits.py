"""Finite achievement rewards and one-time merit purchases (no combat inflation)."""
from dataclasses import dataclass
from ..errors import ActionError

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
}
MERIT_UPGRADES = {
    "roadcraft": {"name": "Roadcraft", "cost": 2, "description": "5% shorter road journeys"},
    "horsemanship": {"name": "Horsemanship", "cost": 2, "description": "+2 to your horse-race score"},
}

class MeritSystem:
    def __init__(self, world):
        self.world = world

    def earned(self, actor_id: str, key: str) -> bool:
        actor = self.world._actor(actor_id)
        events = self.world.events
        if key == "first_steps": return True
        if key == "apprentice": return actor.level >= 2
        if key == "roadfarer": return any(e.kind == "arrived" and e.data.get("actor_id") == actor_id for e in events)
        if key == "spellbound": return bool(actor.magic.unlocked)
        if key == "challenger": return any(e.kind == "duel_finished" and e.data.get("winner_id") == actor_id for e in events)
        if key == "stablehand": return bool(self.world.state.horses.get(actor_id))
        if key == "rider": return self.world.state.riding_xp.get(actor_id, 0) > 0
        if key == "guild_founder": return any(g.founder_id == actor_id for g in self.world.state.guilds.values())
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
        cost = MERIT_UPGRADES[perk]["cost"]
        balance = self.world.state.merit_balance.get(actor_id, 0)
        if balance < cost:
            raise ActionError("Insufficient merit points")
        self.world.state.merit_balance[actor_id] = balance - cost
        owned.add(perk)
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
                    "award": spec.award} for k, spec in ACHIEVEMENTS.items()],
                "upgrades": [{"id": key, **spec, "owned": key in upgrades}
                             for key, spec in MERIT_UPGRADES.items()]}
