"""Read-only player-authorized projection of authoritative world state.

This is the sole single- and multi-account browser snapshot composer.
Never include another player's private economic or account state.
"""
from __future__ import annotations

from dataclasses import asdict

from ..catalog import CAPITAL, CITIES, RAW_RESOURCES, GOODS, PROCESSED_RESOURCES, CONSUMABLES
from ..core.engine import WorldEngine
from ..content.housing import HOMES, HOME_ORDER, FACILITIES, VEHICLES
from ..content.magic_tree import SCHOOLS
from ..equipment import GEAR, suggested_value, effective_attack, effective_defense
from ..systems.cooldowns import MAX_COOLDOWN_MINUTES, FOOD_MINUTES, POTION_MINUTES, remaining
from ..systems.track import HORSES, RACE_STAMINA_COST, RACE_ENTRY, RACE_COOLDOWN
from .chronicle import TRADE_EVENTS, COMBAT_EVENTS, _friendly_event

def activity_projection(w: WorldEngine, actor_id: str, name: str,
                        npc_names: dict[str, str], human_names: dict[str, str],
                        event_times: dict[int, str],
                        multiplayer: bool) -> tuple[list[dict], dict | None, list[dict]]:
    """Only account-visible Chronicle, duel and character summary data.

    This cheaper view is shared by the full page snapshot and SSE updates,
    so live activity never calculates all market quotes, housing or gear prices.
    """
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
    return rendered_events[-500:][::-1], active_duel, characters


from ..content.lineages import LINEAGES, active_trait


