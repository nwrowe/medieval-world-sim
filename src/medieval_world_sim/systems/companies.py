from __future__ import annotations

from ..catalog import CAPITAL, RECIPES
from ..equipment import GEAR, crafted_quality
from ..core.entities import Company, Wage
from ..errors import ActionError

HOUR = 60


class CompanySystem:
    def __init__(self, world):
        self.world = world

    def found_company(self, owner_id: str, company_id: str, industry: str, investment: int) -> None:
        owner = self.world._actor(owner_id)
        if self.world._at_city(owner) != CAPITAL:
            raise ActionError("Founding a company requires being in the capital")
        self.world._positive(investment, "investment")
        if industry not in RECIPES or not company_id or company_id in self.world.companies or company_id in self.world.actors:
            raise ActionError("Invalid company type or ID")
        if owner.gold < investment:
            raise ActionError("Insufficient gold to invest")
        owner.gold -= investment
        self.world.companies[company_id] = Company(company_id, owner_id, industry, gold=investment)
        self.world._emit("company_founded", owner_id, company_id, industry, investment)
        self.world.assert_invariants()

    def hire(self, owner_id: str, company_id: str, worker_id: str, wage: Wage) -> None:
        owner = self.world._actor(owner_id)
        worker = self.world._actor(worker_id)
        company = self.world.companies.get(company_id)
        if not company or company.owner_id != owner.id:
            raise ActionError("Only an owner can hire")
        self.world._nonnegative(wage.gold, "wage gold")
        self.world._nonnegative(wage.quantity, "wage item quantity")
        if wage.item is not None and wage.item not in GOODS and wage.item not in GEAR:
            raise ActionError("Unknown wage item")
        if bool(wage.item) != bool(wage.quantity) or (wage.gold == 0 and wage.quantity == 0):
            raise ActionError("Choose gold, goods, or both as a positive wage")
        company.employees[worker.id] = wage
        self.world._emit("hired", company_id, worker_id, wage.gold, wage.item, wage.quantity)

    def shift(self, worker_id: str, company_id: str) -> None:
        worker = self.world._actor(worker_id)
        company = self.world.companies.get(company_id)
        if company is None or worker_id not in company.employees:
            raise ActionError("Worker not employed at company")
        if self.world._at_city(worker) != company.city or self.world.minute < worker.ready_minute:
            raise ActionError("Worker unavailable at company")
        recipe = RECIPES[company.industry]
        wage = company.employees[worker_id]
        for item, amount in recipe.inputs.items():
            if company.inventory.get(item, 0) < amount:
                raise ActionError(f"Company lacks {item}")
        if company.gold < wage.gold:
            raise ActionError("Company cannot pay wages")

        # Preview the transaction before any state is changed.
        future = dict(company.inventory)
        for item, amount in recipe.inputs.items():
            future[item] -= amount
        produced_gear: list[str] = []
        for item, amount in recipe.outputs.items():
            if item in GEAR:
                produced_gear.extend([item] * amount)
            else:
                future[item] = future.get(item, 0) + amount
        if wage.item in GEAR:
            owned = sum(self.world.gear[g].kind == wage.item for g in company.gear_ids)
            available = owned + produced_gear.count(wage.item)
            if available < wage.quantity:
                raise ActionError("Company cannot pay equipment wage")
        elif wage.item and future.get(wage.item, 0) < wage.quantity:
            raise ActionError("Company cannot pay material wage")
        if wage.item and not self.world._space_for(worker, wage.item, wage.quantity):
            raise ActionError("Worker carrying capacity exceeded")

        company.inventory = future
        for kind in produced_gear:
            quality = crafted_quality(self.world.seed, worker_id, company_id, self.world.minute, self.world.next_gear_id)
            self.world._mint_gear(company, kind, quality, "crafted")
        if wage.item in GEAR:
            # Prefer lower-quality gear to avoid silently taking a masterwork as wages.
            available = sorted((g for g in company.gear_ids if self.world.gear[g].kind == wage.item),
                               key=lambda g: (self.world.gear[g].quality, g))
            for gear_id in available[:wage.quantity]:
                company.gear_ids.remove(gear_id)
                worker.gear_ids.append(gear_id)
        elif wage.item:
            company.inventory[wage.item] -= wage.quantity
            self.world._add(worker, wage.item, wage.quantity)
        company.gold -= wage.gold
        worker.gold += wage.gold
        worker.ready_minute = self.world.minute + HOUR
        self.world._emit("shift_completed", company_id, worker_id, wage.gold, wage.item, wage.quantity)
        self.world.assert_invariants()

