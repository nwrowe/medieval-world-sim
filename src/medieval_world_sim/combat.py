"""Compatibility imports for combat constants and results.

Gameplay logic now lives in systems.combat.CombatSystem.
"""
from .systems.combat import (
    CombatSystem, CombatOutcome, ATTACK_STAMINA_COST,
    STAMINA_REGEN_MINUTES, MAX_STAMINA,
    DEFEAT_RECOVERY_MINUTES, MAX_GOLD_LOOT, xp_to_next_level,
)
