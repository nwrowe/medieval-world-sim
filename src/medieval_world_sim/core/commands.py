"""Single typed command registry for the authoritative game engine.

Each entry specifies its target WorldEngine method, exact parameter names, and
the web modes allowed to submit it. Exposure does not bypass authenticated
identity, per-action validation, replay controls or engine authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping


@dataclass(frozen=True, slots=True)
class CommandSpec:
    method: str
    fields: tuple[str, ...]
    web_modes: frozenset[str] = frozenset()


_BOTH: Final = frozenset({"single", "multi"})
_SINGLE: Final = frozenset({"single"})
_MULTI: Final = frozenset({"multi"})

COMMAND_SPECS: Final[Mapping[str, CommandSpec]] = MappingProxyType({
    "choose_lineage": CommandSpec("choose_lineage", ("lineage",), _BOTH),
    "travel": CommandSpec("start_travel", ("destination",), _BOTH),
    "gather": CommandSpec("gather", ("item", "quantity"), _BOTH),
    "store_goods": CommandSpec("store_goods", ("item", "quantity"), _BOTH),
    "retrieve_goods": CommandSpec("retrieve_goods", ("item", "quantity"), _BOTH),
    "regional_buy": CommandSpec("regional_buy", ("item", "quantity"), _BOTH),
    "regional_sell": CommandSpec("regional_sell", ("item", "quantity"), _BOTH),
    "unlock_magic": CommandSpec("unlock_magic", ("node_id",), _BOTH),
    "attune_magic": CommandSpec("attune_magic", ("paths",), _BOTH),
    "practice_magic": CommandSpec("practice_magic", ("node_id",), _BOTH),
    "buy_home": CommandSpec("buy_home", ("tier",), _BOTH),
    "upgrade_home": CommandSpec("upgrade_home", ("tier",), _BOTH),
    "build_home_facility": CommandSpec("build_home_facility", ("facility",), _BOTH),
    "buy_vehicle": CommandSpec("buy_vehicle", ("vehicle",), _BOTH),
    "select_vehicle": CommandSpec("select_vehicle", ("vehicle",), _BOTH),
    "found_company": CommandSpec("found_company", ("company_id", "industry", "investment")),
    "shift": CommandSpec("shift", ("company_id",)),
    "post_offer": CommandSpec("post_offer", ("seller_id", "item", "quantity", "unit_price")),
    "post_equipment_offer": CommandSpec("post_equipment_offer", ("seller_id", "gear_id", "unit_price")),
    "accept_offer": CommandSpec("accept_offer", ("buyer_id", "offer_id", "quantity")),
    "cancel_offer": CommandSpec("cancel_offer", ("offer_id",)),
    "propose_trade": CommandSpec("propose_trade", ("recipient_id", "offer", "request"), _MULTI),
    "accept_trade": CommandSpec("accept_trade", ("trade_id", "terms_hash"), _MULTI),
    "close_trade": CommandSpec("close_trade", ("trade_id",), _MULTI),
    "complete_city_contract": CommandSpec("complete_city_contract", ("contract_id",), _BOTH),
    "buy_starter_gear": CommandSpec("buy_starter_gear", ("kind",), _BOTH),
    "equip": CommandSpec("equip", ("gear_id",), _BOTH),
    "unequip": CommandSpec("unequip", ("slot",), _BOTH),
    "attack": CommandSpec("attack", ("defender_id",)),
    "start_duel": CommandSpec("start_duel", ("defender_id",), _BOTH),
    "pvp_strike": CommandSpec("pvp_strike", ("defender_id",), _MULTI),
    "duel_turn": CommandSpec("duel_turn", ("move", "node_id"), _BOTH),
    "flee_duel": CommandSpec("flee_duel", (), _BOTH),
    "cast_spell": CommandSpec("cast_spell", ("node_id",), _BOTH),
    "church_heal": CommandSpec("church_heal", (), _BOTH),
    "buy_racehorse": CommandSpec("buy_racehorse", ("breed",), _BOTH),
    "race_horse": CommandSpec("race_horse", ("breed",), _BOTH),
    "found_guild": CommandSpec("found_guild", ("name",), _BOTH),
    "invite_guild": CommandSpec("invite_guild", ("candidate_id",), _BOTH),
    "join_guild": CommandSpec("join_guild", ("guild_id",), _BOTH),
    "set_guild_role": CommandSpec("set_guild_role", ("member_id", "role"), _BOTH),
    "leave_guild": CommandSpec("leave_guild", (), _BOTH),
    "claim_merit": CommandSpec("claim_merit", ("achievement",), _BOTH),
    "enroll_course": CommandSpec("enroll_course", ("school",), _SINGLE),
    "enroll_course_choice": CommandSpec("enroll_course_choice", ("school", "index"), _BOTH),
    "buy_merit_upgrade": CommandSpec("buy_merit_upgrade", ("perk",), _BOTH),
    "send_chat": CommandSpec("send_chat", ("kind", "target", "message"), _BOTH),
    "create_chat_room": CommandSpec("create_chat_room", ("name", "members"), _BOTH),
    "consume": CommandSpec("consume", ("item",), _BOTH),
    "propose_job": CommandSpec("propose_job", ("company_id", "worker_id", "wage")),
    "accept_job": CommandSpec("accept_job", ("company_id",)),
    "leave_job": CommandSpec("leave_job", ("company_id",)),
    "set_wage": CommandSpec("set_wage", ("company_id", "worker_id", "wage")),
    "set_perks": CommandSpec("set_perks", ("company_id", "perks")),
    "upgrade_facility": CommandSpec("upgrade_facility", ("company_id",)),
})

SINGLE_PLAYER_ACTIONS: Final[frozenset[str]] = frozenset(
    name for name, spec in COMMAND_SPECS.items() if "single" in spec.web_modes
)
MULTIPLAYER_ACTIONS: Final[frozenset[str]] = frozenset(
    name for name, spec in COMMAND_SPECS.items() if "multi" in spec.web_modes
)
