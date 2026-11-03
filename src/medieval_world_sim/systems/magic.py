"""Authoritative mana, XP, unlocks and specialization state for six magic schools.

World effects and paid magic contracts deliberately belong to later systems.
Here, practicing a learned node consumes mana and trains that school only.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from ..content.magic_tree import (
    NODES, ROOT_ID, SCHOOLS, MAX_ACTIVE_SPECIALIZATIONS,
    ATTUNEMENT_COOLDOWN_MINUTES, INSIGHT_XP_INTERVAL,
    PRACTICE_XP_CEILING, branch_for,
)
from ..errors import ActionError


@dataclass(frozen=True)
class MagicNodeStatus:
    node_id: str
    school: str
    title: str
    tier: int
    prerequisites: tuple[str, ...]
    school_xp: int
    required_xp: int
    insight_cost: int
    mana_cost: int
    role: str
    unlocked: bool
    eligible: bool
    active: bool


@dataclass(frozen=True)
class MagicPracticeResult:
    actor_id: str
    node_id: str
    success: bool
    roll: int
    chance: int
    mana_spent: int
    xp_gained: int
    school_xp: int
    insight_gained: int


class MagicSystem:
    def __init__(self, world):
        self.world = world

    @staticmethod
    def _node(node_id: str):
        if not isinstance(node_id, str) or node_id not in NODES:
            raise ActionError("Unknown magic node")
        return NODES[node_id]

    @staticmethod
    def _eligible(actor, node) -> bool:
        state = actor.magic
        return (node.id != ROOT_ID and node.id not in state.unlocked
                and state.school_xp.get(node.school, 0) >= node.xp_required
                and state.insight >= node.insight_cost
                and all(pre in state.unlocked for pre in node.prerequisites))

    @staticmethod
    def _active(actor, node) -> bool:
        return (node.id in actor.magic.unlocked
                and (node.tier < 3 or branch_for(node.id) in actor.magic.attuned_paths))

    def tree(self, actor_id: str, school: str | None = None) -> tuple[MagicNodeStatus, ...]:
        """Return stable, detached UI-ready values (no writable references)."""
        actor = self.world._actor(actor_id)
        if school is not None and school not in SCHOOLS:
            raise ActionError("Unknown magic school")
        return tuple(
            MagicNodeStatus(node.id, node.school, node.title, node.tier,
                            node.prerequisites, actor.magic.school_xp.get(node.school, 0),
                            node.xp_required, node.insight_cost, node.mana_cost, node.role,
                            node.id in actor.magic.unlocked, self._eligible(actor, node),
                            self._active(actor, node))
            for node in NODES.values() if school is None or node.school == school
        )

    def unlock(self, actor_id: str, node_id: str) -> None:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        node = self._node(node_id)
        if not self._eligible(actor, node):
            raise ActionError("Magic node prerequisites, experience or Insight not satisfied")
        actor.magic.insight -= node.insight_cost
        actor.magic.unlocked.add(node.id)
        self.world._emit("magic_unlocked", actor.id, node.id, node.school,
                         node.tier, node.insight_cost)

    def attune(self, actor_id: str, paths: tuple[str, ...]) -> None:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        if not isinstance(paths, (tuple, list)) or any(not isinstance(p, str) for p in paths):
            raise ActionError("Specializations must be a sequence of node IDs")
        if len(paths) > MAX_ACTIVE_SPECIALIZATIONS or len(set(paths)) != len(paths):
            raise ActionError("Too many or duplicate active magic specializations")
        for path in paths:
            node = self._node(path)
            if node.tier != 3 or node.id not in actor.magic.unlocked:
                raise ActionError("Only unlocked tier-three branches may be attuned")
        ordered = tuple(sorted(paths))
        state = actor.magic
        if ordered == state.attuned_paths:
            return
        if (state.last_attunement_minute is not None and
                self.world.minute - state.last_attunement_minute < ATTUNEMENT_COOLDOWN_MINUTES):
            raise ActionError("Specialization switching is on cooldown")
        state.attuned_paths = ordered
        state.last_attunement_minute = self.world.minute
        self.world._emit("magic_attuned", actor.id, ordered)

    def practice(self, actor_id: str, node_id: str) -> MagicPracticeResult:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        node = self._node(node_id)
        state = actor.magic
        if node.tier == 0 or not self._active(actor, node):
            raise ActionError("Magic node is not unlocked or active")
        if state.mana < node.mana_cost:
            raise ActionError("Insufficient mana")
        # Hash-based roll has NO external RNG state to leak or desynchronize.
        # It varies by attempt even if a character practices twice in one minute.
        payload = f"{self.world.seed}|{actor_id}|{node_id}|{state.attempts}|{self.world.minute}"
        roll = (int.from_bytes(sha256(payload.encode()).digest()[:8], "big") % 100) + 1
        skill = state.school_xp.get(node.school, 0)
        chance = max(5, min(95, 70 - node.difficulty + min(20, skill // 10)))
        success = roll <= chance
        state.attempts += 1
        state.mana -= node.mana_cost
        # At trivial difficulty, repeated casting eventually stops granting XP.
        ceiling = PRACTICE_XP_CEILING[node.tier]
        awarded = min((3 * node.tier + 3 if success else 1), max(0, ceiling - skill))
        awarded = min(self.world.housing_system.training_xp(
            actor, awarded, f"magic:{node.school}"), max(0, ceiling - skill))
        state.school_xp[node.school] = skill + awarded
        earned_total = sum(state.school_xp.values()) // INSIGHT_XP_INTERVAL
        gained = earned_total - state.insight_earned
        state.insight_earned = earned_total
        state.insight += gained
        self.world._emit("magic_practiced", actor.id, node.id, node.school,
                         success, roll, chance, node.mana_cost,
                         awarded, state.school_xp[node.school], gained)
        return MagicPracticeResult(actor.id, node.id, success, roll, chance,
                                   node.mana_cost, awarded,
                                   state.school_xp[node.school], gained)

    @staticmethod
    def assert_valid(actor, minute: int) -> None:
        """Enforce the same progression invariants for humans and NPCs."""
        state = actor.magic
        if (type(state.max_mana) is not int or state.max_mana != 100
                or type(state.mana) is not int or not 0 <= state.mana <= state.max_mana
                or type(state.attempts) is not int or state.attempts < 0
                or type(state.insight) is not int or state.insight < 0
                or type(state.insight_earned) is not int or state.insight_earned < 0):
            raise AssertionError("Invalid mana or Insight balances")
        if (not isinstance(state.school_xp, dict)
                or any(s not in SCHOOLS or type(xp) is not int or xp < 0
                       for s, xp in state.school_xp.items())):
            raise AssertionError("Invalid magic-school experience")
        if not isinstance(state.unlocked, set) or ROOT_ID not in state.unlocked:
            raise AssertionError("Arcane Fundamentals must remain unlocked")
        if any(node not in NODES for node in state.unlocked):
            raise AssertionError("Unknown unlocked magic node")
        for key in state.unlocked:
            node = NODES[key]
            if (any(parent not in state.unlocked for parent in node.prerequisites)
                    or state.school_xp.get(node.school, 0) < node.xp_required):
                raise AssertionError("Magic unlock without prerequisite or XP")
        spent = sum(NODES[key].insight_cost for key in state.unlocked)
        if (state.insight_earned != sum(state.school_xp.values()) // INSIGHT_XP_INTERVAL
                or state.insight + spent != state.insight_earned):
            raise AssertionError("Invalid Insight accounting")
        if (not isinstance(state.attuned_paths, tuple)
                or len(state.attuned_paths) > MAX_ACTIVE_SPECIALIZATIONS
                or state.attuned_paths != tuple(sorted(set(state.attuned_paths)))):
            raise AssertionError("Invalid magic attunement count")
        if any(key not in state.unlocked or NODES[key].tier != 3
               for key in state.attuned_paths):
            raise AssertionError("Attuned path not unlocked")
        if (state.last_attunement_minute is not None
                and (type(state.last_attunement_minute) is not int
                     or not 0 <= state.last_attunement_minute <= minute)):
            raise AssertionError("Invalid attunement timestamp")
