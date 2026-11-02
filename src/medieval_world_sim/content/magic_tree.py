"""Immutable, six-school magical progression tree. No world effects or income here.

Game rules consume node definitions through MagicSystem; adding a new school or
spell does not add an inheritance level or mutate the actor schema.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


SCHOOLS = ("restoration", "divination", "enchantment",
           "warding", "elemental", "alchemy")
ROOT_ID = "arcane_fundamentals"
MAX_ACTIVE_SPECIALIZATIONS = 2
ATTUNEMENT_COOLDOWN_MINUTES = 360
MAX_MANA = 100
MANA_REGEN_MINUTES = 10
INSIGHT_XP_INTERVAL = 50
TIER_XP = {1: 0, 2: 30, 3: 120, 4: 350}
TIER_INSIGHT_COST = {1: 0, 2: 1, 3: 2, 4: 3}
TIER_MANA_COST = {1: 8, 2: 15, 3: 25, 4: 40}
TIER_DIFFICULTY = {1: 20, 2: 32, 3: 45, 4: 55}
# Low-tier practice eventually stops awarding XP. Higher-tier training is
# required to continue progressing, even when mana is plentiful.
PRACTICE_XP_CEILING = {1: 80, 2: 180, 3: 420, 4: 1000}


@dataclass(frozen=True)
class MagicNode:
    id: str
    title: str
    school: str
    tier: int
    prerequisites: tuple[str, ...]
    role: str  # Future world-effect integration: recovery, trading, crafting, ...
    xp_required: int
    insight_cost: int
    mana_cost: int
    difficulty: int


def _node(school: str, name: str, title: str, tier: int,
          previous: tuple[str, ...], role: str) -> MagicNode:
    return MagicNode(f"{school}.{name}", title, school, tier, previous, role,
                     TIER_XP[tier], TIER_INSIGHT_COST[tier],
                     TIER_MANA_COST[tier], TIER_DIFFICULTY[tier])


# Six nodes per school: entry -> useful practice -> two alternative specialist
# branches, each of which culminates in its own tier-four mastery node.
# Mastering both is possible eventually; only TWO specialist paths across all
# schools may be active (attuned) concurrently.
_BRANCHES = {
    "restoration": (
        ("soothe_wounds", "Soothe Wounds", 1, (ROOT_ID,), "recovery"),
        ("field_healing", "Field Healing", 2, ("soothe_wounds",), "medical_service"),
        ("revival", "Revival Arts", 3, ("field_healing",), "revival"),
        ("battle_medic", "Battle Medic", 3, ("field_healing",), "combat_support"),
        ("master_healer", "Master Healer", 4, ("revival",), "revival"),
        ("combat_restoration", "Combat Restoration", 4, ("battle_medic",), "combat_support"),
    ),
    "divination": (
        ("read_omens", "Read Omens", 1, (ROOT_ID,), "scouting"),
        ("trade_appraisal", "Trade Appraisal", 2, ("read_omens",), "trading"),
        ("merchant_foresight", "Merchant Foresight", 3, ("trade_appraisal",), "trading"),
        ("pathfinder", "Pathfinder", 3, ("trade_appraisal",), "travel"),
        ("oracle", "Oracle", 4, ("merchant_foresight",), "trading"),
        ("wayfinder", "Wayfinder", 4, ("pathfinder",), "travel"),
    ),
    "enchantment": (
        ("etch_rune", "Etch a Rune", 1, (ROOT_ID,), "crafting"),
        ("tool_improvement", "Tool Improvement", 2, ("etch_rune",), "crafting"),
        ("smith_runes", "Smith's Runes", 3, ("tool_improvement",), "crafting"),
        ("combat_imbuement", "Combat Imbuement", 3, ("tool_improvement",), "combat"),
        ("runemaster", "Runemaster", 4, ("smith_runes",), "crafting"),
        ("battle_enchanter", "Battle Enchanter", 4, ("combat_imbuement",), "combat"),
    ),
    "warding": (
        ("minor_shield", "Minor Shield", 1, (ROOT_ID,), "protection"),
        ("ward_goods", "Ward Goods", 2, ("minor_shield",), "caravan"),
        ("caravan_protector", "Caravan Protector", 3, ("ward_goods",), "caravan"),
        ("combat_defender", "Combat Defender", 3, ("ward_goods",), "combat_defense"),
        ("grand_warden", "Grand Warden", 4, ("caravan_protector",), "caravan"),
        ("aegis_master", "Aegis Master", 4, ("combat_defender",), "combat_defense"),
    ),
    "elemental": (
        ("kindle_flame", "Kindle Flame", 1, (ROOT_ID,), "crafting"),
        ("furnace_assistance", "Furnace Assistance", 2, ("kindle_flame",), "crafting"),
        ("crafting_fire", "Crafting Fire", 3, ("furnace_assistance",), "crafting"),
        ("battle_magic", "Battle Magic", 3, ("furnace_assistance",), "combat"),
        ("forge_elementalist", "Forge Elementalist", 4, ("crafting_fire",), "crafting"),
        ("stormcaller", "Stormcaller", 4, ("battle_magic",), "combat"),
    ),
    "alchemy": (
        ("purify_reagents", "Purify Reagents", 1, (ROOT_ID,), "alchemy"),
        ("potion_enhancement", "Potion Enhancement", 2, ("purify_reagents",), "medicine"),
        ("apothecary_art", "Apothecary's Art", 3, ("potion_enhancement",), "medicine"),
        ("resistance_elixirs", "Resistance Elixirs", 3, ("potion_enhancement",), "combat_support"),
        ("master_alchemist", "Master Alchemist", 4, ("apothecary_art",), "medicine"),
        ("elixir_sage", "Elixir Sage", 4, ("resistance_elixirs",), "combat_support"),
    ),
}


def _build_registry() -> dict[str, MagicNode]:
    nodes = {ROOT_ID: MagicNode(ROOT_ID, "Arcane Fundamentals", "arcane",
                                0, (), "foundation", 0, 0, 0, 0)}
    for school in SCHOOLS:
        for name, title, tier, parents, role in _BRANCHES[school]:
            references = tuple(p if p == ROOT_ID else f"{school}.{p}" for p in parents)
            entry = _node(school, name, title, tier, references, role)
            if entry.id in nodes:
                raise ValueError("Duplicate magic node ID")
            nodes[entry.id] = entry
    # Validate all prerequisites and tier relationships when content is loaded.
    for entry in nodes.values():
        for parent_id in entry.prerequisites:
            parent = nodes.get(parent_id)
            if parent is None or parent.tier >= entry.tier:
                raise ValueError(f"Invalid magic prerequisite for {entry.id}")
            if parent.id != ROOT_ID and parent.school != entry.school:
                raise ValueError(f"Cross-school prerequisites need explicit design: {entry.id}")
        if entry.tier > 1 and not entry.prerequisites:
            raise ValueError(f"Missing magic prerequisite: {entry.id}")
        if entry.tier == 4 and nodes[entry.prerequisites[0]].tier != 3:
            raise ValueError(f"Mastery requires a specialist branch: {entry.id}")
    if set(_BRANCHES) != set(SCHOOLS) or len(nodes) != 37:
        raise ValueError("Expected one common root and six six-node school trees")
    return nodes


NODES = MappingProxyType(_build_registry())


def branch_for(node_id: str) -> str | None:
    """Return the tier-III branch that controls active specialist abilities."""
    node = NODES.get(node_id)
    if node is None or node.tier < 3:
        return None
    return node.id if node.tier == 3 else node.prerequisites[0]


def school_nodes(school: str) -> tuple[MagicNode, ...]:
    if school not in SCHOOLS:
        raise ValueError("Unknown magic school")
    return tuple(n for n in NODES.values() if n.school == school)
