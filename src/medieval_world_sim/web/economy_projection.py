"""Strictly actor-scoped company and market read models for the browser.

Only a company's owner receives its funds, stock, equipment and full payroll.
Workers see only their own wages and offers; locally listed sale terms are public.
This module cannot mutate the world or authorize an action.
"""
from __future__ import annotations

from dataclasses import asdict

from ..content.industry import RECIPES, GOODS, INDUSTRY_PRODUCTS
from ..equipment import GEAR


def economy_projection(world, actor_id: str, names: dict[str, str]) -> dict:
    actor = world.actors[actor_id]
    local = (actor.destination is None and actor.wilderness_hex is None
             and actor.defeated_until is None and actor.hp > 0)
    owned = []
    jobs = []
    offers_to_me = []
    candidate_ids = sorted(
        a.id for a in world.actors.values()
        if a.kind == "human" and a.city == actor.city
        and a.destination is None and a.wilderness_hex is None)
    for company in sorted(world.companies.values(), key=lambda c: c.id):
        if company.owner_id == actor_id:
            quality = world.company_quality(company.id)
            owned.append({
                "id": company.id, "city": company.city,
                "industry": company.industry, "gold": company.gold,
                "product": company.product or next(iter(RECIPES[company.industry].outputs)),
                "inventory": {k: v for k, v in company.inventory.items() if v > 0},
                "equipment": [{
                    "id": gid, "kind": world.gear[gid].kind,
                    "quality": world.gear[gid].quality,
                    "durability": world.gear[gid].durability,
                } for gid in sorted(company.gear_ids)],
                "employees": [{
                    "id": worker, "name": names.get(worker, worker),
                    "wage": asdict(wage)}
                    for worker, wage in sorted(company.employees.items())],
                "job_offers": [{
                    "id": worker, "name": names.get(worker, worker),
                    "wage": asdict(wage)}
                    for worker, wage in sorted(company.job_offers.items())],
                "facility_level": company.facility_level,
                "shifts_completed": company.shifts_completed,
                "perks": list(company.perks),
                "quality": asdict(quality),
                "daily_revenue": company.daily_revenue,
                "daily_units_sold": company.daily_units_sold,
                "can_manage": local and actor.city == company.city,
            })
        if actor_id in company.employees:
            jobs.append({
                "company_id": company.id, "industry": company.industry,
                "city": company.city,
                "wage": asdict(company.employees[actor_id]),
                "can_shift": local and actor.city == company.city
                             and world.minute >= actor.ready_minute,
                "ready_minutes": max(0, actor.ready_minute - world.minute),
            })
        if actor_id in company.job_offers:
            offers_to_me.append({
                "company_id": company.id, "industry": company.industry,
                "city": company.city,
                "wage": asdict(company.job_offers[actor_id]),
                "can_accept": local and actor.city == company.city,
            })

    stalls = []
    if local:
        for offer in sorted(world.offers.values(), key=lambda o: o.id):
            if offer.city != actor.city:
                continue
            company = world.companies.get(offer.seller_id)
            label = company.id if company else names.get(
                offer.seller_id, offer.seller_id)
            gear = world.gear.get(offer.gear_id) if offer.gear_id else None
            stalls.append({
                "id": offer.id, "seller_id": offer.seller_id,
                "seller": label, "company": company is not None,
                "item": offer.item, "quantity": offer.quantity,
                "unit_price": offer.unit_price, "total_price":
                    offer.quantity * offer.unit_price,
                "gear_id": offer.gear_id,
                "quality": gear.quality if gear else None,
                "durability": gear.durability if gear else None,
                "can_cancel": offer.seller_id == actor_id or
                    (company is not None and company.owner_id == actor_id),
            })

    return {
        "industries": [{
            "id": key, "inputs": dict(recipe.inputs),
            "outputs": dict(recipe.outputs),
            "products": [{
                "id": label, "inputs": dict(spec.inputs), "outputs": dict(spec.outputs)
            } for label, spec in sorted(INDUSTRY_PRODUCTS[key].items())]
        } for key, recipe in sorted(RECIPES.items())],
        "goods": sorted(GOODS),
        "owned": owned,
        "jobs": jobs,
        "job_offers": offers_to_me,
        "candidates": [{"id": ident, "name": names.get(ident, ident)}
                       for ident in candidate_ids],
        "listings": stalls,
        "market_sources": [
            {"id": actor_id, "name": "My inventory"},
            *[{"id": c["id"], "name": c["id"] + " (company)"}
              for c in owned if c["can_manage"]],
        ] if local else [],
    }
