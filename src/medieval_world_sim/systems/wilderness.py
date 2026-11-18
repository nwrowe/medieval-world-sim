"""Wilderness Phase 1: renewable terrain resources and one-shot site choices.

The geographic generator owns biome/geology/resource *potential*. This system
only stores depleted local stock and per-character site decisions. Site rolls
use a server-keyed digest in multiplayer and are reproducible during replay.
No route traversal opens an encounter or interrupts scheduled road journeys.
"""
from __future__ import annotations

from hashlib import sha256
import hmac

from ..errors import ActionError

MAX_HARVEST = 2
SITE_APPROACHES = {
    # Public costs and descriptive labels; skill and difficulty are calculated
    # authoritatively per player/site, never accepted from the client.
    "survey": ("Survey from safety", 2, "intelligence", 90, 5, 1),
    "scavenge": ("Search for supplies", 4, "manual", 78, 6, 2),
    "delve": ("Explore the depths", 7, "endurance", 70, 7, 4),
}

PREFERRED_FINDS = {
    "abandoned_mine": ("iron_ore", "stone", "coal"),
    "cavern": ("stone", "iron_ore"),
    "forest_shrine": ("herbs", "timber"),
    "sunken_crypt": ("herbs", "stone"),
    "summit_ruin": ("stone", "iron_ore"),
    "bandit_camp": ("hides", "meat", "timber"),
    "ruined_watch": ("stone", "timber"),
    "river_temple": ("herbs", "stone"),
}


