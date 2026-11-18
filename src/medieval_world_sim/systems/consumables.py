"""Consumable rules, separate from combat and from company production."""
from dataclasses import dataclass

from ..errors import ActionError
from .cooldowns import FOOD_MINUTES, POTION_MINUTES, stack, can_add


@dataclass(frozen=True)
class Consumable:
    health: int = 0
    stamina: int = 0
    hunger: int = 0
    mana: int = 0


CONSUMABLE_EFFECTS = {
    "bread": Consumable(health=1, stamina=10, hunger=1),
    "meal": Consumable(health=2, stamina=20, hunger=2),
    "healing_potion": Consumable(health=8),
    "mana_tonic": Consumable(mana=10),
}


class ConsumableSystem:
    def __init__(self, world):
        self.world = world

    def consume(self, actor_id: str, item: str) -> tuple[int, int, int]:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        if item not in CONSUMABLE_EFFECTS:
            raise ActionError("Not an edible or medicinal consumable")
        if actor.inventory.get(item, 0) <= 0:
            raise ActionError("Consumable not owned by actor")
        effect = CONSUMABLE_EFFECTS[item]
        if not (effect.health > 0 and actor.hp < actor.max_hp
                or effect.stamina > 0 and actor.stamina < actor.max_stamina
                or effect.hunger > 0 and actor.vitals.hunger > 0
                or effect.mana > 0 and actor.magic.mana < actor.magic.max_mana):
            raise ActionError("No recovery or nourishment needed")
        channel = "food" if item in FOOD_MINUTES else "potion"
        duration = (FOOD_MINUTES.get(item) if channel == "food"
                    else POTION_MINUTES.get(item))
        if not can_add(actor, channel, duration, self.world.minute):
            raise ActionError(f"{channel.title()} cooldown would exceed 24 hours")
        before = (actor.hp, actor.stamina, actor.vitals.hunger)
        actor.hp = min(actor.max_hp, actor.hp + effect.health)
        actor.stamina = min(actor.max_stamina, actor.stamina + effect.stamina)
        actor.vitals.hunger = max(0, actor.vitals.hunger - effect.hunger)
        before_mana = actor.magic.mana
        actor.magic.mana = min(actor.magic.max_mana, actor.magic.mana + effect.mana)
        actor.inventory[item] -= 1
        stack(actor, channel, duration, self.world.minute)
        gains = (actor.hp - before[0], actor.stamina - before[1],
                 before[2] - actor.vitals.hunger)
        self.world._emit("consumed", actor.id, item, *gains)
        if actor.magic.mana > before_mana:
            self.world._emit("mana_restored", actor.id, item,
                             actor.magic.mana - before_mana)
        return gains
