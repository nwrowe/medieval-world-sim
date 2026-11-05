"""Bounded, off-world NPC memory, needs and objective-level learning.

Only WorldEngine changes money, inventory, travel, equipment and experience.
This telemetry and its goals may influence proposals but have no authority.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

from ..catalog import CAPITAL
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


@dataclass
class TradeRoute:
    """Committed delivered-cargo goal using actual transaction cost basis."""
    source: str
    destination: str
    item: str
    quantity: int
    remaining: int
    cost: int
    start_minute: int
    revenue: int = 0


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
    sequence: int = 0
    marked_wealth_delta: int = 0
    work_xp_delta: int = 0
    magic_xp_delta: int = 0
    combat_xp_delta: int = 0
    level_xp_delta: int = 0
    courses_delta: int = 0
    equipment_delta: int = 0
    trade_profit: int | None = None
    city: str = ""


@dataclass
class NPCMemory:
    """A per-actor bounded log and bounded exponentially smoothed action values.

    No model calls, saved user account data, or mutable WorldEngine entities.
    A complete purchase/travel/sale trade route is valued as one objective,
    not by the misleading immediate cash deltas of its component steps.
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
    sequence: int = 0
    active_route: TradeRoute | None = None
    trade_cycles: deque[dict] = field(default_factory=lambda: deque(maxlen=24))
    trade_completed: int = 0
    trade_net_profit: int = 0
    trade_loss_cycles: int = 0

    @staticmethod
    def key(action) -> str:
        return action.name

    def utility_modifier(self, action, view: NPCView, curiosity: float) -> float:
        name = self.key(action)
        learned = max(-3.0, min(3.0, self.values.get(name, 0.0)))
        recent_failures = sum(
            1 for item in list(self.recent)[-5:]
            if item.action == name and not item.success)
        repeat = min(4, self.repeat_count) if self.last_action == name else 0
        novelty = curiosity * 1.4 if name not in self.attempts else 0.0
        return (learned * 0.6 - min(4, recent_failures) * 1.0
                - repeat * curiosity * 0.5 + novelty)

    def record_trade(self, before: NPCView, after: NPCView,
                     action, error: str = "") -> int | None:
        """Record a validated cash/cargo transfer, returning completed profit.

        This never changes game inventory. Failed actions cannot start or
        complete an objective. Later quota shortages simply delay delivery.
        """
        if error:
            return None
        item = action.params.get("item")
        if (action.name == "regional_buy" and before.city != CAPITAL
                and self.active_route is None):
            qty = int(action.params["quantity"])
            spent = before.gold - after.gold
            if qty > 0 and spent > 0 and after.stock(item) >= qty:
                self.active_route = TradeRoute(
                    before.city, CAPITAL, str(item), qty, qty, spent,
                    before.minute)
            return None
        route = self.active_route
        if not (route and action.name == "regional_sell"
                and before.city == route.destination and item == route.item):
            return None
        qty = int(action.params["quantity"])
        received = after.gold - before.gold
        if qty <= 0 or qty > route.remaining or received < 0:
            return None
        route.remaining -= qty
        route.revenue += received
        if route.remaining:
            return None
        profit = route.revenue - route.cost
        self.trade_completed += 1
        self.trade_net_profit += profit
        if profit <= 0:
            self.trade_loss_cycles += 1
        self.trade_cycles.append({
            "source": route.source, "destination": route.destination,
            "item": route.item, "quantity": route.quantity,
            "spent": route.cost, "revenue": route.revenue,
            "profit": profit, "elapsed_minutes": after.minute - route.start_minute,
        })
        self.active_route = None
        # Delayed route credit, using realized profit rather than revenue.
        reward = max(-4.0, min(4.0, profit / 12.0))
        self.values["trade_route"] = max(
            -4.0, min(4.0, 0.7 * self.values.get("trade_route", 0.0)
                          + 0.3 * reward))
        return profit

    def record(self, before: NPCView, after: NPCView, action,
               events: tuple[str, ...], error: str = "",
               *, defer_trade_credit: bool = False,
               trade_profit: int | None = None) -> DecisionTrace:
        name = self.key(action)
        self.decision_count += 1
        self.attempts[name] += 1
        if error:
            self.failures[name] += 1
        else:
            self.successes[name] += 1
        discovered = tuple(sorted(set(after.discovered_cities)
                                  - set(before.discovered_cities)))
        gold_delta = after.gold - before.gold
        hp_delta = after.hp - before.hp
        level_delta = after.level - before.level
        trade_step = (defer_trade_credit
                      and name in ("regional_buy", "regional_sell"))
        cash_reward = 0 if trade_step else gold_delta
        reward = max(-3.0, min(3.0, cash_reward / 12))
        reward += min(3, len(discovered) * 2)
        reward += min(4, level_delta * 2)
        reward += max(-3.0, min(2.0, hp_delta / 8))
        if error:
            reward -= 3.0
        if not trade_step:
            self.values[name] = max(-4.0, min(
                4.0, self.values.get(name, 0.0) * 0.85
                + max(-4, min(4, reward)) * 0.15))
        self.repeat_count = self.repeat_count + 1 if name == self.last_action else 1
        self.last_action = name
        self.last_city = after.city
        self.visited.update(after.discovered_cities)
        work_delta = after.work_xp - before.work_xp
        magic_delta = after.magic_xp - before.magic_xp
        combat_delta = after.combat_xp - before.combat_xp
        level_xp_delta = after.level_xp - before.level_xp
        courses_delta = after.courses_completed - before.courses_completed
        equipment_delta = len(after.gear) - len(before.gear)
        wealth_delta = (after.gold + after.quoted_inventory_value
                        - before.gold - before.quoted_inventory_value)
        progress = (
            cash_reward > 0 or level_delta > 0 or bool(discovered)
            or max(0, work_delta, magic_delta, combat_delta,
                   level_xp_delta, courses_delta, equipment_delta) > 0
            or (trade_profit is not None and trade_profit > 0))
        self.stagnant_count = 0 if progress else self.stagnant_count + 1
        for kind in events:
            self.noteworthy[kind] += 1
        target = str(action.params.get("destination")
                     or action.params.get("contract_id")
                     or action.params.get("node_id")
                     or action.params.get("school")
                     or action.params.get("item") or "")
        self.sequence += 1
        trace = DecisionTrace(
            before.minute, name, target[:72], not bool(error),
            gold_delta, hp_delta, level_delta, discovered,
            tuple(events[:12]), error[:160], sequence=self.sequence,
            marked_wealth_delta=wealth_delta, work_xp_delta=work_delta,
            magic_xp_delta=magic_delta, combat_xp_delta=combat_delta,
            level_xp_delta=level_xp_delta, courses_delta=courses_delta,
            equipment_delta=equipment_delta, trade_profit=trade_profit,
            city=before.city)
        self.recent.append(trace)
        return trace

    def record_arrival(self, minute: int, city: str) -> None:
        self.visited.add(city)
        self.sequence += 1
        self.recent.append(DecisionTrace(
            minute, "arrived", city, True, 0, 0, 0,
            (city,), ("arrived",), sequence=self.sequence, city=city))

    def record_idle(self, city: str) -> None:
        self.idle_count += 1
        self.stagnant_count += 1
        self.visited.add(city)

    def summary(self) -> dict:
        return {
            "decisions": self.decision_count, "idle": self.idle_count,
            "actions": dict(sorted(self.attempts.items())),
            "rejected": dict(sorted(self.failures.items())),
            "learned_values": {k: round(v, 3)
                               for k, v in sorted(self.values.items())},
            "cities_visited": sorted(self.visited),
            "stagnant_decisions": self.stagnant_count,
            "trade_completed": self.trade_completed,
            "trade_net_profit": self.trade_net_profit,
            "trade_loss_cycles": self.trade_loss_cycles,
            "trade_cycles": list(self.trade_cycles),
            "active_trade": (
                None if self.active_route is None else {
                    "source": self.active_route.source,
                    "destination": self.active_route.destination,
                    "item": self.active_route.item,
                    "quantity": self.active_route.quantity,
                    "remaining": self.active_route.remaining,
                    "cost": self.active_route.cost,
                    "revenue": self.active_route.revenue}),
            "recent": [
                {"minute": t.minute, "action": t.action, "target": t.target,
                 "ok": t.success, "gold_delta": t.gold_delta,
                 "hp_delta": t.hp_delta, "level_delta": t.level_delta,
                 "discovered": list(t.discovered), "events": list(t.events),
                 "error": t.error, "sequence": t.sequence,
                 "marked_wealth_delta": t.marked_wealth_delta,
                 "work_xp_delta": t.work_xp_delta,
                 "magic_xp_delta": t.magic_xp_delta,
                 "combat_xp_delta": t.combat_xp_delta,
                 "level_xp_delta": t.level_xp_delta,
                 "courses_delta": t.courses_delta,
                 "equipment_delta": t.equipment_delta,
                 "trade_profit": t.trade_profit, "city": t.city}
                for t in list(self.recent)[-30:],
            ],
        }
