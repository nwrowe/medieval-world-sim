"""Replayable turn-based duels against NPCs and auto-defending players."""
from __future__ import annotations
import secrets
from ..core.entities import DuelState
from ..core.transactions import transfer_gold
from ..errors import ActionError
from .combat import ATTACK_STAMINA_COST, DEFEAT_RECOVERY_MINUTES, GUARD_STAMINA

MAGIC_STAMINA_COST = 6
MAX_PVP_ROUNDS = 10

class DuelSystem:
    def __init__(self, world):
        self.world = world

    def start(self, attacker_id: str, defender_id: str) -> dict:
        w = self.world
        if attacker_id == defender_id:
            raise ActionError("Cannot attack yourself")
        attacker, defender = w._actor(attacker_id), w._actor(defender_id)
        if w._at_city(attacker) != w._at_city(defender):
            raise ActionError("Target must be in your city")
        if attacker.kind != "human" or defender.kind not in ("human", "npc"):
            raise ActionError("Only player characters may initiate duels")
        if any(attacker_id in (d.attacker_id, d.defender_id) or
               defender_id in (d.attacker_id, d.defender_id)
               for d in w.state.duels.values()):
            raise ActionError("A participant is already in combat")
        legacy = getattr(w, "_legacy_duel_rules", False)
        if legacy and attacker.stamina < ATTACK_STAMINA_COST:
            raise ActionError("Not enough stamina to initiate combat")
        entrance_cost = ATTACK_STAMINA_COST if legacy else 0
        attacker.stamina -= entrance_cost
        ward = attacker.magic.ward_charge
        attacker.magic.ward_charge = 0
        w.state.last_duels.pop(attacker_id, None)
        w.state.duels[attacker_id] = DuelState(attacker_id, defender_id, pending_ward=ward)
        w._emit("duel_started", attacker_id, defender_id, entrance_cost)
        return {"opponent_id": defender_id, "stamina_spent": entrance_cost}

    def _finish(self, duel, winner, loser, outcome: str) -> dict:
        w = self.world
        gold = 0
        if outcome in ("won", "lost"):
            loser.hp = 0
            loser.defeated_until = w.minute + DEFEAT_RECOVERY_MINUTES
            gold = loser.gold * 5 // 100
            transfer_gold(w, loser, winner, gold)
            w._emit("duel_finished", winner.id, loser.id, gold, DEFEAT_RECOVERY_MINUTES)
        xp = duel.xp_earned + (5 if outcome == "won" else 0)
        if xp:
            attacker = w.actors[duel.attacker_id]
            trained = w.housing_system.training_xp(attacker, xp, "combat")
            w.combat._award_xp(attacker, trained)
            if attacker.defeated_until is not None:
                attacker.hp = 0
        result = {"outcome": outcome, "opponent_id": duel.defender_id,
                  "gold": gold, "xp": xp, "rounds": duel.round, "log": list(duel.log),
                  "role": "attacker"}
        w.state.last_duels[duel.attacker_id] = result
        defender = w.actors[duel.defender_id]
        if defender.kind == "human":
            reverse = {"won": "lost", "lost": "won", "draw": "draw",
                       "fled": "opponent_fled", "opponent_fled": "fled"}[outcome]
            w.state.last_duels[defender.id] = {
                "outcome": reverse, "opponent_id": duel.attacker_id,
                "gold": gold, "xp": 0, "rounds": duel.round,
                "log": list(duel.log), "role": "defender",
            }
        del w.state.duels[duel.attacker_id]
        return result

    def turn(self, attacker_id: str, move: str, node_id: str) -> dict:
        w = self.world
        duel = w.state.duels.get(attacker_id)
        if duel is None:
            raise ActionError("No active duel")
        legacy = getattr(w, "_legacy_duel_rules", False)
        valid_moves = ("strike", "guard", "cast") if legacy else (
            "strike", "fists", "dagger", "guard", "cast")
        if move not in valid_moves or not isinstance(node_id, str):
            raise ActionError("Unknown combat move")
        if move != "cast" and node_id:
            raise ActionError("Only spell casting accepts a spell ID")
        attacker, defender = w.actors[duel.attacker_id], w.actors[duel.defender_id]
        if attacker.hp <= 0 or defender.hp <= 0:
            raise ActionError("Duel has invalid combatants")
        protection = 0
        stamina_spent = 0
        if move in ("strike", "fists", "dagger"):
            if legacy:
                damage = w.combat._strike(attacker, defender)
                description = f"You strike for {damage} damage"
            else:
                label, slot, stamina_spent = w.combat.melee_option(attacker, move)
                if getattr(w, "_legacy_guard_rules", False):
                    # Ruleset 7 recorded the original fists/dagger costs.
                    if move == "fists" or (move == "strike" and slot is None):
                        stamina_spent = 1
                    elif move == "dagger":
                        stamina_spent = 2
                    elif move == "strike" and slot == "weapon":
                        kind = w.gear[attacker.equipped["weapon"]].kind
                        stamina_spent = {"sword": 5, "axe": 7, "bow": 4}.get(kind, 5)
                if attacker.stamina < stamina_spent:
                    raise ActionError(f"Not enough stamina for {label.lower()} attack")
                attacker.stamina -= stamina_spent
                damage = w.combat._strike(attacker, defender, slot or "unarmed")
                description = f"{label} attack costs {stamina_spent} stamina and deals {damage} damage"
        elif move == "guard":
            if not getattr(w, "_legacy_guard_rules", False):
                if attacker.stamina < GUARD_STAMINA:
                    raise ActionError("Not enough stamina to guard")
                attacker.stamina -= GUARD_STAMINA
                stamina_spent = GUARD_STAMINA
            damage = 0
            protection = 6
            description = f"You brace for the next attack ({stamina_spent} stamina)"
        else:
            # Enchantment and divination create a physical strike too.
            # Charge the same main-weapon cost, in addition to their mana.
            node = w.spell_system._ready(attacker, node_id)
            if not getattr(w, "_legacy_guard_rules", False):
                stamina_spent = MAGIC_STAMINA_COST
                if node.school in ("enchantment", "divination"):
                    _, _, swing_cost = w.combat.melee_option(attacker, "strike")
                    stamina_spent += swing_cost
                if attacker.stamina < stamina_spent:
                    raise ActionError("Not enough stamina to cast this combat spell")
                attacker.stamina -= stamina_spent
            damage, protection, description = w.spell_system.combat_cast(attacker, defender, node_id)
            if stamina_spent:
                description += f" ({stamina_spent} stamina)"
        duel.round += 1
        if move in ("strike", "fists", "dagger") or (move == "cast" and damage > 0):
            duel.first_attack = True
        duel.xp_earned += max(1, damage // 4) if damage else 0
        retaliation = 0
        if defender.hp:
            # Defensive reactions never consume stamina, even if armed. A
            # secondary dagger can serve as a fallback defensive weapon.
            defense_slot = "weapon" if defender.equipped.get("weapon") else (
                "secondary" if defender.equipped.get("secondary") else "unarmed")
            retaliation = w.combat._strike(defender, attacker, defense_slot)
            blocked = min(retaliation, protection + duel.pending_ward)
            attacker.hp = min(attacker.max_hp, attacker.hp + blocked)
            retaliation -= blocked
            duel.pending_ward = 0
        duel.log.append(f"Round {duel.round}: {description}. Opponent dealt {retaliation} damage.")
        duel.log = duel.log[-12:]
        w._emit("duel_round", attacker_id, defender.id, duel.round, move, damage, retaliation)
        if defender.hp == 0:
            return self._finish(duel, attacker, defender, "won")
        if attacker.hp == 0:
            return self._finish(duel, defender, attacker, "lost")
        # Historical NPC duels are intentionally unchanged. PvP duels have a
        # fixed upper bound so neither party can be held indefinitely.
        if defender.kind == "human" and duel.round >= MAX_PVP_ROUNDS:
            duel.log.append("The tenth round ends in a draw. Both fighters withdraw.")
            w._emit("duel_draw", duel.attacker_id, duel.defender_id, duel.round)
            return self._finish(duel, attacker, defender, "draw")
        return {"outcome": "ongoing", "round": duel.round, "damage": damage,
                "stamina_spent": stamina_spent,
                "retaliation": retaliation, "message": duel.log[-1]}

    def flee(self, actor_id: str) -> dict:
        """One escape attempt consumes a round; failed attempts invite a hit.

        New attempts use a server-supplied cryptographic coin flip, captured
        in the command journal for exact replay. Older journal entries keep
        the historical guaranteed-escape rule.
        """
        w = self.world
        duel = w.state.duels.get(actor_id)
        attacker_fleeing = duel is not None
        if duel is None:
            duel = next((d for d in w.state.duels.values()
                         if d.defender_id == actor_id and
                         w.actors[actor_id].kind == "human"), None)
        if duel is None:
            raise ActionError("No active duel")
        attacker = w.actors[duel.attacker_id]
        defender = w.actors[duel.defender_id]
        fleeing = attacker if attacker_fleeing else defender
        pursuer = defender if attacker_fleeing else attacker
        if getattr(w, "_legacy_flee_rules", False):
            if attacker_fleeing:
                w._emit("duel_fled", actor_id, duel.defender_id)
                return self._finish(duel, attacker, defender, "fled")
            w._emit("duel_defender_fled", duel.attacker_id, duel.defender_id)
            self._finish(duel, attacker, defender, "opponent_fled")
            return dict(w.state.last_duels[actor_id])

        roll = getattr(w, "_flee_success", None)
        if roll is None:
            roll = bool(secrets.randbits(1))
        duel.round += 1
        w._emit("duel_flee_attempt", duel.attacker_id, duel.defender_id,
                actor_id, duel.round, bool(roll))
        if roll:
            duel.log.append(f"Round {duel.round}: {fleeing.id} escaped successfully.")
            duel.log = duel.log[-12:]
            if attacker_fleeing:
                w._emit("duel_fled", actor_id, defender.id)
                return self._finish(duel, attacker, defender, "fled")
            w._emit("duel_defender_fled", attacker.id, defender.id)
            self._finish(duel, attacker, defender, "opponent_fled")
            return dict(w.state.last_duels[actor_id])

        # An unsuccessful attempt is a lost offensive turn: the other
        # combatant takes an automatic, zero-stamina response.
        slot = ("weapon" if pursuer.equipped.get("weapon") else
                "secondary" if pursuer.equipped.get("secondary") else "unarmed")
        damage = w.combat._strike(pursuer, fleeing, slot)
        duel.log.append(
            f"Round {duel.round}: {fleeing.id} failed to escape; "
            f"{pursuer.id} counterattacked for {damage} damage."
        )
        duel.log = duel.log[-12:]
        if fleeing.hp <= 0:
            if attacker_fleeing:
                return self._finish(duel, defender, attacker, "lost")
            self._finish(duel, attacker, defender, "won")
            return dict(w.state.last_duels[actor_id])
        if defender.kind == "human" and duel.round >= MAX_PVP_ROUNDS:
            duel.log.append("The tenth round ends in a draw. Both fighters withdraw.")
            w._emit("duel_draw", duel.attacker_id, duel.defender_id, duel.round)
            self._finish(duel, attacker, defender, "draw")
            return (dict(w.state.last_duels[actor_id]) if not attacker_fleeing
                    else dict(w.state.last_duels[attacker.id]))
        return {"outcome": "ongoing", "round": duel.round,
                "escape_success": False, "retaliation": damage,
                "message": duel.log[-1]}
