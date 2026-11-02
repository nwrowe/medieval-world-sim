"""An accelerated 5-city economy: independent NPCs propose validated commands.

No privileged direct mutations during runtime. Setup is authorized through the
same WorldEngine APIs; the controller uses a seeded RNG only for decisions.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import random
from statistics import median

from ..catalog import CAPITAL
from ..core.engine import WorldEngine
from ..core.entities import Actor, Wage
from ..errors import ActionError
from .observation import observe
from .policy import NPCProfile, RuleBasedPolicy, NPCAction


INDUSTRIES = ("steelworks", "forge", "tannery", "leatherworker")
RESOURCES = (
    ("ironvale", "iron_ore"),
    ("emberfall", "coal"),
    ("greenhollow", "timber"),
    ("goldmeadow", "hides"),
    ("ironvale", "iron_ore"),
    ("emberfall", "coal"),
    ("greenhollow", "timber"),
    ("goldmeadow", "hides"),
    ("goldmeadow", "grain"),
    ("greenhollow", "herbs"),
)


@dataclass
class AutonomousSimulation:
    world: WorldEngine
    profiles: tuple[NPCProfile, ...]
    seed: int
    rng: random.Random = field(repr=False)
    attempts: Counter = field(default_factory=Counter)
    rejected: Counter = field(default_factory=Counter)
    idle: int = 0
    ticks: int = 0
    elapsed_minutes: int = 0

    def step(self, step_minutes: int = 360) -> None:
        if not isinstance(step_minutes, int) or isinstance(step_minutes, bool) or step_minutes <= 0:
            raise ValueError("step_minutes must be a positive integer")
        # A single deterministic, reproducible processing order avoids starvation
        # of the same NPC on repeated runs.
        controller = RuleBasedPolicy(self.rng)
        order = list(self.profiles)
        self.rng.shuffle(order)
        for profile in order:
            view = observe(self.world, profile.id)
            proposal = controller.choose(profile, view)
            if proposal is None:
                self.idle += 1
                continue
            action_id = f"npc:{self.ticks}:{profile.id}"
            try:
                self.world.execute(profile.id, proposal.name, proposal.params, action_id)
                self.attempts[proposal.name] += 1
            except ActionError as exc:
                # NPCs are not allowed to silently bypass engine validation.
                self.rejected[type(exc).__name__ + ":" + str(exc)] += 1
        self.world.advance(step_minutes)
        self.elapsed_minutes += step_minutes
        self.ticks += 1
        self.world.assert_invariants()

    def run(self, days: int, step_minutes: int = 360) -> dict:
        if not isinstance(days, int) or days < 0:
            raise ValueError("days must be a nonnegative integer")
        if 1440 % step_minutes:
            raise ValueError("step_minutes must evenly divide 1440")
        for _ in range(days * 1440 // step_minutes):
            self.step(step_minutes)
        return self.report()

    def report(self) -> dict:
        events = self.world.events
        counts = Counter(e.kind for e in events)
        gold = [a.gold for a in self.world.actors.values()]
        holdings = {c.id: c.gold for c in self.world.companies.values()}
        trades = [e for e in events if e.kind == "offer_filled"]
        equipment_listing_ids = {
            e.data["offer_id"] for e in events if e.kind == "equipment_offered"
        }
        by_role = {}
        for role in sorted({p.role for p in self.profiles}):
            actor_gold = [self.world.actors[p.id].gold for p in self.profiles if p.role == role]
            by_role[role] = {"count": len(actor_gold), "median_gold": median(actor_gold)}
        ore = sum(e.data["quantity"] for e in events if e.kind == "gathered")
        minted = sum(e.kind == "gear_created" and e.data["origin"] == "crafted"
                     for e in events)
        return {
            "seed": self.seed,
            "npcs": len(self.profiles),
            "simulated_days": round(self.elapsed_minutes / 1440, 3),
            "ticks": self.ticks,
            "gold_total": self.world.total_gold,
            "initial_gold": self.world.initial_gold,
            "gold_conserved": self.world.total_gold == self.world.initial_gold,
            "market_trades": len(trades),
            "market_gold_volume": sum(int(e.data["total_price"]) for e in trades),
            "resources_gathered": ore,
            "shifts_completed": counts["shift_completed"],
            "crafted_equipment": minted,
            "equipment_purchases": sum(e.data["offer_id"] in equipment_listing_ids
                                       for e in trades),
            "combat_attacks": counts["combat"],
            "company_gold": holdings,
            "company_profit_gold": {company: balance - 430 for company, balance in holdings.items()},
            "roles": by_role,
            "event_count": len(events),
            "npc_gold_min": min(gold),
            "npc_gold_median": median(gold),
            "npc_gold_max": max(gold),
            "actions": dict(sorted(self.attempts.items())),
            "rejections": dict(sorted(self.rejected.items())),
            "idle_decisions": self.idle,
        }



def create_simulation(npcs: int = 50, seed: int = 42) -> AutonomousSimulation:
    """Seed 4 staffed companies and independent workers across 5 cities.

    All initial gold is explicitly assigned, never silently minted during play.
    """
    if not isinstance(npcs, int) or npcs < 20 or npcs > 150:
        raise ValueError("Choose 20 to 150 NPCs for this bounded prototype")
    rng = random.Random(seed)
    actors: list[Actor] = []
    profiles: list[NPCProfile] = []

    def register(actor_id: str, role: str, city: str, gold: int,
                 resource: str | None = None, company_id: str | None = None):
        actors.append(Actor(actor_id, "npc", city=city, gold=gold))
        profiles.append(NPCProfile(
            actor_id, role, city, resource, company_id,
            greed=round(rng.uniform(0.9, 1.08), 3),
            risk=round(rng.uniform(0.15, 0.75), 3),
            curiosity=round(rng.uniform(0.1, 0.85), 3),
            volatility=round(rng.uniform(0.3, 1.8), 3),
        ))

    for industry in INDUSTRIES:
        register(f"owner_{industry}", "manager", CAPITAL, 550, company_id=f"{industry}_co")
        register(f"worker_{industry}", "worker", CAPITAL, 60, company_id=f"{industry}_co")

    for i, (city, resource) in enumerate(RESOURCES[:4]):
        register(f"hauler_{i}", "hauler", city, 160, resource)

    adventurers = 4
    for i in range(adventurers):
        register(f"adventurer_{i}", "adventurer", CAPITAL, 240)

    for i in range(npcs - len(actors)):
        city, resource = RESOURCES[i % len(RESOURCES)]
        register(f"gatherer_{i}", "gatherer", city, 40, resource)

    world = WorldEngine(actors, seed=seed)
    for industry in INDUSTRIES:
        owner = f"owner_{industry}"
        company = f"{industry}_co"
        world.found_company(owner, company, industry, investment=430)
        world.hire(owner, company, f"worker_{industry}", Wage(gold=2))
    return AutonomousSimulation(world, tuple(profiles), seed, random.Random(seed + 9999))
