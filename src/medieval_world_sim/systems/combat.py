"""Stamina-based, open-world combat with unarmed attacks and progression."""
from dataclasses import dataclass
from ..equipment import GEAR, effective_attack, effective_defense
from ..errors import ActionError

ATTACK_STAMINA_COST = 20
STAMINA_REGEN_MINUTES = 5
MAX_STAMINA = 100
DEFEAT_RECOVERY_MINUTES = 60
MAX_GOLD_LOOT = 10

def xp_to_next_level(level: int) -> int:
    return 10 * level * level

@dataclass(frozen=True)
class CombatOutcome:
    damage: int
    retaliation: int
    xp_gained: int
    gold_looted: int
    opponent_defeated: bool
    attacker_defeated: bool
    levels_gained: int = 0

class CombatSystem:
    def __init__(self, world):
        self.world = world

    def buy_starter_gear(self, actor_id: str, kind: str) -> int:
        actor = self.world._actor(actor_id)
        if self.world._at_city(actor) != "crownreach":
            raise ActionError("Starter equipment is sold only in the capital")
        if kind not in GEAR:
            raise ActionError("Not a durable equipment item")
        price = GEAR[kind].base_value
        if actor.gold < price or not self.world._space_for(actor, kind, 1):
            raise ActionError("Insufficient gold or carrying capacity")
        actor.gold -= price
        self.world.crown_gold += price
        gear = self.world._mint_gear(actor, kind, 10, "capital_starter_vendor")
        self.world._emit("starter_purchase", actor_id, gear.id, kind, price)
        self.world.assert_invariants()
        return gear.id

    def equip(self, actor_id: str, gear_id: int) -> None:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        if gear_id not in actor.gear_ids:
            raise ActionError("Actor does not own equipment")
        gear = self.world.gear[gear_id]
        if gear.durability <= 0:
            raise ActionError("Broken equipment")
        slot = GEAR[gear.kind].slot
        actor.equipped[slot] = gear_id
        self.world._emit("equipped", actor_id, gear_id, slot)
        self.world.assert_invariants()

    def unequip(self, actor_id: str, slot: str) -> None:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        if slot not in actor.equipped:
            raise ActionError("Slot already empty")
        del actor.equipped[slot]
        self.world._emit("unequipped", actor_id, slot)
        self.world.assert_invariants()

    def _strike(self, attacker, defender) -> int:
        weapon_id = attacker.equipped.get("weapon")
        # Fists are always available; even an unarmed defender counterattacks.
        base_attack = effective_attack(self.world.gear[weapon_id]) if weapon_id is not None else 3
        armor_ids = [defender.equipped.get("body"), defender.equipped.get("offhand")]
        defense = defender.defense + sum(
            effective_defense(self.world.gear[g_id]) for g_id in armor_ids if g_id is not None
        )
        damage = max(1, base_attack + attacker.strength - 1 - defense // 2)
        defender.hp = max(0, defender.hp - damage)
        if weapon_id is not None:
            self._wear(attacker, weapon_id)
        for g_id in armor_ids:
            if g_id is not None:
                self._wear(defender, g_id)
        return damage

    def _wear(self, owner, gear_id: int) -> None:
        item = self.world.gear[gear_id]
        item.durability -= 1
        if item.durability == 0:
            owner.gear_ids.remove(gear_id)
            for slot, equipped_id in list(owner.equipped.items()):
                if equipped_id == gear_id:
                    del owner.equipped[slot]
            del self.world.gear[gear_id]
            self.world._emit("gear_broken", owner.id, gear_id, item.kind)

    def _award_xp(self, actor, amount: int) -> int:
        actor.combat_xp += amount
        actor.level_xp += amount
        levels = 0
        while actor.level_xp >= xp_to_next_level(actor.level):
            actor.level_xp -= xp_to_next_level(actor.level)
            actor.level += 1
            actor.strength += 1
            actor.defense += 1
            actor.max_hp += 4
            actor.hp += 4
            levels += 1
            self.world._emit("level_up", actor.id, actor.level, actor.max_hp)
        return levels

    def attack(self, attacker_id: str, defender_id: str) -> CombatOutcome:
        attacker = self.world._actor(attacker_id)
        defender = self.world._actor(defender_id)
        if attacker_id == defender_id:
            raise ActionError("Cannot attack yourself")
        if self.world._at_city(attacker) != self.world._at_city(defender):
            raise ActionError("Both participants must be in the same city")
        if attacker.hp <= 0 or defender.hp <= 0:
            raise ActionError("Cannot fight while defeated")
        if attacker.stamina < ATTACK_STAMINA_COST:
            raise ActionError("Insufficient stamina")
        # Attacking anyone is permitted: neither NPC hostility nor PvP consent required.
        attacker.stamina -= ATTACK_STAMINA_COST
        damage = self._strike(attacker, defender)
        xp = 1 + damage // 4
        counter = 0
        looted = 0
        defender_dead = defender.hp == 0
        if defender_dead:
            defender.defeated_until = self.world.minute + DEFEAT_RECOVERY_MINUTES
            looted = min(MAX_GOLD_LOOT, defender.gold)
            defender.gold -= looted
            attacker.gold += looted
            xp += 5  # Victory bonus, but no repeated reward while target is defeated.
        else:
            counter = self._strike(defender, attacker)
            if attacker.hp == 0:
                attacker.defeated_until = self.world.minute + DEFEAT_RECOVERY_MINUTES
        # A defeated attacker does not level up into an instant resurrection.
        levels = self._award_xp(attacker, xp)
        if attacker.defeated_until is not None:
            attacker.hp = 0
        outcome = CombatOutcome(damage, counter, xp, looted, defender_dead, attacker.hp == 0, levels)
        self.world._emit("combat", attacker_id, defender_id, damage, counter, xp, looted, defender_dead)
        self.world.assert_invariants()
        return outcome