def world_snapshot(w: WorldEngine | None, actor_id: str, name: str,
                   npc_names: dict[str, str], human_names: dict[str, str],
                   event_times: dict[int, str], multiplayer: bool) -> dict:
    """Present one player's authorized view from a shared or single-player world.

    Never serialize another player's inventory, gold, work/battle stats or
    private Chronicle events into this response. Both modes use one projection
    to avoid duplicating gameplay/UI calculations.
    """
    if w is None:
        return {"started": False}
    actor = w.actors[actor_id]
    housing = w.housing_view(actor_id)
    is_traveling = actor.destination is not None
    now = w.minute
    cargo = sum(actor.inventory.values()) + len(actor.gear_ids)
    places = []
    for city_id, city in CITIES.items():
        discovered = city_id in actor.discovered_cities
        places.append({
            "id": city_id, "name": city.name if discovered else "Uncharted settlement",
            "discovered": discovered, "is_current": city_id == actor.city,
            "minutes": (0 if is_traveling or actor.hp <= 0 or actor.defeated_until is not None
                        else w.estimated_travel_minutes(actor_id, city_id)),
        })
    quote_list = [
        {**asdict(w.regional_quote(actor.city, item)),
         "locally_produced": item in CITIES[actor.city].deposits}
        for item in RAW_RESOURCES
    ]
    magic_nodes = [
        {**asdict(node), "prerequisites": list(node.prerequisites)}
        for node in w.magic_tree(actor_id)
    ]
    owned_gear = [
        {
            "id": gid, "kind": w.gear[gid].kind,
            "slot": GEAR[w.gear[gid].kind].slot,
            "quality": w.gear[gid].quality,
            "durability": w.gear[gid].durability,
            "max_durability": w.gear[gid].max_durability,
            "attack": effective_attack(w.gear[gid]),
            "defense": effective_defense(w.gear[gid]),
            "value": suggested_value(w.gear[gid]),
        }
        for gid in actor.gear_ids
    ]
    stored_gear_here = [
        {
            "id": gid, "kind": w.gear[gid].kind,
            "slot": GEAR[w.gear[gid].kind].slot,
            "quality": w.gear[gid].quality,
            "durability": w.gear[gid].durability,
        }
        for gid in sorted(actor.stored_gear.get(actor.city, []))
    ]
    gear_catalog = [
        {"kind": kind, "slot": spec.slot, "price": spec.base_value,
         "attack": round(spec.attack * 0.85),
         "defense": round(spec.defense * 0.85),
         "durability": max(5, spec.max_durability // 2),
         "quality": 10}
        for kind, spec in GEAR.items()
    ]
    # Display all catalogued goods, not only currently stocked market items.
    # Unlisted crafted/consumable products have no merchant price; do not
    # invent supply or imply that NPC/player markets are live.
    world_items = []
    for item in sorted(GOODS | set(GEAR)):
        if item in RAW_RESOURCES:
            quotes = [w.regional_quote(city, item) for city in CITIES]
            buys = [q for q in quotes if q.sell_capacity > 0]
            sells = [q for q in quotes if q.buy_capacity > 0
                     and w.cities[q.city].gold >= q.player_sell_price]
            cheapest = min(buys, key=lambda q: (q.player_buy_price, q.city)) if buys else None
            highest = max(sells, key=lambda q: (q.player_sell_price, q.city)) if sells else None
            buy_data = ({"city": cheapest.city, "price": cheapest.player_buy_price}
                        if cheapest else None)
            sell_data = ({"city": highest.city, "price": highest.player_sell_price}
                         if highest else None)
        elif item in GEAR:
            buy_data = {"city": CAPITAL, "price": GEAR[item].base_value}
            sell_data = None
        else:
            buy_data = sell_data = None
        world_items.append({"id": item, "category": (
            "Equipment" if item in GEAR else
            "Processed" if item in PROCESSED_RESOURCES else
            "Consumable" if item in CONSUMABLES else "Resource"),
            "lowest_buy": buy_data, "highest_sell": sell_data,
            "market_value": None})
    resale_prices = {q["item"]: q["player_sell_price"] for q in quote_list}
    property_value = (HOMES[housing.tier].price if housing.tier else 0)
    facility_value = sum(FACILITIES[k].price for k in housing.facilities)
    vehicle_value = sum(VEHICLES[k].price for k in housing.vehicles)
    trade_goods_value = sum(
        quantity * resale_prices.get(item, 0)
        for item, quantity in actor.inventory.items()
    )
    # Ownership does not change when moving goods to local storage.
    for storage_city, goods in actor.storage.items():
        for item, quantity in goods.items():
            if quantity and item in RAW_RESOURCES:
                trade_goods_value += quantity * w.regional_quote(
                    storage_city, item).player_sell_price
    stored_equipment_value = sum(
        suggested_value(w.gear[gid])
        for ids in actor.stored_gear.values() for gid in ids)
    net_worth = (actor.gold + property_value + facility_value + vehicle_value
                 + trade_goods_value + sum(item["value"] for item in owned_gear)
                 + stored_equipment_value)
    housing_data = {
        **asdict(housing),
        "facilities": list(housing.facilities),
        "vehicles": list(housing.vehicles),
    }
    rendered_events, active_duel, characters = activity_projection(
        w, actor_id, name, npc_names, human_names, event_times, multiplayer)
    combat_moves = []
    for move in ("strike", "dagger", "fists"):
        if move == "strike" and "weapon" not in actor.equipped:
            continue
        if move == "dagger" and "secondary" not in actor.equipped:
            continue
        label, _, cost = w.combat.melee_option(actor, move)
        combat_moves.append({
            "move": move, "label": "Primary: " + label if move == "strike" else label,
            "stamina": cost, "available": actor.stamina >= cost,
        })
    return {
        "started": True, "name": name,
        "lineage_options": [
            {"id": key, "name": spec.title, "description": spec.description,
             "work": {"manual": spec.work[0], "intelligence": spec.work[1],
                      "endurance": spec.work[2]},
             "attack": spec.attack, "defense": spec.defense,
             "trait": spec.trait, "trait_description": spec.trait_description,
             "trait_level": spec.trait_level}
            for key, spec in LINEAGES.items()
        ],
        "minute": now, "day": now // 1440 + 1,
        "days_played": now // 1440,
        "net_worth_estimate": net_worth,
        "net_worth_basis": "Gold plus purchase prices of property and vehicles, "
                           "local raw-goods resale quotes (including city storage), "
                           "and estimated equipment value",
        "gear": owned_gear,
        "stored_gear_here": stored_gear_here,
        "equipment_catalog": gear_catalog,
        "world_items": world_items,
        "guilds": w.guild_system.view(actor_id),
        "merits": w.merit_system.view(actor_id),
        "training_hall": w.curriculum_system.view(actor_id),
        "chat": w.chat_system.view(actor_id),
        "equipped": dict(actor.equipped),
        "player": {
            "lineage": actor.lineage, "lineage_selected": actor.lineage_selected,
            "lineage_trait_unlocked": active_trait(actor),
            "discovered_cities": sorted(actor.discovered_cities),
            "city": actor.city, "destination": actor.destination,
            "arrival_minute": actor.arrival_minute,
            "gold": actor.gold, "hp": actor.hp, "max_hp": actor.max_hp,
            "stamina": actor.stamina, "max_stamina": actor.max_stamina,
            "hunger": actor.vitals.hunger, "level": actor.level,
            "combat_xp": actor.combat_xp,
            "level_xp": actor.level_xp,
            "strength": actor.strength, "defense": actor.defense,
            "work": {
                "manual": actor.work.manual,
                "intelligence": actor.work.intelligence,
                "endurance": actor.work.endurance,
                "shifts": actor.work.shifts,
                "experience": dict(actor.work.experience),
            },
            "mana": actor.magic.mana, "max_mana": actor.magic.max_mana,
            "school_xp": dict(actor.magic.school_xp),
            "insight": actor.magic.insight,
            "attuned_paths": list(actor.magic.attuned_paths),
            "inventory": dict(actor.inventory),
            "stored_here": dict(actor.storage.get(actor.city, {})),
            "stored_gear_cities": {
                city: len(ids) for city, ids in actor.stored_gear.items()
            },
            "storage_cities": {
                city: sum(contents.values())
                for city, contents in actor.storage.items()
            },
            "cargo": cargo, "cargo_limit": housing.travel_cargo_limit,
            "ready_minute": actor.ready_minute,
            "cooldowns": {
                kind: {
                    "remaining_minutes": remaining(actor, kind, now),
                    "max_minutes": MAX_COOLDOWN_MINUTES,
                }
                for kind in ("job", "food", "potion")
            },
            "consumables": [
                {"item": item, "quantity": actor.inventory.get(item, 0),
                 "channel": ("food" if item in FOOD_MINUTES else "potion"),
                 "cooldown_minutes": FOOD_MINUTES.get(item, POTION_MINUTES.get(item, 0))}
                for item in (*FOOD_MINUTES, *POTION_MINUTES)
            ],
            "defeated_until": actor.defeated_until,
            "road_charm": actor.magic.road_charm,
            "ward_charge": actor.magic.ward_charge,
            # Durations are whole simulation minutes. The multiplayer client
            # subtracts the trusted server clock's partial minute for tooltips.
            "stamina_next_sim_seconds": (
                (5 - now % 5) * 60 if actor.stamina < actor.max_stamina else None),
            "mana_next_sim_seconds": (
                (10 - now % 10) * 60 if actor.magic.mana < actor.magic.max_mana else None),
            "health_next_sim_seconds": (
                (3 - now % 3) * 60 if actor.hp < actor.max_hp else None),

        },
        "cities": places,
        "contracts": w.city_contracts.view(actor_id),
        "users": characters,
        "multiplayer": multiplayer,
        "duel": active_duel,
        "last_duel": w.state.last_duels.get(actor_id),
        "combat_stamina_cost": 0,
        "guard_stamina_cost": 2,
        "magic_stamina_cost": 6,
        "combat_moves": combat_moves,
        "church": {"price": 20, "available": (
            actor.hp > 0 and actor.defeated_until is None
            and actor.hp < actor.max_hp and
            w.state.church_healed_day.get(actor_id) != now // 1440),
            "used_today": w.state.church_healed_day.get(actor_id) == now // 1440},
        "track": {"horses": [
            {"id": breed, "name": spec["name"], "price": spec["price"],
             "speed": spec["speed"], "stamina": spec["stamina"],
             "owned": breed in w.state.horses.get(actor_id, [])}
            for breed, spec in HORSES.items()
        ], "riding_xp": w.state.riding_xp.get(actor_id, 0),
           "last_result": w.state.race_results.get(actor_id),
           "race_cost": RACE_STAMINA_COST, "entry_fee": RACE_ENTRY,
           "cooldown_remaining": max(0, w.state.last_race_minute.get(
               actor_id, -RACE_COOLDOWN) + RACE_COOLDOWN - now)},
        "gatherable": dict(w.cities[actor.city].deposits),
        "quotes": quote_list,
        "housing": housing_data,
        "homes": [
            {"id": kind, **asdict(HOMES[kind])} for kind in HOME_ORDER
        ],
        "facilities": [
            {"id": kind, **asdict(spec)} for kind, spec in FACILITIES.items()
        ],
        "vehicles": [
            {"id": kind, **asdict(spec)} for kind, spec in VEHICLES.items()
        ],
        "magic_schools": list(SCHOOLS),
        "magic_nodes": magic_nodes,
        "events": rendered_events,
    }
