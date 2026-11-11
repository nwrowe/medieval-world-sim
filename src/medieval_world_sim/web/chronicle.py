"""Chronicle event classification and player-safe display text.

Pure presentation: no account mutation, storage access or replay state.
"""
from __future__ import annotations

TRADE_EVENTS = {"trade_proposed", "trade_settled", "trade_closed"}
COMBAT_EVENTS = {"pvp_strike", "duel_started", "duel_round",
                 "duel_finished", "duel_fled", "duel_defender_fled",
                 "duel_draw", "duel_flee_attempt", "combat", "spell_cast"}
UNIVERSITY_EVENTS = {"course_started", "course_tuition_paid", "course_completed",
                     "school_graduated", "school_capstone_perk", "school_martial_perk"}
TRAVEL_EVENTS = {"travel_started", "arrived", "hex_explored",
                 "hex_journey_started", "hex_arrived"}
GUILD_EVENTS = {"guild_founded", "guild_invited", "guild_joined",
                "guild_role_changed", "guild_left"}
EQUIPMENT_EVENTS = {"gear_created", "gear_broken", "starter_purchase",
                    "equipped", "unequipped", "equipment_offered"}
PROPERTY_EVENTS = {"home_purchased", "home_upgraded", "home_facility_built",
                   "vehicle_purchased", "vehicle_selected"}
MAGIC_EVENTS = {"magic_unlocked", "magic_practiced", "magic_attuned"}
HEALTH_EVENTS = {"recovered", "consumed", "church_healed"}
RACING_EVENTS = {"horse_purchased", "horse_raced"}
PROGRESSION_EVENTS = {"level_up", "merit_claimed", "merit_upgrade"}
ECONOMY_EVENTS = {"regional_bought", "regional_sold", "gathered",
                  "goods_stored", "goods_retrieved", "city_contract_completed",
                  "offer_posted", "offer_filled", "offer_canceled", "city_sale",
                  "company_founded", "hired", "shift_completed", "job_offered",
                  "wage_changed", "worker_left", "perks_changed",
                  "facility_upgraded", "training_paid", "perk_awarded"}


def event_category(kind: str) -> str:
    """Stable Chronicle categories shared by single- and multi-player views."""
    for label, events in (
        ("Trade", TRADE_EVENTS), ("Combat", COMBAT_EVENTS),
        ("Travel", TRAVEL_EVENTS), ("University", UNIVERSITY_EVENTS),
        ("Guild", GUILD_EVENTS), ("Equipment", EQUIPMENT_EVENTS),
        ("Property", PROPERTY_EVENTS), ("Magic", MAGIC_EVENTS),
        ("Health", HEALTH_EVENTS), ("Racing", RACING_EVENTS),
        ("Progression", PROGRESSION_EVENTS), ("Economy", ECONOMY_EVENTS),
    ):
        if kind in events:
            return label
    return "Other"


def _trade_assets_text(assets) -> str:
    if not isinstance(assets, dict):
        return "unspecified assets"
    parts = []
    if assets.get("gold"):
        parts.append(f"{assets['gold']}g")
    for entry in assets.get("items", []):
        parts.append(f"{entry.get('quantity')} {entry.get('item')}")
    for gear_id in assets.get("gear_ids", []):
        parts.append(f"equipment #{gear_id}")
    return ", ".join(parts) if parts else "nothing"


