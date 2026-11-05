"""Lightweight, actor-authorized live event projection.

The live stream needs only public character state, the actor's Chronicle,
and current duel. It must not calculate merchant price tables, housing,
equipment catalogs, course lists or private inventories of other accounts.
This single implementation is shared with the full snapshot to prevent
privacy and behavior drift.
"""
from __future__ import annotations

from ..systems.cooldowns import remaining
from .chronicle import TRADE_EVENTS, COMBAT_EVENTS, _friendly_event


def vital_timers(actor, now: int) -> dict:
    """Remaining simulated seconds to the next *increase* in each vital."""
    return {
        "health_next_sim_seconds":
            (3 - now % 3) * 60 if actor.hp < actor.max_hp else None,
        "stamina_next_sim_seconds":
            (5 - now % 5) * 60 if actor.stamina < actor.max_stamina else None,
        "mana_next_sim_seconds":
            (10 - now % 10) * 60 if actor.magic.mana < actor.magic.max_mana else None,
    }


def activity_projection(w, actor_id: str, name: str, npc_names: dict[str, str],
                        human_names: dict[str, str], event_times: dict[int, str],
                        multiplayer: bool) -> dict:
    """Return public roster, private actor events, duel and vitals countdowns."""
    actor = w.actors[actor_id]
    now = w.minute
    is_traveling = actor.destination is not None

    gear_kinds = {}
    equipped_kinds = {}
    rendered_events = []
    for event in w.events:
        # A player's Chronicle must never expose another account's private
        # purchases, inventory changes, employment or other action history.
        if multiplayer:
            data = event.data
            participants = (
                (data.get("maker_id"), data.get("recipient_id"))
                if event.kind in TRADE_EVENTS else
                (data.get("attacker_id"), data.get("defender_id"),
                 data.get("winner_id"), data.get("loser_id"))
                if event.kind in COMBAT_EVENTS else
                (data.get("actor_id"),)
            )
            if actor_id not in participants:
                continue
        info = event.data
        if event.kind in ("starter_purchase", "gear_created"):
            gear_kinds[info.get("gear_id")] = info.get("item")
        if event.kind == "equipped":
            prior_slot = info.get("slot")
            rendered = _friendly_event(
                event, gear_kinds=gear_kinds,
                equipped_kinds=equipped_kinds,
                recorded_at=event_times.get(event.event_id),
                human_names=human_names)
            equipped_kinds[prior_slot] = gear_kinds.get(info.get("gear_id"), prior_slot)
        else:
            rendered = _friendly_event(
                event, gear_kinds=gear_kinds,
                equipped_kinds=equipped_kinds,
                recorded_at=event_times.get(event.event_id),
                human_names=human_names)
            if event.kind == "unequipped":
                equipped_kinds.pop(info.get("slot"), None)
        rendered_events.append(rendered)
    duel = w.state.duels.get(actor_id)
    duel_role = "attacker" if duel else None
    if multiplayer and not duel:
        duel = next((d for d in w.state.duels.values()
                     if d.defender_id == actor_id), None)
        if duel:
            duel_role = "defender"
    active_duel = None
    if duel:
        opponent_id = (duel.defender_id if duel_role == "attacker"
                       else duel.attacker_id)
        foe = w.actors[opponent_id]
        active_duel = {
            "opponent_id": foe.id,
            "opponent_name": npc_names.get(
                foe.id, human_names.get(foe.id, foe.id)),
            "opponent_hp": foe.hp, "opponent_max_hp": foe.max_hp,
            "round": duel.round, "log": list(duel.log),
            "attack_started": duel.first_attack,
            "pending_ward": duel.pending_ward if duel_role == "attacker" else 0,
            "role": duel_role,
            "max_rounds": 10 if w.actors[duel.defender_id].kind == "human" else None,
        }
    characters = [{
        "id": actor_id, "name": name, "city": actor.city,
        "destination": actor.destination, "level": actor.level,
        "kind": "human", "hp": actor.hp, "max_hp": actor.max_hp,
        "can_attack": False, "recovering_minutes": max(0, (actor.defeated_until or 0) - now),
    }]
    for npc_id, npc_name in npc_names.items():
        npc = w.actors[npc_id]
        characters.append({
            "id": npc.id, "name": npc_name, "city": npc.city,
            "destination": npc.destination,
            "level": npc.level, "kind": "npc", "hp": npc.hp, "max_hp": npc.max_hp,
            "can_attack": (
                npc.city == actor.city and npc.destination is None
                and npc.hp > 0 and npc.defeated_until is None
                and actor.hp > 0 and actor.defeated_until is None and not is_traveling
                and active_duel is None and not any(
                    npc.id in (d.attacker_id, d.defender_id)
                    for d in w.state.duels.values())
            ),
            "recovering_minutes": max(0, (npc.defeated_until or 0) - now),
        })
    if multiplayer:
        for human_id, human_name in human_names.items():
            if human_id == actor_id:
                continue
            other = w.actors[human_id]
            characters.append({
                "id": other.id, "name": human_name, "city": other.city,
                "destination": other.destination,
                "level": other.level, "kind": "human",
                "hp": other.hp, "max_hp": other.max_hp,
                "can_attack": (
                    other.city == actor.city and other.destination is None
                    and other.hp > 0 and other.defeated_until is None
                and actor.hp > 0 and actor.defeated_until is None and not is_traveling
                    and active_duel is None and not any(
                        other.id in (d.attacker_id, d.defender_id)
                        for d in w.state.duels.values())
                ),
                "recovering_minutes": max(0, (other.defeated_until or 0) - now),
            })
    return {
        "users": characters,
        "events": rendered_events[-500:][::-1],
        "duel": active_duel,
        "last_duel": w.state.last_duels.get(actor_id),
        **vital_timers(actor, now),
    }
