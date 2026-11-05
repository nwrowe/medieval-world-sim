"""Detached, read-only observations for unprivileged NPC decision policies."""
from dataclasses import dataclass
from ..core.quality import suggested_wage
from ..systems.regional_trade import BASE_LOCAL_ASK, RegionalQuote


@dataclass(frozen=True)
class OfferView:
    id: int
    seller_id: str
    city: str
    item: str
    quantity: int
    price: int
    gear_id: int | None
    quality: int | None


@dataclass(frozen=True)
class CompanyView:
    id: str
    owner_id: str
    industry: str
    city: str
    gold: int
    inventory: tuple[tuple[str, int], ...]
    gear: tuple[tuple[int, str, int], ...]
    employees: tuple[str, ...]
    employee_pay: tuple[tuple[str, int, int], ...]
    facility_level: int
    training_fee: int = 0

    def stock(self, item: str) -> int:
        return dict(self.inventory).get(item, 0)


@dataclass(frozen=True)
class CombatTarget:
    """Observable simulated NPC target, never a real player's private stats."""
    id: str
    hp: int
    max_hp: int
    level: int
    armed: bool


@dataclass(frozen=True)
class NPCView:
    id: str
    city: str
    destination: str | None
    gold: int
    inventory: tuple[tuple[str, int], ...]
    gear: tuple[tuple[int, str, int], ...]
    equipped: tuple[tuple[str, int], ...]
    hp: int
    max_hp: int
    hunger: int
    stamina: int
    ready_minute: int
    minute: int
    deposits: tuple[tuple[str, int], ...]
    offers: tuple[OfferView, ...]
    companies: tuple[CompanyView, ...]
    opponents: tuple[str, ...]
    regional_quotes: tuple[RegionalQuote, ...]
    capital_quotes: tuple[RegionalQuote, ...]
    # Optional test-agent progression fields; legacy economy observations are cheap.
    discovered_cities: tuple[str, ...] = ()
    level: int = 1
    mana: int = 100
    contracts: tuple[str, ...] = ()
    magic_eligible: tuple[str, ...] = ()
    magic_practice: tuple[tuple[str, int], ...] = ()
    courses: tuple[tuple[str, int, int], ...] = ()
    studying: bool = False
    combat_xp: int = 0
    level_xp: int = 0
    work_xp: int = 0
    magic_xp: int = 0
    courses_completed: int = 0
    travel_cargo_limit: int = 12
    combat_targets: tuple[CombatTarget, ...] = ()

    def stock(self, item: str) -> int:
        return dict(self.inventory).get(item, 0)

    @property
    def quoted_inventory_value(self) -> int:
        """Illustrative capital-bid mark, not a liquidation guarantee.

        Excludes equipment and ignores quotas and merchant funding.
        """
        bids = {q.item: q.player_sell_price for q in self.capital_quotes}
        return sum(qty * bids.get(item, 0) for item, qty in self.inventory)

    def company(self, company_id: str) -> CompanyView | None:
        return next((company for company in self.companies if company.id == company_id), None)

    def regional_quote(self, item: str, capital: bool = False) -> RegionalQuote | None:
        quotes = self.capital_quotes if capital else self.regional_quotes
        return next((q for q in quotes if q.item == item), None)

    def local_offers(self, item: str | None = None) -> tuple[OfferView, ...]:
        return tuple(o for o in self.offers if o.city == self.city
                     and (item is None or o.item == item))


def observe(world, actor_id: str, *, include_progression: bool = False) -> NPCView:
    """Copy only public decision inputs, not mutable Actor/Company/World objects."""
    actor = world.actors[actor_id]
    offers = tuple(OfferView(
        o.id, o.seller_id, o.city, o.item, o.quantity, o.unit_price,
        o.gear_id, world.gear[o.gear_id].quality if o.gear_id is not None else None,
    ) for o in sorted(world.offers.values(), key=lambda o: o.id))
    companies = tuple(CompanyView(
        c.id, c.owner_id, c.industry, c.city, c.gold,
        tuple(sorted(c.inventory.items())),
        tuple((gid, world.gear[gid].kind, world.gear[gid].quality)
              for gid in sorted(c.gear_ids)),
        tuple(sorted(c.employees)),
        tuple((aid, wage.gold, suggested_wage(world.actors[aid], c.industry))
              for aid, wage in sorted(c.employees.items())),
        c.facility_level, int("training" in c.perks)
    ) for c in sorted(world.companies.values(), key=lambda c: c.id))
    opponents = tuple(sorted(a.id for a in world.actors.values()
                             if a.id != actor.id and a.city == actor.city
                             and a.destination is None and a.hp > 0))
    # The autonomous offline simulator may attack its own NPC accounts;
    # do not leak a human player's health, assets or gear through this field.
    combat_targets = tuple(sorted((
        CombatTarget(a.id, a.hp, a.max_hp, a.level, bool(a.equipped.get("weapon")))
        for a in world.actors.values()
        if a.id != actor.id and a.kind == "npc" and a.city == actor.city
        and a.destination is None and a.hp > 0 and a.defeated_until is None
    ), key=lambda a: a.id))
    contracts: tuple[str, ...] = ()
    eligible: tuple[str, ...] = ()
    practice: tuple[tuple[str, int], ...] = ()
    courses: tuple[tuple[str, int, int], ...] = ()
    studying = False
    combat_xp = level_xp = work_xp = magic_xp = courses_completed = 0
    if include_progression:
        combat_xp = actor.combat_xp
        level_xp = actor.progression.level_xp
        work_xp = sum(actor.work.experience.values())
        magic_xp = sum(actor.magic.school_xp.values())
        contracts = tuple(contract['id'] for contract in world.city_contracts.view(actor_id)
                          if contract['can_pay'] and contract['cooldown_available']
                          and contract['has_material']
                          and actor.stamina >= contract['stamina']
                          and actor.magic.mana >= contract['mana'])
        nodes = world.magic_tree(actor_id)
        eligible = tuple(node.node_id for node in nodes if node.eligible)
        practice = tuple((node.node_id, node.mana_cost) for node in nodes
                         if node.can_practice)
        curriculum = world.curriculum_system.view(actor_id)
        courses_completed = sum(school['completed'] for school in curriculum['schools'])
        studying = curriculum['active'] is not None
        if not studying:
            courses = tuple((school['id'], idx, course['tuition'])
                            for school in curriculum['schools']
                            for idx, course in enumerate(school['courses'])
                            if course['available'] and idx == 0)
    return NPCView(
        actor.id, actor.city, actor.destination, actor.gold,
        tuple(sorted(actor.inventory.items())),
        tuple((gid, world.gear[gid].kind, world.gear[gid].quality)
              for gid in sorted(actor.gear_ids)),
        tuple(sorted(actor.equipped.items())), actor.hp, actor.max_hp,
        actor.vitals.hunger, actor.stamina,
        actor.ready_minute, world.minute,
        tuple(sorted(world.cities[actor.city].deposits.items())),
        offers, companies, opponents,
        tuple(world.regional_quote(actor.city, good) for good in sorted(BASE_LOCAL_ASK)),
        tuple(world.regional_quote("crownreach", good) for good in sorted(BASE_LOCAL_ASK)),
        tuple(sorted(actor.discovered_cities)), actor.level, actor.magic.mana,
        contracts, eligible, practice, courses, studying,
        combat_xp, level_xp, work_xp, magic_xp, courses_completed,
        world.housing_system.travel_cargo_limit(actor), combat_targets,
    )
