"""Replayable turn-based duels against NPC actors."""
from __future__ import annotations
from ..core.entities import DuelState
from ..core.transactions import transfer_gold
from ..errors import ActionError
from .combat import ATTACK_STAMINA_COST, DEFEAT_RECOVERY_MINUTES

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
        if defender.kind != "npc":
            raise ActionError("Local turn-based fights currently require NPC targets")
        if attacker.stamina < ATTACK_STAMINA_COST:
            raise ActionError("Not enough stamina to initiate combat")
        if any(defender_id in (d.attacker_id, d.defender_id) for d in w.state.duels.values()):
            raise ActionError("Opponent is already in combat")
        attacker.stamina -= ATTACK_STAMINA_COST
        ward = attacker.magic.ward_charge
        attacker.magic.ward_charge = 0
        w.state.last_duels.pop(attacker_id, None)
        w.state.duels[attacker_id] = DuelState(attacker_id, defender_id, pending_ward=ward)
        w._emit("duel_started", attacker_id, defender_id, ATTACK_STAMINA_COST)
        return {"opponent_id": defender_id, "stamina_spent": ATTACK_STAMINA_COST}

    def _finish(self, duel, winner, loser, outcome: str) -> dict:
        w = self.world
        gold = 0
        if outcome != "fled":
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
                  "gold": gold, "xp": xp, "rounds": duel.round, "log": list(duel.log)}
        w.state.last_duels[duel.attacker_id] = result
        del w.state.duels[duel.attacker_id]
        return result

    def turn(self, attacker_id: str, move: str, node_id: str) -> dict:
        w = self.world
        duel = w.state.duels.get(attacker_id)
        if duel is None:
            raise ActionError("No active duel")
        if move not in ("strike", "guard", "cast") or not isinstance(node_id, str):
            raise ActionError("Unknown combat move")
        if move != "cast" and node_id:
            raise ActionError("Only spell casting accepts a spell ID")
        attacker, defender = w.actors[duel.attacker_id], w.actors[duel.defender_id]
        if attacker.hp <= 0 or defender.hp <= 0:
            raise ActionError("Duel has invalid combatants")
        protection = 0
        if move == "strike":
            damage = w.combat._strike(attacker, defender)
            description = f"You strike for {damage} damage"
        elif move == "guard":
            damage = 0
            protection = 6
            description = "You brace for the next attack"
        else:
            damage, protection, description = w.spell_system.combat_cast(attacker, defender, node_id)
        duel.round += 1
        duel.xp_earned += max(1, damage // 4) if damage else 0
        retaliation = 0
        if defender.hp:
            retaliation = w.combat._strike(defender, attacker)
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
        return {"outcome": "ongoing", "round": duel.round, "damage": damage,
                "retaliation": retaliation, "message": duel.log[-1]}

    def flee(self, attacker_id: str) -> dict:
        duel = self.world.state.duels.get(attacker_id)
        if duel is None:
            raise ActionError("No active duel")
        self.world._emit("duel_fled", attacker_id, duel.defender_id)
        return self._finish(duel, self.world.actors[attacker_id],
                            self.world.actors[duel.defender_id], "fled")
