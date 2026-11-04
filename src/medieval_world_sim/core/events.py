"""Schema v1: named event payloads suitable for audit and future persistence.

No persistent event store or replay executor exists yet.
"""
EVENT_FIELDS = {
    "gear_created": [
        "holder_id",
        "gear_id",
        "item",
        "quality",
        "origin"
    ],
    "travel_started": [
        "actor_id",
        "origin",
        "destination",
        "arrival_minute"
    ],
    "arrived": [
        "actor_id",
        "city"
    ],
    "recovered": [
        "actor_id"
    ],
    "gathered": [
        "actor_id",
        "city",
        "item",
        "quantity"
    ],
    "company_founded": [
        "owner_id",
        "company_id",
        "industry",
        "investment"
    ],
    "hired": [
        "company_id",
        "worker_id",
        "gold",
        "item",
        "quantity"
    ],
    "shift_completed": [
        "company_id",
        "worker_id",
        "gold",
        "item",
        "quantity"
    ],
    "offer_posted": [
        "offer_id",
        "seller_id",
        "city",
        "item",
        "quantity",
        "unit_price"
    ],
    "equipment_offered": [
        "offer_id",
        "seller_id",
        "gear_id",
        "quality",
        "unit_price"
    ],
    "offer_filled": [
        "offer_id",
        "buyer_id",
        "quantity",
        "total_price"
    ],
    "trade_proposed": ["maker_id", "recipient_id", "trade_id"],
    "trade_settled": ["maker_id", "recipient_id", "trade_id"],
    "trade_closed": ["actor_id", "trade_id"],
    "offer_canceled": [
        "offer_id"
    ],
    "starter_purchase": [
        "buyer_id",
        "gear_id",
        "item",
        "price"
    ],
    "equipped": [
        "actor_id",
        "gear_id",
        "slot"
    ],
    "unequipped": [
        "actor_id",
        "slot"
    ],
    "gear_broken": [
        "actor_id",
        "gear_id",
        "item"
    ],
    "level_up": [
        "actor_id",
        "level",
        "max_life"
    ],
    "job_offered": ["company_id", "worker_id", "gold", "item", "quantity"],
    "wage_changed": ["company_id", "worker_id", "gold", "item", "quantity"],
    "worker_left": ["company_id", "worker_id"],
    "perks_changed": ["company_id", "perks"],
    "facility_upgraded": ["company_id", "level", "cost"],
    "training_paid": ["company_id", "worker_id", "gold"],
    "perk_awarded": ["company_id", "worker_id", "item"],
    "home_purchased": ["actor_id", "city", "tier", "gold"],
    "home_upgraded": ["actor_id", "city", "previous_tier", "tier", "gold"],
    "home_facility_built": ["actor_id", "facility", "gold"],
    "vehicle_purchased": ["actor_id", "vehicle", "gold"],
    "vehicle_selected": ["actor_id", "vehicle"],
    "magic_unlocked": ["actor_id", "node_id", "school", "tier", "insight_spent"],
    "magic_attuned": ["actor_id", "paths"],
    "magic_practiced": [
        "actor_id", "node_id", "school", "success", "roll", "chance",
        "mana_spent", "xp_gained", "school_xp", "insight_gained"
    ],
    "goods_stored": ["actor_id", "city", "item", "quantity"],
    "goods_retrieved": ["actor_id", "city", "item", "quantity"],
    "city_contract_completed": ["actor_id", "city", "contract_id", "gold", "stamina", "mana", "xp", "material"],
    "regional_bought": ["actor_id", "city", "item", "quantity", "unit_price", "total"],
    "regional_sold": ["actor_id", "city", "item", "quantity", "unit_price", "total"],
    "city_sale": ["city_id", "company_id", "item", "price", "quality_stars", "day"],
    "consumed": ["actor_id", "item", "health_restored", "stamina_restored", "hunger_relieved"],
    "duel_started": ["attacker_id", "defender_id", "stamina_spent"],
    "duel_round": ["attacker_id", "defender_id", "round", "move", "damage", "retaliation"],
    "duel_finished": ["winner_id", "loser_id", "gold", "recovery_minutes"],
    "duel_fled": ["attacker_id", "defender_id"],
    "spell_cast": ["actor_id", "node_id", "context", "amount", "message"],
    "guild_founded": ["actor_id", "guild_id", "name"],
    "guild_invited": ["guild_id", "actor_id", "candidate_id"],
    "guild_joined": ["guild_id", "actor_id"],
    "guild_role_changed": ["guild_id", "member_id", "role"],
    "guild_left": ["guild_id", "actor_id"],
    "course_started": ["actor_id", "school", "course_index", "ends_at"],
    "course_tuition_paid": ["actor_id", "school", "course_index", "gold"],
    "course_completed": ["actor_id", "school", "course_index", "stat", "bonus"],
    "school_graduated": ["actor_id", "school"],
    "school_capstone_perk": ["actor_id", "school", "stat", "bonus"],
    "school_martial_perk": ["actor_id", "school", "stat", "bonus"],
    "merit_claimed": ["actor_id", "achievement", "amount"],
    "merit_upgrade": ["actor_id", "perk", "cost"],
    "church_healed": ["actor_id", "gold", "health_restored"],
    "horse_purchased": ["actor_id", "breed", "gold"],
    "horse_raced": ["actor_id", "breed", "placing", "xp", "prize"],
    "combat": [
        "attacker_id",
        "defender_id",
        "damage",
        "retaliation",
        "xp",
        "loot",
        "defender_defeated"
    ]
}

def event_payload(kind: str, details: tuple) -> dict[str, object]:
    labels = EVENT_FIELDS.get(kind)
    if labels is None or len(labels) != len(details):
        raise ValueError(f"Missing or incorrect event schema: {kind}")
    return dict(zip(labels, details))
