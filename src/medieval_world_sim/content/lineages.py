"""Playable lineages, their small starting aptitudes and earned passive traits.

Lineage is orthogonal to future careers/classes. No client-supplied bonuses,
stats or trait flags are trusted: this is the single authoritative catalog.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..errors import ActionError


@dataclass(frozen=True)
class Lineage:
    title: str
    description: str
    work: tuple[int, int, int]  # manual, intelligence, endurance at creation
    attack: int
    defense: int
    trait: str
    trait_description: str
    trait_level: int = 3


LINEAGES = {
    "human": Lineage("Human", "Adaptable citizens of the Five Cities.",
                     (1, 1, 1), 0, 0, "Versatility",
                     "Earn +1 extra work experience on civic assignments."),
    "elf": Lineage("Elf", "Observant scholars with a natural affinity for magic.",
                   (0, 2, 0), 0, 1, "Arcane Insight",
                   "Earn +1 extra magical experience when practicing."),
    "dwarf": Lineage("Dwarf", "Resilient artisans who know stone and steel.",
                     (2, 0, 0), 0, 1, "Stoneguard",
                     "Gain +1 additional defense in physical combat."),
    "orc": Lineage("Orc", "Driven fighters prized for their endurance.",
                   (0, 0, 2), 1, 0, "Battle Fury",
                   "Gain +1 additional physical attack damage."),
}


def select_lineage(actor, lineage: str) -> None:
    """Set an actor's one-time birthright; keeps historical actors unchanged."""
    if not isinstance(lineage, str) or lineage not in LINEAGES:
        raise ActionError("Choose a valid lineage")
    if actor.kind != "human" or actor.lineage_selected:
        raise ActionError("Lineage may only be selected once by a player")
    spec = LINEAGES[lineage]
    actor.lineage = lineage
    actor.lineage_selected = True
    actor.work.manual += spec.work[0]
    actor.work.intelligence += spec.work[1]
    actor.work.endurance += spec.work[2]


def active_trait(actor) -> bool:
    return (actor.kind == "human" and actor.lineage_selected
            and actor.level >= LINEAGES[actor.lineage].trait_level)


def combat_modifiers(actor) -> tuple[int, int]:
    """Flat physical attack/defense bonuses; no effect on old saves or NPCs."""
    if actor.kind != "human" or not actor.lineage_selected:
        return 0, 0
    spec = LINEAGES[actor.lineage]
    extra_attack = int(actor.lineage == "orc" and active_trait(actor))
    extra_defense = int(actor.lineage == "dwarf" and active_trait(actor))
    return spec.attack + extra_attack, spec.defense + extra_defense


def work_experience_bonus(actor) -> int:
    return int(actor.lineage_selected and actor.lineage == "human"
               and active_trait(actor))


def magic_experience_bonus(actor) -> int:
    return int(actor.lineage_selected and actor.lineage == "elf"
               and active_trait(actor))