def supply_cap(potential: int) -> int:
    """At most five units on a tile, scaled directly from geological potential."""
    return max(1, min(5, (potential + 19) // 20))


class WildernessSystem:
    def __init__(self, world):
        self.world = world

    def _here(self, actor_id):
        actor = self.world._actor(actor_id)
        if (actor.destination is not None or actor.wilderness_hex is None
                or actor.hp <= 0 or actor.defeated_until is not None):
            raise ActionError("Finish traveling and enter a wilderness hex")
        x, y = actor.wilderness_hex
        return actor, x, y, self.world.geography.tile(x, y)

    def _available(self, tile, item: str) -> int:
        potential = tile.resources.get(item, 0)
        if potential <= 0:
            return 0
        maximum = supply_cap(potential)
        record = self.world.state.wilderness_stock.get(
            (tile.y * self.world.geography.width + tile.x, item))
        if record is None:
            return maximum
        remaining, day = record
        elapsed_days = max(0, self.world.minute // 1440 - day)
        return min(maximum, remaining + elapsed_days * max(1, maximum // 2))

    def gather(self, actor_id: str, item: str, quantity: int) -> dict:
        actor, x, y, tile = self._here(actor_id)
        self.world._positive(quantity, "quantity")
        if type(item) is not str or quantity > MAX_HARVEST or item not in tile.resources:
            raise ActionError("Cannot harvest that resource at this location")
        cost = 1 + 2 * quantity
        if actor.stamina < cost:
            raise ActionError("Not enough stamina to gather")
        available = self._available(tile, item)
        if available < quantity:
            raise ActionError("This deposit is exhausted; let it recover")
        # Only committed successful commands consume stamina and stock.
        actor.stamina -= cost
        key = (y * self.world.geography.width + x, item)
        self.world.state.wilderness_stock[key] = (
            available - quantity, self.world.minute // 1440)
        self.world._add(actor, item, quantity)
        self.world._emit("wilderness_gathered", actor_id, x, y, item,
                         quantity, cost, available - quantity)
        return {"item": item, "quantity": quantity, "stamina_spent": cost,
                "remaining": available - quantity}

    def _site(self, site_id):
        if type(site_id) is not str or len(site_id) > 64:
            raise ActionError("Invalid wilderness site")
        return next((s for s in self.world.geography.sites if s.id == site_id), None)

    @staticmethod
    def _chance(actor, site, approach: str) -> int:
        _, _, stat, base, danger_factor, _ = SITE_APPROACHES[approach]
        score = getattr(actor.work, stat)
        bonus = actor.level * (2 if approach == "delve" else 1)
        return max(15, min(96, base + score // 2 + bonus - site.danger * danger_factor))

    @staticmethod
    def _find(tile, site) -> str:
        possible = tile.resources
        for item in PREFERRED_FINDS.get(site.kind, ()):
            if possible.get(item, 0):
                return item
        if possible:
            return sorted(possible, key=lambda item: (-possible[item], item))[0]
        # Sites with no local natural goods reward their exploration record
        # but cannot conjure a biome-inappropriate resource.
        return ""

    def investigate(self, actor_id: str, site_id: str, approach: str) -> dict:
        actor, x, y, tile = self._here(actor_id)
        if type(approach) is not str or approach not in SITE_APPROACHES:
            raise ActionError("Unknown investigation approach")
        site = self._site(site_id)
        if site is None or (site.x, site.y) != (x, y):
            raise ActionError("You must stand at a discovered site to investigate")
        if site_id in self.world.state.site_attempts.get(actor_id, {}):
            raise ActionError("You have already explored this site")
        label, cost, _, _, _, reward = SITE_APPROACHES[approach]
        if actor.stamina < cost:
            raise ActionError("Not enough stamina to investigate")
        # Server-only key in multiplayer prevents client prediction. The same
        # stored key and committed action replay yield exactly the same roll.
        payload = f"wilderness|{self.world.seed}|{actor_id}|{site_id}|{approach}".encode()
        private_key = getattr(self.world, "_private_rng_key", None)
        digest = (hmac.digest(private_key, payload, "sha256")
                  if private_key is not None else sha256(payload).digest())
        roll = int.from_bytes(digest[:8], "big") % 100 + 1
        chance = self._chance(actor, site, approach)
        success = roll <= chance
        item = self._find(tile, site) if success else ""
        quantity = (reward + int.from_bytes(digest[8:12], "big") % 2
                    if success and item and approach == "delve" else
                    reward if success and item else 0)
        # The worst outcome is a small, nonlethal scrape; it does not initiate
        # an unavoidable duel or prevent a player from leaving the hex.
        damage = min(max(0, actor.hp - 1), max(1, site.danger // 3)) if (
            not success and approach == "delve") else 0
        actor.stamina -= cost
        actor.hp -= damage
        if quantity:
            self.world._add(actor, item, quantity)
        result = (approach, success, item, quantity, damage)
        self.world.state.site_attempts.setdefault(actor_id, {})[site_id] = result
        self.world._emit("site_investigated", actor_id, site_id, approach,
                         success, roll, chance, item, quantity, cost, damage)
        return {"site_id": site_id, "approach": approach, "success": success,
                "chance": chance, "roll": roll, "item": item,
                "quantity": quantity, "stamina_spent": cost,
                "damage": damage, "description": label}

    def view(self, actor_id: str):
        actor = self.world._actor(actor_id)
        if actor.wilderness_hex is None or actor.destination is not None:
            return None
        x, y = actor.wilderness_hex
        tile = self.world.geography.tile(x, y)
        stocks = [
            {"item": item, "potential": strength,
             "available": self._available(tile, item)}
            for item, strength in sorted(tile.resources.items())
        ]
        history = self.world.state.site_attempts.get(actor_id, {})
        sites = []
        for site in self.world.geography.sites:
            if (site.x, site.y) != (x, y):
                continue
            prior = history.get(site.id)
            sites.append({
                "id": site.id, "name": site.name, "kind": site.kind,
                "clue": site.clue, "danger": site.danger,
                "resolved": ({"approach": prior[0], "success": prior[1],
                              "item": prior[2], "quantity": prior[3],
                              "damage": prior[4]} if prior is not None else None),
                "choices": [
                    {"id": key, "label": name, "stamina": cost,
                     "chance": self._chance(actor, site, key),
                     "reward_estimate": reward,
                     "available": (prior is None and actor.stamina >= cost
                                   and actor.hp > 0 and actor.defeated_until is None)}
                    for key, (name, cost, _, _, _, reward) in SITE_APPROACHES.items()
                ],
            })
        return {"x": x, "y": y, "biome": tile.biome,
                "geology": tile.geology, "elevation_m": tile.elevation_m,
                "river": tile.river, "stamina": actor.stamina,
                "gather_cost": {"1": 3, "2": 5},
                "resources": stocks, "sites": sites}
