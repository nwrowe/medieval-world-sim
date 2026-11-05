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
from .activity import activity_projection

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
        places.append({
            "id": city_id, "name": city.name, "is_current": city_id == actor.city,
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
    net_worth = (actor.gold + property_value + facility_value + vehicle_value
                 + trade_goods_value + sum(item["value"] for item in owned_gear))
    housing_data = {
        **asdict(housing),
        "facilities": list(housing.facilities),
        "vehicles": list(housing.vehicles),
    }
    activity = activity_projection(
        w, actor_id, npc_names, human_names, event_times, multiplayer)
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
        "minute": now, "day": now // 1440 + 1,
        "days_played": now // 1440,
        "net_worth_estimate": net_worth,
        "net_worth_basis": "Gold plus purchase prices of property and vehicles, "
                           "local raw-goods resale quotes (including city storage), "
                           "and estimated equipment value",
        "gear": owned_gear,
        "equipment_catalog": gear_catalog,
        "world_items": world_items,
        "guilds": w.guild_system.view(actor_id),
        "merits": w.merit_system.view(actor_id),
        "training_hall": w.curriculum_system.view(actor_id),
        "chat": w.chat_system.view(actor_id),
        "equipped": dict(actor.equipped),
        "player": {
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
            "stamina_next_sim_seconds": activity["stamina_next_sim_seconds"],
            "mana_next_sim_seconds": activity["mana_next_sim_seconds"],
            "health_next_sim_seconds": activity["health_next_sim_seconds"],

        },
        "cities": places,
        "contracts": w.city_contracts.view(actor_id),
        "users": activity["users"],
        "multiplayer": multiplayer,
        "duel": activity["duel"],
        "last_duel": activity["last_duel"],
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
        "events": activity["events"],
    }
