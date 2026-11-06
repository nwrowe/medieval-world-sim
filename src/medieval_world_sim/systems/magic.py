"""Authoritative mana, XP, unlocks and specialization state for six magic schools.

World effects and paid magic contracts deliberately belong to later systems.
Here, practicing a learned node consumes mana and trains that school only.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac

from ..content.magic_tree import (
    NODES, ROOT_ID, SCHOOLS, MAX_ACTIVE_SPECIALIZATIONS,
    ATTUNEMENT_COOLDOWN_MINUTES, INSIGHT_XP_INTERVAL,
    PRACTICE_XP_CEILING, PRACTICE_COOLDOWN_MINUTES, branch_for,
)
from ..errors import ActionError
from ..content.lineages import magic_experience_bonus


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
    mastered: bool = False
    can_practice: bool = False
    practice_ready_minute: int = 0
    castable: bool = False


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
    level_xp_gained: int = 0
    levels_gained: int = 0


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

    @staticmethod
    def _mastered(actor, node) -> bool:
        """Practice mastery is a server rule, shared by clients and NPCs.

        Spell *casting* remains available after training mastery. Lower-tier
        practice stops after a higher-tier spell is learned; at the XP ceiling
        even the highest learned tier stops granting XP.
        """
        return (actor.magic.school_xp.get(node.school, 0) >=
                PRACTICE_XP_CEILING.get(node.tier, 0)
                or any(other.school == node.school and other.tier > node.tier
                       and other.id in actor.magic.unlocked
                       for other in NODES.values()))

    @staticmethod
    def _castable(actor, node) -> bool:
        """A spell is castable only at 100/100 for its tier, and while active.

        Unlocking starts the study of a tier; it does not grant its effect.
        A previously mastered lower-tier spell stays available after
        advancement to higher tiers.
        """
        return (node.tier > 0 and MagicSystem._active(actor, node)
                and actor.magic.school_xp.get(node.school, 0) >=
                PRACTICE_XP_CEILING[node.tier])

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
                            self._active(actor, node),
                            self._mastered(actor, node) if node.tier > 0 else False,
                            node.tier > 0 and self._active(actor, node)
                            and not self._mastered(actor, node),
                            0, self._castable(actor, node))
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
        # Save-journal v1 actions need their historical rule set when replayed.
        # New commands always follow the current mastered-tier restriction.
        legacy = getattr(self.world, "_legacy_magic_rules", False)
        legacy_training = getattr(self.world, "_legacy_magic_training_rules", False)
        if not legacy and self._mastered(actor, node):
            raise ActionError("This school tier is mastered; practice a higher tier")
        # Cooldowns exist only when replaying v15 / xp_version 3 commands.
        # Current practice is limited exclusively by mana and tier mastery.
        historic_cooldown = getattr(
            self.world, "_legacy_magic_practice_cooldown", False)
        if historic_cooldown and self.world.minute < state.next_practice_minute.get(node.school, 0):
            remaining = state.next_practice_minute[node.school] - self.world.minute
            raise ActionError(f"Magic training recovers in {remaining} simulated minutes")
        if state.mana < node.mana_cost:
            raise ActionError("Insufficient mana")
        # Hash-based roll has NO external RNG state to leak or desynchronize.
        # It varies by attempt even if a character practices twice in one minute.
        payload = f"{self.world.seed}|{actor_id}|{node_id}|{state.attempts}|{self.world.minute}"
        private_key = getattr(self.world, "_private_rng_key", None)
        digest = (hmac.digest(private_key, payload.encode(), "sha256")
                  if private_key is not None else sha256(payload.encode()).digest())
        roll = (int.from_bytes(digest[:8], "big") % 100) + 1
        skill = state.school_xp.get(node.school, 0)
        chance = (max(5, min(95, 70 - node.difficulty + min(20, skill // 10)))
                  if legacy else
                  max(90, min(98, 95 - node.difficulty // 12 + min(3, skill // 150))))
        success = roll <= chance
        state.attempts += 1
        state.mana -= node.mana_cost
        if historic_cooldown:
            state.next_practice_minute[node.school] = (
                self.world.minute + PRACTICE_COOLDOWN_MINUTES)
        # Old journals retain their historic training yield. New training
        # produces one base school XP per deliberate practice session;
        # unsuccessful attempts still teach from mistakes, as before.
        # Housing and lineage bonuses apply to actually earned XP only.
        ceiling = PRACTICE_XP_CEILING[node.tier]
        base_xp = ((3 * node.tier + 3 if success else 1)
                   if legacy_training else 1)
        awarded = min(base_xp, max(0, ceiling - skill))
        if awarded:
            awarded = min(self.world.housing_system.training_xp(
                actor, awarded, f"magic:{node.school}") + magic_experience_bonus(actor),
                max(0, ceiling - skill))
        state.school_xp[node.school] = skill + awarded
        earned_total = sum(state.school_xp.values()) // INSIGHT_XP_INTERVAL
        gained = earned_total - state.insight_earned
        state.insight_earned = earned_total
        state.insight += gained
        # Every genuinely earned point of school XP can also advance the
        # character, without mislabeling it as combat XP. Half-rate limits
        # the level-speed advantage of repeatable, low-risk spell practice.
        # Pre-change journals replay under their original rules.
        level_gain = (max(1, awarded // 2) if awarded > 0
                      and not getattr(self.world, "_legacy_magic_leveling_rules", False)
                      else 0)
        levels = self.world.combat._award_level_xp(actor, level_gain)
        self.world._emit("magic_practiced", actor.id, node.id, node.school,
                         success, roll, chance, node.mana_cost,
                         awarded, state.school_xp[node.school], gained)
        return MagicPracticeResult(actor.id, node.id, success, roll, chance,
                                   node.mana_cost, awarded,
                                   state.school_xp[node.school], gained,
                                   level_gain, levels)

    @staticmethod
    def assert_valid(actor, minute: int) -> None:
        """Enforce the same progression invariants for humans and NPCs."""
        state = actor.magic
        if (type(state.max_mana) is not int or state.max_mana != 100
                or type(state.mana) is not int or not 0 <= state.mana <= state.max_mana
                or type(state.attempts) is not int or state.attempts < 0
                or type(state.insight) is not int or state.insight < 0
                or type(state.insight_earned) is not int or state.insight_earned < 0
                or type(state.road_charm) is not int or not 0 <= state.road_charm <= 40
                or type(state.ward_charge) is not int or not 0 <= state.ward_charge <= 20):
            raise AssertionError("Invalid mana or Insight balances")
        if (not isinstance(state.school_xp, dict)
                or any(s not in SCHOOLS or type(xp) is not int or xp < 0
                       for s, xp in state.school_xp.items())):
            raise AssertionError("Invalid magic-school experience")
        if (type(state.next_practice_minute) is not dict
                or any(school not in SCHOOLS or type(ready) is not int
                       or ready < 0 or ready > minute + PRACTICE_COOLDOWN_MINUTES
                       for school, ready in state.next_practice_minute.items())):
            raise AssertionError("Invalid magic practice schedule")
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
