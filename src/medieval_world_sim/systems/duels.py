"""Replayable turn-based duels against NPCs and auto-defending players."""
from __future__ import annotations
import secrets
from ..core.entities import DuelState
from ..core.transactions import transfer_gold
from ..errors import ActionError
from .combat import DEFEAT_RECOVERY_MINUTES, GUARD_STAMINA

MAGIC_STAMINA_COST = 6
MAX_PVP_ROUNDS = 10

def _who(actor):
    # Names are account metadata; project the marker into a display name later.
    return "[[" + actor.id + "]]"


def _attack_text(attacker, defender, weapon, damage, critical=False, blocked=0):
    source, target = _who(attacker), _who(defender)
    attack = {"fists": "punched", "dagger": "stabbed with a dagger",
              "sword": "swung a sword", "axe": "swung an axe",
              "bow": "shot an arrow"}.get(weapon.lower(), "attacked with " + weapon.lower())
    if damage == 0:
        if blocked:
            return f"{target} blocked {source}'s attack ({blocked} damage absorbed)"
        return f"{source} {attack} but missed {target}"
    detail = f" ({blocked} blocked)" if blocked else ""
    if critical:
        return f"{source} {attack}, critically hitting {target} for {damage} damage{detail}"
    return f"{source} {attack}, dealing {damage} damage to {target}{detail}"


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
        war_id = w.war_system.duel_context(attacker_id, defender_id)
        if attacker.kind != "human" or defender.kind not in ("human", "npc"):
            raise ActionError("Only player characters may initiate duels")
        if any(attacker_id in (d.attacker_id, d.defender_id, *d.assistants) or
               defender_id in (d.attacker_id, d.defender_id, *d.assistants)
               for d in w.state.duels.values()):
            raise ActionError("A participant is already in combat")
        entrance_cost = 0  # Only an actual combat move spends stamina.
        ward = attacker.magic.ward_charge
        attacker.magic.ward_charge = 0
        w.state.last_duels.pop(attacker_id, None)
        w.state.duels[attacker_id] = DuelState(
            attacker_id, defender_id, pending_ward=ward, war_id=war_id)
        w._emit("duel_started", attacker_id, defender_id, entrance_cost)
        return {"opponent_id": defender_id, "stamina_spent": entrance_cost}

    def _finish(self, duel, winner, loser, outcome: str) -> dict:
        w = self.world
        gold = 0
        war_honor_attacker = 0
        war_honor_defender = 0
        if duel.war_id is not None:
            if outcome in ("won", "lost", "fled", "opponent_fled"):
                # A war loss routes a fighter; no ordinary hospital or gold theft.
                actual_winner = (w.actors[duel.defender_id] if outcome == "fled"
                                 else w.actors[duel.attacker_id] if outcome == "opponent_fled"
                                 else winner)
                actual_loser = (w.actors[duel.attacker_id] if outcome == "fled"
                                else w.actors[duel.defender_id] if outcome == "opponent_fled"
                                else loser)
                war = w.state.wars[duel.war_id]
                if war.status == "live":
                    ledger = war.honor
                    before = ledger.get(actual_winner.id, 0)
                    w.war_system.hit(duel.war_id, actual_winner.id, actual_loser.id,
                                     tuple(duel.assistants),
                                     award_honor=outcome in ("won", "lost"))
                    earned = ledger.get(actual_winner.id, 0) - before
                    if actual_winner.id == duel.attacker_id:
                        war_honor_attacker = earned
                    else:
                        war_honor_defender = earned
                # A duel finishing after the war ends must still close safely,
                # without ordinary gold theft or late Honor.
                actual_loser.hp = actual_loser.max_hp
                w._emit("duel_finished", actual_winner.id, actual_loser.id, 0, 0)
        elif outcome in ("won", "lost"):
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
                  "role": "attacker", "war_id": duel.war_id,
                  "war_honor": war_honor_attacker}
        w.state.last_duels[duel.attacker_id] = result
        defender = w.actors[duel.defender_id]
        if defender.kind == "human":
            reverse = {"won": "lost", "lost": "won", "draw": "draw",
                       "fled": "opponent_fled", "opponent_fled": "fled"}[outcome]
            w.state.last_duels[defender.id] = {
                "outcome": reverse, "opponent_id": duel.attacker_id,
                "gold": gold, "xp": 0, "rounds": duel.round,
                "log": list(duel.log), "role": "defender",
                "war_id": duel.war_id, "war_honor": war_honor_defender,
            }
        del w.state.duels[duel.attacker_id]
        return result

    def turn(self, attacker_id: str, move: str, node_id: str) -> dict:
        w = self.world
        duel = w.state.duels.get(attacker_id)
        if duel is None:
            raise ActionError("No active duel")
        valid_moves = ("strike", "fists", "dagger", "guard", "cast")
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
            label, slot, stamina_spent = w.combat.melee_option(attacker, move)
            if attacker.stamina < stamina_spent:
                raise ActionError(f"Not enough stamina for {label.lower()} attack")
            attacker.stamina -= stamina_spent
            damage, critical = w.combat.duel_strike(attacker, defender, slot or "unarmed")
            description = _attack_text(attacker, defender, label, damage, critical)
            if damage and duel.war_id and duel.assistants and defender.hp > 0:
                assist_damage = min(defender.hp, 2 * len(duel.assistants))
                defender.hp -= assist_damage
                damage += assist_damage
                description += f"; guildmates added {assist_damage} damage"
        elif move == "guard":
            if attacker.stamina < GUARD_STAMINA:
                raise ActionError("Not enough stamina to guard")
            attacker.stamina -= GUARD_STAMINA
            stamina_spent = GUARD_STAMINA
            damage = 0
            protection = 6
            description = f"{_who(attacker)} braced for the next attack ({stamina_spent} stamina)"
        else:
            # Enchantment and divination create a physical strike too.
            # Charge the same main-weapon cost, in addition to their mana.
            node = w.spell_system._ready(attacker, node_id)
            stamina_spent = MAGIC_STAMINA_COST
            if node.school in ("enchantment", "divination"):
                _, _, swing_cost = w.combat.melee_option(attacker, "strike")
                stamina_spent += swing_cost
            if attacker.stamina < stamina_spent:
                raise ActionError("Not enough stamina to cast this combat spell")
            attacker.stamina -= stamina_spent
            damage, protection, description = w.spell_system.combat_cast(attacker, defender, node_id)
            description = f"{_who(attacker)} cast {node_id.split('.')[-1].replace('_', ' ')}: {description} ({stamina_spent} stamina)"
        duel.round += 1
        if move in ("strike", "fists", "dagger") or (move == "cast" and damage > 0):
            duel.first_attack = True
        duel.xp_earned += max(1, damage // 4) if damage else 0
        retaliation = 0
        response = ""
        if defender.hp:
            # Defensive reactions never consume stamina, even if armed. A
            # secondary dagger can serve as a fallback defensive weapon.
            defense_slot = "weapon" if defender.equipped.get("weapon") else (
                "secondary" if defender.equipped.get("secondary") else "unarmed")
            gear_id = defender.equipped.get(defense_slot)
            label = w.gear[gear_id].kind if gear_id is not None else "fists"
            hp_before = attacker.hp
            retaliation, counter_critical = w.combat.duel_strike(defender, attacker, defense_slot)
            blocked = min(retaliation, protection + duel.pending_ward)
            retaliation -= blocked
            attacker.hp = max(0, hp_before - retaliation)
            duel.pending_ward = 0
            response = _attack_text(defender, attacker, label, retaliation, counter_critical, blocked)
        duel.log.append(f"Round {duel.round}: {description}." +
                        (f" {response}." if response else ""))
        duel.log = duel.log[-12:]
        w._emit("duel_round", attacker_id, defender.id, duel.round, move, damage, retaliation)
        if defender.hp == 0:
            return self._finish(duel, attacker, defender, "won")
        if attacker.hp == 0:
            return self._finish(duel, defender, attacker, "lost")
        # Bound PvP duel duration so neither party is held indefinitely.
        if defender.kind == "human" and duel.round >= MAX_PVP_ROUNDS:
            duel.log.append("The tenth round ends in a draw. Both fighters withdraw.")
            w._emit("duel_draw", duel.attacker_id, duel.defender_id, duel.round)
            return self._finish(duel, attacker, defender, "draw")
        return {"outcome": "ongoing", "round": duel.round, "damage": damage,
                "stamina_spent": stamina_spent,
                "retaliation": retaliation, "message": duel.log[-1]}

    def flee(self, actor_id: str) -> dict:
        """One escape attempt consumes a round; failed attempts invite a hit.

        A cryptographic coin flip is captured for deterministic journal replay.
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
        roll = getattr(w, "_flee_success", None)
        if roll is None:
            roll = bool(secrets.randbits(1))
        duel.round += 1
        w._emit("duel_flee_attempt", duel.attacker_id, duel.defender_id,
                actor_id, duel.round, bool(roll))
        if roll:
            duel.log.append(f"Round {duel.round}: {_who(fleeing)} escaped successfully.")
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
        gear_id = pursuer.equipped.get(slot)
        label = w.gear[gear_id].kind if gear_id is not None else "fists"
        damage, critical = w.combat.duel_strike(pursuer, fleeing, slot)
        duel.log.append(
            f"Round {duel.round}: {_who(fleeing)} failed to escape. "
            + _attack_text(pursuer, fleeing, label, damage, critical) + "."
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
