"""Bounded, engine-independent NPC needs, short memory and simple online learning.

This is not a second world state or reinforcement-learning policy. The values
only bias *future proposals*; all asset and action changes belong to WorldEngine.
Nothing here calls an LLM.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

from .observation import NPCView


@dataclass(frozen=True)
class Needs:
    safety: float
    food: float
    liquidity: float
    fatigue: float
    exploration: float

    @classmethod
    def from_view(cls, view: NPCView, curiosity: float) -> "Needs":
        return cls(
            safety=1.0 - view.hp / max(1, view.max_hp),
            food=min(1.0, view.hunger / 3.0),
            liquidity=max(0.0, (70 - view.gold) / 70.0),
            fatigue=max(0.0, (100 - view.stamina) / 100.0),
            exploration=max(0.0, min(1.0, curiosity)),
        )


@dataclass(frozen=True)
class DecisionTrace:
    minute: int
    action: str
    target: str
    success: bool
    gold_delta: int
    hp_delta: int
    level_delta: int
    discovered: tuple[str, ...]
    events: tuple[str, ...]
    error: str = ""


@dataclass
class NPCMemory:
    """One bounded learning record per NPC, *outside* the authority model.

    A clipped EMA tracks which action families have recently paid off. Failed
    actions get a stronger penalty; curiosity discounts monotonous repetition.
    Decision telemetry is bounded to 48 records and is never a raw transcript.
    """
    recent: deque[DecisionTrace] = field(default_factory=lambda: deque(maxlen=48))
    attempts: Counter = field(default_factory=Counter)
    successes: Counter = field(default_factory=Counter)
    failures: Counter = field(default_factory=Counter)
    values: dict[str, float] = field(default_factory=dict)
    decision_count: int = 0
    idle_count: int = 0
    stagnant_count: int = 0
    last_action: str = ""
    last_city: str = ""
    repeat_count: int = 0
    visited: set[str] = field(default_factory=set)
    noteworthy: Counter = field(default_factory=Counter)

    @staticmethod
    def key(action) -> str:
        # Train at action-family granularity, not on unbounded user text/IDs.
        return action.name

    def utility_modifier(self, action, view: NPCView, curiosity: float) -> float:
        name = self.key(action)
        learned = max(-3.0, min(3.0, self.values.get(name, 0.0)))
        recent_failures = sum(
            1 for item in list(self.recent)[-5:]
            if item.action == name and not item.success)
        repeat = min(4, self.repeat_count) if self.last_action == name else 0
        novelty = curiosity * 1.4 if name not in self.attempts else 0.0
        # Repeated failing proposals should not starve a viable alternative.
        return learned * 0.6 - min(4, recent_failures) * 1.0 - repeat * curiosity * 0.5 + novelty

    def record(self, before: NPCView, after: NPCView, action,
               events: tuple[str, ...], error: str = "") -> DecisionTrace:
        name = self.key(action)
        self.decision_count += 1
        self.attempts[name] += 1
        if error:
            self.failures[name] += 1
        else:
            self.successes[name] += 1
        discovered = tuple(sorted(set(after.discovered_cities) -
                                  set(before.discovered_cities)))
        gold_delta = after.gold - before.gold
        hp_delta = after.hp - before.hp
        level_delta = after.level - before.level
        reward = max(-3.0, min(3.0, gold_delta / 12))
        reward += min(3, len(discovered) * 2)
        reward += min(4, level_delta * 2)
        reward += max(-3.0, min(2.0, hp_delta / 8))
        if error:
            reward -= 3.0
        self.values[name] = max(-4.0, min(4.0,
            self.values.get(name, 0.0) * 0.85 + max(-4, min(4, reward)) * 0.15))
        self.repeat_count = self.repeat_count + 1 if name == self.last_action else 1
        self.last_action = name
        self.last_city = after.city
        self.visited.update(after.discovered_cities)
        progress = (gold_delta > 0 or level_delta > 0 or bool(discovered)
                    or "course_completed" in events or "magic_practiced" in events)
        self.stagnant_count = 0 if progress else self.stagnant_count + 1
        for kind in events:
            self.noteworthy[kind] += 1
        target = str(action.params.get("destination") or
                     action.params.get("contract_id") or
                     action.params.get("node_id") or
                     action.params.get("school") or
                     action.params.get("item") or "")
        trace = DecisionTrace(before.minute, name, target[:72], not bool(error),
                              gold_delta, hp_delta, level_delta, discovered,
                              tuple(events[:12]), error[:160])
        self.recent.append(trace)
        return trace

    def record_idle(self, city: str) -> None:
        self.idle_count += 1
        self.stagnant_count += 1
        self.visited.add(city)

    def summary(self) -> dict:
        return {
            "decisions": self.decision_count,
            "idle": self.idle_count,
            "actions": dict(sorted(self.attempts.items())),
            "rejected": dict(sorted(self.failures.items())),
            "learned_values": {k: round(v, 3) for k, v in sorted(self.values.items())},
            "cities_visited": sorted(self.visited),
            "stagnant_decisions": self.stagnant_count,
            "recent": [
                {"minute": t.minute, "action": t.action, "target": t.target,
                 "ok": t.success, "gold_delta": t.gold_delta,
                 "hp_delta": t.hp_delta, "level_delta": t.level_delta,
                 "discovered": list(t.discovered), "events": list(t.events),
                 "error": t.error}
                for t in list(self.recent)[-30:]
            ],
        }
