from __future__ import annotations

from ..errors import ActionError

HOUR = 60
HARVEST_LIMIT = 2


class ResourceSystem:
    def __init__(self, world):
        self.world = world

    def gather(self, actor_id: str, item: str, quantity: int = 1) -> None:
        actor = self.world._actor(actor_id)
        city = self.world._at_city(actor)
        self.world._positive(quantity, "quantity")
        if quantity > HARVEST_LIMIT or item not in self.world.deposits[city]:
            raise ActionError("Resource cannot be gathered here at that rate")
        if self.world.minute < actor.ready_minute:
            raise ActionError("Worker cooldown active")
        if self.world.deposits[city][item] < quantity or not self.world._space_for(actor, item, quantity):
            raise ActionError("Insufficient local stock or carrying capacity")
        self.world.deposits[city][item] -= quantity
        self.world._add(actor, item, quantity)
        actor.ready_minute = self.world.minute + HOUR
        self.world._emit("gathered", actor_id, city, item, quantity)
        self.world.assert_invariants()

