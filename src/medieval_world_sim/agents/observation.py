"""Detached, read-only observations for unprivileged NPC decision policies."""
from dataclasses import dataclass


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

    def stock(self, item: str) -> int:
        return dict(self.inventory).get(item, 0)


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
    stamina: int
    ready_minute: int
    minute: int
    offers: tuple[OfferView, ...]
    companies: tuple[CompanyView, ...]
    opponents: tuple[str, ...]

    def stock(self, item: str) -> int:
        return dict(self.inventory).get(item, 0)

    def company(self, company_id: str) -> CompanyView | None:
        return next((company for company in self.companies if company.id == company_id), None)

    def local_offers(self, item: str | None = None) -> tuple[OfferView, ...]:
        return tuple(o for o in self.offers if o.city == self.city
                     and (item is None or o.item == item))


def observe(world, actor_id: str) -> NPCView:
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
        tuple(sorted(c.employees))
    ) for c in sorted(world.companies.values(), key=lambda c: c.id))
    opponents = tuple(sorted(a.id for a in world.actors.values()
                             if a.id != actor.id and a.city == actor.city
                             and a.destination is None and a.hp > 0))
    return NPCView(
        actor.id, actor.city, actor.destination, actor.gold,
        tuple(sorted(actor.inventory.items())),
        tuple((gid, world.gear[gid].kind, world.gear[gid].quality)
              for gid in sorted(actor.gear_ids)),
        tuple(sorted(actor.equipped.items())), actor.hp, actor.stamina,
        actor.ready_minute, world.minute, offers, companies, opponents
    )
