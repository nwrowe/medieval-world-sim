from __future__ import annotations

import re

from ..catalog import CAPITAL, RECIPES, GOODS
from ..content.industry import INDUSTRY_PRODUCTS, company_recipe
from ..content.staffing import positions, openings, occupancy, qualified, active_offer, OFFER_MINUTES
from ..equipment import GEAR, crafted_quality
from ..core.entities import Company, Wage
from ..errors import ActionError
from ..core.transactions import transfer_gold
from ..core.quality import ALLOWED_PERKS, company_quality, suggested_wage

HOUR = 60
MAX_OWNED_COMPANIES = 1
MAX_COMPANY_ASSETS_TRANSFER = 10000
COMPANY_NAME = re.compile(r"[a-z][a-z0-9_-]{2,31}\Z")
DISPLAY_NAME = re.compile(r"[A-Za-z][A-Za-z0-9 &'._-]{2,39}\Z")


class CompanySystem:
    def __init__(self, world):
        self.world = world

    def found_company(self, owner_id: str, company_id: str, industry: str, investment: int) -> None:
        owner = self.world._actor(owner_id)
        if self.world._at_city(owner) != CAPITAL:
            raise ActionError("Founding a company requires being in the capital")
        self.world._positive(investment, "investment")
        if (type(industry) is not str or industry not in RECIPES or not isinstance(company_id, str)
                or not COMPANY_NAME.fullmatch(company_id)
                or company_id in self.world.companies
                or company_id in self.world.actors):
            raise ActionError("Choose a unique company ID (3–32 letters, digits, _ or -)")
        if sum(company.owner_id == owner_id for company in
               self.world.companies.values()) >= MAX_OWNED_COMPANIES:
            raise ActionError("One company per owner; sell or dissolve yours first")
        if owner.gold < investment:
            raise ActionError("Insufficient gold to invest")
        company = Company(company_id, owner_id, industry)
        self.world.companies[company_id] = company
        transfer_gold(self.world, owner, company, investment)
        self.world._emit("company_founded", owner_id, company_id, industry, investment)
        self.world.assert_invariants()

    def found_named_company(self, owner_id: str, name: str,
                            industry: str, investment: int) -> None:
        if (type(name) is not str or name != name.strip() or
                not DISPLAY_NAME.fullmatch(name)):
            raise ActionError("Company name must be 3–40 characters; spaces are allowed")
        if any((c.display_name or c.id).casefold() == name.casefold()
               for c in self.world.companies.values()):
            raise ActionError("Another company already uses that name")
        ident = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:32]
        if not COMPANY_NAME.fullmatch(ident):
            raise ActionError("Choose a longer company name")
        self.found_company(owner_id, ident, industry, investment)
        self.world.companies[ident].display_name = name

    def set_hiring(self, owner_id: str, company_id: str, hiring: bool) -> None:
        _, company = self._owned_local(owner_id, company_id)
        if type(hiring) is not bool:
            raise ActionError("Invalid hiring preference")
        company.hiring = hiring
        self.world._emit("company_hiring_changed", owner_id, company_id, hiring)

    def apply(self, actor_id: str, company_id: str) -> None:
        """Historical general application: choose the first eligible vacancy."""
        actor = self.world._actor(actor_id)
        company = self.world.companies.get(company_id)
        if company is None:
            raise ActionError("Unknown company")
        choice = next((p for p in openings(company, self.world.minute)
                       if qualified(actor, p)), None)
        if choice is None:
            raise ActionError("No eligible openings")
        self.apply_role(actor_id, company_id, choice["id"])

    def apply_role(self, actor_id: str, company_id: str, position_id: str) -> None:
        actor = self.world._actor(actor_id)
        company = self.world.companies.get(company_id) if type(company_id) is str else None
        if (company is None or not company.hiring or actor.kind != "human" or
                actor_id == company.owner_id or actor_id in company.employees or
                active_offer(company, actor_id, self.world.minute) or
                actor_id in company.applicants):
            raise ActionError("No available application for this company")
        vacancy = next((p for p in openings(company, self.world.minute)
                        if p["id"] == position_id), None)
        if vacancy is None or not qualified(actor, vacancy):
            raise ActionError("Position is unavailable or work requirements are not met")
        company.applicants.add(actor_id)
        company.applicant_positions[actor_id] = position_id
        self.world._emit("company_applied", actor_id, company_id)

    def withdraw_application(self, actor_id: str, company_id: str) -> None:
        company = self.world.companies.get(company_id) if type(company_id) is str else None
        if company is None or actor_id not in company.applicants:
            raise ActionError("No application to withdraw")
        company.applicants.remove(actor_id)
        company.applicant_positions.pop(actor_id, None)
        self.world._emit("company_application_withdrawn", actor_id, company_id)

    def list_for_sale(self, owner_id: str, company_id: str, price: int) -> None:
        _, company = self._owned_local(owner_id, company_id)
        if type(price) is not int or not 0 <= price <= 1_000_000_000:
            raise ActionError("Invalid company asking price")
        company.sale_price = price
        self.world._emit("company_listed", owner_id, company_id, price)

    def purchase(self, buyer_id: str, company_id: str) -> None:
        buyer = self.world._actor(buyer_id)
        company = self.world.companies.get(company_id) if type(company_id) is str else None
        if company is None or not company.sale_price or company.owner_id == buyer_id:
            raise ActionError("Company is not for sale to this buyer")
        if (buyer.kind != "human" or self.world._at_city(buyer) != company.city or
                any(c.owner_id == buyer_id for c in self.world.companies.values())):
            raise ActionError("Be in the company's city and own no other company")
        seller_id, price = company.owner_id, company.sale_price
        transfer_gold(self.world, buyer, self.world._actor(seller_id), price)
        company.owner_id = buyer_id
        company.sale_price = 0
        self.world._emit("company_sold", seller_id, buyer_id, company_id, price)

    def dissolve(self, owner_id: str, company_id: str) -> None:
        """Return every asset, including market escrow, before removal."""
        owner, company = self._owned_local(owner_id, company_id)
        for offer_id, offer in tuple(self.world.offers.items()):
            if offer.seller_id != company_id:
                continue
            if offer.gear_id is not None:
                owner.gear_ids.append(offer.gear_id)
            else:
                self.world._add(owner, offer.item, offer.quantity)
            del self.world.offers[offer_id]
        for item, qty in company.inventory.items():
            if qty:
                self.world._add(owner, item, qty)
        owner.gear_ids.extend(company.gear_ids)
        transfer_gold(self.world, company, owner, company.gold)
        del self.world.companies[company_id]
        self.world._emit("company_dissolved", owner_id, company_id)

    def _owned_local(self, actor_id: str, company_id: str):
        """Validate an authenticated owner's physical access to company assets."""
        actor = self.world._actor(actor_id)
        if type(company_id) is not str:
            raise ActionError("Invalid company ID")
        company = self.world.companies.get(company_id)
        if company is None or company.owner_id != actor_id:
            raise ActionError("Company is not owned by this character")
        if self.world._at_city(actor) != company.city:
            raise ActionError("Travel to the company's city to manage it")
        return actor, company

    def deposit_gold(self, actor_id: str, company_id: str, amount: int) -> None:
        actor, company = self._owned_local(actor_id, company_id)
        self.world._positive(amount, "gold amount")
        if actor.gold < amount:
            raise ActionError("Not enough personal gold")
        transfer_gold(self.world, actor, company, amount)
        self.world._emit("company_funded", actor_id, company_id, amount)

    def withdraw_gold(self, actor_id: str, company_id: str, amount: int) -> None:
        actor, company = self._owned_local(actor_id, company_id)
        self.world._positive(amount, "gold amount")
        if company.gold < amount:
            raise ActionError("Company cannot cover withdrawal")
        transfer_gold(self.world, company, actor, amount)
        self.world._emit("company_withdrawn", actor_id, company_id, amount)

    def deposit_goods(self, actor_id: str, company_id: str,
                      item: str, quantity: int) -> None:
        actor, company = self._owned_local(actor_id, company_id)
        self.world._positive(quantity, "quantity")
        if quantity > MAX_COMPANY_ASSETS_TRANSFER or type(item) is not str or item not in GOODS:
            raise ActionError("Invalid goods transfer")
        if actor.inventory.get(item, 0) < quantity:
            raise ActionError("Not enough personal inventory")
        actor.inventory[item] -= quantity
        self.world._add(company, item, quantity)
        self.world._emit("company_stocked", actor_id, company_id, item, quantity)

    def withdraw_goods(self, actor_id: str, company_id: str,
                       item: str, quantity: int) -> None:
        actor, company = self._owned_local(actor_id, company_id)
        self.world._positive(quantity, "quantity")
        if quantity > MAX_COMPANY_ASSETS_TRANSFER or type(item) is not str or item not in GOODS:
            raise ActionError("Invalid goods transfer")
        if company.inventory.get(item, 0) < quantity:
            raise ActionError("Not enough company inventory")
        company.inventory[item] -= quantity
        self.world._add(actor, item, quantity)
        self.world._emit("company_unstocked", actor_id, company_id, item, quantity)

    def deposit_gear(self, actor_id: str, company_id: str, gear_id: int) -> None:
        actor, company = self._owned_local(actor_id, company_id)
        if type(gear_id) is not int or gear_id not in actor.gear_ids:
            raise ActionError("Equipment is not in your inventory")
        actor.gear_ids.remove(gear_id)
        for slot, owned in list(actor.equipped.items()):
            if owned == gear_id:
                del actor.equipped[slot]
        company.gear_ids.append(gear_id)
        self.world._emit("company_gear_stocked", actor_id, company_id, gear_id)

    def withdraw_gear(self, actor_id: str, company_id: str, gear_id: int) -> None:
        actor, company = self._owned_local(actor_id, company_id)
        if type(gear_id) is not int or gear_id not in company.gear_ids:
            raise ActionError("Equipment is not owned by the company")
        company.gear_ids.remove(gear_id)
        actor.gear_ids.append(gear_id)
        self.world._emit("company_gear_withdrawn", actor_id, company_id, gear_id)

    def offer_job(self, owner_id: str, company_id: str, worker_id: str,
                  gold: int, item: str, quantity: int) -> None:
        self._owned_local(owner_id, company_id)
        worker = self.world._actor(worker_id)
        if worker.kind != "human":
            raise ActionError("Employment offers require a player character")
        if type(item) is not str:
            raise ActionError("Invalid wage item")
        wage = Wage(gold, item or None, quantity)
        self.propose_job(owner_id, company_id, worker_id, wage)

    def change_job_wage(self, owner_id: str, company_id: str, worker_id: str,
                        gold: int, item: str, quantity: int) -> None:
        self._owned_local(owner_id, company_id)
        if type(item) is not str:
            raise ActionError("Invalid wage item")
        wage = Wage(gold, item or None, quantity)
        self.set_wage(owner_id, company_id, worker_id, wage)

    def _offer_position(self, owner_id: str, company_id: str, worker_id: str,
                        wage: Wage, position_id: str | None = None) -> None:
        company = self.world.companies.get(company_id)
        if company is None or company.owner_id != owner_id:
            raise ActionError("Only the owner may offer employment")
        worker = self.world._actor(worker_id)
        if (worker.kind != "human" or worker_id == owner_id or
                worker_id in company.employees or
                active_offer(company, worker_id, self.world.minute)):
            raise ActionError("Worker is unavailable for an offer")
        self._validate_wage(wage)
        vacancy = next((p for p in openings(company, self.world.minute)
                        if (position_id is None or p["id"] == position_id)
                        and qualified(worker, p)), None)
        if vacancy is None:
            raise ActionError("No vacant position for this worker's work stats")
        company.job_offers[worker_id] = wage
        company.offer_positions[worker_id] = vacancy["id"]
        company.offer_expires[worker_id] = self.world.minute + OFFER_MINUTES
        company.applicants.discard(worker_id)
        company.applicant_positions.pop(worker_id, None)
        self.world._emit("job_offered", company_id, worker_id, wage.gold,
                         wage.item, wage.quantity)

    def propose_job(self, owner_id: str, company_id: str, worker_id: str, wage: Wage) -> None:
        self._offer_position(owner_id, company_id, worker_id, wage)

    def offer_job_position(self, owner_id: str, company_id: str, worker_id: str,
                           gold: int, position_id: str) -> None:
        self._owned_local(owner_id, company_id)
        if type(gold) is not int or gold <= 0:
            raise ActionError("Offer a positive gold wage")
        self._offer_position(owner_id, company_id, worker_id, Wage(gold), position_id)

    def accept_applicant(self, owner_id: str, company_id: str, worker_id: str,
                         gold: int, position_id: str) -> None:
        _, company = self._owned_local(owner_id, company_id)
        if worker_id not in company.applicants:
            raise ActionError("The player has no active application")
        self.offer_job_position(owner_id, company_id, worker_id, gold, position_id)

    def accept_job(self, worker_id: str, company_id: str) -> None:
        worker = self.world._actor(worker_id)
        company = self.world.companies.get(company_id)
        if company is None or not active_offer(company, worker_id, self.world.minute):
            raise ActionError("No active employment offer (it may have expired)")
        if worker_id in company.employees:
            raise ActionError("Already employed here")
        if self.world._at_city(worker) != company.city:
            raise ActionError("Go to the company's city to accept the job")
        assigned = next((slot for slot, holder in occupancy(company, self.world.minute).items()
                         if holder == ("offer", worker_id)), None)
        position = next((p for p in positions(company) if p["id"] == assigned), None)
        if position is None or not qualified(worker, position):
            raise ActionError("Position unavailable or work requirements not met")
        wage = company.job_offers.pop(worker_id)
        company.offer_positions.pop(worker_id, None)
        company.offer_expires.pop(worker_id, None)
        company.employee_positions[worker_id] = assigned
        company.employees[worker_id] = wage
        company.applicants.discard(worker_id)
        company.applicant_positions.pop(worker_id, None)
        self.world._emit("hired", company_id, worker_id, wage.gold, wage.item, wage.quantity)

    def decline_job(self, worker_id: str, company_id: str) -> None:
        self.world._actor(worker_id)
        company = self.world.companies.get(company_id)
        if company is None or not active_offer(company, worker_id, self.world.minute):
            raise ActionError("No active employment offer")
        company.job_offers.pop(worker_id)
        company.offer_positions.pop(worker_id, None)
        company.offer_expires.pop(worker_id, None)
        self.world._emit("job_declined", company_id, worker_id)

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
        company.employee_positions.pop(worker_id, None)
        self.world._emit("worker_left", company_id, worker_id)

    def set_perks(self, owner_id: str, company_id: str, perks: tuple[str, ...]) -> None:
        self._owned_local(owner_id, company_id)
        company = self.world.companies.get(company_id)
        if company is None or company.owner_id != owner_id:
            raise ActionError("Only the owner may set perks")
        if (not isinstance(perks, (list, tuple))
                or any(type(p) is not str for p in perks)
                or len(set(perks)) != len(perks)
                or not set(perks).issubset(ALLOWED_PERKS)):
            raise ActionError("Unknown or duplicate perk")
        company.perks = tuple(sorted(perks))
        self.world._emit("perks_changed", company_id, company.perks)

    def upgrade_facility(self, owner_id: str, company_id: str) -> int:
        self._owned_local(owner_id, company_id)
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
        if wage.gold > 1000000000 or wage.quantity > 10000:
            raise ActionError("Wage is too large")
        if (wage.item is not None and
                (type(wage.item) is not str or
                 wage.item not in GOODS and wage.item not in GEAR)):
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
        if worker.id in company.employees or active_offer(company, worker.id, self.world.minute):
            raise ActionError("Worker already hired or has a pending offer")
        slot = next((p for p in openings(company, self.world.minute)
                     if qualified(worker, p)), None)
        if slot is None:
            raise ActionError("No eligible vacancy")
        company.employees[worker.id] = wage
        company.employee_positions[worker.id] = slot["id"]
        self.world._emit("hired", company_id, worker_id, wage.gold, wage.item, wage.quantity)

    def set_product(self, owner_id: str, company_id: str, product: str) -> None:
        """Choose one of the company's real recipes; stock and assets remain."""
        _, company = self._owned_local(owner_id, company_id)
        if type(product) is not str or product not in INDUSTRY_PRODUCTS[company.industry]:
            raise ActionError("Product is not made by this company")
        company.product = product
        self.world._emit("company_product_selected", owner_id, company_id, product)

    def shift(self, worker_id: str, company_id: str) -> None:
        worker = self.world._actor(worker_id)
        company = self.world.companies.get(company_id)
        if company is None or worker_id not in company.employees:
            raise ActionError("Worker not employed at company")
        if self.world._at_city(worker) != company.city or self.world.minute < worker.ready_minute:
            raise ActionError("Worker unavailable at company")
        recipe = company_recipe(company)
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
            occupied = occupancy(company, self.world.minute)
            slot = next((s for s, occupant in occupied.items()
                         if occupant == ("employee", worker_id)), None)
            career = next((p for p in positions(company) if p["id"] == slot), None)
            focus = career["focus"] if career else (
                "intelligence" if company.industry in ("apothecary", "tavern")
                else "manual" if company.industry in ("steelworks", "armorer", "forge")
                else "endurance")
            setattr(worker.work, focus, getattr(worker.work, focus) + 1)
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

