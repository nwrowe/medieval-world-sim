"""Combat actions share the regional world's authoritative state and gear.

No randomness or opponent-created gold. The defending combatant can counterstrike.
This intentionally small ruleset is designed to expose equipment utility and wear.
"""
from dataclasses import dataclass

from .equipment import GEAR, effective_attack, effective_defense
from .errors import ActionError


ATTACK_COOLDOWN_MINUTES = 5
DEFEAT_RECOVERY_MINUTES = 60
MAX_GOLD_LOOT = 10


@dataclass(frozen=True)
class CombatOutcome:
    damage: int
    retaliation: int
    xp_gained: int
    gold_looted: int
    opponent_defeated: bool
    attacker_defeated: bool


class CombatMixin:
    def buy_starter_gear(self, actor_id: str, kind: str) -> int:
        actor = self._actor(actor_id)
        if self._at_city(actor) != "crownreach":
            raise ActionError("Starter equipment is sold only in the capital")
        if kind not in GEAR:
            raise ActionError("Not a durable equipment item")
        price = GEAR[kind].base_value
        if actor.gold < price or not self._space_for(actor, kind, 1):
            raise ActionError("Insufficient gold or carrying capacity")
        actor.gold -= price
        self.crown_gold += price
        gear = self._mint_gear(actor, kind, 10, "capital_starter_vendor")
        self._emit("starter_purchase", actor_id, gear.id, kind, price)
        self.assert_invariants()
        return gear.id

    def equip(self, actor_id: str, gear_id: int) -> None:
        actor = self._actor(actor_id)
        self._at_city(actor)
        if gear_id not in actor.gear_ids:
            raise ActionError("Actor does not own equipment")
        gear = self.gear[gear_id]
        if gear.durability <= 0:
            raise ActionError("Broken equipment")
        slot = GEAR[gear.kind].slot
        actor.equipped[slot] = gear_id
        self._emit("equipped", actor_id, gear_id, slot)
        self.assert_invariants()

    def unequip(self, actor_id: str, slot: str) -> None:
        actor = self._actor(actor_id)
        self._at_city(actor)
        if slot not in actor.equipped:
            raise ActionError("Slot already empty")
        del actor.equipped[slot]
        self._emit("unequipped", actor_id, slot)
        self.assert_invariants()

    def _strike(self, attacker, defender) -> int:
        weapon_id = attacker.equipped.get("weapon")
        if weapon_id is None:
            raise ActionError("Attacker must equip a weapon")
        weapon = self.gear[weapon_id]
        armor_ids = [defender.equipped.get("body"), defender.equipped.get("offhand")]
        defense = sum(
            effective_defense(self.gear[g_id])
            for g_id in armor_ids if g_id is not None
        )
        damage = max(1, effective_attack(weapon) - defense // 2)
        defender.hp = max(0, defender.hp - damage)
        self._wear(attacker, weapon_id)
        for g_id in armor_ids:
            if g_id is not None:
                self._wear(defender, g_id)
        return damage

    def _wear(self, owner, gear_id: int) -> None:
        item = self.gear[gear_id]
        item.durability -= 1
        if item.durability == 0:
            owner.gear_ids.remove(gear_id)
            for slot, equipped_id in list(owner.equipped.items()):
                if equipped_id == gear_id:
                    del owner.equipped[slot]
            del self.gear[gear_id]
            self._emit("gear_broken", owner.id, gear_id, item.kind)

    def attack(self, attacker_id: str, defender_id: str) -> CombatOutcome:
        attacker = self._actor(attacker_id)
        defender = self._actor(defender_id)
        if attacker_id == defender_id:
            raise ActionError("Cannot attack yourself")
        if self._at_city(attacker) != self._at_city(defender):
            raise ActionError("Both participants must be in the same city")
        if attacker.hp <= 0 or defender.hp <= 0:
            raise ActionError("Cannot fight while defeated")
        if self.minute < attacker.attack_ready_minute:
            raise ActionError("Attack cooldown active")
        if attacker.equipped.get("weapon") is None:
            raise ActionError("Equip a weapon first")
        if defender.kind == "npc":
            if not defender.hostile:
                raise ActionError("This NPC is not an enemy")
        elif not (attacker.pvp_opt_in and defender.pvp_opt_in):
            raise ActionError("Both players must opt into PvP")

        damage = self._strike(attacker, defender)
        attacker.attack_ready_minute = self.minute + ATTACK_COOLDOWN_MINUTES
        xp = 1 + damage // 4
        attacker.combat_xp += xp
        counter = 0
        looted = 0
        defender_dead = defender.hp == 0
        if defender_dead:
            defender.defeated_until = self.minute + DEFEAT_RECOVERY_MINUTES
            # Explicit transfer of the defender's money, never minting rewards.
            looted = min(MAX_GOLD_LOOT, defender.gold)
            defender.gold -= looted
            attacker.gold += looted
        elif defender.equipped.get("weapon") is not None:
            counter = self._strike(defender, attacker)
            if attacker.hp == 0:
                attacker.defeated_until = self.minute + DEFEAT_RECOVERY_MINUTES
        outcome = CombatOutcome(damage, counter, xp, looted, defender_dead, attacker.hp == 0)
        self._emit("combat", attacker_id, defender_id, damage, counter, xp, looted, defender_dead)
        self.assert_invariants()
        return outcome
