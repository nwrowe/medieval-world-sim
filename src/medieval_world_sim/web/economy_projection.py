"""Strictly actor-scoped company and market read models for the browser.

Only a company's owner receives its funds, stock, equipment and full payroll.
Workers see only their own wages and offers; locally listed sale terms are public.
This module cannot mutate the world or authorize an action.
"""
from __future__ import annotations

from dataclasses import asdict

from ..content.industry import RECIPES, GOODS, INDUSTRY_PRODUCTS
from ..content.staffing import positions, occupancy, openings, qualified, active_offer, career_stage, capacity
from ..equipment import GEAR



def incoming_job_offers(world, actor_id: str, names: dict[str, str]) -> list[dict]:
    """Actor-private, active employment letters for snapshot and live updates."""
    actor = world.actors[actor_id]
    local = actor.destination is None and actor.wilderness_hex is None and actor.defeated_until is None and actor.hp > 0
    result = []
    for company in sorted(world.companies.values(), key=lambda c: c.id):
        if not active_offer(company, actor_id, world.minute):
            continue
        slot = next((k for k, holder in occupancy(company, world.minute).items()
                     if holder == ("offer", actor_id)), None)
        position = next((p for p in positions(company) if p["id"] == slot), None)
        if position is None:
            continue
        expiry = company.offer_expires.get(actor_id, 0)
        result.append({
            "company_id": company.id, "company_name": company.display_name or company.id,
            "sender": names.get(company.owner_id, company.owner_id),
            "industry": company.industry, "city": company.city,
            "position_id": position["id"], "position": position["title"],
            "requirements": position["requirements"], "wage": asdict(company.job_offers[actor_id]),
            "expires_in_minutes": max(0, expiry - world.minute) if expiry else None,
            "can_accept": local and actor.city == company.city and qualified(actor, position),
        })
    return result


def economy_projection(world, actor_id: str, names: dict[str, str]) -> dict:
    actor = world.actors[actor_id]
    local = (actor.destination is None and actor.wilderness_hex is None
             and actor.defeated_until is None and actor.hp > 0)
    owned = []
    jobs = []
    directory = []
    extra_candidates = set()
    candidate_ids = sorted(a.id for a in world.actors.values()
                           if a.kind == "human" and a.id != actor_id)
    for company in sorted(world.companies.values(), key=lambda c: c.id):
        visible_name = company.display_name or company.id
        applied = actor_id in company.applicants
        slots = positions(company)
        taken = occupancy(company, world.minute)
        vacant = openings(company, world.minute)
        my_openings = [dict(p, eligible=qualified(actor, p)) for p in vacant]
        directory.append({
            "id": company.id, "name": visible_name,
            "industry": company.industry, "city": company.city,
            "owner": names.get(company.owner_id, company.owner_id),
            "hiring": company.hiring, "applied": applied,
            "employees": len(company.employees), "capacity": capacity(company),
            "openings": my_openings,
            "can_apply": company.hiring and any(p["eligible"] for p in my_openings) and not applied and
                         actor_id != company.owner_id and
                         actor_id not in company.employees and
                         not active_offer(company, actor_id, world.minute),
            "sale_price": company.sale_price,
            "can_buy": bool(company.sale_price) and
                       company.owner_id != actor_id and not any(
                           c.owner_id == actor_id for c in world.companies.values()) and
                       local and actor.city == company.city and
                       actor.gold >= company.sale_price,
            "facility_level": company.facility_level,
            "shifts_completed": company.shifts_completed,
            "daily_revenue": company.daily_revenue,
        })
        if company.owner_id == actor_id:
            extra_candidates.update(company.applicants)
            quality = world.company_quality(company.id)
            owned.append({
                "id": company.id, "name": visible_name, "city": company.city,
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
                    "wage": asdict(wage),
                    "position": next((p["title"] for p in slots if taken.get(p["id"]) == ("employee", worker)), "Staff member")}
                    for worker, wage in sorted(company.employees.items())],
                "job_offers": [{
                    "id": worker, "name": names.get(worker, worker),
                    "wage": asdict(wage),
                    "position": next((p["title"] for p in slots if taken.get(p["id"]) == ("offer", worker)), "Staff member"),
                    "expires_in_minutes": max(0, company.offer_expires[worker] - world.minute)
                        if company.offer_expires.get(worker) else None}
                    for worker, wage in sorted(company.job_offers.items())
                    if active_offer(company, worker, world.minute)],
                "facility_level": company.facility_level,
                "shifts_completed": company.shifts_completed,
                "career_stage": career_stage(company) + 1,
                "capacity": capacity(company),
                "positions": [dict(p, status=(
                    "filled" if taken.get(p["id"], ("",))[0] == "employee" else
                    "offered" if taken.get(p["id"], ("",))[0] == "offer" else "open"),
                    worker=names.get(taken[p["id"]][1], taken[p["id"]][1])
                        if p["id"] in taken else None) for p in slots],
                "perks": list(company.perks),
                "quality": asdict(quality),
                "daily_revenue": company.daily_revenue,
                "daily_units_sold": company.daily_units_sold,
                "can_manage": local and actor.city == company.city,
                "hiring": company.hiring, "sale_price": company.sale_price,
                "applicants": [{
                    "id": member, "name": names.get(member, member),
                    "position_id": company.applicant_positions.get(member, ""),
                    "position": next((p["title"] for p in slots if p["id"] == company.applicant_positions.get(member)), "Any open position"),
                    "eligible_positions": [p["id"] for p in vacant
                        if qualified(world.actors[member], p)]}
                    for member in sorted(company.applicants)],
            })
        if actor_id in company.employees:
            jobs.append({
                "company_id": company.id, "company_name": visible_name,
                "industry": company.industry,
                "city": company.city,
                "wage": asdict(company.employees[actor_id]),
                "position": next((p["title"] for p in slots if taken.get(p["id"]) == ("employee", actor_id)), "Staff member"),
                "can_shift": local and actor.city == company.city
                             and world.minute >= actor.ready_minute,
                "ready_minutes": max(0, actor.ready_minute - world.minute),
            })

    stalls = []
    if local:
        for offer in sorted(world.offers.values(), key=lambda o: o.id):
            if offer.city != actor.city:
                continue
            company = world.companies.get(offer.seller_id)
            label = (company.display_name or company.id) if company else names.get(
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
        "owned": owned, "directory": directory,
        "jobs": jobs,
        "job_offers": incoming_job_offers(world, actor_id, names),
        "candidates": [{"id": ident, "name": names.get(ident, ident)}
                       for ident in sorted(set(candidate_ids) | extra_candidates)],
        "listings": stalls,
        "market_sources": [
            {"id": actor_id, "name": "My inventory"},
            *[{"id": c["id"], "name": c["name"] + " (company)"}
              for c in owned if c["can_manage"]],
        ] if local else [],
    }
