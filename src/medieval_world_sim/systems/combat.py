"""Stamina-based, open-world combat with unarmed attacks and progression."""
from dataclasses import dataclass
from ..equipment import GEAR, effective_attack, effective_defense
from ..errors import ActionError
from ..core.transactions import transfer_gold

ATTACK_STAMINA_COST = 20
STAMINA_REGEN_MINUTES = 5
MAX_STAMINA = 100
DEFEAT_RECOVERY_MINUTES = 60
MAX_GOLD_LOOT = 10

# Turn-based combat expenditure occurs for an *initiated* melee swing only.
# Counterattacks are defensive reactions, regardless of their weapon.
SWING_STAMINA = {"fists": 2, "dagger": 3, "sword": 5, "axe": 7, "bow": 5}
GUARD_STAMINA = 2
WEAR_INTERVAL = 12
DEFAULT_WEAPON_STAMINA = 5
ARMOR_SLOTS = ("body", "offhand", "helm", "boots", "greaves", "gloves")


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
        transfer_gold(self.world, actor, None, price)
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

    def melee_option(self, actor, move: str) -> tuple[str, str | None, int]:
        """Return attack label, equipped slot and stamina cost, without mutation."""
        if move == "fists":
            return "Fists", None, SWING_STAMINA["fists"]
        if move == "dagger":
            gear_id = actor.equipped.get("secondary")
            if gear_id is None or self.world.gear[gear_id].kind != "dagger":
                raise ActionError("Equip a dagger in your secondary slot first")
            return "Dagger", "secondary", SWING_STAMINA["dagger"]
        if move == "strike":
            gear_id = actor.equipped.get("weapon")
            if gear_id is None:
                return "Fists", None, SWING_STAMINA["fists"]
            kind = self.world.gear[gear_id].kind
            return kind.replace("_", " ").title(), "weapon", SWING_STAMINA.get(
                kind, DEFAULT_WEAPON_STAMINA)
        raise ActionError("Unknown melee attack")

    def _strike(self, attacker, defender, weapon_slot: str = "weapon") -> int:
        weapon_id = attacker.equipped.get(weapon_slot)
        # Fists are always available; even an unarmed defender counterattacks.
        base_attack = effective_attack(self.world.gear[weapon_id]) if weapon_id is not None else 3
        armor_ids = [defender.equipped.get(slot) for slot in ARMOR_SLOTS]
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
        if getattr(self.world, "_legacy_equipment_wear", False):
            item.durability -= 1
        else:
            count = self.world.state.gear_wear.get(gear_id, 0) + 1
            if count < WEAR_INTERVAL:
                self.world.state.gear_wear[gear_id] = count
                return
            self.world.state.gear_wear.pop(gear_id, None)
            item.durability -= 1
        if item.durability == 0:
            self.world.state.gear_wear.pop(gear_id, None)
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
            transfer_gold(self.world, defender, attacker, looted)
            xp += 5  # Victory bonus, but no repeated reward while target is defeated.
        else:
            counter = self._strike(defender, attacker)
            if attacker.hp == 0:
                attacker.defeated_until = self.world.minute + DEFEAT_RECOVERY_MINUTES
        # A defeated attacker does not level up into an instant resurrection.
        xp = self.world.housing_system.training_xp(attacker, xp, "combat")
        levels = self._award_xp(attacker, xp)
        if attacker.defeated_until is not None:
            attacker.hp = 0
        outcome = CombatOutcome(damage, counter, xp, looted, defender_dead, attacker.hp == 0, levels)
        self.world._emit("combat", attacker_id, defender_id, damage, counter, xp, looted, defender_dead)
        self.world.assert_invariants()
        return outcome
