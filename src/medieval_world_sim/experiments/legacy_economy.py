"""Deterministic toy economy: authoritative rules and transparent transactions.

Not intended as an equilibrium economy or a complete RPG.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random

PRICES = {"food": 2, "wood": 3, "iron": 4, "sword": 14}
ROLES = {"farmer": 40, "woodcutter": 20, "miner": 20, "blacksmith": 10, "guard": 10}
RESOURCES = tuple(PRICES)


@dataclass
class Citizen:
    id: int
    role: str
    gold: int = 30
    stock: dict[str, int] = field(default_factory=lambda: {r: 0 for r in RESOURCES})
    hungry_days: int = 0


@dataclass(frozen=True)
class Event:
    day: int
    kind: str
    actor_id: int | None
    detail: str


class World:
    """Single-settlement, closed-world economy with a finite royal treasury."""

    def __init__(self, citizens: list[Citizen], treasury: int = 5_000, seed: int = 0):
        if treasury < 0 or len({c.id for c in citizens}) != len(citizens):
            raise ValueError("Treasury must be nonnegative and citizen IDs unique")
        self.citizens = citizens
        self.treasury = treasury
        self.day = 0
        self.events: list[Event] = []
        self.rng = Random(seed)
        self.initial_gold = self.total_gold
        self.trades = 0

    @classmethod
    def create(cls, count: int = 200, seed: int = 42) -> World:
        if count < 1:
            raise ValueError("At least one citizen required")
        rng = Random(seed)
        roles = list(ROLES)
        # Largest-remainder allocation; every population size gets exactly count roles.
        fractions = {r: count * w / 100 for r, w in ROLES.items()}
        allocations = {r: int(v) for r, v in fractions.items()}
        remainder = count - sum(allocations.values())
        for role in sorted(roles, key=lambda r: (- (fractions[r] - allocations[r]), r))[:remainder]:
            allocations[role] += 1
        assigned = [role for role, n in allocations.items() for _ in range(n)]
        rng.shuffle(assigned)
        citizens = [Citizen(id=i, role=role) for i, role in enumerate(assigned)]
        for c in citizens:
            c.stock["food"] = 3
        return cls(citizens, seed=seed)

    @property
    def total_gold(self) -> int:
        return self.treasury + sum(c.gold for c in self.citizens)

    def _event(self, kind: str, actor: Citizen | None, detail: str) -> None:
        self.events.append(Event(self.day, kind, actor.id if actor else None, detail))

    def _pay(self, buyer: Citizen | None, seller: Citizen | None, amount: int) -> bool:
        """Move gold between actors and the royal treasury; None denotes treasury."""
        if amount < 0 or (buyer is not None and seller is not None and buyer.id == seller.id):
            raise ValueError("Invalid transfer")
        balance = self.treasury if buyer is None else buyer.gold
        if balance < amount:
            return False
        if buyer is None:
            self.treasury -= amount
        else:
            buyer.gold -= amount
        if seller is None:
            self.treasury += amount
        else:
            seller.gold += amount
        return True

    def _trade(self, buyer: Citizen | None, seller: Citizen, resource: str) -> bool:
        if resource not in PRICES or seller.stock[resource] < 1:
            return False
        if not self._pay(buyer, seller, PRICES[resource]):
            return False
        seller.stock[resource] -= 1
        if buyer is not None:
            buyer.stock[resource] += 1
        else:
            # Swords delivered to the royal armory leave the modeled market.
            pass
        self.trades += 1
        self._event("trade", buyer, f"{resource} from citizen {seller.id}, price {PRICES[resource]}")
        return True

    def _producers(self, role: str) -> list[Citizen]:
        people = [c for c in self.citizens if c.role == role]
        self.rng.shuffle(people)
        return people

    def _buy_from(self, buyer: Citizen, sellers: list[Citizen], resource: str, limit: int, reserve: int = 0) -> None:
        """Match against shuffled sellers, respecting seller's minimum reserve."""
        while buyer.stock[resource] < limit and buyer.gold >= PRICES[resource]:
            seller = next((s for s in sellers if s.id != buyer.id and s.stock[resource] > reserve), None)
            if seller is None or not self._trade(buyer, seller, resource):
                break

    def step(self) -> dict:
        self.day += 1
        # Wages are paid by a finite treasury, never minted.
        for guard in self._producers("guard"):
            if self._pay(None, guard, 3):
                self._event("wage", guard, "3 gold from treasury")

        # Production and crafting obey inventory constraints.
        for person in self.citizens:
            if person.role == "farmer":
                person.stock["food"] += 4
            elif person.role == "woodcutter":
                person.stock["wood"] += 2
            elif person.role == "miner":
                person.stock["iron"] += 2
            elif person.role == "blacksmith" and person.stock["iron"] >= 2 and person.stock["wood"] >= 1:
                person.stock["iron"] -= 2
                person.stock["wood"] -= 1
                person.stock["sword"] += 1
                self._event("craft", person, "1 sword")

        # Smiths source their inputs for a possible next-day craft.
        iron_sellers = self._producers("miner")
        wood_sellers = self._producers("woodcutter")
        for smith in self._producers("blacksmith"):
            self._buy_from(smith, iron_sellers, "iron", 2)
            self._buy_from(smith, wood_sellers, "wood", 1)

        # Citizens acquire food, if the market and their funds permit.
        farmers = self._producers("farmer")
        buyers = self.citizens[:]
        self.rng.shuffle(buyers)
        for citizen in buyers:
            if citizen.role != "farmer":
                self._buy_from(citizen, farmers, "food", 2, reserve=2)

        # Royal procurement is finite, so the state can exhaust its funds.
        for smith in self._producers("blacksmith"):
            while smith.stock["sword"] and self._trade(None, smith, "sword"):
                pass

        for citizen in self.citizens:
            if citizen.stock["food"]:
                citizen.stock["food"] -= 1
            else:
                citizen.hungry_days += 1
                self._event("hunger", citizen, "no food")

        self.assert_invariants()
        return self.summary()

    def assert_invariants(self) -> None:
        assert self.total_gold == self.initial_gold, "Gold conservation violated"
        assert self.treasury >= 0, "Negative treasury"
        for c in self.citizens:
            assert c.gold >= 0 and all(qty >= 0 for qty in c.stock.values()), f"Negative assets: {c.id}"

    def summary(self) -> dict:
        assets = sorted(c.gold for c in self.citizens)
        n = len(assets)
        total = sum(assets)
        gini = (2 * sum(i * v for i, v in enumerate(assets, start=1)) / (n * total) - (n + 1) / n) if total else 0.0
        return {
            "day": self.day,
            "citizens": n,
            "treasury": self.treasury,
            "gold_total": self.total_gold,
            "median_gold": assets[n // 2],
            "gini_gold": round(gini, 4),
            "hungry_citizens_today": sum(1 for e in self.events if e.day == self.day and e.kind == "hunger"),
            "total_hungry_days": sum(c.hungry_days for c in self.citizens),
            "trades_cumulative": self.trades,
            "stocks": {r: sum(c.stock[r] for c in self.citizens) for r in RESOURCES},
        }
