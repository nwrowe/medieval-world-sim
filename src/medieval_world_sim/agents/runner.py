"""An accelerated 5-city economy: independent NPCs propose validated commands.

No privileged direct mutations during runtime. Setup is authorized through the
same WorldEngine APIs; the controller uses a seeded RNG only for decisions.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
import random
from statistics import median

from ..catalog import CAPITAL
from ..core.engine import WorldEngine
from ..core.entities import Actor, Wage
from ..errors import ActionError
from .observation import observe
from .policy import NPCProfile, RuleBasedPolicy, NPCAction
from .cognition import NPCMemory, DecisionTrace
from .critics import Critic, HeuristicCritic, PlaytestObserver, aggregate_issues, MAJOR_EVENTS


INDUSTRIES = ("steelworks", "forge", "tannery", "leatherworker", "bakery", "apothecary")
RESOURCES = (
    ("ironvale", "iron_ore"),
    ("emberfall", "coal"),
    ("greenhollow", "timber"),
    ("goldmeadow", "hides"),
    ("goldmeadow", "grain"),
    ("greenhollow", "herbs"),
    ("ironvale", "iron_ore"),
    ("emberfall", "coal"),
    ("greenhollow", "timber"),
    ("goldmeadow", "hides"),
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
    memories: dict[str, NPCMemory] = field(default_factory=dict, repr=False)
    observers: dict[str, PlaytestObserver] = field(default_factory=dict, repr=False)

    def step(self, step_minutes: int = 360) -> None:
        if not isinstance(step_minutes, int) or isinstance(step_minutes, bool) or step_minutes <= 0:
            raise ValueError("step_minutes must be a positive integer")
        # A single deterministic, reproducible processing order avoids starvation
        # of the same NPC on repeated runs.
        controller = RuleBasedPolicy(self.rng)
        order = list(self.profiles)
        self.rng.shuffle(order)
        for profile in order:
            memory = self.memories.setdefault(profile.id, NPCMemory())
            view = observe(self.world, profile.id,
                           include_progression=profile.role == "playtester")
            memory.visited.update(view.discovered_cities)
            proposal = controller.choose(profile, view, memory)
            if proposal is None:
                self.idle += 1
                memory.record_idle(view.city)
                continue
            action_id = f"npc:{self.ticks}:{profile.id}"
            before_events = len(self.world.events)
            error = ""
            try:
                self.world.execute(profile.id, proposal.name, proposal.params, action_id)
                self.attempts[proposal.name] += 1
            except ActionError as exc:
                # The same engine rejection path applies to AI and players.
                error = type(exc).__name__ + ": " + str(exc)
                self.rejected[error] += 1
            actor = self.world.actors[profile.id]
            emitted = tuple(e.kind for e in self.world.events[before_events:]
                            if e.data.get("actor_id") == profile.id
                            or e.data.get("attacker_id") == profile.id)
            after = replace(view, gold=actor.gold, hp=actor.hp,
                            level=actor.level, city=actor.city,
                            discovered_cities=tuple(sorted(actor.discovered_cities)))
            memory.record(view, after, proposal, emitted, error)
            if profile.id in self.observers:
                reason = next((kind for kind in emitted if kind in MAJOR_EVENTS), "")
                if not reason and memory.failures[proposal.name] >= 3 and error:
                    reason = "repeated_rejection"
                self.observers[profile.id].maybe_reflect(after, reason=reason)
        self.world.advance(step_minutes)
        # Arrivals happen during time advancement, not at travel initiation.
        # Register actual discoveries only after the authoritative tick settles.
        for profile in self.profiles:
            memory = self.memories[profile.id]
            actor = self.world.actors[profile.id]
            discovered = sorted(set(actor.discovered_cities) - memory.visited)
            for city in discovered:
                memory.visited.add(city)
                memory.recent.append(DecisionTrace(
                    self.world.minute, "arrived", city, True, 0, 0, 0,
                    (city,), ("arrived",)))
            if discovered and profile.id in self.observers:
                self.observers[profile.id].maybe_reflect(
                    observe(self.world, profile.id, include_progression=True),
                    reason="arrived")
        self.elapsed_minutes += step_minutes
        self.ticks += 1
        self.world.assert_invariants()

    def run(self, days: int, step_minutes: int = 360) -> dict:
        if not isinstance(days, int) or days < 0:
            raise ValueError("days must be a nonnegative integer")
        if (not isinstance(step_minutes, int) or isinstance(step_minutes, bool)
                or step_minutes <= 0 or 1440 % step_minutes):
            raise ValueError("step_minutes must be a positive divisor of 1440")
        for _ in range(days * 1440 // step_minutes):
            self.step(step_minutes)
        for agent_id, observer in self.observers.items():
            observer.maybe_reflect(observe(self.world, agent_id, include_progression=True),
                                   final=True)
        return self.report()

    def report(self) -> dict:
        events = self.world.events
        counts = Counter(e.kind for e in events)
        gold = [a.gold for a in self.world.actors.values()]
        holdings = {c.id: c.gold for c in self.world.companies.values()}
        trades = [e for e in events if e.kind == "offer_filled"]
        city_sales = [e for e in events if e.kind == "city_sale"]
        regional_buys = [e for e in events if e.kind == "regional_bought"]
        regional_sells = [e for e in events if e.kind == "regional_sold"]
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
        report = {
            "seed": self.seed,
            "npcs": len(self.profiles),
            "simulated_days": round(self.elapsed_minutes / 1440, 3),
            "ticks": self.ticks,
            "gold_total": self.world.total_gold,
            "initial_gold": self.world.initial_gold,
            "gold_conserved": self.world.total_gold == self.world.initial_gold,
            "market_trades": len(trades),
            "regional_purchases": len(regional_buys),
            "regional_sales": len(regional_sells),
            "regional_buy_spend": sum(e.data["total"] for e in regional_buys),
            "regional_sale_revenue": sum(e.data["total"] for e in regional_sells),
            "hauler_cash_change": sum(self.world.actors[p.id].gold - 160
                                      for p in self.profiles if p.role == "hauler"),
            "background_sales": len(city_sales),
            "background_sales_gold": sum(e.data["price"] for e in city_sales),
            "meals_consumed": sum(e.kind == "consumed" and e.data["item"] in ("bread", "meal")
                                  for e in events),
            "potions_consumed": sum(e.kind == "consumed" and e.data["item"] == "healing_potion"
                                    for e in events),
            "total_city_household_gold": sum(c.household_gold for c in self.world.cities.values()),
            "market_gold_volume": sum(int(e.data["total_price"]) for e in trades),
            "resources_gathered": ore,
            "shifts_completed": counts["shift_completed"],
            "crafted_equipment": minted,
            "equipment_purchases": sum(e.data["offer_id"] in equipment_listing_ids
                                       for e in trades),
            "combat_attacks": counts["combat"],
            "company_gold": holdings,
            "company_cash_change": {company: balance - 430 for company, balance in holdings.items()},
            "company_inventory_units": {company.id: sum(company.inventory.values()) +
                                        len(company.gear_ids)
                                        for company in self.world.companies.values()},
            "unsold_gear_listings": sum(o.gear_id is not None
                                        for o in self.world.offers.values()),
            "roles": by_role,
            "event_count": len(events),
            "npc_gold_min": min(gold),
            "npc_gold_median": median(gold),
            "npc_gold_max": max(gold),
            "actions": dict(sorted(self.attempts.items())),
            "rejections": dict(sorted(self.rejected.items())),
            "idle_decisions": self.idle,
        }
        if self.observers:
            report["playtesting"] = {
                "agents": {key: observer.output()
                           for key, observer in sorted(self.observers.items())},
                "aggregate": aggregate_issues(self.observers),
                "notes": ("Critic reports are hypotheses from simulated agents, "
                          "not findings confirmed by human playtesters."),
            }
        return report



def create_simulation(npcs: int = 50, seed: int = 42, *,
                      playtesters: bool = False, reflection_every: int = 30,
                      critic: Critic | None = None) -> AutonomousSimulation:
    """Seed 4 staffed companies and independent workers across 5 cities.

    All initial gold is explicitly assigned, never silently minted during play.
    """
    if not isinstance(npcs, int) or npcs < 20 or npcs > 150:
        raise ValueError("Choose 20 to 150 NPCs for this bounded prototype")
    if type(playtesters) is not bool:
        raise ValueError("playtesters must be a boolean")
    if type(reflection_every) is not int or not 1 <= reflection_every <= 1000:
        raise ValueError("reflection_every must be 1–1000")
    rng = random.Random(seed)
    actors: list[Actor] = []
    profiles: list[NPCProfile] = []

    def register(actor_id: str, role: str, city: str, gold: int,
                 resource: str | None = None, company_id: str | None = None,
                 *, persona: str | None = None, actor_kind: str = "npc"):
        actors.append(Actor(actor_id, actor_kind, city=city, gold=gold))
        profiles.append(NPCProfile(
            actor_id, role, city, resource, company_id,
            greed=round(rng.uniform(0.9, 1.08), 3),
            risk=round(rng.uniform(0.15, 0.75), 3),
            curiosity=round(rng.uniform(0.1, 0.85), 3),
            volatility=round(rng.uniform(0.3, 1.8), 3),
            persona=persona,
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

    if playtesters:
        # Isolated offline avatars use the real playable-actor rules, including
        # player-only commands, but are NEVER registered on a live server.
        register("playtest_explorer", "playtester", CAPITAL, 240,
                 persona="explorer", actor_kind="human")
        register("playtest_optimizer", "playtester", CAPITAL, 240,
                 persona="optimizer", actor_kind="human")
    world = WorldEngine(actors, seed=seed)
    if playtesters:
        world.choose_lineage("playtest_explorer", "elf")
        world.choose_lineage("playtest_optimizer", "human")
    for industry in INDUSTRIES:
        owner = f"owner_{industry}"
        company = f"{industry}_co"
        world.found_company(owner, company, industry, investment=430)
        world.hire(owner, company, f"worker_{industry}", Wage(gold=2))
    simulation = AutonomousSimulation(world, tuple(profiles), seed, random.Random(seed + 9999))
    if playtesters:
        for persona in ("explorer", "optimizer"):
            actor_id = "playtest_" + persona
            memory = NPCMemory()
            simulation.memories[actor_id] = memory
            simulation.observers[actor_id] = PlaytestObserver(
                actor_id, persona, memory, critic=critic or HeuristicCritic(),
                every=reflection_every)
    return simulation
