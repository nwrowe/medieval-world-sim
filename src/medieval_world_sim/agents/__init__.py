"""Seeded, bounded, rule-based NPC decisions: no direct state mutation."""
from .policy import NPCProfile, RuleBasedPolicy, NPCAction
from .runner import AutonomousSimulation, create_simulation
__all__ = ["NPCProfile", "RuleBasedPolicy", "NPCAction", "AutonomousSimulation", "create_simulation"]