def _friendly_event(event, *, gear_kinds=None, equipped_kinds=None,
                    recorded_at=None, human_names=None):
    """Short and safe display labels; the UI never executes event payloads."""
    info = event.data
    gear_kinds = gear_kinds or {}
    equipped_kinds = equipped_kinds or {}
    human_names = human_names or {}
    def who(account_id):
        return human_names.get(account_id, account_id)
    gear_kind = gear_kinds.get(info.get("gear_id"))
    readable = {
        "trade_proposed": (
            f"Trade #{info.get('trade_id')}: "
            f"{who(info.get('maker_id'))} offered to {who(info.get('recipient_id'))}: "
            f"offered {_trade_assets_text(info.get('offer'))}; "
            f"requested {_trade_assets_text(info.get('request'))}"
        ),
        "trade_settled": (
            f"Trade #{info.get('trade_id')} completed: "
            f"{who(info.get('maker_id'))} offered {_trade_assets_text(info.get('offer'))}; "
            f"{who(info.get('recipient_id'))} provided {_trade_assets_text(info.get('request'))}"
        ),
        "trade_closed": (
            f"Trade #{info.get('trade_id')} canceled by {who(info.get('actor_id'))}: "
            f"escrow returned to {who(info.get('maker_id'))}"
        ),
        "recovered": "Recovered from injuries",
        "level_up": f"Reached level {info.get('level')}",
        "gear_broken": f"{info.get('item')} broke",
        "gathered": f"Gathered {info.get('quantity')} {info.get('item')}",
        "travel_started": f"Departed for {info.get('destination')}",
        "arrived": f"Arrived in {info.get('city')}",
        "hex_explored": f"Explored hex {info.get('x')}, {info.get('y')}",
        "hex_journey_started": (
            f"Began exploring hex {info.get('x')}, {info.get('y')}"),
        "hex_arrived": f"Arrived at hex {info.get('x')}, {info.get('y')}",
        "regional_bought": f"Bought {info.get('quantity')} {info.get('item')} for {info.get('total')}g",
        "regional_sold": f"Sold {info.get('quantity')} {info.get('item')} for {info.get('total')}g",
        "home_purchased": f"Purchased a {info.get('tier')}",
        "home_upgraded": f"Upgraded home to {info.get('tier')}",
        "home_facility_built": f"Built {info.get('facility')}",
        "vehicle_purchased": f"Purchased {info.get('vehicle')}",
        "vehicle_selected": f"Travel vehicle: {info.get('vehicle') or 'walking'}",
        "magic_unlocked": f"Unlocked {info.get('node_id')}",
        "magic_practiced": (
            f"Practiced {str(info.get('node_id', '')).replace('_', ' ').replace('.', ' / ')} "
            f"— {'succeeded' if info.get('success') else 'attempted'} "
            f"(+{info.get('xp_gained', 0)} XP, "
            f"-{info.get('mana_spent', 0)} mana"
            f"{', +' + str(info.get('insight_gained')) + ' Insight' if info.get('insight_gained') else ''})"
        ),
        "magic_attuned": "Updated advanced magic specializations",
        "consumed": f"Used {info.get('item')}",
        "starter_purchase": f"Purchased {str(info.get('item', 'equipment')).replace('_', ' ')} for {info.get('price', 0)}g",
        "equipped": f"Equipped {str(gear_kind or info.get('slot', 'gear')).replace('_', ' ')}",
        "unequipped": f"Unequipped {str(equipped_kinds.get(info.get('slot')) or info.get('slot') or 'gear').replace('_', ' ')}",
        "goods_stored": f"Stored {info.get('quantity')} {str(info.get('item')).replace('_',' ')} in {info.get('city')}",
        "goods_retrieved": f"Retrieved {info.get('quantity')} {str(info.get('item')).replace('_',' ')} from {info.get('city')}",
        "guild_founded": f"Founded the guild {info.get('name')}",
        "guild_invited": f"Guild invitation sent to {info.get('candidate_id')}",
        "guild_joined": f"Joined guild {info.get('guild_id')}",
        "guild_role_changed": f"Appointed {info.get('member_id')} as {info.get('role')}",
        "guild_left": f"Left guild {info.get('guild_id')}",
        "course_tuition_paid": f"Paid {info.get('gold')} gold to study {info.get('school')}",
        "course_started": f"Enrolled in {info.get('school')} course #{info.get('course_index', 0) + 1}",
        "course_completed": f"Finished {info.get('school')} course; +{info.get('bonus')} {info.get('stat')}",
        "school_graduated": f"Graduated from {info.get('school')}",
        "school_capstone_perk": f"{info.get('school')} capstone: +{info.get('bonus')} {info.get('stat')}",
        "school_martial_perk": f"{info.get('school')} martial training: +{info.get('bonus')} {info.get('stat')}",
        "merit_claimed": f"Achievement claimed: {info.get('achievement')}",
        "merit_upgrade": f"Merit upgrade purchased: {info.get('perk')}",
        "church_healed": f"Church healing restored {info.get('health_restored')} HP for {info.get('gold')} gold",
        "horse_purchased": f"Purchased {info.get('breed')} racehorse for {info.get('gold')} gold",
        "horse_raced": f"Raced {info.get('breed')}: place {info.get('placing')}, earned {info.get('xp')} riding XP and {info.get('prize')} gold",
        "pvp_strike": (f"Skirmish against {info.get('defender_id')}: "
                       f"{info.get('damage')} damage, "
                       f"{info.get('retaliation')} retaliated, "
                       f"{info.get('gold_looted')}g looted"),
        "duel_started": f"Challenge begun against {info.get('defender_id')}",
        "duel_round": (
            f"Combat round {info.get('round')}: {info.get('move')} "
            f"({info.get('damage')} damage, {info.get('retaliation')} returned)"
        ),
        "duel_finished": (
            f"{info.get('winner_id')} defeated {info.get('loser_id')} "
            f"and claimed {info.get('gold')} gold"
        ),
        "duel_flee_attempt": (
            f"{'Successful' if info.get('success') else 'Failed'} escape attempt "
            f"in combat round {info.get('round')}"
        ),
        "duel_fled": "Attacker retreated from combat",
        "duel_defender_fled": "Defending player withdrew from combat",
        "duel_draw": f"Combat ended in a draw after {info.get('round')} rounds",
        "spell_cast": f"Cast {info.get('node_id')}: {info.get('message')}",
        "city_contract_completed": (
            f"Completed {str(info.get('contract_id', '')).replace('_', ' ')} "
            f"(+{info.get('gold')}g, +{info.get('xp')} XP)"
        ),
    }
    return {
        "id": event.event_id,
        "kind": event.kind,
        "category": event_category(event.kind),
        "minute": event.minute,
        "text": readable.get(event.kind, event.kind),
        # Legacy records have no wall-time metadata. Never invent timestamps.
        "recorded_at": recorded_at,
    }
