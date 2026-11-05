"""Authenticated social view and ephemeral presence projections.

All social payloads are derived per requested actor. Never return another
account's unoffered gear, private inventory, gold or internal identifiers.
The owning MultiplayerGame holds the lock and mutable presence dictionaries;
this module only applies scoped social policies and projection formatting.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..systems.cooldowns import remaining
from .activity import activity_projection, vital_timers

if TYPE_CHECKING:
    from .multiplayer import MultiplayerGame


def presence_state(game: MultiplayerGame, actor_id: str, now: float) -> str:
    entry = game._presence.get(actor_id)
    if entry is None or now - entry[0] >= 90:
        return "offline"
    return "active" if entry[1] else "away"

def refresh_presence(game: MultiplayerGame) -> None:
    now = time.monotonic()
    changed = False
    for actor_id in game.names:
        current = game._presence_state(actor_id, now)
        if game._presence_status.get(actor_id, "offline") != current:
            game._presence_status[actor_id] = current
            changed = True
    if changed:
        game._revision += 1
        game._activity_changed.notify_all()

def annotate_presence(game: MultiplayerGame, projection: dict) -> None:
    game._refresh_presence()
    for user in projection["users"]:
        if user["kind"] == "human":
            user["presence"] = game._presence_status.get(user["id"], "offline")

def social_view(game: MultiplayerGame, actor_id: str,
                projection: dict | None = None) -> dict:
    """Account-scoped streaming data; never broadcast raw world state."""
    if projection is None:
        # An SSE update must never rebuild market, equipment, magic, housing,
        # and all other full-page state on every presence or chat revision.
        activity = activity_projection(game.world, actor_id, game.npc_names,
                                       game.names, game.event_times, True)
        projection = {
            "users": activity["users"], "events": activity["events"],
            "duel": activity["duel"], "last_duel": activity["last_duel"],
            "player": vital_timers(game.world.actors[actor_id], game.world.minute),
        }
    actor = game.world._actor(actor_id)
    game._annotate_presence(projection)
    chat = game.world.chat_system.view(actor_id)
    for channel in chat["channels"]:
        if channel["kind"] == "direct":
            channel["label"] = game.names.get(channel["target"], "Player")
    for message in chat["messages"]:
        message["sender_name"] = game.names.get(
            message["sender"], message["sender"])
    trades = game.world.trades_system.list_for(actor_id)
    for proposal in trades:
        proposal["maker_name"] = game.names.get(proposal["maker"], "Player")
        proposal["recipient_name"] = game.names.get(proposal["recipient"], "Player")
        for side in ("offer", "request"):
            # Offered equipment is visible to the recipient; requested
            # equipment details belong only to the requested owner.
            # A maker must not probe other people's gear by guessing IDs.
            can_inspect = side == "offer" or actor_id == proposal["recipient"]
            proposal[side + "_gear"] = [
                {"id": gid, "kind": game.world.gear[gid].kind,
                 "quality": game.world.gear[gid].quality,
                 "durability": game.world.gear[gid].durability}
                for gid in proposal[side]["gear_ids"]
                if can_inspect and gid in game.world.gear
            ]
    return {
        "actor_id": actor_id, "revision": game._revision,
        "chat": chat, "trades": trades, "minute": game.world.minute,
        "next_world_tick_seconds": game._next_world_tick_seconds(),
        "users": projection["users"], "events": projection["events"],
        "duel": projection["duel"], "last_duel": projection["last_duel"],
        "course_active": game.world.curriculum_system.view(actor_id)["active"],
        "player_status": {
            "hp": actor.hp, "max_hp": actor.max_hp,
            "stamina": actor.stamina, "max_stamina": actor.max_stamina,
            "mana": actor.magic.mana, "max_mana": actor.magic.max_mana,
            "gold": actor.gold, "city": actor.city,
            "defeated_until": actor.defeated_until,
            "health_next_sim_seconds": projection["player"]["health_next_sim_seconds"],
            "stamina_next_sim_seconds": projection["player"]["stamina_next_sim_seconds"],
            "mana_next_sim_seconds": projection["player"]["mana_next_sim_seconds"],
            "destination": actor.destination,
            "arrival_minute": actor.arrival_minute,
            "cooldowns": {
                name: {"remaining_minutes": remaining(
                    actor, name, game.world.minute), "max_minutes": 1440}
                for name in ("job", "food", "potion")
            },
        },
    }
