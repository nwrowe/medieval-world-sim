"""School-based spell effects. Unlock and mana rules stay with MagicSystem."""
from __future__ import annotations
from ..errors import ActionError

class SpellSystem:
    def __init__(self, world):
        self.world = world

    def _ready(self, actor, node_id):
        node = self.world.magic_system._node(node_id)
        if node.tier == 0 or not self.world.magic_system._active(actor, node):
            raise ActionError("Spell must be learned and, if specialized, attuned")
        if (not getattr(self.world, "_legacy_spell_mastery_rules", False)
                and not self.world.magic_system._castable(actor, node)):
            raise ActionError("Master the spell's tier to 100/100 before casting")
        if actor.magic.mana < node.mana_cost:
            raise ActionError("Insufficient mana to cast spell")
        return node

    def combat_cast(self, caster, opponent, node_id):
        """Return damage, protection, narrative for the current combat turn."""
        node = self._ready(caster, node_id)
        rank, school = node.tier, node.school
        damage = protection = 0
        if school == "restoration":
            amount = min(caster.max_hp - caster.hp, 5 + 3 * rank)
            if amount <= 0:
                raise ActionError("Already at full health")
            caster.hp += amount
            message = f"Healed {amount} HP"
        elif school == "warding":
            protection = 3 + 2 * rank
            message = f"Raised a ward absorbing {protection} damage"
        elif school == "elemental":
            damage = min(opponent.hp, 4 + 2 * rank)
            opponent.hp -= damage
            message = f"Elemental blast dealt {damage} damage"
        elif school == "enchantment":
            damage = self.world.combat._strike(caster, opponent)
            extra = min(opponent.hp, rank + 2)
            opponent.hp -= extra
            damage += extra
            message = f"Runed strike dealt {damage} damage"
        elif school == "divination":
            damage = self.world.combat._strike(caster, opponent)
            protection = 2 + 2 * rank
            message = f"Foreseen strike dealt {damage}; anticipated retaliation"
        elif school == "alchemy":
            damage = min(opponent.hp, 3 + 2 * rank)
            opponent.hp -= damage
            caster.hp = min(caster.max_hp, caster.hp + rank)
            message = f"Alchemical blast dealt {damage} damage"
        else:
            raise ActionError("No combat spell effect")
        caster.magic.mana -= node.mana_cost
        self.world._emit("spell_cast", caster.id, node.id, "duel", damage or protection, message)
        return damage, protection, message

    def field_cast(self, actor_id: str, node_id: str) -> dict:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        node = self._ready(actor, node_id)
        rank, amount = node.tier, 0
        if node.school == "restoration":
            amount = min(actor.max_hp - actor.hp, 5 + 3 * rank)
            if amount == 0:
                raise ActionError("Already at full health")
            actor.hp += amount
            message = f"Restored {amount} HP"
        elif node.school == "warding":
            if actor.magic.ward_charge:
                raise ActionError("A protective ward is already prepared")
            amount = actor.magic.ward_charge = 3 + 2 * rank
            message = f"Prepared a {amount}-point ward for your next duel"
        elif node.school == "divination":
            if node.id in ("divination.pathfinder", "divination.wayfinder"):
                if actor.magic.road_charm:
                    raise ActionError("A travel charm is already prepared")
                amount = actor.magic.road_charm = 20 if rank == 3 else 30
                message = f"Next road journey will be {amount}% shorter"
            else:
                nearby = [a for a in self.world.actors.values() if a.id != actor.id
                          and a.kind == "npc" and a.city == actor.city and a.hp > 0]
                amount = len(nearby)
                message = (f"Foresee {amount} nearby adventurers; richest purse: "
                           f"{max((a.gold for a in nearby), default=0)} gold")
        elif node.school == "enchantment":
            worn = [self.world.gear[g] for g in actor.equipped.values()
                    if self.world.gear[g].durability < self.world.gear[g].max_durability]
            if not worn:
                raise ActionError("Equip damaged gear before repairing with a rune")
            item = worn[0]
            amount = min(item.max_durability - item.durability, 2 + rank)
            item.durability += amount
            message = f"Restored {amount} durability to {item.kind.replace('_', ' ')}"
        elif node.school == "elemental":
            if actor.inventory.get("iron_ore", 0) < 2 or actor.inventory.get("coal", 0) < 1:
                raise ActionError("Forge magic needs 2 iron ore and 1 coal")
            actor.inventory["iron_ore"] -= 2
            actor.inventory["coal"] -= 1
            amount = 1
            self.world._add(actor, "steel", 1)
            message = "Forged 1 steel from 2 iron ore and 1 coal"
        elif node.school == "alchemy":
            if actor.inventory.get("herbs", 0) < 2:
                raise ActionError("Alchemy needs 2 herbs")
            actor.inventory["herbs"] -= 2
            amount = 1
            self.world._add(actor, "healing_potion", 1)
            message = "Brewed a healing potion from 2 herbs"
        else:
            raise ActionError("No field spell effect")
        actor.magic.mana -= node.mana_cost
        self.world._emit("spell_cast", actor.id, node.id, "field", amount, message)
        return {"node_id": node.id, "effect": node.school, "amount": amount, "message": message}
