from __future__ import annotations

from ..catalog import CAPITAL, RECIPES, GOODS
from ..equipment import GEAR, crafted_quality
from ..core.entities import Company, Wage
from ..errors import ActionError
from ..core.transactions import transfer_gold
from ..core.quality import ALLOWED_PERKS, company_quality, suggested_wage

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
        company = Company(company_id, owner_id, industry)
        self.world.companies[company_id] = company
        transfer_gold(self.world, owner, company, investment)
        self.world._emit("company_founded", owner_id, company_id, industry, investment)
        self.world.assert_invariants()

    def propose_job(self, owner_id: str, company_id: str, worker_id: str, wage: Wage) -> None:
        company = self.world.companies.get(company_id)
        if company is None or company.owner_id != owner_id:
            raise ActionError("Only the owner may offer employment")
        self.world._actor(worker_id)
        self._validate_wage(wage)
        company.job_offers[worker_id] = wage
        self.world._emit("job_offered", company_id, worker_id, wage.gold, wage.item, wage.quantity)

    def accept_job(self, worker_id: str, company_id: str) -> None:
        self.world._actor(worker_id)
        company = self.world.companies.get(company_id)
        if company is None or worker_id not in company.job_offers:
            raise ActionError("No pending employment offer")
        wage = company.job_offers.pop(worker_id)
        company.employees[worker_id] = wage
        self.world._emit("hired", company_id, worker_id, wage.gold, wage.item, wage.quantity)

    def set_wage(self, owner_id: str, company_id: str, worker_id: str, wage: Wage) -> None:
        company = self.world.companies.get(company_id)
        if company is None or company.owner_id != owner_id:
            raise ActionError("Only the owner may set wages")
        if worker_id not in company.employees:
            raise ActionError("Worker is not an employee")
        self._validate_wage(wage)
        company.employees[worker_id] = wage
        self.world._emit("wage_changed", company_id, worker_id, wage.gold, wage.item, wage.quantity)

    def leave_job(self, worker_id: str, company_id: str) -> None:
        self.world._actor(worker_id)
        company = self.world.companies.get(company_id)
        if company is None or worker_id not in company.employees:
            raise ActionError("Not employed there")
        del company.employees[worker_id]
        self.world._emit("worker_left", company_id, worker_id)

    def set_perks(self, owner_id: str, company_id: str, perks: tuple[str, ...]) -> None:
        company = self.world.companies.get(company_id)
        if company is None or company.owner_id != owner_id:
            raise ActionError("Only the owner may set perks")
        if (not isinstance(perks, (list, tuple)) or len(set(perks)) != len(perks)
                or not set(perks).issubset(ALLOWED_PERKS)):
            raise ActionError("Unknown or duplicate perk")
        company.perks = tuple(sorted(perks))
        self.world._emit("perks_changed", company_id, company.perks)

    def upgrade_facility(self, owner_id: str, company_id: str) -> int:
        company = self.world.companies.get(company_id)
        if company is None or company.owner_id != owner_id:
            raise ActionError("Only the owner may upgrade facilities")
        if company.facility_level >= 5:
            raise ActionError("Facility at maximum level")
        price = 30 * company.facility_level
        transfer_gold(self.world, company, None, price)
        company.facility_level += 1
        self.world._emit("facility_upgraded", company_id, company.facility_level, price)
        return price

    def _validate_wage(self, wage: Wage) -> None:
        self.world._nonnegative(wage.gold, "wage gold")
        self.world._nonnegative(wage.quantity, "wage item quantity")
        if wage.item is not None and wage.item not in GOODS and wage.item not in GEAR:
            raise ActionError("Unknown wage item")
        if bool(wage.item) != bool(wage.quantity) or (wage.gold == 0 and wage.quantity == 0):
            raise ActionError("Choose gold, goods, or both as a positive wage")

    def quality(self, company_id: str):
        company = self.world.companies.get(company_id)
        if company is None:
            raise ActionError("Unknown company")
        return company_quality(self.world, company)

    def suggested_wage(self, worker_id: str, company_id: str) -> int:
        company = self.world.companies.get(company_id)
        if company is None:
            raise ActionError("Unknown company")
        return suggested_wage(self.world._actor(worker_id), company.industry)

    def hire(self, owner_id: str, company_id: str, worker_id: str, wage: Wage) -> None:
        owner = self.world._actor(owner_id)
        worker = self.world._actor(worker_id)
        company = self.world.companies.get(company_id)
        if not company or company.owner_id != owner.id:
            raise ActionError("Only an owner can hire")
        self._validate_wage(wage)
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
        training_fee = 1 if "training" in company.perks else 0
        if company.gold < wage.gold + training_fee:
            raise ActionError("Company cannot pay wages and training costs")

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
            baseline = crafted_quality(self.world.seed, worker_id, company_id, self.world.minute, self.world.next_gear_id)
            # Skills and facilities shift the quality distribution; rare rolls remain rare.
            bonus = (worker.work.experience.get(company.industry, 0) // 6
                     + 2 * (company.facility_level - 1))
            quality = min(100, baseline + min(20, bonus))
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
        transfer_gold(self.world, company, worker, wage.gold)
        if training_fee:
            transfer_gold(self.world, company, None, training_fee)
            self.world._emit("training_paid", company_id, worker_id, training_fee)
        # Each actual paid shift improves specialized experience; no idle XP farming.
        growth = 2 if "training" in company.perks else 1
        growth = self.world.housing_system.training_xp(worker, growth, f"work:{company.industry}")
        worker.work.experience[company.industry] = min(
            100, worker.work.experience.get(company.industry, 0) + growth
        )
        worker.work.shifts += 1
        if worker.work.shifts % 5 == 0:
            if company.industry in ("apothecary", "tavern"):
                worker.work.intelligence += 1
            elif company.industry in ("steelworks", "armorer", "forge"):
                worker.work.manual += 1
            else:
                worker.work.endurance += 1
        company.shifts_completed += 1
        # Independently award each stocked perk; nothing materializes for free.
        for perk, item in (("meal", "bread"), ("medical", "healing_potion")):
            if (perk in company.perks and company.inventory.get(item, 0) > 0
                    and self.world._space_for(worker, item, 1)):
                company.inventory[item] -= 1
                self.world._add(worker, item, 1)
                self.world._emit("perk_awarded", company_id, worker_id, item)
        worker.ready_minute = self.world.minute + HOUR
        self.world._emit("shift_completed", company_id, worker_id, wage.gold, wage.item, wage.quantity)
        self.world.assert_invariants()

